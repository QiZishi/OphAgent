"""Asynchronous DAG orchestration for OphAgent-Pro runs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from app.core.config import Settings, settings
from app.domain.models import (
    Artifact,
    ClinicalFact,
    ClinicalState,
    ContextStats,
    EvidenceItem,
    NodeStatus,
    RiskLevel,
    RunBudget,
    RunEvent,
    RunInput,
    RunRecord,
    RunStatus,
    TaskComplexity,
    TaskIntent,
    utc_now,
)
from app.evolution.continuous import ContinuousEvolutionController
from app.observability.tracing import safe_span
from app.plugins.registry import PluginRegistry, plugin_registry
from app.runtime.agents import AgentRunner, AgentScopeRunner, parse_json_object
from app.runtime.context import ConversationContextManager, ConversationContextSnapshot
from app.runtime.errors import BudgetExceeded, CapabilityUnavailable, RunCancelled
from app.runtime.planning import build_plan
from app.runtime.routing import is_contextual_follow_up, route_task
from app.runtime.safety import apply_red_flag_gate, emergency_banner
from app.runtime.store import RuntimeStore
from app.services.provider_config import ProviderConfigStore
from app.services.state import MemoryStore
from app.tools.capabilities import (
    CapabilityClients,
    DocumentParseRequest,
    ImageAnalysisRequest,
    SearchRequest,
    SpeechRequest,
)

RunnerFactory = Callable[[CapabilityClients], AgentRunner]


class RunOrchestrator:
    def __init__(
        self,
        store: RuntimeStore,
        clients: CapabilityClients,
        config: Settings = settings,
        plugins: PluginRegistry = plugin_registry,
        runner_factory: RunnerFactory | None = None,
        memory_store: MemoryStore | None = None,
        provider_config_store: ProviderConfigStore | None = None,
        evolution_controller: ContinuousEvolutionController | None = None,
    ) -> None:
        self.store = store
        self.clients = clients
        self.config = config
        self.plugins = plugins
        self.runner_factory = runner_factory or (
            lambda active_clients: AgentScopeRunner(active_clients, active_clients.config)
        )
        self.memory_store = memory_store
        self.provider_config_store = provider_config_store
        self.evolution_controller = evolution_controller
        self.context_manager = ConversationContextManager(store, config)
        self._client_context: ContextVar[CapabilityClients] = ContextVar(
            "ophagent_active_clients",
            default=clients,
        )
        self._conversation_context: ContextVar[ConversationContextSnapshot | None] = ContextVar(
            "ophagent_conversation_context",
            default=None,
        )
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancelled: set[str] = set()

    async def create(self, user_id: int, run_input: RunInput) -> RunRecord:
        run_input = run_input.model_copy(deep=True)
        existing = await self.store.find_run_by_idempotency(
            user_id,
            run_input.idempotency_key,
        )
        if existing is not None:
            return existing
        for attachment_id in run_input.attachment_ids:
            attachment = await self.store.get_attachment(attachment_id)
            if attachment is None or attachment.user_id != user_id:
                raise ValueError(f"附件不存在或无权访问：{attachment_id}")
            target = {
                "image": run_input.image_paths,
                "document": run_input.document_paths,
                "audio": run_input.audio_paths,
            }[attachment.kind]
            target.append(attachment.stored_path)
        run_input.image_paths = list(dict.fromkeys(run_input.image_paths))
        run_input.document_paths = list(dict.fromkeys(run_input.document_paths))
        run_input.audio_paths = list(dict.fromkeys(run_input.audio_paths))
        public_plugin_ids = {manifest.id for manifest in self.plugins.list()}
        invalid_plugins = [
            plugin_id
            for plugin_id in run_input.requested_plugins
            if plugin_id not in public_plugin_ids
        ]
        if invalid_plugins:
            raise ValueError(f"未知或已停用的插件：{', '.join(invalid_plugins)}")
        run_id = None
        if run_input.idempotency_key:
            digest = hashlib.sha256(
                f"{user_id}:{run_input.idempotency_key}".encode()
            ).hexdigest()
            run_id = f"run_{digest[:32]}"
        run_id = run_id or f"run_{uuid4().hex}"
        conversation_context = await self.context_manager.build(
            run_id=run_id,
            user_id=user_id,
            run_input=run_input,
        )
        plugin = self.plugins.get(run_input.plugin_id)
        clinical_state = run_input.clinical_state.model_copy(deep=True)
        if conversation_context and conversation_context.previous_run_id:
            previous_run = await self.store.get_run(conversation_context.previous_run_id)
            if previous_run is not None and previous_run.user_id == user_id:
                clinical_state = _merge_clinical_state(
                    previous_run.clinical_state,
                    clinical_state,
                )
        risk = apply_red_flag_gate(run_input.query, clinical_state)
        previous_route = conversation_context.previous_route if conversation_context else None
        if (
            risk == RiskLevel.ROUTINE
            and previous_route is not None
            and is_contextual_follow_up(run_input.query, previous_route)
            and previous_route.risk in {RiskLevel.HIGH, RiskLevel.EMERGENCY}
        ):
            risk = previous_route.risk
        route = route_task(run_input, risk, previous_route)
        budget_limits = {
            TaskComplexity.QUICK: (1, 2_000, 15, 500),
            TaskComplexity.STANDARD: (3, 12_000, 60, 1_200),
            TaskComplexity.DEEP: (8, 32_000, 300, 2_000),
        }
        calls, tokens, seconds, reserve = budget_limits[route.complexity]
        budget = RunBudget(
            max_model_calls=min(
                calls,
                self.config.RUN_MAX_MODEL_CALLS,
            ),
            max_tokens=min(
                tokens,
                self.config.RUN_MAX_TOKENS,
            ),
            max_seconds=seconds,
            reserved_output_tokens=reserve,
        )
        run = RunRecord(
            id=run_id,
            user_id=user_id,
            input=run_input,
            plugin=plugin,
            clinical_state=clinical_state,
            risk_level=risk,
            route=route,
            budget=budget,
            context_snapshot_id=(
                conversation_context.id if conversation_context else None
            ),
            context_stats=(
                conversation_context.stats
                if conversation_context
                else ContextStats()
            ),
        )
        run.plan = build_plan(plugin, run_input, risk, route)
        try:
            await self.store.create_run(run)
        except ValueError:
            existing = await self.store.get_run(run.id)
            if existing is not None and existing.user_id == user_id:
                return existing
            raise
        if conversation_context is not None:
            await self.store.save_context_snapshot(
                conversation_context,
                self.context_manager.cache_key(conversation_context),
            )
        await self._event(run, "run.created", "任务已创建", status=run.status)
        if conversation_context and conversation_context.stats.source_turns:
            stats = conversation_context.stats
            summary = f"已衔接 {stats.source_turns} 轮历史对话"
            if stats.summarized_turns:
                summary += f"，其中 {stats.summarized_turns} 轮已压缩"
            await self._event(
                run,
                "context.prepared",
                summary,
                data={
                    "source_turns": stats.source_turns,
                    "retained_turns": stats.retained_turns,
                    "summarized_turns": stats.summarized_turns,
                    "tokens_before": stats.tokens_before,
                    "tokens_after": stats.tokens_after,
                    "cache_hit": stats.cache_hit,
                },
            )
        banner = emergency_banner(clinical_state)
        if banner:
            await self._event(
                run,
                "safety.alert",
                banner,
                data={"reason_codes": [fact.value for fact in clinical_state.red_flags]},
            )
        await self._event(
            run,
            "plan.created",
            f"已建立包含 {len(run.plan)} 个节点的执行计划",
            data={"nodes": [node.model_dump(mode="json") for node in run.plan]},
        )
        if "lesion_localizer" in route.selected_plugins and not run.input.image_paths:
            run.status = RunStatus.WAITING
            run.pending_question = "请上传至少 1 张支持的眼科影像后继续病灶定位。"
            await self.store.save_run(run)
            await self._event(
                run,
                "run.question",
                run.pending_question,
                status=run.status,
                data={"accepts": ["image"], "required_count": 1},
            )
            return run
        self._spawn(run.id)
        return run

    def _spawn(self, run_id: str) -> None:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            self._tasks[run_id] = asyncio.create_task(self._execute(run_id), name=f"ophagent:{run_id}")

    async def recover_interrupted(self) -> None:
        """Recover queued work and make interrupted execution explicit after restart."""
        for run in await self.store.list_all_runs():
            if run.status == RunStatus.QUEUED:
                self._spawn(run.id)
                continue
            if run.status != RunStatus.RUNNING:
                continue
            run.status = RunStatus.INTERRUPTED
            for node in run.plan:
                if node.status == NodeStatus.RUNNING:
                    node.status = NodeStatus.PENDING
                    node.started_at = None
            await self.store.save_run(run)
            await self._event(
                run,
                "run.interrupted",
                "服务重启中断了任务；已保留结果，可确认后继续",
                status=run.status,
                error_code="worker_interrupted",
            )

    async def cancel(self, run_id: str, user_id: int) -> RunRecord:
        run = await self._owned_run(run_id, user_id)
        if run.status in {
            RunStatus.COMPLETED,
            RunStatus.COMPLETED_WITH_WARNINGS,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return run
        self._cancelled.add(run_id)
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
        run.status = RunStatus.CANCELLED
        for node in run.plan:
            if node.status in {NodeStatus.PENDING, NodeStatus.RUNNING}:
                node.status = NodeStatus.CANCELLED
        await self.store.save_run(run)
        await self._event(run, "run.cancelled", "任务已取消", status=run.status)
        if task and not task.done():
            await asyncio.gather(task, return_exceptions=True)
        return run

    async def resume(self, run_id: str, user_id: int) -> RunRecord:
        run = await self._owned_run(run_id, user_id)
        if run.status in {RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_WARNINGS}:
            return run
        self._cancelled.discard(run_id)
        for node in run.plan:
            if node.status in {NodeStatus.RUNNING, NodeStatus.CANCELLED, NodeStatus.FAILED}:
                node.status = NodeStatus.PENDING
                node.error_code = None
                node.output = None
        run.attempt += 1
        if run.budget.prompt_tokens + run.budget.completion_tokens >= run.budget.max_tokens:
            run.budget.max_tokens = min(
                self.config.RUN_MAX_TOKENS,
                run.budget.max_tokens + max(2_000, run.budget.reserved_output_tokens),
            )
            run.budget.max_model_calls = min(
                self.config.RUN_MAX_MODEL_CALLS,
                run.budget.max_model_calls + 1,
            )
        run.status = RunStatus.QUEUED
        run.error_code = None
        run.error_message = None
        await self.store.save_run(run)
        await self._event(run, "plan.updated", "任务已恢复，将继续未完成节点")
        self._spawn(run_id)
        return run

    async def retry(self, run_id: str, user_id: int) -> RunRecord:
        previous = await self._owned_run(run_id, user_id)
        if previous.status not in {
            RunStatus.COMPLETED,
            RunStatus.COMPLETED_WITH_WARNINGS,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INTERRUPTED,
        }:
            raise ValueError("当前回答仍在生成，请先停止后再重新生成")
        next_input = previous.input.model_copy(deep=True)
        next_input.idempotency_key = f"retry:{run_id}:{uuid4().hex}"
        next_input.regenerated_from = run_id
        return await self.create(user_id, next_input)

    async def record_feedback(
        self,
        run_id: str,
        user_id: int,
        value: str | None,
    ) -> RunRecord:
        run = await self._owned_run(run_id, user_id)
        previous = run.feedback
        run.feedback = value if value in {"up", "down"} else None
        await self.store.save_run(run)
        if self.evolution_controller is not None:
            try:
                await self.evolution_controller.record_feedback(
                    run,
                    previous,
                    run.feedback,
                    await self.store.get_events(run.id),
                )
            except (OSError, TypeError, ValueError):
                # Feedback remains durable even if optional improvement
                # telemetry is temporarily unavailable.
                pass
        return run

    async def delete(self, run_id: str, user_id: int) -> None:
        run = await self._owned_run(run_id, user_id)
        if run.status not in {
            RunStatus.COMPLETED,
            RunStatus.COMPLETED_WITH_WARNINGS,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INTERRUPTED,
        }:
            await self.cancel(run_id, user_id)
        if not await self.store.delete_run(run_id, user_id):
            raise KeyError(run_id)

    async def provide_input(
        self,
        run_id: str,
        user_id: int,
        content: str | None,
        attachment_ids: list[str],
    ) -> RunRecord:
        run = await self._owned_run(run_id, user_id)
        if run.status != RunStatus.WAITING:
            raise ValueError("当前任务不在等待补充信息状态")
        for attachment_id in attachment_ids:
            attachment = await self.store.get_attachment(attachment_id)
            if attachment is None or attachment.user_id != user_id:
                raise ValueError(f"附件不存在或无权访问：{attachment_id}")
            target = {
                "image": run.input.image_paths,
                "document": run.input.document_paths,
                "audio": run.input.audio_paths,
            }[attachment.kind]
            target.append(attachment.stored_path)
            if attachment_id not in run.input.attachment_ids:
                run.input.attachment_ids.append(attachment_id)
        if content:
            run.user_inputs.append(content)
            run.input.query = f"{run.input.query}\n\n补充信息：{content}"
        if run.plugin.id == "lesion_localizer" and not run.input.image_paths:
            raise ValueError("病灶定位仍需要至少 1 张支持的眼科影像")
        run.route = route_task(run.input, run.risk_level)
        recalculated_limits = {
            TaskComplexity.QUICK: (1, 2_000, 15, 500),
            TaskComplexity.STANDARD: (3, 12_000, 60, 1_200),
            TaskComplexity.DEEP: (8, 32_000, 300, 2_000),
        }
        calls, tokens, seconds, reserve = recalculated_limits[run.route.complexity]
        run.budget.max_model_calls = max(
            run.budget.max_model_calls,
            min(calls, self.config.RUN_MAX_MODEL_CALLS),
        )
        run.budget.max_tokens = max(
            run.budget.max_tokens,
            min(
                tokens,
                self.config.RUN_MAX_TOKENS,
            ),
        )
        run.budget.max_seconds = max(run.budget.max_seconds, seconds)
        run.budget.reserved_output_tokens = max(
            run.budget.reserved_output_tokens,
            reserve,
        )
        run.plan = build_plan(run.plugin, run.input, run.risk_level, run.route)
        run.pending_question = None
        run.status = RunStatus.QUEUED
        await self.store.save_run(run)
        await self._event(
            run,
            "plan.updated",
            "已接收补充信息，仅执行新的计划节点",
            data={"nodes": [node.model_dump(mode="json") for node in run.plan]},
        )
        self._spawn(run.id)
        return run

    async def approve(self, run_id: str, user_id: int) -> RunRecord:
        run = await self._owned_run(run_id, user_id)
        if run.status != RunStatus.WAITING or run.pending_approval is None:
            raise ValueError("当前任务没有待批准操作")
        run.pending_approval = None
        run.status = RunStatus.QUEUED
        await self.store.save_run(run)
        await self._event(run, "run.approved", "用户已批准继续执行")
        self._spawn(run.id)
        return run

    async def _owned_run(self, run_id: str, user_id: int) -> RunRecord:
        run = await self.store.get_run(run_id)
        if run is None or run.user_id != user_id:
            raise KeyError(run_id)
        return run

    async def _execute(self, run_id: str) -> None:
        run = await self.store.get_run(run_id)
        if run is None:
            return
        with safe_span(
            "run.execute",
            **{
                "ophagent.run_id": run.id,
                "ophagent.trace_id": run.trace_id,
                "ophagent.plugin_id": run.plugin.id,
                "ophagent.risk_level": run.risk_level.value,
                "ophagent.route.intent": run.route.intent.value if run.route else "unknown",
                "ophagent.route.complexity": run.route.complexity.value if run.route else "standard",
            },
        ) as span:
            started = time.monotonic()
            await self._execute_inner(run_id)
            completed = await self.store.get_run(run_id)
            if completed is not None:
                events = await self.store.get_events(run_id)
                if self.evolution_controller is not None:
                    try:
                        await self.evolution_controller.record_run_outcome(
                            completed,
                            events,
                        )
                    except (OSError, TypeError, ValueError):
                        # Evolution telemetry may never change the clinical
                        # response or its terminal status.
                        pass
                first_delta = next(
                    (event for event in events if event.type == "answer.delta"),
                    None,
                )
                span.set_attribute("ophagent.run.status", completed.status.value)
                span.set_attribute(
                    "ophagent.run.duration_ms",
                    int((time.monotonic() - started) * 1000),
                )
                span.set_attribute("ophagent.model_calls", completed.budget.model_calls)
                span.set_attribute(
                    "ophagent.tokens.total",
                    completed.budget.prompt_tokens + completed.budget.completion_tokens,
                )
                span.set_attribute("ophagent.partial_success", bool(completed.warnings))
                if first_delta is not None:
                    span.set_attribute(
                        "ophagent.ttft_ms",
                        max(0, int((first_delta.timestamp - completed.created_at).total_seconds() * 1000)),
                    )

    async def _execute_inner(self, run_id: str) -> None:
        run = await self.store.get_run(run_id)
        if run is None:
            return
        active_clients = self.clients
        owns_clients = False
        if self.provider_config_store and await self.provider_config_store.has_overrides(run.user_id):
            active_clients = CapabilityClients(
                await self.provider_config_store.resolved_settings(run.user_id)
            )
            owns_clients = True
        client_token = self._client_context.set(active_clients)
        raw_context = await self.store.get_context_snapshot(run.id)
        conversation_context = (
            ConversationContextSnapshot.model_validate(raw_context)
            if raw_context is not None
            else None
        )
        conversation_token = self._conversation_context.set(conversation_context)
        runner = self.runner_factory(active_clients)
        set_context = getattr(runner, "set_run_context", None)
        if callable(set_context):
            set_context(
                run.route.selected_plugins if run.route and run.route.selected_plugins else "core",
                run.input.requested_skills,
            )
        started = time.monotonic()
        try:
            run.status = RunStatus.RUNNING
            await self.store.save_run(run)
            await self._event(
                run,
                "agent.started",
                "OphAgent 开始处理",
                data={"complexity": run.route.complexity if run.route else "standard"},
            )

            while True:
                self._check_cancel(run)
                if time.monotonic() - started > run.budget.max_seconds:
                    raise BudgetExceeded("任务超过时间预算")

                pending = [node for node in run.plan if node.status == NodeStatus.PENDING]
                if not pending:
                    break
                by_id = {node.id: node for node in run.plan}
                ready = [
                    node
                    for node in pending
                    if all(
                        by_id[dependency].status
                        in {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED}
                        for dependency in node.depends_on
                    )
                ]
                if not ready:
                    raise RuntimeError("DAG 无可执行节点，可能存在循环或未决依赖")

                semaphore = asyncio.Semaphore(self.config.RUN_MAX_CONCURRENCY)

                async def execute_node(
                    node,
                    gate: asyncio.Semaphore = semaphore,
                ) -> None:
                    async with gate:
                        await self._execute_node(run, node, runner)

                await asyncio.gather(*(execute_node(node) for node in ready))

            terminal_id = "report" if run.route and run.route.needs_report else "answer"
            terminal = next((node for node in run.plan if node.id == terminal_id), None)
            if terminal and terminal.status == NodeStatus.COMPLETED and terminal.output:
                run.answer = str(terminal.output.get("answer") or "")
                existing_events = await self.store.get_events(run.id)
                if not any(event.type == "answer.delta" for event in existing_events):
                    await self._emit_answer_deltas(run, run.answer)
                optional_failures = [
                    node for node in run.plan
                    if not node.required and node.status in {NodeStatus.FAILED, NodeStatus.SKIPPED}
                ]
                run.warnings = list(dict.fromkeys([
                    *run.warnings,
                    *(f"{node.title}未完成" for node in optional_failures),
                ]))
                run.status = (
                    RunStatus.COMPLETED_WITH_WARNINGS
                    if optional_failures or run.warnings
                    else RunStatus.COMPLETED
                )
                if terminal_id == "report":
                    artifact = Artifact(
                        run_id=run.id,
                        user_id=run.user_id,
                        type="report",
                        title="眼科结构化报告",
                        mime_type="text/markdown",
                        content=run.answer,
                        metadata={
                            "plugin_id": run.plugin.id,
                            "risk_level": run.risk_level,
                            "trace_id": run.trace_id,
                        },
                    )
                    await self.store.save_artifact(artifact)
                    await self._event(
                        run,
                        "artifact.created",
                        "报告产物已生成",
                        data={"artifact": artifact.model_dump(mode="json")},
                    )
                await self._event(
                    run,
                    "answer.completed",
                    "回答生成完成",
                    data={"answer": run.answer},
                )
                await self._event(run, "run.completed", "任务执行完成", status=run.status)
            else:
                run.status = RunStatus.FAILED
                run.error_code = f"{terminal_id}_unavailable"
                run.error_message = f"{terminal.title if terminal else '最终输出'}未成功完成"
                await self._event(
                    run,
                    "run.failed",
                    f"任务未能生成{terminal.title if terminal else '最终输出'}",
                    status=run.status,
                    error_code=run.error_code,
                )
        except asyncio.CancelledError:
            run.status = RunStatus.CANCELLED
            events = await self.store.get_events(run.id)
            if not any(event.type == "run.cancelled" for event in events):
                await self._event(run, "run.cancelled", "任务已取消", status=run.status)
        except Exception as exc:
            run.status = RunStatus.FAILED
            run.error_code = getattr(exc, "code", "runtime_error")
            run.error_message = str(exc)
            banner = emergency_banner(run.clinical_state)
            if banner:
                run.answer = banner + "\n\n系统能力异常，未继续生成诊断性内容。"
            await self._event(
                run,
                "run.failed",
                f"任务失败：{str(exc)[:240]}",
                status=run.status,
                error_code=run.error_code,
            )
        finally:
            await self.store.save_run(run)
            self._tasks.pop(run_id, None)
            self._client_context.reset(client_token)
            self._conversation_context.reset(conversation_token)
            if owns_clients:
                await active_clients.close()

    async def _emit_answer_deltas(self, run: RunRecord, answer: str) -> None:
        for offset in range(0, len(answer), 240):
            await self._event(
                run,
                "answer.delta",
                "正在生成回答",
                data={"delta": answer[offset:offset + 240], "offset": offset},
            )
            await asyncio.sleep(0)

    async def _execute_node(self, run: RunRecord, node, runner: AgentRunner) -> None:
        with safe_span(
            "run.node",
            **{
                "ophagent.run_id": run.id,
                "ophagent.trace_id": run.trace_id,
                "ophagent.node_id": node.id,
                "ophagent.agent": node.agent,
                "ophagent.capability": node.capability,
            },
        ) as span:
            await self._execute_node_inner(run, node, runner)
            span.set_attribute("ophagent.node_status", node.status.value)

    async def _execute_node_inner(self, run: RunRecord, node, runner: AgentRunner) -> None:
        self._check_cancel(run)
        by_id = {item.id: item for item in run.plan}
        failed_required = [
            by_id[dependency]
            for dependency in node.depends_on
            if by_id[dependency].required and by_id[dependency].status == NodeStatus.FAILED
        ]
        if failed_required:
            node.status = NodeStatus.SKIPPED
            node.error_code = "required_dependency_failed"
            node.output = {
                "status": "skipped",
                "failed_dependencies": [item.id for item in failed_required],
            }
            await self.store.save_run(run)
            await self._event(
                run,
                "tool.failed",
                f"{node.title}未执行：必要的前置步骤失败",
                data={
                    "node_id": node.id,
                    "failed_dependencies": [item.id for item in failed_required],
                },
                error_code=node.error_code,
            )
            return
        node.status = NodeStatus.RUNNING
        node.started_at = utc_now()
        await self.store.save_run(run)
        await self._event(
            run,
            "agent.started" if node.agent.endswith("Agent") else "tool.started",
            f"{node.agent} 开始：{node.title}",
            data={"node_id": node.id, "agent": node.agent, "capability": node.capability},
        )
        started = time.monotonic()
        try:
            if node.id == "supervisor":
                output = await self._supervisor(run, runner)
            elif node.id == "clinical":
                output = await self._clinical(run, runner)
            elif node.id == "evidence":
                output = await self._evidence(run)
            elif node.id == "imaging":
                output = await self._imaging(run, node)
            elif node.id == "documents":
                output = await self._documents(run)
            elif node.id == "audio":
                output = await self._audio(run)
            elif node.id == "assessment":
                output = await self._assessment(run, runner)
            elif node.id.startswith("specialist_"):
                output = await self._specialist(run, node, runner)
            elif node.id == "draft":
                output = await self._draft(run, runner)
            elif node.id == "critic":
                output = await self._critic(run, runner)
            elif node.id == "report":
                output = await self._report(run, runner)
            elif node.id == "answer":
                output = await self._answer(run, runner)
            else:
                raise RuntimeError(f"未知节点：{node.id}")
            node.output = output
            node.status = NodeStatus.COMPLETED
            node.completed_at = utc_now()
            await self._event(
                run,
                "agent.completed",
                f"{node.agent} 已完成：{node.title}",
                data={
                    "node_id": node.id,
                    "used_skills": sorted(
                        getattr(runner, "used_skill_ids", set()),
                    ),
                },
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except CapabilityUnavailable as exc:
            node.status = NodeStatus.FAILED if node.required else NodeStatus.SKIPPED
            node.error_code = exc.code
            node.output = {"status": "unavailable", "capability": exc.capability, "detail": exc.detail}
            await self._event(
                run,
                "tool.failed",
                f"{node.title}不可用：{exc.detail}",
                data={"node_id": node.id, "capability": exc.capability},
                error_code=exc.code,
            )
        except Exception as exc:
            if node.id in {"answer", "report"}:
                events = await self.store.get_events(run.id)
                partial_answer = "".join(
                    str(event.data.get("delta") or "")
                    for event in sorted(events, key=lambda item: item.sequence)
                    if event.type == "answer.delta"
                ).strip()
                if partial_answer:
                    node.status = NodeStatus.COMPLETED
                    node.completed_at = utc_now()
                    node.output = {
                        "answer": partial_answer,
                        "partial": True,
                        "postprocessing_error": str(exc),
                    }
                    run.warnings.append(
                        "正文已生成并保留，但生成后的校验或记账未完全完成"
                    )
                    await self._event(
                        run,
                        "agent.completed",
                        f"{node.title}正文已保留，后处理存在警告",
                        data={
                            "node_id": node.id,
                            "partial": True,
                            "postprocessing_error": str(exc),
                        },
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                    return
            node.status = NodeStatus.FAILED
            node.error_code = getattr(exc, "code", "node_failed")
            node.output = {"status": "failed", "detail": str(exc)}
            await self._event(
                run,
                "tool.failed",
                f"{node.title}失败：{str(exc)[:200]}",
                data={"node_id": node.id},
                error_code=node.error_code,
            )
        finally:
            await self.store.save_run(run)

    async def _ask(
        self,
        run: RunRecord,
        runner: AgentRunner,
        role: str,
        prompt: str,
        *,
        stream: bool = False,
    ) -> str:
        conversation_context = self._conversation_context.get()
        if conversation_context is not None:
            role_limits = {
                "DirectAnswerAgent": 1_200,
                "ClinicalReasoningAgent": 900,
                "DifferentialAssessmentAgent": 1_800,
                "OphthalmologySpecialistAgent": 2_000,
                "AnswerSynthesizer": self.config.CONTEXT_MAX_INPUT_TOKENS,
                "ReportAgent": self.config.CONTEXT_MAX_INPUT_TOKENS,
            }
            history_limit = role_limits.get(role.partition(":")[0], 0)
            history = (
                conversation_context.clinical_text
                if role.partition(":")[0] == "ClinicalReasoningAgent"
                else conversation_context.prompt_text
            )
            if history_limit and history:
                prompt = (
                    "会话历史上下文：\n"
                    f"{_truncate_to_tokens(history, history_limit, self.config.main_model_name)}"
                    "\n\n本轮任务与已完成组件：\n"
                    f"{prompt}"
                )
        planned_calls = 1
        if run.budget.model_calls + planned_calls > run.budget.max_model_calls:
            raise BudgetExceeded("模型调用次数超过预算")
        estimated_input = _token_count(prompt, self.config.main_model_name)
        used_tokens = run.budget.prompt_tokens + run.budget.completion_tokens
        if used_tokens + estimated_input + run.budget.reserved_output_tokens > run.budget.max_tokens:
            raise BudgetExceeded("剩余 token 不足以安全生成最终输出")
        remaining_seconds = max(
            1.0,
            run.budget.max_seconds
            - (utc_now() - run.created_at).total_seconds(),
        )
        with safe_span(
            "agent.model",
            **{
                "ophagent.run_id": run.id,
                "ophagent.trace_id": run.trace_id,
                "ophagent.agent": role,
            },
        ) as span:
            async with asyncio.timeout(remaining_seconds):
                stream_method = getattr(runner, "ask_stream", None)
                if stream and callable(stream_method):
                    pending_deltas: list[str] = []
                    pending_length = 0
                    last_flush = time.monotonic()

                    async def flush_deltas() -> None:
                        nonlocal pending_length, last_flush
                        if not pending_deltas:
                            return
                        combined = "".join(pending_deltas)
                        pending_deltas.clear()
                        pending_length = 0
                        last_flush = time.monotonic()
                        await self._event(
                            run,
                            "answer.delta",
                            "正在生成回答",
                            data={"delta": combined},
                        )

                    async def emit_delta(delta: str) -> None:
                        nonlocal pending_length
                        pending_deltas.append(delta)
                        pending_length += len(delta)
                        if (
                            pending_length >= 96
                            or "\n\n" in delta
                            or time.monotonic() - last_flush >= 0.18
                        ):
                            await flush_deltas()

                    reply = await stream_method(role, prompt, emit_delta)
                    await flush_deltas()
                else:
                    reply = await runner.ask(role, prompt)
            span.set_attribute("gen_ai.usage.input_tokens", reply.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", reply.completion_tokens)
            span.set_attribute("ophagent.model_calls", reply.model_calls)
            span.set_attribute("ophagent.usage_estimated", reply.usage_estimated)
        run.budget.model_calls += reply.model_calls
        run.budget.prompt_tokens += reply.prompt_tokens
        run.budget.completion_tokens += reply.completion_tokens
        run.budget.token_usage_estimated = run.budget.token_usage_estimated or reply.usage_estimated
        if run.budget.prompt_tokens + run.budget.completion_tokens > run.budget.max_tokens:
            run.warnings.append(
                "本次模型实际 token 使用超过预估预算，已保留生成结果并阻止追加调用"
            )
        return reply.text

    async def _answer(
        self,
        run: RunRecord,
        runner: AgentRunner,
        *,
        stream: bool = True,
    ) -> dict[str, Any]:
        preferences = await self._confirmed_preferences(run)
        if run.route and run.route.intent == TaskIntent.QUICK_ANSWER:
            prompt = (
                f"用户问题：{run.input.query}\n"
                f"用户已确认的表达偏好：{json.dumps(preferences, ensure_ascii=False)}\n"
                "直接、简洁地回答。若问题超出眼科范围也可正常简短回答；"
                "不得虚构医学来源，不要生成报告格式。"
            )
            answer = await self._ask(run, runner, "DirectAnswerAgent", prompt, stream=stream)
            return {"answer": answer}
        context = self._completed_context(run)
        evidence_raw = (context.get("evidence") or {}).get("evidence", [])
        evidence = [EvidenceItem.model_validate(item) for item in evidence_raw]
        knowledge_query = bool(
            run.route and run.route.intent == TaskIntent.KNOWLEDGE_RETRIEVAL
        )
        evidence_for_prompt = _pack_evidence(
            evidence,
            max_tokens=2_000 if knowledge_query else 1_400,
            model_name=self.config.main_model_name,
        )
        if knowledge_query:
            prompt = (
                f"用户问题：{run.input.query}\n"
                f"用户已确认的表达偏好：{json.dumps(preferences, ensure_ascii=False)}\n"
                f"检索证据：{json.dumps(evidence_for_prompt, ensure_ascii=False)}\n"
                "先直接回答核心问题，再自然组织与问题最相关的机制、表现、检查或处理。"
                "每个医学主张紧跟对应 [ev_xxx]；"
                "没有证据支持的内容不要补写，不要重复来源清单，不要输出通用免责声明。"
                "只有问题本身包含急症表现时，才追加一句明确的紧急行动。"
            )
        else:
            specialist_context = {
                key: value for key, value in context.items()
                if key.startswith("specialist_") or key == "draft"
            }
            prompt = (
                f"用户任务：{run.input.query}\n风险：{run.risk_level}\n"
                f"用户已确认的表达偏好：{json.dumps(preferences, ensure_ascii=False)}\n"
                f"已接收输入：影像 {len(run.input.image_paths)} 张、文档 {len(run.input.document_paths)} 份、音频 {len(run.input.audio_paths)} 段。\n"
                f"本次专业插件：{json.dumps(run.route.selected_plugins if run.route else [], ensure_ascii=False)}\n"
                f"ClinicalState：{_json_for_prompt(run.clinical_state.model_dump(mode='json'), 1_300, self.config.main_model_name)}\n"
                f"影像观察：{_json_for_prompt(context.get('imaging'), 900, self.config.main_model_name)}\n"
                f"结构化鉴别评估：{_json_for_prompt(context.get('assessment'), 1_200, self.config.main_model_name)}\n"
                f"文档内容：{_json_for_prompt(context.get('documents'), 1_100, self.config.main_model_name)}\n"
                f"音频转写：{_json_for_prompt(context.get('audio'), 500, self.config.main_model_name)}\n"
                f"检索证据：{json.dumps(evidence_for_prompt, ensure_ascii=False)}\n"
                f"专科复核与候选稿：{_json_for_prompt(specialist_context, 1_400, self.config.main_model_name)}\n"
                f"候选稿安全审查：{_json_for_prompt(context.get('critic'), 700, self.config.main_model_name)}\n"
                "先直接回应用户问题，再说明关键依据、未知项和下一步。"
                "影像观察来自已接收的原始上传影像，不得声称未提供图像或仅基于文本。"
                "如果请求病灶定位但影像观察的 regions 为空，必须明确没有形成通过校验的坐标，"
                "不得把解剖关注区写成已经标定的病灶。鉴别表使用“当前资料支持程度”，不得写患病概率。"
                "若有候选稿和安全审查，逐项落实修订要求。"
                "仅在存在证据时使用对应 [ev_xxx]，不要另写重复来源清单或通用免责声明。"
            )
        should_stream = stream and not bool(run.route and run.route.selected_plugins)
        answer = await self._ask(
            run,
            runner,
            "AnswerSynthesizer",
            prompt,
            stream=should_stream,
        )
        if knowledge_query:
            answer = _remove_knowledge_boilerplate(answer)
        answer = _sanitize_public_image_context(
            answer,
            has_images=bool(run.input.image_paths),
            localization_requested=bool(
                run.route and "lesion_localizer" in run.route.selected_plugins
            ),
            validated_region_count=len(
                (context.get("imaging") or {}).get("regions") or []
            ),
        )
        answer = _moderate_unconfirmed_medical_language(answer, run.risk_level)
        banner = emergency_banner(run.clinical_state)
        if banner:
            answer = banner + "\n\n" + answer
        validation = self._client_context.get().validate_citations(answer, evidence)
        if evidence and not validation.data["valid"]:
            answer += "\n\n> 部分陈述未通过引用一致性核验，请以已列明来源为准。"
        output_validation = _validate_answer_output(
            answer,
            query=run.input.query,
            evidence=evidence,
            citation_validation=validation.data,
            has_images=bool(run.input.image_paths),
            localization_requested=bool(
                run.route and "lesion_localizer" in run.route.selected_plugins
            ),
            validated_region_count=len(
                (context.get("imaging") or {}).get("regions") or []
            ),
        )
        return {
            "answer": answer,
            "citation_validation": validation.data,
            "output_validation": output_validation,
        }

    async def _supervisor(self, run: RunRecord, runner: AgentRunner) -> dict[str, Any]:
        prompt = (
            f"插件：{run.plugin.id}\n风险等级：{run.risk_level}\n用户任务：{run.input.query}\n"
            f"输入影像数：{len(run.input.image_paths)}；文档数：{len(run.input.document_paths)}。\n"
            "给出可公开的执行摘要，不要输出隐藏分析过程。"
        )
        return {"summary": await self._ask(run, runner, "SupervisorAgent", prompt)}

    async def _clinical(self, run: RunRecord, runner: AgentRunner) -> dict[str, Any]:
        confirmed_memory: list[dict[str, Any]] = []
        if self.memory_store is not None:
            memories = await self.memory_store.search(
                run.user_id,
                run.input.query,
                categories={"history", "medication", "allergy"},
                limit=6,
            )
            confirmed_memory = [
                {
                    "category": item.category,
                    "content": item.content,
                    "source": item.source,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in memories
            ]
            if confirmed_memory:
                await self._event(
                    run,
                    "memory.recalled",
                    f"已调用 {len(confirmed_memory)} 条相关已确认记忆",
                    data={
                        "count": len(confirmed_memory),
                        "categories": sorted({item["category"] for item in confirmed_memory}),
                        "memories": [
                            {"id": item.id, "category": item.category}
                            for item in memories
                        ],
                    },
                )
        prompt = (
            "请从本轮用户原话抽取候选临床信息。不得把推测写成事实或提前给出诊断。输出严格 JSON："
            '{"chief_complaint":string|null,"positives":[string],"negatives":[string],'
            '"medications":[string],"allergies":[string],"unresolved_questions":[string],'
            '"red_flags":[string]}'
            f"\n已有 ClinicalState：{run.clinical_state.model_dump_json()}"
            f"\n用户已确认的长期记忆（仅作有来源参考，不自动写成事实）："
            f"{json.dumps(confirmed_memory, ensure_ascii=False)}"
            f"\n本轮系统已接收：影像 {len(run.input.image_paths)} 张、"
            f"文档 {len(run.input.document_paths)} 份、音频 {len(run.input.audio_paths)} 段。"
            "附件会由独立组件解析；不得因用户文字未重复提及附件而写成“未提供附件”。"
            f"\n本轮用户原话：{run.input.query}"
        )
        text = await self._ask(run, runner, "ClinicalReasoningAgent", prompt)
        parsed = parse_json_object(text)
        if parsed.get("chief_complaint") and not run.clinical_state.chief_complaint:
            run.clinical_state.chief_complaint = str(parsed["chief_complaint"])
        for field in ("positives", "negatives", "medications", "allergies"):
            target = getattr(run.clinical_state, field)
            existing = {item.value for item in target}
            for value in parsed.get(field, []):
                if isinstance(value, str) and value not in existing:
                    target.append(ClinicalFact(value=value, source="用户本轮输入（待确认）", confirmed=False))
        unresolved_questions = [
            question
            for question in parsed.get("unresolved_questions", [])
            if isinstance(question, str)
            and not (
                run.input.image_paths
                and any(term in question for term in ("未提供影像", "未提供图像", "未提供图片"))
            )
            and not (
                run.input.document_paths
                and any(term in question for term in ("未提供文档", "未提供报告", "未提供资料"))
            )
        ]
        for question in unresolved_questions:
            if isinstance(question, str) and question not in run.clinical_state.unresolved_questions:
                run.clinical_state.unresolved_questions.append(question)
        run.clinical_state.updated_at = utc_now()
        proposed: list[dict[str, Any]] = []
        if self.memory_store is not None:
            candidates = await self.memory_store.propose_from_clinical_state(
                user_id=run.user_id,
                run_id=run.id,
                state=run.clinical_state,
            )
            proposed = [
                item.model_dump(mode="json")
                for item in candidates
                if item.status == "proposed"
            ]
            for item in proposed:
                await self._event(
                    run,
                    "memory.proposed",
                    "检测到可确认的长期记忆候选",
                    data={
                        "memory_id": item["id"],
                        "category": item["category"],
                    },
                )
        return {
            "clinical_state": run.clinical_state.model_dump(mode="json"),
            "memory_candidates": proposed,
        }

    async def _evidence(self, run: RunRecord) -> dict[str, Any]:
        clients = self._client_context.get()
        retrieval_query = run.input.query
        conversation_context = self._conversation_context.get()
        if (
            run.route
            and run.route.reason_code == "contextual_follow_up"
            and conversation_context
            and conversation_context.previous_query
        ):
            retrieval_query = (
                f"{conversation_context.previous_query}\n"
                f"本轮追问：{run.input.query}"
            )
        local = await clients.retrieve_medical_evidence(retrieval_query, top_k=6)
        evidence = list(local.data.get("evidence", []))
        needs_fresh = any(term in run.input.query for term in ("最新", "目前", "今年", "2026", "新指南"))
        if (
            needs_fresh
            or len(evidence) < 2
            or (run.route and run.route.intent == TaskIntent.KNOWLEDGE_RETRIEVAL)
        ):
            try:
                external = await clients.search_web(
                    SearchRequest(query=retrieval_query, max_results=5)
                )
                evidence.extend(external.data.get("evidence", []))
            except CapabilityUnavailable:
                if not evidence:
                    raise
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for item in evidence:
            key = (str(item.get("source") or ""), str(item.get("locator") or item.get("title") or ""))
            previous = unique.get(key)
            if previous is None or float(item.get("score", 0)) > float(previous.get("score", 0)):
                unique[key] = item
        evidence = sorted(
            unique.values(),
            key=_evidence_sort_score,
            reverse=True,
        )[:8]
        await self._event(
            run,
            "retrieval.result",
            f"检索到 {len(evidence)} 条可追踪证据",
            data={
                "node_id": "evidence",
                "evidence": evidence,
                "score_max": max((float(item.get("score", 0)) for item in evidence), default=0),
                "score_min": min((float(item.get("score", 0)) for item in evidence), default=0),
            },
        )
        return {"evidence": evidence}

    async def _imaging(self, run: RunRecord, node) -> dict[str, Any]:
        result = await self._client_context.get().analyze_image(
            ImageAnalysisRequest(
                image_paths=run.input.image_paths,
                question=run.input.query,
                request_regions=bool(node.input.get("request_regions")),
            ),
        )
        output = dict(result.data)
        regions: list[dict[str, Any]] = []
        for raw in output.get("regions", []):
            if not isinstance(raw, dict):
                continue
            region = dict(raw)
            confidence = region.get("confidence")
            region["reliability"] = _region_reliability(confidence)
            regions.append(region)
        output["regions"] = regions
        output["region_count"] = len(regions)
        output["localization_status"] = (
            "validated_regions_available"
            if regions
            else "no_reliable_region_returned"
        )
        return output

    async def _documents(self, run: RunRecord) -> dict[str, Any]:
        documents: list[dict[str, Any]] = []
        for path in run.input.document_paths:
            result = await self._client_context.get().parse_document(DocumentParseRequest(path=path))
            documents.append({"path": path, **result.data})
        return {"documents": documents}

    async def _audio(self, run: RunRecord) -> dict[str, Any]:
        transcripts: list[dict[str, Any]] = []
        for path in run.input.audio_paths:
            result = await self._client_context.get().transcribe(SpeechRequest(path=path))
            transcripts.append({"path": path, **result.data})
        return {"transcripts": transcripts}

    async def _assessment(self, run: RunRecord, runner: AgentRunner) -> dict[str, Any]:
        from app.domain.models import DifferentialDiagnosis

        context = self._completed_context(run)
        evidence_raw = (context.get("evidence") or {}).get("evidence", [])
        evidence = [EvidenceItem.model_validate(item) for item in evidence_raw]
        evidence_for_prompt = _pack_evidence(
            evidence,
            max_tokens=1_700,
            model_name=self.config.main_model_name,
        )
        prompt = (
            f"用户任务：{run.input.query}\n风险等级：{run.risk_level}\n"
            f"ClinicalState：{_json_for_prompt(run.clinical_state.model_dump(mode='json'), 1_400, self.config.main_model_name)}\n"
            f"影像可见观察：{_json_for_prompt(context.get('imaging'), 1_200, self.config.main_model_name)}\n"
            f"文档解析：{_json_for_prompt(context.get('documents'), 1_000, self.config.main_model_name)}\n"
            f"音频转写：{_json_for_prompt(context.get('audio'), 500, self.config.main_model_name)}\n"
            f"可追踪证据：{json.dumps(evidence_for_prompt, ensure_ascii=False)}\n"
            "输出严格 JSON："
            '{"summary":string,"differentials":[{"name":string,'
            '"supporting_evidence":[string],"opposing_evidence":[string],'
            '"missing_evidence":[string],"confidence":"low|medium|high"}],'
            '"red_flags":[string],"missing_information":[string],'
            '"recommended_actions":[string],"evidence_ids":[string]}。'
            "候选数量由资料决定，可以为空；confidence 是当前资料支持程度而非患病概率。"
            "只凭单次影像且缺少眼压、房角、病史等关键资料时，不得写成明确分期，"
            "不得直接要求启动药物或手术治疗；应提出需要补充的检查和专科评估。"
            "只引用输入中真实存在的 ev_ id，不得补造。"
        )
        parsed = parse_json_object(
            await self._ask(run, runner, "DifferentialAssessmentAgent", prompt)
        )
        parsed = _map_public_strings(
            parsed,
            lambda value: _moderate_unconfirmed_medical_language(value, run.risk_level),
        )
        differentials: list[DifferentialDiagnosis] = []
        for item in parsed.get("differentials", []):
            if not isinstance(item, dict):
                continue
            try:
                differentials.append(DifferentialDiagnosis.model_validate(item))
            except ValueError:
                continue
        run.clinical_state.differentials = differentials
        missing_information = [
            str(item)
            for item in parsed.get("missing_information", [])
            if isinstance(item, str)
        ]
        for item in missing_information:
            if item not in run.clinical_state.unresolved_questions:
                run.clinical_state.unresolved_questions.append(item)
        known_evidence_ids = {item.id for item in evidence}
        evidence_ids = [
            item for item in parsed.get("evidence_ids", [])
            if isinstance(item, str) and item in known_evidence_ids
        ]
        output = {
            "summary": str(parsed.get("summary") or ""),
            "differentials": [item.model_dump(mode="json") for item in differentials],
            "red_flags": [
                str(item) for item in parsed.get("red_flags", []) if isinstance(item, str)
            ],
            "missing_information": missing_information,
            "recommended_actions": [
                str(item)
                for item in parsed.get("recommended_actions", [])
                if isinstance(item, str)
            ],
            "evidence_ids": evidence_ids,
            "confidence_semantics": "qualitative_support_not_probability",
        }
        run.clinical_state.updated_at = utc_now()
        return output

    async def _specialist(self, run: RunRecord, node, runner: AgentRunner) -> dict[str, Any]:
        specialty = str(node.input.get("specialty") or "general")
        labels = {
            "retina": "眼底与黄斑",
            "glaucoma": "青光眼",
            "cornea": "角膜与眼表",
            "neuro": "神经眼科",
            "pediatric": "儿童眼病与斜弱视",
            "general": "综合眼科",
        }
        context = self._completed_context(run)
        prompt = (
            f"复核亚专科：{labels.get(specialty, labels['general'])}\n"
            f"用户任务：{run.input.query}\n风险等级：{run.risk_level}\n"
            f"ClinicalState：{run.clinical_state.model_dump_json()}\n"
            f"已完成组件：{_json_for_prompt(context, 3_200, self.config.main_model_name)}\n"
            f"系统已接收原始影像 {len(run.input.image_paths)} 张；上下文中的影像观察由多模态组件"
            "直接读取这些上传影像后产生。不得声称只获得文本摘要或未提供原始图像。"
            "输出公开复核意见，覆盖关键观察、"
            "支持/反对信息、危险信号与证据缺口、建议补充的检查或转诊。"
            "不得给出隐藏推理，不得把待确认信息写成确诊。"
        )
        review = await self._ask(
            run,
            runner,
            f"OphthalmologySpecialistAgent:{specialty}",
            prompt,
        )
        review = _sanitize_public_image_context(
            review,
            has_images=bool(run.input.image_paths),
            localization_requested=bool(
                run.route and "lesion_localizer" in run.route.selected_plugins
            ),
            validated_region_count=len(
                (context.get("imaging") or {}).get("regions") or []
            ),
        )
        review = _moderate_unconfirmed_medical_language(review, run.risk_level)
        return {
            "specialty": specialty,
            "label": labels.get(specialty, labels["general"]),
            "review": review,
        }

    async def _critic(self, run: RunRecord, runner: AgentRunner) -> dict[str, Any]:
        context = self._completed_context(run)
        prompt = (
            f"风险等级：{run.risk_level}\nClinicalState：{run.clinical_state.model_dump_json()}\n"
            f"已完成组件：{_json_for_prompt(context, 3_600, self.config.main_model_name)}\n"
            "检查红旗遗漏、无依据诊断、药物/过敏冲突、坐标伪造与引用风险。"
            "只输出公开问题清单。"
        )
        return {"review": await self._ask(run, runner, "CriticAgent", prompt)}

    async def _draft(self, run: RunRecord, runner: AgentRunner) -> dict[str, Any]:
        if run.route and run.route.needs_report:
            result = await self._report(run, runner, stream=False)
        else:
            result = await self._answer(run, runner, stream=False)
        return {
            "answer": result.get("answer", ""),
            "citation_validation": result.get("citation_validation"),
        }

    async def _report(
        self,
        run: RunRecord,
        runner: AgentRunner,
        *,
        stream: bool = True,
    ) -> dict[str, Any]:
        context = self._completed_context(run)
        preferences = await self._confirmed_preferences(run)
        evidence_raw = context.get("evidence", {}).get("evidence", [])
        evidence = [EvidenceItem.model_validate(item) for item in evidence_raw]
        evidence_for_prompt = _pack_evidence(
            evidence,
            max_tokens=2_800,
            model_name=self.config.main_model_name,
        )
        prompt = (
            f"任务：{run.input.query}\n插件：{run.plugin.id}\n风险：{run.risk_level}\n"
            f"用户已确认的表达偏好：{json.dumps(preferences, ensure_ascii=False)}\n"
            f"已接收输入：影像 {len(run.input.image_paths)} 张、文档 {len(run.input.document_paths)} 份。\n"
            f"ClinicalState：{run.clinical_state.model_dump_json()}\n"
            f"影像观察：{_json_for_prompt(context.get('imaging'), 1_200, self.config.main_model_name)}\n"
            f"结构化鉴别评估：{_json_for_prompt(context.get('assessment'), 1_500, self.config.main_model_name)}\n"
            f"文档内容：{_json_for_prompt(context.get('documents'), 2_000, self.config.main_model_name)}\n"
            f"音频转写：{_json_for_prompt(context.get('audio'), 700, self.config.main_model_name)}\n"
            f"候选稿：{_json_for_prompt(context.get('draft'), 1_800, self.config.main_model_name)}\n"
            f"专科复核：{_json_for_prompt({key: value for key, value in context.items() if key.startswith('specialist_')}, 1_800, self.config.main_model_name)}\n"
            f"高风险审查：{_json_for_prompt(context.get('critic'), 900, self.config.main_model_name)}\n"
            f"证据：{json.dumps(evidence_for_prompt, ensure_ascii=False)}\n"
            "若存在候选稿和高风险审查，必须逐项落实修订要求。"
            "生成结构化 Markdown，并根据输入识别实际检查模态；无法确定的患者信息、"
            "检查日期或模态必须标为未提供，不得填写占位事实。依次组织检查资料、"
            "可见观察、临床印象、鉴别与依据、局限、建议。"
            "上下文中的影像观察来自已上传原始影像，不得声称未提供图像或仅基于文本。"
            "若病灶定位 regions 为空，只能说明未形成经校验坐标，不得自行描述已标定边界。"
            "每个医学主张使用对应 [ev_xxx]；没有证据就明确标为证据不足。"
            "包含不确定性、下一步行动和研究级诊疗增强免责声明。"
        )
        should_stream = stream and not bool(run.route and run.route.selected_plugins)
        answer = await self._ask(
            run,
            runner,
            "ReportAgent",
            prompt,
            stream=should_stream,
        )
        answer = _sanitize_public_image_context(
            answer,
            has_images=bool(run.input.image_paths),
            localization_requested=bool(
                run.route and "lesion_localizer" in run.route.selected_plugins
            ),
            validated_region_count=len(
                (context.get("imaging") or {}).get("regions") or []
            ),
        )
        answer = _moderate_unconfirmed_medical_language(answer, run.risk_level)
        banner = emergency_banner(run.clinical_state)
        if banner:
            answer = banner + "\n\n" + answer
        validation = self._client_context.get().validate_citations(answer, evidence)
        if evidence and not validation.data["valid"]:
            answer += (
                "\n\n## 引用核验提示\n"
                "生成内容未通过逐条引用一致性核验；以下仅列出本次实际检索到的来源，"
                "未绑定的医学陈述不应作为诊疗依据。\n"
            )
            for item in evidence:
                answer += f"- [{item.id}] {item.title}，{item.locator or '定位未提供'}（{item.source}）\n"
        if not evidence:
            answer += "\n\n> 本次未检索到足够的可追踪证据，系统没有用模型常识补造来源。"
        return {"answer": answer, "citation_validation": validation.data}

    async def _confirmed_preferences(self, run: RunRecord) -> list[dict[str, str]]:
        if self.memory_store is None:
            return []
        memories = await self.memory_store.search(
            run.user_id,
            run.input.query,
            categories={"preference", "workspace"},
            limit=4,
        )
        if memories:
            await self._event(
                run,
                "memory.recalled",
                f"已应用 {len(memories)} 条已确认的用户偏好",
                data={
                    "count": len(memories),
                    "categories": sorted({item.category for item in memories}),
                    "memories": [
                        {"id": item.id, "category": item.category}
                        for item in memories
                    ],
                },
            )
        return [
            {
                "category": item.category,
                "content": item.content,
                "source": item.source,
            }
            for item in memories
        ]

    @staticmethod
    def _completed_context(run: RunRecord) -> dict[str, Any]:
        return {
            node.id: node.output
            for node in run.plan
            if node.status == NodeStatus.COMPLETED and node.output is not None
        }

    def _check_cancel(self, run: RunRecord) -> None:
        if run.id in self._cancelled:
            raise RunCancelled("任务已取消")

    async def _event(
        self,
        run: RunRecord,
        event_type: str,
        summary: str,
        *,
        status: Any | None = None,
        data: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        await self.store.append_event(
            RunEvent(
                run_id=run.id,
                trace_id=run.trace_id,
                type=event_type,
                status=str(status) if status is not None else None,
                public_summary=summary,
                data=data or {},
                prompt_tokens=run.budget.prompt_tokens,
                completion_tokens=run.budget.completion_tokens,
                duration_ms=duration_ms,
                error_code=error_code,
            ),
        )


def _encoding_for_model(model_name: str):
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def _token_count(text: str, model_name: str) -> int:
    return max(1, len(_encoding_for_model(model_name).encode(text)))


def _truncate_to_tokens(text: str, max_tokens: int, model_name: str) -> str:
    encoding = _encoding_for_model(model_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoding.decode(tokens[:max_tokens]).rstrip() + "…"


def _json_for_prompt(value: Any, max_tokens: int, model_name: str) -> str:
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    return _truncate_to_tokens(serialized, max_tokens, model_name)


def _merge_clinical_state(previous: ClinicalState, current: ClinicalState) -> ClinicalState:
    """Carry thread facts forward without promoting model assessments to facts."""

    merged = previous.model_copy(deep=True)
    if current.chief_complaint:
        merged.chief_complaint = current.chief_complaint
    for field in (
        "timeline",
        "positives",
        "negatives",
        "examinations",
        "medications",
        "allergies",
        "red_flags",
    ):
        target = getattr(merged, field)
        known = {(item.value, item.source) for item in target}
        for fact in getattr(current, field):
            if (fact.value, fact.source) not in known:
                target.append(fact.model_copy(deep=True))
    for question in current.unresolved_questions:
        if question not in merged.unresolved_questions:
            merged.unresolved_questions.append(question)
    # Differential diagnoses are generated assessments, not durable facts.
    merged.differentials = []
    merged.updated_at = utc_now()
    return merged


def _region_reliability(confidence: Any) -> str:
    """Convert a model localization score into a non-probabilistic UI label."""
    if not isinstance(confidence, (int, float)):
        return "not_reported"
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def _pack_evidence(
    evidence: list[EvidenceItem],
    *,
    max_tokens: int,
    model_name: str,
) -> list[dict[str, Any]]:
    packed: list[dict[str, Any]] = []
    used = 2
    for item in evidence:
        base = {
            "id": item.id,
            "title": item.title,
            "source": item.source,
            "locator": item.locator,
            "source_type": item.source_type,
        }
        base_tokens = _token_count(
            json.dumps(base, ensure_ascii=False, default=str),
            model_name,
        )
        remaining = max_tokens - used - base_tokens
        if remaining < 80:
            break
        excerpt = _truncate_to_tokens(
            item.excerpt,
            min(420, remaining),
            model_name,
        )
        candidate = {**base, "excerpt": excerpt}
        candidate_tokens = _token_count(
            json.dumps(candidate, ensure_ascii=False, default=str),
            model_name,
        )
        if used + candidate_tokens > max_tokens:
            continue
        packed.append(candidate)
        used += candidate_tokens
    return packed


def _remove_knowledge_boilerplate(answer: str) -> str:
    """Keep medical content while removing UI-duplicated source lists and legal filler."""
    generic_phrases = (
        "本内容仅为医学科普",
        "本内容仅供医学科普",
        "不构成个体化诊断或处方建议",
        "具体诊疗路径需由执业医师",
        "本系统用于研究级诊疗增强",
    )
    cleaned: list[str] = []
    skipping_sources = False
    for raw_line in answer.splitlines():
        stripped = raw_line.strip()
        if "资料来源" in stripped or "参考来源" in stripped:
            skipping_sources = True
            continue
        if skipping_sources:
            if stripped.startswith(("#", "⚠️", "下一步", "建议")):
                skipping_sources = False
            else:
                continue
        if any(phrase in stripped for phrase in generic_phrases):
            continue
        if "医疗边界与下一步建议" in stripped:
            raw_line = raw_line.replace("医疗边界与下一步建议", "下一步建议")
        cleaned.append(raw_line)
    return "\n".join(cleaned).strip()


def _sanitize_public_image_context(
    text: str,
    *,
    has_images: bool,
    localization_requested: bool,
    validated_region_count: int,
) -> str:
    """Enforce attachment and localization facts after prose generation."""
    cleaned = text.strip()
    if has_images:
        replacements = {
            "（基于文本描述推断）": "",
            "基于文本描述推断": "基于已上传影像的自动观察",
            "因未提供可交互的原始图像文件，": "",
            "因未提供原始图像文件，": "",
            "仅凭摘要无法直接确认": "基于当前自动影像观察仍无法确认",
            "仅凭摘要无法直接标定": "当前自动影像分析未能形成经校验坐标来标定",
            "置信度": "当前资料支持程度",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        cleaned = re.sub(
            r"(?:未提供|缺少|没有)(?:可交互的)?(?:原始)?(?:眼底)?(?:影像|图像|图片)(?:文件)?",
            "已接收上传影像，但当前自动分析未获得该项信息",
            cleaned,
        )
    if localization_requested and validated_region_count == 0:
        cleaned = cleaned.replace(
            "可疑区域标定与定性鉴别",
            "影像观察与定性鉴别",
        ).replace(
            "可疑区域标定",
            "解剖关注区（未形成坐标标注）",
        )
        notice = (
            "> **定位校验结果：** 多模态组件已读取上传影像，但没有返回通过坐标校验的"
            "病灶区域，因此系统未在原图补画边界。下列解剖关注点不等同于已定位病灶。"
        )
        if "定位校验结果" not in cleaned:
            cleaned = f"{notice}\n\n{cleaned}"
    return cleaned


def _moderate_unconfirmed_medical_language(text: str, risk: RiskLevel) -> str:
    """Replace unsupported certainty or treatment commands without adding boilerplate."""
    cleaned = text
    cleaned = cleaned.replace("强烈提示", "较支持考虑")
    cleaned = re.sub(
        r"(?:疑似)?晚期青光眼性视神经病变",
        "青光眼性视神经病变（严重程度待临床评估）",
        cleaned,
    )
    cleaned = cleaned.replace(
        "尽快启动降眼压干预或专科转诊",
        "尽快由眼科专科评估是否需要降眼压干预",
    )
    cleaned = cleaned.replace(
        "启动降眼压治疗或转诊专科",
        "由眼科专科结合眼压与房角检查决定是否需要降眼压治疗",
    )
    if risk not in {RiskLevel.HIGH, RiskLevel.EMERGENCY}:
        cleaned = cleaned.replace("立即进行规范眼压测量", "尽快安排规范眼压测量")
    return cleaned


def _map_public_strings(value: Any, transform: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, list):
        return [_map_public_strings(item, transform) for item in value]
    if isinstance(value, dict):
        return {
            key: _map_public_strings(item, transform)
            for key, item in value.items()
        }
    return value


def _evidence_sort_score(item: dict[str, Any]) -> float:
    """Blend retrieval relevance with provenance quality without changing UI scores."""
    raw_score = float(item.get("score", 0) or 0)
    title = str(item.get("title") or "").lower()
    source = str(item.get("source") or "").lower()
    identity = f"{title} {source}"
    if any(
        marker in identity
        for marker in ("baidubaike_", "xywy_", "dxy_", "百度百科", "寻医问药")
    ):
        return raw_score * 0.18
    if item.get("source_type") == "guideline" and item.get("verified"):
        return raw_score * 1.2
    if source.startswith("http"):
        authoritative = (
            ".gov",
            ".gov.cn",
            "who.int",
            "aao.org",
            "nei.nih.gov",
            "nih.gov",
            "ncbi.nlm.nih.gov",
            "nice.org.uk",
            "rcophth.ac.uk",
            "cochrane.org",
            "mayoclinic.org",
        )
        return raw_score * (
            1.12 if any(domain in source for domain in authoritative) else 0.82
        )
    return raw_score


def _validate_answer_output(
    answer: str,
    *,
    query: str,
    evidence: list[EvidenceItem],
    citation_validation: dict[str, Any],
    has_images: bool = False,
    localization_requested: bool = False,
    validated_region_count: int = 0,
) -> dict[str, Any]:
    ophthalmic_anchors = (
        "青光眼",
        "白内障",
        "视网膜",
        "黄斑",
        "角膜",
        "结膜",
        "干眼",
        "近视",
        "视神经",
        "眼压",
        "飞蚊",
        "闪光",
    )
    expected = [term for term in ophthalmic_anchors if term in query]
    missing = [term for term in expected if term not in answer]
    issues: list[str] = []
    if not answer.strip():
        issues.append("empty_answer")
    if missing:
        issues.append("query_anchor_missing")
    if evidence and not citation_validation.get("valid", False):
        issues.append("citation_coverage_failed")
    if has_images and re.search(
        r"(?:未提供|缺少|没有)(?:可交互的)?(?:原始)?(?:眼底)?(?:影像|图像|图片)",
        answer,
    ):
        issues.append("image_context_contradiction")
    if (
        localization_requested
        and validated_region_count == 0
        and "定位校验结果" not in answer
    ):
        issues.append("missing_empty_localization_disclosure")
    return {
        "valid": not issues,
        "issues": issues,
        "missing_query_anchors": missing,
        "evidence_count": len(evidence),
    }

import asyncio
import json
import re

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.models import (
    Artifact,
    AttachmentRecord,
    EvidenceItem,
    InterventionMode,
    InterventionStatus,
    NodeStatus,
    PlanNode,
    RiskLevel,
    RunEvent,
    RunInput,
    RunIntervention,
    RunRecord,
    RunStatus,
)
from app.plugins.registry import plugin_registry
from app.runtime.agents import AgentReply
from app.runtime.context import ConversationContextManager, ExecutionContextManager
from app.runtime.errors import (
    BudgetExceeded,
    CapabilityUnavailable,
    ContextCompactionError,
)
from app.runtime.orchestrator import (
    RunOrchestrator,
    _clean_public_answer,
    _moderate_unconfirmed_medical_language,
    _sanitize_public_image_context,
)
from app.runtime.store import RuntimeStore
from tests.fakes import FakeCapabilityClients, FakeRunner


def build_settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        ENVIRONMENT="test",
        STRICT_STARTUP=False,
        JWT_SECRET_KEY=SecretStr("test-secret"),
        AGENT_URL="https://model.test/v1",
        AGENT_API_KEY=SecretStr("key"),
        AGENT_MODEL="test",
        SUB_AGENT_URL="https://model.test/v1",
        SUB_AGENT_API_KEY=SecretStr("key"),
        SUB_AGENT_MODEL="vision",
        RUNTIME_STATE_DIR=str(tmp_path / "runs"),
        ARTIFACT_DIR=str(tmp_path / "artifacts"),
        ATTACHMENT_DIR=str(tmp_path / "attachments"),
        MEMORY_STATE_PATH=str(tmp_path / "memories.json"),
        SKILL_STATE_PATH=str(tmp_path / "skills.json"),
    )


def test_image_context_sanitizer_preserves_uploaded_image_fact_and_empty_regions():
    cleaned = _sanitize_public_image_context(
        "### 可疑区域标定与定性鉴别\n因未提供可交互的原始图像文件，以下基于文本描述推断。"
        "\n| 鉴别 | 置信度 |\n|---|---|\n| 青光眼 | 中等 |",
        has_images=True,
        localization_requested=True,
        validated_region_count=0,
    )

    assert "未提供可交互的原始图像" not in cleaned
    assert "基于文本描述推断" not in cleaned
    assert "定位结果" in cleaned
    assert "未获得可显示的坐标定位" in cleaned
    assert "当前资料支持程度" in cleaned


def test_public_answer_removes_generic_safety_boilerplate_but_keeps_requested_content():
    cleaned = _clean_public_answer(
        "## 回答\n青光眼随访通常关注眼压与视野。\n\n"
        "## 免责声明\n本系统用于研究级诊疗增强，不能替代医生诊断。\n\n"
        "## 下一步\n按计划复查。"
    )

    assert "青光眼随访通常关注眼压与视野" in cleaned
    assert "按计划复查" in cleaned
    assert "免责声明" not in cleaned
    assert "研究级诊疗增强" not in cleaned
    assert "不能替代" not in cleaned


def test_routine_output_moderates_unconfirmed_staging_and_treatment_commands():
    cleaned = _moderate_unconfirmed_medical_language(
        "影像强烈提示晚期青光眼性视神经病变，建议立即进行规范眼压测量，"
        "并启动降眼压治疗或转诊专科。",
        RiskLevel.ROUTINE,
    )

    assert "强烈提示" not in cleaned
    assert "晚期青光眼" not in cleaned
    assert "立即进行" not in cleaned
    assert "决定是否需要降眼压治疗" in cleaned


async def wait_for_terminal(store, run_id):
    for _ in range(100):
        current = await store.get_run(run_id)
        if current and current.status in {
            RunStatus.COMPLETED,
            RunStatus.COMPLETED_WITH_WARNINGS,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return current
        await asyncio.sleep(0.01)
    raise AssertionError("run did not reach a terminal state")


@pytest.mark.asyncio
async def test_quick_math_uses_one_call_no_retrieval_no_report(tmp_path):
    class TrackingRunner(FakeRunner):
        roles: list[str] = []

        async def ask(self, role, prompt):
            self.roles.append(role)
            return await super().ask(role, prompt)

    class TrackingClients(FakeCapabilityClients):
        retrieval_calls = 0

        async def retrieve_medical_evidence(self, query, top_k=6, *, user_id=None):
            del user_id
            self.retrieval_calls += 1
            return await super().retrieve_medical_evidence(query, top_k)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = TrackingRunner()
    clients = TrackingClients()
    orchestrator = RunOrchestrator(
        store,
        clients,
        config,
        runner_factory=lambda active_clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="1+1等于多少？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED
    assert current.route and current.route.complexity == "quick"
    assert [node.id for node in current.plan] == ["answer"]
    assert runner.roles == ["DirectAnswerAgent"]
    assert current.budget.model_calls == 1
    assert clients.retrieval_calls == 0
    assert await store.list_artifacts(7, run.id) == []


@pytest.mark.asyncio
async def test_standard_eye_question_is_not_misrouted_to_quick(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="眼睛干涩怎么办？", plugin_id="interactive_vqa"),
    )
    assert run.route and run.route.complexity == "standard"
    assert any(node.id == "clinical" for node in run.plan)


@pytest.mark.asyncio
async def test_composed_plugins_receive_deep_graph_budget(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    image = tmp_path / "fundus.jpg"
    image.write_bytes(b"image")
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(
            query="请定位、评估并生成报告",
            image_paths=[str(image)],
            requested_plugins=[
                "lesion_localizer",
                "aux_diagnosis",
                "report_generator",
            ],
        ),
    )

    assert run.route and run.route.complexity == "deep"
    assert run.budget.max_tokens == min(40_000, config.RUN_MAX_TOKENS)
    assert run.budget.max_model_calls == min(8, config.RUN_MAX_MODEL_CALLS)


@pytest.mark.asyncio
async def test_glaucoma_definition_routes_to_retrieval_without_clinical_extraction(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    assert run.route and run.route.intent == "knowledge_retrieval"
    assert [node.id for node in run.plan] == ["evidence", "answer"]


@pytest.mark.asyncio
async def test_follow_up_receives_prior_turn_and_inherits_retrieval_route(tmp_path):
    class PromptRunner(FakeRunner):
        prompts: list[tuple[str, str]] = []

        async def ask(self, role, prompt):
            self.prompts.append((role, prompt))
            return await super().ask(role, prompt)

    class RetrievalClients(FakeCapabilityClients):
        queries: list[str] = []

        async def retrieve_medical_evidence(self, query, top_k=6, *, user_id=None):
            self.queries.append(query)
            return await super().retrieve_medical_evidence(
                query,
                top_k,
                user_id=user_id,
            )

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = PromptRunner()
    clients = RetrievalClients()
    orchestrator = RunOrchestrator(
        store,
        clients,
        config,
        runner_factory=lambda clients: runner,
    )
    first = await orchestrator.create(
        7,
        RunInput(
            query="什么是青光眼？",
            plugin_id="interactive_vqa",
            conversation_id=88,
        ),
    )
    await wait_for_terminal(store, first.id)
    runner.prompts.clear()

    second = await orchestrator.create(
        7,
        RunInput(
            query="那需要做哪些检查？",
            plugin_id="interactive_vqa",
            conversation_id=88,
        ),
    )
    current = await wait_for_terminal(store, second.id)

    assert current.route and current.route.reason_code == "contextual_follow_up"
    assert current.route.needs_retrieval is True
    answer_prompt = next(
        prompt for role, prompt in runner.prompts if role == "AnswerSynthesizer"
    )
    assert "什么是青光眼" in answer_prompt
    assert "历史助手回答（待核验）" in answer_prompt
    assert "什么是青光眼" in clients.queries[-1]
    assert "那需要做哪些检查" in clients.queries[-1]
    assert current.context_stats.source_turns == 1
    assert any(
        event.type == "context.prepared"
        for event in await store.get_events(second.id)
    )


@pytest.mark.asyncio
async def test_context_compaction_is_bounded_and_keeps_recent_turns(tmp_path):
    config = build_settings(tmp_path).model_copy(
        update={
            "CONVERSATION_CONTEXT_MAX_INPUT_TOKENS": 800,
            "CONTEXT_RECENT_TURNS": 2,
        },
    )
    store = RuntimeStore(config)
    for index in range(6):
        run = RunRecord(
            user_id=7,
            status=RunStatus.COMPLETED,
            input=RunInput(
                query=f"第 {index + 1} 轮问题：" + "眼科病史" * 80,
                conversation_id=91,
            ),
            plugin=plugin_registry.get("interactive_vqa"),
            answer=f"第 {index + 1} 轮回答：" + "需要结合检查复核。" * 120,
        )
        await store.create_run(run)

    manager = ConversationContextManager(store, config)
    snapshot = await manager.build(
        run_id="run_context_test",
        user_id=7,
        run_input=RunInput(query="继续", conversation_id=91),
    )

    assert snapshot is not None
    assert snapshot.compaction_status == "pending"
    expected_summary_ids = [
        run_id
        for run_id in snapshot.source_run_ids
        if run_id not in snapshot.retained_source_run_ids
    ]
    snapshot = await manager.complete_compaction(
        snapshot,
        {
            "version": "v1",
            "summary": "用户希望延续此前眼科任务；旧回答需要结合本轮资料重新核验。",
            "user_goals": ["继续此前任务"],
            "decisions": [],
            "unresolved_items": ["结合本轮资料复核"],
            "corrections": [],
            "source_run_ids": expected_summary_ids,
        },
        attempt=1,
    )
    assert snapshot.stats.source_turns == 6
    assert snapshot.stats.retained_turns <= 2
    assert snapshot.stats.summarized_turns >= 4
    assert snapshot.stats.tokens_after <= 800
    assert snapshot.compaction_status == "completed"
    assert snapshot.stats.compaction_method == "model_structured_summary"
    assert "模型压缩摘要" in snapshot.prompt_text
    assert "临床事实只能来自" in snapshot.prompt_text


@pytest.mark.asyncio
async def test_context_below_threshold_keeps_full_history_without_summary(tmp_path):
    config = build_settings(tmp_path).model_copy(
        update={
            "CONVERSATION_CONTEXT_MAX_INPUT_TOKENS": 2_000,
            "CONTEXT_COMPRESSION_TRIGGER_RATIO": 0.82,
        },
    )
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=RunStatus.COMPLETED,
        input=RunInput(query="不是左眼，是右眼。", conversation_id=92),
        plugin=plugin_registry.get("interactive_vqa"),
        answer="收到，我会按右眼信息继续。",
    )
    await store.create_run(run)

    snapshot = await ConversationContextManager(store, config).build(
        run_id="run_context_no_compaction",
        user_id=7,
        run_input=RunInput(query="继续", conversation_id=92),
    )

    assert snapshot is not None
    assert snapshot.compaction_status == "not_needed"
    assert snapshot.stats.summarized_turns == 0
    assert "不是左眼，是右眼。" in snapshot.prompt_text
    assert "收到，我会按右眼信息继续。" in snapshot.prompt_text


@pytest.mark.asyncio
async def test_failed_run_correction_is_retained_verbatim_during_compaction(tmp_path):
    config = build_settings(tmp_path).model_copy(
        update={
            "CONVERSATION_CONTEXT_MAX_INPUT_TOKENS": 700,
            "CONTEXT_RECENT_TURNS": 1,
        },
    )
    store = RuntimeStore(config)
    correction = RunRecord(
        user_id=7,
        status=RunStatus.FAILED,
        input=RunInput(
            query="更正：不是左眼，是右眼；已经停用噻吗洛尔。",
            conversation_id=95,
        ),
        plugin=plugin_registry.get("interactive_vqa"),
    )
    await store.create_run(correction)
    for index in range(4):
        await store.create_run(
            RunRecord(
                user_id=7,
                status=RunStatus.COMPLETED,
                input=RunInput(
                    query=f"普通历史任务 {index}：" + "背景" * 80,
                    conversation_id=95,
                ),
                plugin=plugin_registry.get("interactive_vqa"),
                answer="待核验历史回答。" * 90,
            ),
        )
    manager = ConversationContextManager(store, config)
    snapshot = await manager.build(
        run_id="run_context_correction",
        user_id=7,
        run_input=RunInput(query="继续", conversation_id=95),
    )

    assert snapshot is not None
    assert snapshot.compaction_status == "pending"
    assert correction.id in snapshot.retained_source_run_ids
    expected_ids = [
        run_id
        for run_id in snapshot.source_run_ids
        if run_id not in snapshot.retained_source_run_ids
    ]
    compacted = await manager.complete_compaction(
        snapshot,
        {
            "version": "v1",
            "summary": "此前还有普通历史任务需要结合本轮资料复核。",
            "user_goals": ["继续任务"],
            "decisions": [],
            "unresolved_items": [],
            "corrections": [],
            "source_run_ids": expected_ids,
        },
        attempt=1,
    )

    assert "更正：不是左眼，是右眼；已经停用噻吗洛尔。" in compacted.prompt_text


@pytest.mark.asyncio
async def test_generated_summary_cannot_carry_clinical_detail(tmp_path):
    config = build_settings(tmp_path).model_copy(
        update={
            "CONVERSATION_CONTEXT_MAX_INPUT_TOKENS": 500,
            "CONTEXT_RECENT_TURNS": 0,
        },
    )
    store = RuntimeStore(config)
    for index in range(3):
        await store.create_run(
            RunRecord(
                user_id=7,
                status=RunStatus.COMPLETED,
                input=RunInput(
                    query=f"长历史 {index}：" + "背景" * 100,
                    conversation_id=96,
                ),
                plugin=plugin_registry.get("interactive_vqa"),
                answer="待核验。" * 100,
            ),
        )
    manager = ConversationContextManager(store, config)
    snapshot = await manager.build(
        run_id="run_context_reject_clinical_summary",
        user_id=7,
        run_input=RunInput(query="继续", conversation_id=96),
    )
    assert snapshot is not None

    with pytest.raises(
        ContextCompactionError,
        match="模型摘要未通过确定性校验",
    ) as exc_info:
        await manager.complete_compaction(
            snapshot,
            {
                "version": "v1",
                "summary": "用户右眼眼压 30 mmHg，已经停药。",
                "user_goals": ["继续任务"],
                "decisions": [],
                "unresolved_items": [],
                "corrections": [],
                "source_run_ids": snapshot.source_run_ids,
            },
            attempt=1,
        )
    assert "clinical_detail_must_stay_in_lossless_context" in exc_info.value.issues


@pytest.mark.asyncio
async def test_orchestrator_compacts_with_model_and_persists_validated_snapshot(
    tmp_path,
):
    class TrackingRunner(FakeRunner):
        roles: list[str] = []

        async def ask(self, role, prompt):
            self.roles.append(role)
            return await super().ask(role, prompt)

    config = build_settings(tmp_path).model_copy(
        update={
            "CONVERSATION_CONTEXT_MAX_INPUT_TOKENS": 700,
            "CONTEXT_RECENT_TURNS": 2,
        },
    )
    store = RuntimeStore(config)
    for index in range(5):
        await store.create_run(
            RunRecord(
                user_id=7,
                status=RunStatus.COMPLETED,
                input=RunInput(
                    query=f"第 {index + 1} 轮眼科任务：" + "背景说明" * 70,
                    conversation_id=93,
                ),
                plugin=plugin_registry.get("interactive_vqa"),
                answer="历史回答需要复核。" * 100,
            ),
        )
    runner = TrackingRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )

    created = await orchestrator.create(
        7,
        RunInput(
            query="继续说明青光眼检查",
            plugin_id="interactive_vqa",
            conversation_id=93,
        ),
    )
    current = await wait_for_terminal(store, created.id)
    raw_snapshot = await store.get_context_snapshot(created.id)
    events = await store.get_events(created.id)

    assert current.status in {
        RunStatus.COMPLETED,
        RunStatus.COMPLETED_WITH_WARNINGS,
    }
    assert runner.roles[0] == "ContextCompactorAgent"
    assert raw_snapshot is not None
    assert raw_snapshot["compaction_status"] == "completed"
    assert raw_snapshot["summary"]["source_run_ids"]
    assert current.context_stats.compaction_method == "model_structured_summary"
    assert current.context_stats.tokens_after <= 700
    assert any(event.type == "context.compacted" for event in events)


@pytest.mark.asyncio
async def test_invalid_context_summary_retries_with_failure_reason(tmp_path):
    class RepairingRunner(FakeRunner):
        compaction_prompts: list[str] = []

        async def ask(self, role, prompt):
            if role != "ContextCompactorAgent":
                return await super().ask(role, prompt)
            self.compaction_prompts.append(prompt)
            reply = await super().ask(role, prompt)
            if len(self.compaction_prompts) == 1:
                payload = json.loads(reply.text)
                payload["source_run_ids"] = ["run_fabricated"]
                return AgentReply(
                    text=json.dumps(payload, ensure_ascii=False),
                    prompt_tokens=20,
                    completion_tokens=10,
                )
            return reply

    config = build_settings(tmp_path).model_copy(
        update={
            "CONVERSATION_CONTEXT_MAX_INPUT_TOKENS": 600,
            "CONTEXT_RECENT_TURNS": 1,
            "CONTEXT_SUMMARY_MAX_ATTEMPTS": 2,
        },
    )
    store = RuntimeStore(config)
    for index in range(3):
        await store.create_run(
            RunRecord(
                user_id=7,
                status=RunStatus.COMPLETED,
                input=RunInput(
                    query=f"历史任务 {index}：" + "说明" * 100,
                    conversation_id=94,
                ),
                plugin=plugin_registry.get("interactive_vqa"),
                answer="待核验回答。" * 100,
            ),
        )
    runner = RepairingRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )

    created = await orchestrator.create(
        7,
        RunInput(
            query="继续了解青光眼",
            plugin_id="interactive_vqa",
            conversation_id=94,
        ),
    )
    current = await wait_for_terminal(store, created.id)
    events = await store.get_events(created.id)

    assert current.status in {
        RunStatus.COMPLETED,
        RunStatus.COMPLETED_WITH_WARNINGS,
    }
    assert len(runner.compaction_prompts) == 2
    assert "source_run_ids_mismatch" in runner.compaction_prompts[1]
    assert any(event.type == "context.compaction_retrying" for event in events)


@pytest.mark.asyncio
async def test_actual_over_budget_result_is_preserved_with_warning(tmp_path):
    class UsageSpikeRunner(FakeRunner):
        async def ask(self, role, prompt):
            reply = await super().ask(role, prompt)
            return reply.model_copy(update={"completion_tokens": 25_000}) if hasattr(reply, "model_copy") else AgentReply(
                text=reply.text,
                prompt_tokens=reply.prompt_tokens,
                completion_tokens=25_000,
            )

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: UsageSpikeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED_WITH_WARNINGS
    assert current.answer
    assert any("已保留生成结果" in warning for warning in current.warnings)


@pytest.mark.asyncio
async def test_persistent_primary_postprocessor_uses_validated_builtin_fallback(tmp_path):
    class StreamingRunner(FakeRunner):
        calls = 0

        async def ask_stream(self, role, prompt, on_delta):
            self.calls += 1
            evidence_ids = re.findall(r'"id": "(ev_[0-9a-f]+)"', prompt)
            citation = f" [{evidence_ids[0]}]" if evidence_ids else ""
            answer = f"青光眼相关信息需要结合完整眼科检查复核。{citation}"
            for character in answer:
                await on_delta(character)
            return AgentReply(
                text=answer,
                prompt_tokens=30,
                completion_tokens=20,
            )

    class BrokenCitationValidator(FakeCapabilityClients):
        @staticmethod
        def validate_citations(answer, evidence):
            raise RuntimeError("测试后处理失败")

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = StreamingRunner()
    orchestrator = RunOrchestrator(
        store,
        BrokenCitationValidator(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED_WITH_WARNINGS
    assert runner.calls == 3
    assert current.answer
    assert current.plan[-1].status == NodeStatus.COMPLETED
    assert any("内置确定性安全与引用校验" in item for item in current.warnings)
    events = await store.get_events(run.id)
    deltas = [
        event
        for event in events
        if event.type == "answer.delta"
    ]
    assert deltas
    assert len([event for event in events if event.type == "guardrail.retrying"]) == 6
    assert len([event for event in events if event.type == "agent.retrying"]) == 2
    assert len([event for event in events if event.type == "guardrail.fallback"]) == 1


@pytest.mark.asyncio
async def test_transient_postprocessing_failure_reuses_same_generated_answer(tmp_path):
    class CountingStreamingRunner(FakeRunner):
        calls = 0

        async def ask_stream(self, role, prompt, on_delta):
            self.calls += 1
            return AgentReply(
                text="青光眼相关信息需结合眼科检查。",
                prompt_tokens=30,
                completion_tokens=20,
            )

    class FlakyCitationValidator(FakeCapabilityClients):
        calls = 0

        @classmethod
        def validate_citations(cls, answer, evidence):
            cls.calls += 1
            if cls.calls == 1:
                raise RuntimeError("一次性后处理故障")
            return super().validate_citations(answer, evidence)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = CountingStreamingRunner()
    orchestrator = RunOrchestrator(
        store,
        FlakyCitationValidator(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    events = await store.get_events(run.id)

    assert current.status == RunStatus.COMPLETED
    assert current.answer == "青光眼相关信息需结合眼科检查。"
    assert runner.calls == 1
    assert FlakyCitationValidator.calls == 2
    assert len([event for event in events if event.type == "guardrail.retrying"]) == 1
    assert not any(event.type == "agent.retrying" for event in events)


@pytest.mark.asyncio
async def test_persistent_postprocessing_failure_rolls_back_and_regenerates_node(tmp_path):
    class CountingStreamingRunner(FakeRunner):
        calls = 0

        async def ask_stream(self, role, prompt, on_delta):
            self.calls += 1
            evidence_ids = re.findall(r'"id": "(ev_[0-9a-f]+)"', prompt)
            citation = f" [{evidence_ids[0]}]" if evidence_ids else ""
            return AgentReply(
                text=(
                    "青光眼相关信息需结合完整病史和系统眼科检查后复核"
                    f"（第 {self.calls} 次生成）。{citation}"
                ),
                prompt_tokens=30,
                completion_tokens=20,
            )

    class RecoversAfterRollbackValidator(FakeCapabilityClients):
        calls = 0

        @classmethod
        def validate_citations(cls, answer, evidence):
            cls.calls += 1
            if cls.calls <= 3:
                raise RuntimeError("当前生成轮次的后处理持续失败")
            return super().validate_citations(answer, evidence)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = CountingStreamingRunner()
    orchestrator = RunOrchestrator(
        store,
        RecoversAfterRollbackValidator(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    events = await store.get_events(run.id)

    assert current.status == RunStatus.COMPLETED
    assert "第 2 次生成" in current.answer
    assert runner.calls == 2
    assert RecoversAfterRollbackValidator.calls == 4
    assert len([event for event in events if event.type == "guardrail.retrying"]) == 2
    assert len([event for event in events if event.type == "agent.retrying"]) == 1
    assert next(event for event in events if event.type == "agent.retrying").visibility == "internal"


@pytest.mark.asyncio
async def test_invalid_citations_regenerate_terminal_node_before_publication(tmp_path):
    class CitationRepairRunner(FakeRunner):
        answer_calls = 0
        answer_prompts: list[str] = []

        async def ask_stream(self, role, prompt, on_delta):
            if role != "AnswerSynthesizer":
                return await super().ask(role, prompt)
            self.answer_calls += 1
            self.answer_prompts.append(prompt)
            evidence_ids = re.findall(r'"id": "(ev_[0-9a-f]+)"', prompt)
            citation = f" [{evidence_ids[0]}]" if self.answer_calls > 1 else ""
            return AgentReply(
                text=f"青光眼评估需结合完整病史和系统眼科检查后再复核。{citation}",
                prompt_tokens=30,
                completion_tokens=20,
            )

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = CitationRepairRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    events = await store.get_events(run.id)

    assert current.status == RunStatus.COMPLETED
    assert runner.answer_calls == 2
    assert "[ev_" in current.answer
    assert current.plan[-1].output["citation_validation"]["valid"] is True
    assert len([event for event in events if event.type == "agent.retrying"]) == 1
    assert "citation_coverage_failed" in runner.answer_prompts[1]
    assert "每个医学事实段落" in runner.answer_prompts[1]
    assert "claim_paragraph_count" in runner.answer_prompts[1]
    assert "至多 3 个短段落" in runner.answer_prompts[1]


@pytest.mark.asyncio
async def test_persistent_citation_coverage_failure_keeps_safe_answer_with_warning(
    tmp_path,
):
    class UncitedRunner(FakeRunner):
        answer_calls = 0

        async def ask_stream(self, role, prompt, on_delta):
            if role != "AnswerSynthesizer":
                return await super().ask(role, prompt)
            self.answer_calls += 1
            return AgentReply(
                text="青光眼通常需要结合病史和系统眼科检查进行评估。",
                prompt_tokens=30,
                completion_tokens=20,
            )

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = UncitedRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    events = await store.get_events(run.id)

    assert current.status == RunStatus.COMPLETED_WITH_WARNINGS
    assert current.answer == "青光眼通常需要结合病史和系统眼科检查进行评估。"
    assert runner.answer_calls == 2
    assert any("引用" in warning for warning in current.warnings)
    assert current.plan[-1].output["output_validation"]["degraded"] is True
    assert any(event.type == "citation.degraded" for event in events)


def test_node_context_is_dependency_scoped_and_compacts_before_limit(tmp_path):
    config = build_settings(tmp_path).model_copy(
        update={
            "CONTEXT_MAX_INPUT_TOKENS": 400,
            "CONTEXT_COMPRESSION_TRIGGER_RATIO": 0.82,
        }
    )
    clinical = PlanNode(
        id="clinical",
        title="临床状态",
        agent="ClinicalReasoningAgent",
        capability="main_model",
        status=NodeStatus.COMPLETED,
        output={
            "clinical_state": {
                "red_flags": [{"value": "突发视力下降", "source": "user"}],
                "medications": [{"value": "噻吗洛尔", "source": "user"}],
                "allergies": [{"value": "磺胺", "source": "user"}],
                "unresolved_questions": ["眼压是多少？"],
                "notes": "冗余描述" * 1000,
            }
        },
    )
    unrelated = PlanNode(
        id="documents",
        title="无关文档",
        agent="DocumentParser",
        capability="document_parser",
        status=NodeStatus.COMPLETED,
        output={"text": "不应传给本节点" * 1000},
    )
    evidence_item = EvidenceItem(
        title="测试证据",
        source="tests/fixture.md",
        excerpt="证据正文" * 1000,
        locator="第 1 段",
        verified=True,
    )
    evidence = PlanNode(
        id="evidence",
        title="证据",
        agent="EvidenceAgent",
        capability="medical_retrieval",
        status=NodeStatus.COMPLETED,
        output={"evidence": [evidence_item.model_dump(mode="json")]},
    )
    answer = PlanNode(
        id="answer",
        title="回答",
        agent="AnswerSynthesizer",
        capability="main_model",
        depends_on=["clinical", "evidence"],
        attempt=1,
    )
    run = RunRecord(
        id="run_node_context",
        user_id=7,
        input=RunInput(query="下一步怎么办"),
        plugin=plugin_registry.get("interactive_vqa"),
        plan=[clinical, unrelated, evidence, answer],
    )

    context = ExecutionContextManager(config).build(run, answer, token_limit=400)

    assert set(context.payload) == {"clinical", "evidence"}
    assert set(context.prompt_payload) == {"clinical", "evidence"}
    assert context.checkpoint.source_nodes == ["clinical", "evidence"]
    assert context.checkpoint.compressed is True
    assert context.checkpoint.tokens_after <= int(400 * 0.82)
    assert context.payload["clinical"]["clinical_state"]["notes"].endswith("冗余描述")
    restored_evidence = EvidenceItem.model_validate(
        context.payload["evidence"]["evidence"][0]
    )
    assert restored_evidence.retrieved_at == evidence_item.retrieved_at
    state = context.prompt_payload["clinical"]["clinical_state"]
    assert state["red_flags"]
    assert state["medications"]
    assert state["allergies"]
    assert state["unresolved_questions"]
    assert context.checkpoint.preserved_fields == [
        "clinical.red_flags",
        "clinical.medications",
        "clinical.allergies",
        "clinical.unresolved_questions",
        "evidence.id",
        "evidence.source",
        "evidence.locator",
        "evidence.verified",
        "evidence.source_status",
    ]


def test_context_fails_before_silently_truncating_critical_clinical_fields(
    tmp_path,
):
    config = build_settings(tmp_path).model_copy(
        update={
            "CONTEXT_MAX_INPUT_TOKENS": 256,
            "CONTEXT_COMPRESSION_TRIGGER_RATIO": 0.5,
        },
    )
    clinical = PlanNode(
        id="clinical",
        title="临床状态",
        agent="ClinicalReasoningAgent",
        capability="main_model",
        status=NodeStatus.COMPLETED,
        output={
            "clinical_state": {
                "red_flags": [
                    {
                        "value": f"必须保留的红旗症状 {index} " + "突发视力下降" * 12,
                        "source": "user",
                    }
                    for index in range(40)
                ],
                "medications": [],
                "allergies": [],
                "unresolved_questions": [],
            },
        },
    )
    answer = PlanNode(
        id="answer",
        title="回答",
        agent="AnswerSynthesizer",
        capability="main_model",
        depends_on=["clinical"],
        attempt=1,
    )
    run = RunRecord(
        id="run_critical_context_overflow",
        user_id=7,
        input=RunInput(query="继续"),
        plugin=plugin_registry.get("interactive_vqa"),
        plan=[clinical, answer],
    )

    with pytest.raises(BudgetExceeded, match="不能静默截断关键临床字段"):
        ExecutionContextManager(config).build(run, answer, token_limit=256)


@pytest.mark.asyncio
async def test_resume_preserves_completed_dependencies_and_requeues_failure_descendants(
    tmp_path,
):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=RunStatus.FAILED,
        input=RunInput(query="恢复报告"),
        plugin=plugin_registry.get("report_generator"),
        plan=[
            PlanNode(
                id="clinical",
                title="临床状态",
                agent="ClinicalReasoningAgent",
                capability="main_model",
                status=NodeStatus.FAILED,
                error_code="node_failed",
                output={"status": "failed", "detail": "测试失败"},
            ),
            PlanNode(
                id="evidence",
                title="证据",
                agent="EvidenceAgent",
                capability="medical_retrieval",
                status=NodeStatus.COMPLETED,
                output={"evidence": []},
            ),
            PlanNode(
                id="report",
                title="报告",
                agent="ReportAgent",
                capability="main_model",
                depends_on=["clinical", "evidence"],
                status=NodeStatus.SKIPPED,
                output={"status": "skipped"},
            ),
        ],
    )
    await store.create_run(run)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    orchestrator._spawn = lambda run_id: None

    resumed = await orchestrator.resume(run.id, 7)

    assert resumed.status == RunStatus.QUEUED
    assert resumed.plan[0].status == NodeStatus.PENDING
    assert resumed.plan[1].status == NodeStatus.COMPLETED
    assert resumed.plan[1].output == {"evidence": []}
    assert resumed.plan[2].status == NodeStatus.PENDING
    event = (await store.get_events(run.id))[-1]
    assert event.type == "run.resumed"
    assert event.data["preserved_nodes"] == ["evidence"]
    assert event.data["requeued_nodes"] == ["clinical", "report"]
    persisted = await store.get_run(run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.QUEUED
    assert persisted.attempt == 2
    assert persisted.plan[0].status == NodeStatus.PENDING
    assert persisted.plan[1].status == NodeStatus.COMPLETED


@pytest.mark.asyncio
async def test_stale_worker_cannot_overwrite_cancelled_terminal_state(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    running = RunRecord(
        user_id=7,
        status=RunStatus.RUNNING,
        input=RunInput(query="并发取消测试"),
        plugin=plugin_registry.get("core"),
    )
    await store.create_run(running)
    stale_worker = running.model_copy(deep=True)
    cancelled = await store.get_run(running.id)
    assert cancelled is not None
    cancelled.status = RunStatus.CANCELLED
    assert await store.save_run(cancelled)

    stale_worker.status = RunStatus.COMPLETED
    stale_worker.answer = "旧 worker 的迟到结果"
    assert not await store.save_run(stale_worker)
    persisted = await store.get_run(running.id)
    assert persisted is not None
    assert persisted.status == RunStatus.CANCELLED
    assert persisted.answer is None


@pytest.mark.asyncio
async def test_terminal_event_is_unique_per_attempt_not_per_run(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=RunStatus.FAILED,
        input=RunInput(query="重试后再次失败"),
        plugin=plugin_registry.get("core"),
    )
    await store.create_run(run)
    await store.append_event(RunEvent(
        run_id=run.id,
        trace_id=run.trace_id,
        type="run.failed",
        status=RunStatus.FAILED,
        public_summary="第一次失败",
        data={"attempt": 1},
    ))
    run.attempt = 2
    run.status = RunStatus.QUEUED
    assert await store.save_run(run, allow_resume=True)
    run.status = RunStatus.FAILED
    assert await store.save_run(run)
    await store.append_event(RunEvent(
        run_id=run.id,
        trace_id=run.trace_id,
        type="run.failed",
        status=RunStatus.FAILED,
        public_summary="第二次失败",
        data={"attempt": 2},
    ))

    failures = [
        event for event in await store.get_events(run.id)
        if event.type == "run.failed"
    ]
    assert [event.data["attempt"] for event in failures] == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.WAITING],
)
async def test_resume_rejects_nonrecoverable_states(tmp_path, status):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=status,
        input=RunInput(query="错误状态恢复"),
        plugin=plugin_registry.get("core"),
    )
    await store.create_run(run)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    orchestrator._spawn = lambda run_id: None

    with pytest.raises(ValueError, match="只有失败、已停止或服务中断"):
        await orchestrator.resume(run.id, 7)


@pytest.mark.asyncio
async def test_retry_feedback_and_delete_are_persistent_runtime_actions(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    original = await orchestrator.create(
        7,
        RunInput(query="你好", plugin_id="interactive_vqa"),
    )
    await wait_for_terminal(store, original.id)
    regenerated = await orchestrator.retry(original.id, 7)
    assert regenerated.id != original.id
    assert regenerated.input.regenerated_from == original.id
    rated = await orchestrator.record_feedback(original.id, 7, "up")
    assert rated.feedback == "up"
    await orchestrator.delete(original.id, 7)
    assert await store.get_run(original.id) is None


@pytest.mark.asyncio
async def test_localizer_waits_for_image_and_continues_after_input(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="请定位病灶", plugin_id="lesion_localizer"),
    )
    assert run.status == RunStatus.WAITING
    assert run.pending_question
    assert any(event.type == "run.question" for event in await store.get_events(run.id))

    image = tmp_path / "retina.png"
    image.write_bytes(b"image")
    attachment = AttachmentRecord(
        user_id=7,
        original_filename="retina.png",
        stored_path=str(image),
        mime_type="image/png",
        size=5,
        checksum="checksum",
        kind="image",
    )
    await store.save_attachment(attachment)
    resumed = await orchestrator.provide_input(
        run.id,
        7,
        "这是右眼眼底图",
        [attachment.id],
    )
    assert resumed.status == RunStatus.QUEUED
    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED
    assert any(node.id == "imaging" for node in current.plan)


@pytest.mark.asyncio
async def test_supplemental_input_rechecks_red_flags_before_execution(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="请定位病灶", plugin_id="lesion_localizer"),
    )
    image = tmp_path / "urgent.png"
    image.write_bytes(b"image")
    attachment = AttachmentRecord(
        user_id=7,
        original_filename="urgent.png",
        stored_path=str(image),
        mime_type="image/png",
        size=5,
        checksum="urgent",
        kind="image",
    )
    await store.save_attachment(attachment)
    orchestrator._spawn = lambda run_id: None

    resumed = await orchestrator.provide_input(
        run.id,
        7,
        "清洁剂刚溅进右眼，现在很痛并且看东西模糊",
        [attachment.id],
    )

    assert resumed.risk_level == RiskLevel.EMERGENCY
    assert resumed.clinical_state.red_flags
    events = await store.get_events(run.id)
    safety_sequence = next(
        event.sequence for event in events if event.type == "safety.alert"
    )
    plan_sequence = next(
        event.sequence for event in events if event.type == "plan.updated"
    )
    assert safety_sequence < plan_sequence


@pytest.mark.asyncio
async def test_emergency_alert_precedes_model_activity(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="清洁剂进入眼睛，突然看不清", plugin_id="interactive_vqa"),
    )
    await wait_for_terminal(store, run.id)
    events = await store.get_events(run.id)
    alert = next(event for event in events if event.type == "safety.alert")
    first_model_activity = next(
        event for event in events
        if event.type == "agent.started" and event.data.get("node_id")
    )
    assert alert.sequence < first_model_activity.sequence


@pytest.mark.asyncio
async def test_concurrent_events_receive_unique_monotonic_sequences(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run_id = "run_concurrent_events"
    await store.create_run(
        RunRecord(
            id=run_id,
            user_id=7,
            input=RunInput(query="并发事件测试"),
            plugin=plugin_registry.get("interactive_vqa"),
        )
    )
    await asyncio.gather(
        *(
                store.append_event(
                    RunEvent(
                        run_id=run_id,
                        trace_id="trace_concurrent_events",
                        type="tool.progress",
                        message=f"事件 {index}",
                        public_summary=f"事件 {index}",
                    )
                )
            for index in range(20)
        )
    )
    events = await store.get_events(run_id)
    assert [event.sequence for event in events] == list(range(1, 21))


@pytest.mark.asyncio
async def test_terminal_output_bundle_is_invisible_until_cas_succeeds(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=RunStatus.RUNNING,
        input=RunInput(query="原子发布测试"),
        plugin=plugin_registry.get("interactive_vqa"),
    )
    await store.create_run(run)
    intervention = RunIntervention(
        run_id=run.id,
        user_id=7,
        mode=InterventionMode.QUEUE,
        content="终态前加入的新要求",
        expected_attempt=1,
        client_message_id="terminal-race",
    )
    await store.create_intervention(intervention)

    run.answer = "OBSOLETE_OUTPUT_SENTINEL"
    run.status = RunStatus.COMPLETED
    obsolete_events = [
        RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="answer.delta",
            public_summary="正在生成回答",
            data={"attempt": 1, "output_revision": 1, "delta": run.answer},
        ),
        RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="answer.completed",
            public_summary="回答生成完成",
            data={"attempt": 1, "output_revision": 1, "answer": run.answer},
        ),
    ]
    obsolete_artifact = Artifact(
        run_id=run.id,
        user_id=7,
        type="report",
        title="不应发布",
        mime_type="text/markdown",
        content=run.answer,
    )
    committed = await store.commit_terminal(
        run,
        RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="run.completed",
            public_summary="任务执行完成",
            data={"attempt": 1},
        ),
        public_events=obsolete_events,
        artifacts=[obsolete_artifact],
    )

    assert committed is False
    assert await store.get_events(run.id) == []
    assert await store.list_artifacts(7, run.id) == []
    persisted = await store.get_run(run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.RUNNING
    assert persisted.answer is None

    await store.update_intervention_status(
        run.id,
        intervention.id,
        InterventionStatus.CANCELLED,
    )
    persisted.answer = "FINAL_OUTPUT"
    persisted.status = RunStatus.COMPLETED
    final_events = [
        RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="answer.delta",
            public_summary="正在生成回答",
            data={"attempt": 1, "output_revision": 1, "delta": persisted.answer},
        ),
        RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="answer.completed",
            public_summary="回答生成完成",
            data={"attempt": 1, "output_revision": 1, "answer": persisted.answer},
        ),
    ]
    final_artifact = obsolete_artifact.model_copy(
        update={"id": "art_final", "title": "最终报告", "content": persisted.answer},
    )
    assert await store.commit_terminal(
        persisted,
        RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="run.completed",
            public_summary="任务执行完成",
            data={"attempt": 1},
        ),
        public_events=final_events,
        artifacts=[final_artifact],
    )
    published_events = await store.get_events(run.id)
    assert [event.type for event in published_events] == [
        "answer.delta",
        "answer.completed",
        "run.completed",
    ]
    assert [event.sequence for event in published_events] == [1, 2, 3]
    assert [item.id for item in await store.list_artifacts(7, run.id)] == ["art_final"]


@pytest.mark.asyncio
async def test_terminal_conflict_with_cancelled_run_never_reschedules_or_publishes(tmp_path):
    class CancelWinsStore(RuntimeStore):
        async def commit_terminal(
            self,
            run,
            event,
            *,
            public_events=(),
            artifacts=(),
        ):
            if event.type == "run.completed":
                current = await self.get_run(run.id)
                assert current is not None
                current.status = RunStatus.CANCELLED
                cancelled = RunEvent(
                    run_id=current.id,
                    trace_id=current.trace_id,
                    type="run.cancelled",
                    public_summary="任务已取消",
                    data={
                        "attempt": current.attempt,
                        "execution_revision": current.execution_revision,
                    },
                )
                assert await super().commit_terminal(current, cancelled)
                return False
            return await super().commit_terminal(
                run,
                event,
                public_events=public_events,
                artifacts=artifacts,
            )

    config = build_settings(tmp_path)
    store = CancelWinsStore(config)
    runner = FakeRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="1+1等于多少？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.CANCELLED
    events = await store.get_events(run.id)
    cancelled_index = next(
        index for index, item in enumerate(events) if item.type == "run.cancelled"
    )
    assert events[cancelled_index + 1:] == []
    assert not any(item.type in {"answer.delta", "answer.completed"} for item in events)
    assert await store.list_artifacts(7, run.id) == []


@pytest.mark.asyncio
async def test_idempotency_key_reuses_run_and_answer_stream_is_replayable(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    payload = RunInput(
        query="你好",
        plugin_id="interactive_vqa",
        idempotency_key="same-client-request",
    )
    first = await orchestrator.create(7, payload)
    second = await orchestrator.create(7, payload)
    assert second.id == first.id
    await wait_for_terminal(store, first.id)
    events = await store.get_events(first.id)
    assert len([event for event in events if event.type == "run.created"]) == 1
    deltas = [event.data["delta"] for event in events if event.type == "answer.delta"]
    assert "".join(deltas)
    replay = await store.get_events(first.id, events[-2].sequence)
    assert all(event.sequence > events[-2].sequence for event in replay)


@pytest.mark.asyncio
async def test_restart_marks_running_run_interrupted_and_resume_requeues_node(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=RunStatus.RUNNING,
        input=RunInput(query="继续此前任务"),
        plugin=plugin_registry.get("interactive_vqa"),
        plan=[
            PlanNode(
                id="answer",
                title="生成回答",
                agent="AnswerSynthesizer",
                capability="main_model",
                status=NodeStatus.RUNNING,
            )
        ],
    )
    await store.create_run(run)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    await orchestrator.recover_interrupted()
    interrupted = await store.get_run(run.id)
    assert interrupted and interrupted.status == RunStatus.INTERRUPTED
    assert interrupted.plan[0].status == NodeStatus.PENDING
    assert any(event.type == "run.interrupted" for event in await store.get_events(run.id))

    resumed = await orchestrator.resume(run.id, 7)
    assert resumed.status == RunStatus.QUEUED
    completed = await wait_for_terminal(store, run.id)
    assert completed.status == RunStatus.COMPLETED
    assert completed.answer


@pytest.mark.asyncio
async def test_optional_imaging_failure_returns_partial_success(tmp_path):
    class ImagingUnavailable(FakeCapabilityClients):
        async def analyze_image(self, request):
            raise CapabilityUnavailable("medical_image_analysis", "测试中不可用")

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        ImagingUnavailable(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(
            query="结合图像评估下一步",
            plugin_id="aux_diagnosis",
            image_paths=[str(tmp_path / "eye.png")],
        ),
    )
    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED_WITH_WARNINGS
    assert current.answer
    assert current.warnings == ["分析眼科影像未完成"]


@pytest.mark.asyncio
async def test_required_node_failure_replays_hidden_execution_with_feedback(tmp_path):
    class ImagingFailsOnce(FakeCapabilityClients):
        calls = 0

        async def analyze_image(self, request):
            self.calls += 1
            if self.calls == 1:
                raise CapabilityUnavailable("sub_model", "首次请求超时")
            assert "本影像步骤此前未完成" in request.question
            assert "capability_unavailable" in request.question
            return await super().analyze_image(request)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    image = tmp_path / "eye.png"
    image.write_bytes(b"image")
    clients = ImagingFailsOnce()
    orchestrator = RunOrchestrator(
        store,
        clients,
        config,
        runner_factory=lambda active_clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(
            query="请定位、评估并生成报告",
            image_paths=[str(image)],
            requested_plugins=[
                "lesion_localizer",
                "aux_diagnosis",
                "report_generator",
            ],
        ),
    )

    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED
    assert current.execution_revision == 2
    assert clients.calls == 2
    assert all(node.status == NodeStatus.COMPLETED for node in current.plan if node.required)
    imaging = next(node for node in current.plan if node.id == "imaging")
    assert imaging.attempt == 2
    assert imaging.recovery_feedback[-1]["issues"] == ["capability_unavailable"]
    events = await store.get_events(run.id)
    retry_event = next(event for event in events if event.type == "agent.retrying")
    assert retry_event.visibility == "internal"
    assert retry_event.data["execution_revision"] == 2


@pytest.mark.asyncio
async def test_repeated_cancel_emits_exactly_one_terminal_event(tmp_path):
    class SlowRunner(FakeRunner):
        async def ask(self, role, prompt):
            await asyncio.sleep(5)
            return await super().ask(role, prompt)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: SlowRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="你好", plugin_id="interactive_vqa"),
    )
    await asyncio.sleep(0.02)
    first = await orchestrator.cancel(run.id, 7)
    second = await orchestrator.cancel(run.id, 7)
    await asyncio.sleep(0.02)
    assert first.status == second.status == RunStatus.CANCELLED
    events = await store.get_events(run.id)
    assert len([event for event in events if event.type == "run.cancelled"]) == 1


@pytest.mark.asyncio
async def test_queued_intervention_is_applied_fifo_at_next_node_boundary(tmp_path):
    class BoundaryRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.prompts: list[str] = []

        async def ask(self, role, prompt):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                self.started.set()
                await self.release.wait()
            return await super().ask(role, prompt)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = BoundaryRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="1+1等于多少？", plugin_id="interactive_vqa"),
    )
    await asyncio.wait_for(runner.started.wait(), timeout=1)
    queued = await orchestrator.intervene(
        run.id,
        7,
        mode=InterventionMode.QUEUE,
        content="请同时说明计算过程，并保持两句话以内。",
        attachment_ids=[],
        expected_attempt=1,
        client_message_id="queue-1",
    )
    assert queued.interventions[-1].status == InterventionStatus.QUEUED
    runner.release.set()

    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED
    assert current.attempt == 1
    assert current.execution_revision == 2
    assert len(runner.prompts) == 2
    assert "请同时说明计算过程" in runner.prompts[-1]
    assert "QueuedUserRequirement" in runner.prompts[-1]
    assert current.interventions[-1].status == InterventionStatus.APPLIED
    events = await store.get_events(run.id)
    assert [event.type for event in events].count("user.intervention_applied") == 1


@pytest.mark.asyncio
async def test_queued_intervention_can_be_cancelled_before_boundary(tmp_path):
    class BoundaryRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def ask(self, role, prompt):
            self.calls += 1
            self.started.set()
            await self.release.wait()
            return await super().ask(role, prompt)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = BoundaryRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="1+1等于多少？", plugin_id="interactive_vqa"),
    )
    await asyncio.wait_for(runner.started.wait(), timeout=1)
    queued = await orchestrator.intervene(
        run.id,
        7,
        mode=InterventionMode.QUEUE,
        content="这一条稍后取消",
        attachment_ids=[],
        expected_attempt=1,
        client_message_id="queue-cancel",
    )
    intervention_id = queued.interventions[-1].id
    cancelled = await orchestrator.cancel_intervention(run.id, intervention_id, 7)
    assert cancelled.interventions[-1].status == InterventionStatus.CANCELLED
    runner.release.set()

    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED
    assert runner.calls == 1
    assert "这一条稍后取消" not in current.input.query


@pytest.mark.asyncio
async def test_intervention_rejects_stale_attempt_without_mutating_run(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=RunStatus.RUNNING,
        input=RunInput(query="正在执行"),
        plugin=plugin_registry.get("interactive_vqa"),
        attempt=2,
    )
    await store.create_run(run)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )

    with pytest.raises(ValueError, match="第 2 次执行"):
        await orchestrator.intervene(
            run.id,
            7,
            mode=InterventionMode.QUEUE,
            content="来自旧页面的要求",
            attachment_ids=[],
            expected_attempt=1,
            client_message_id="stale-attempt",
        )
    current = await store.get_run(run.id)
    assert current and current.interventions == []
    assert current.input.query == "正在执行"


@pytest.mark.asyncio
async def test_interrupt_intervention_resumes_with_reason_and_new_attempt(tmp_path):
    class InterruptibleRunner(FakeRunner):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.prompts: list[str] = []

        async def ask(self, role, prompt):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                self.started.set()
                await asyncio.sleep(30)
            return await super().ask(role, prompt)

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    runner = InterruptibleRunner()
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: runner,
    )
    run = await orchestrator.create(
        7,
        RunInput(query="1+1等于多少？", plugin_id="interactive_vqa"),
    )
    await asyncio.wait_for(runner.started.wait(), timeout=1)
    resumed = await orchestrator.intervene(
        run.id,
        7,
        mode=InterventionMode.INTERRUPT,
        content="改为回答 2+2，并解释为什么之前的任务被替换。",
        attachment_ids=[],
        expected_attempt=1,
        client_message_id="interrupt-1",
    )
    assert resumed.attempt == 2
    assert resumed.execution_revision == 2
    assert resumed.status in {RunStatus.QUEUED, RunStatus.RUNNING}

    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED
    assert current.attempt == 2
    assert current.execution_revision == 2
    assert len(runner.prompts) >= 2
    assert all("改为回答 2+2" in prompt for prompt in runner.prompts[1:])
    assert any("UserInterrupted" in prompt for prompt in runner.prompts[1:])
    event_types = [event.type for event in await store.get_events(run.id)]
    assert "run.interrupted" in event_types
    assert "run.resumed" in event_types
    assert current.interventions[-1].status == InterventionStatus.APPLIED


@pytest.mark.asyncio
async def test_conversation_resource_deletion_cascades_files_runs_and_artifacts(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    run = RunRecord(
        user_id=7,
        status=RunStatus.COMPLETED,
        input=RunInput(query="测试", conversation_id=88),
        plugin=plugin_registry.get("interactive_vqa"),
    )
    await store.create_run(run)
    await store.append_event(
        RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="run.completed",
            message="完成",
            public_summary="完成",
        )
    )
    artifact = Artifact(
        run_id=run.id,
        user_id=7,
        type="document",
        title="测试产物",
        mime_type="application/octet-stream",
    )
    await store.save_artifact(artifact, binary=b"artifact")
    upload = tmp_path / "private-upload.png"
    upload.write_bytes(b"upload")
    attachment = AttachmentRecord(
        user_id=7,
        conversation_id=88,
        original_filename="private-upload.png",
        stored_path=str(upload),
        mime_type="image/png",
        size=6,
        checksum="checksum",
        kind="image",
    )
    await store.save_attachment(attachment)

    await store.delete_conversation_resources(7, 88)

    assert await store.get_run(run.id) is None
    assert await store.get_artifact(artifact.id) is None
    assert await store.get_attachment(attachment.id) is None
    assert not upload.exists()


@pytest.mark.asyncio
async def test_standard_run_completes_with_evidence_without_forced_report(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="右眼视物模糊，需要评估", plugin_id="aux_diagnosis"),
    )
    for _ in range(100):
        current = await store.get_run(run.id)
        if current and current.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
            break
        await asyncio.sleep(0.01)
    assert current is not None
    assert current.status == RunStatus.COMPLETED
    assert "当前资料支持以下初步评估" in (current.answer or "")
    assert "不能替代医生诊断" not in (current.answer or "")
    assert current.clinical_state.unresolved_questions
    assessment = next(node for node in current.plan if node.id == "assessment")
    assert assessment.output
    assert assessment.output["confidence_semantics"] == "qualitative_support_not_probability"
    assert assessment.output["differentials"][0]["confidence"] == "low"
    artifacts = await store.list_artifacts(7, run.id)
    assert artifacts == []
    events = await store.get_events(run.id)
    assert any(event.type == "plan.created" for event in events)
    assert any(event.type == "retrieval.result" for event in events)
    assert any(event.type == "run.completed" for event in events)


@pytest.mark.asyncio
async def test_report_request_creates_artifact(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="请生成一份简短眼科报告", plugin_id="report_generator"),
    )
    for _ in range(100):
        current = await store.get_run(run.id)
        if current and current.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
            break
        await asyncio.sleep(0.01)
    assert current is not None
    assert current.status == RunStatus.COMPLETED
    assert len(await store.list_artifacts(7, run.id)) == 1


@pytest.mark.asyncio
async def test_emergency_run_has_critic_and_banner(tmp_path):
    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        FakeCapabilityClients(),
        config,
        runner_factory=lambda clients: FakeRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="清洁剂进入眼睛，突然看不清", plugin_id="aux_diagnosis"),
    )
    assert run.risk_level == "emergency"
    assert any(node.id == "critic" for node in run.plan)
    for _ in range(100):
        current = await store.get_run(run.id)
        if current and current.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
            break
        await asyncio.sleep(0.01)
    assert current is not None
    assert current.status == RunStatus.COMPLETED
    assert "眼科急诊" in (current.answer or "")

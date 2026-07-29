import asyncio

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.domain.models import (
    Artifact,
    AttachmentRecord,
    NodeStatus,
    PlanNode,
    RiskLevel,
    RunEvent,
    RunInput,
    RunRecord,
    RunStatus,
)
from app.plugins.registry import plugin_registry
from app.runtime.agents import AgentReply
from app.runtime.context import ConversationContextManager
from app.runtime.errors import CapabilityUnavailable
from app.runtime.orchestrator import (
    RunOrchestrator,
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
    assert "定位校验结果" in cleaned
    assert "未在原图补画边界" in cleaned
    assert "当前资料支持程度" in cleaned


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

        async def retrieve_medical_evidence(self, query, top_k=6):
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
    assert run.budget.max_tokens == min(32_000, config.RUN_MAX_TOKENS)
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

        async def retrieve_medical_evidence(self, query, top_k=6):
            self.queries.append(query)
            return await super().retrieve_medical_evidence(query, top_k)

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
            "CONTEXT_MAX_INPUT_TOKENS": 800,
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

    snapshot = await ConversationContextManager(store, config).build(
        run_id="run_context_test",
        user_id=7,
        run_input=RunInput(query="继续", conversation_id=91),
    )

    assert snapshot is not None
    assert snapshot.stats.source_turns == 6
    assert snapshot.stats.retained_turns == 2
    assert snapshot.stats.summarized_turns == 4
    assert snapshot.stats.tokens_after <= 800
    assert "第 6 轮问题" in snapshot.prompt_text
    assert "较早对话压缩摘要" in snapshot.prompt_text
    assert "历史助手回答不是临床事实" in snapshot.prompt_text


@pytest.mark.asyncio
async def test_actual_over_budget_result_is_preserved_with_warning(tmp_path):
    class UsageSpikeRunner(FakeRunner):
        async def ask(self, role, prompt):
            reply = await super().ask(role, prompt)
            return reply.model_copy(update={"completion_tokens": 13_000}) if hasattr(reply, "model_copy") else AgentReply(
                text=reply.text,
                prompt_tokens=reply.prompt_tokens,
                completion_tokens=13_000,
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
async def test_streamed_answer_survives_postprocessing_failure(tmp_path):
    class StreamingRunner(FakeRunner):
        async def ask_stream(self, role, prompt, on_delta):
            for character in "青光眼是一组进行性视神经病变。":
                await on_delta(character)
            return AgentReply(
                text="青光眼是一组进行性视神经病变。",
                prompt_tokens=30,
                completion_tokens=20,
            )

    class BrokenCitationValidator(FakeCapabilityClients):
        @staticmethod
        def validate_citations(answer, evidence):
            raise RuntimeError("测试后处理失败")

    config = build_settings(tmp_path)
    store = RuntimeStore(config)
    orchestrator = RunOrchestrator(
        store,
        BrokenCitationValidator(),
        config,
        runner_factory=lambda clients: StreamingRunner(),
    )
    run = await orchestrator.create(
        7,
        RunInput(query="什么是青光眼？", plugin_id="interactive_vqa"),
    )
    current = await wait_for_terminal(store, run.id)
    assert current.status == RunStatus.COMPLETED_WITH_WARNINGS
    assert current.answer == "青光眼是一组进行性视神经病变。"
    assert current.plan[-1].output and current.plan[-1].output["partial"] is True
    deltas = [
        event
        for event in await store.get_events(run.id)
        if event.type == "answer.delta"
    ]
    assert len(deltas) == 1


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
    assert "不能替代医生诊断" in (current.answer or "")
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

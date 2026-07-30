from app.domain.models import (
    NodeStatus,
    PlanNode,
    RunEvent,
    RunInput,
    RunRecord,
    RunStatus,
)
from app.plugins.registry import plugin_registry
from app.runtime.public_projection import public_event_payload, public_run_record


def _run_with_private_state() -> RunRecord:
    return RunRecord(
        user_id=7,
        status=RunStatus.FAILED,
        input=RunInput(
            query="测试公开投影",
            image_paths=["/private/upload.png"],
        ),
        plugin=plugin_registry.get("interactive_vqa"),
        plan=[
            PlanNode(
                id="draft",
                title="候选回答",
                agent="DraftAgent",
                capability="main_model",
                status=NodeStatus.COMPLETED,
                output={"answer": "PRIVATE_DRAFT_SENTINEL"},
                recovery_feedback=[{"issues": ["PRIVATE_FEEDBACK_SENTINEL"]}],
            ),
            PlanNode(
                id="answer",
                title="生成回答",
                agent="AnswerSynthesizer",
                capability="main_model",
                status=NodeStatus.FAILED,
                output={
                    "detail": "PRIVATE_EXCEPTION_SENTINEL",
                    "output_validation": {"issues": ["PRIVATE_VALIDATION_SENTINEL"]},
                },
                error_code="citation_coverage_failed",
                recovery_feedback=[{"issues": ["PRIVATE_FEEDBACK_SENTINEL"]}],
            ),
        ],
        error_code="citation_coverage_failed",
        error_message="PRIVATE_EXCEPTION_SENTINEL",
        warnings=["PRIVATE_WARNING_SENTINEL"],
    )


def test_public_run_projection_removes_retry_and_validation_internals():
    run = _run_with_private_state()
    run.input.query += (
        "\n\n【用户在执行期间追加的要求；后续步骤必须遵循】"
        "\n1. PRIVATE_DIRECTIVE_SENTINEL"
    )
    payload = public_run_record(run).model_dump_json()

    for sentinel in (
        "PRIVATE_DRAFT_SENTINEL",
        "PRIVATE_FEEDBACK_SENTINEL",
        "PRIVATE_EXCEPTION_SENTINEL",
        "PRIVATE_VALIDATION_SENTINEL",
        "PRIVATE_WARNING_SENTINEL",
        "citation_coverage_failed",
        "/private/upload.png",
        "PRIVATE_DIRECTIVE_SENTINEL",
    ):
        assert sentinel not in payload
    public = public_run_record(_run_with_private_state())
    assert public.plan == []
    assert public.error_message == "本次任务未能完成，可以从检查点重试。"


def test_public_plan_event_does_not_expose_node_input_or_recovery_feedback():
    run = _run_with_private_state()
    event = RunEvent(
        run_id=run.id,
        trace_id=run.trace_id,
        type="plan.updated",
        public_summary="计划已更新",
        data={"attempt": 2, "nodes": [node.model_dump(mode="json") for node in run.plan]},
    )

    payload = public_event_payload(event)
    assert payload is not None
    serialized = str(payload)
    assert "PRIVATE_DRAFT_SENTINEL" not in serialized
    assert "PRIVATE_FEEDBACK_SENTINEL" not in serialized
    assert "PRIVATE_EXCEPTION_SENTINEL" not in serialized
    assert payload["data"]["nodes"] == []


def test_public_event_projection_filters_internal_events_and_failure_details():
    run = _run_with_private_state()
    internal = RunEvent(
        run_id=run.id,
        trace_id=run.trace_id,
        type="guardrail.retrying",
        visibility="internal",
        public_summary="PRIVATE_RETRY_SENTINEL",
        data={"issues": ["PRIVATE_VALIDATION_SENTINEL"]},
    )
    assert public_event_payload(internal) is None

    failed = RunEvent(
        run_id=run.id,
        trace_id=run.trace_id,
        type="tool.failed",
        public_summary="生成回答失败：PRIVATE_EXCEPTION_SENTINEL",
        data={
            "attempt": 1,
            "node_id": "answer",
            "issues": ["PRIVATE_VALIDATION_SENTINEL"],
        },
        error_code="citation_coverage_failed",
    )
    assert public_event_payload(failed) is None


def test_public_event_projection_hides_private_node_lifecycle():
    run = _run_with_private_state()
    for node_id, agent in (("draft", "DraftAgent"), ("critic", "CriticAgent")):
        event = RunEvent(
            run_id=run.id,
            trace_id=run.trace_id,
            type="agent.completed",
            public_summary=f"{agent} 已完成",
            data={
                "attempt": 1,
                "execution_revision": 1,
                "node_id": node_id,
                "agent": agent,
            },
        )
        assert public_event_payload(event) is None

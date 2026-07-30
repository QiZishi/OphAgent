"""Allowlisted public projections for durable Run state and events.

The runtime persistence model intentionally contains retry feedback, context
checkpoints and intermediate validation details.  Those fields are useful for
recovery and audit, but they are not part of the user-facing protocol.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import (
    ContextStats,
    InterventionMode,
    InterventionStatus,
    NodeStatus,
    PlanNode,
    RiskLevel,
    RunEvent,
    RunRecord,
    RunStatus,
    TaskRoute,
)

_PRIVATE_NODE_IDS = {"draft", "critic"}
_HIDDEN_NODE_STATUSES = {
    NodeStatus.FAILED,
    NodeStatus.SKIPPED,
    NodeStatus.CANCELLED,
}
_PUBLIC_NODE_OUTPUT_KEYS = {
    "summary",
    "observations",
    "limitations",
    "regions",
    "region_count",
    "differentials",
    "confidence_semantics",
    "transcripts",
    "evidence",
}
_PRIVATE_DATA_KEYS = {
    "candidate_answer",
    "citation_validation",
    "context_checkpoint",
    "draft",
    "failure_feedback",
    "issues",
    "output_validation",
    "recovery_feedback",
    "required_corrections",
}
_INTERVENTION_DIRECTIVE = "\n\n【用户在执行期间追加的要求；后续步骤必须遵循】"


class PublicRunInput(BaseModel):
    query: str
    plugin_id: str
    conversation_id: int | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    requested_plugins: list[str] = Field(default_factory=list)
    requested_skills: list[str] = Field(default_factory=list)
    mode: str = "auto"
    regenerated_from: str | None = None


class PublicPlanNode(BaseModel):
    id: str
    title: str
    agent: str
    capability: str
    depends_on: list[str] = Field(default_factory=list)
    status: NodeStatus
    required: bool = True
    attempt: int = 0
    output: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PublicRunIntervention(BaseModel):
    id: str
    run_id: str
    mode: InterventionMode
    content: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)
    expected_attempt: int
    client_message_id: str
    status: InterventionStatus
    created_at: datetime
    applied_at: datetime | None = None
    cancelled_at: datetime | None = None


class PublicRunBudget(BaseModel):
    max_model_calls: int
    max_tokens: int
    model_calls: int
    prompt_tokens: int
    completion_tokens: int


class PublicContextStats(BaseModel):
    source_turns: int
    retained_turns: int
    summarized_turns: int
    tokens_before: int
    tokens_after: int
    cache_hit: bool
    compaction_status: str
    compaction_method: str
    compaction_attempts: int

    @classmethod
    def from_internal(cls, stats: ContextStats) -> PublicContextStats:
        return cls.model_validate(stats.model_dump(exclude={"source_hash"}))


class PublicRunRecord(BaseModel):
    id: str
    trace_id: str
    status: RunStatus
    risk_level: RiskLevel
    route: TaskRoute | None = None
    input: PublicRunInput
    plan: list[PublicPlanNode] = Field(default_factory=list)
    answer: str | None = None
    feedback: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    pending_question: str | None = None
    pending_approval: dict[str, Any] | None = None
    user_inputs: list[str] = Field(default_factory=list)
    interventions: list[PublicRunIntervention] = Field(default_factory=list)
    attempt: int
    execution_revision: int
    budget: PublicRunBudget
    context_stats: PublicContextStats
    created_at: datetime
    updated_at: datetime


def public_plan_node(node: PlanNode) -> dict[str, Any]:
    """Return the small, stable node surface the UI is allowed to inspect."""

    output: dict[str, Any] | None = None
    if (
        node.status == NodeStatus.COMPLETED
        and node.id not in _PRIVATE_NODE_IDS
        and node.agent != "CriticAgent"
        and isinstance(node.output, dict)
    ):
        output = {
            key: value
            for key, value in node.output.items()
            if key in _PUBLIC_NODE_OUTPUT_KEYS
        } or None
    return {
        "id": node.id,
        "title": node.title,
        "agent": node.agent,
        "capability": node.capability,
        "depends_on": [
            dependency
            for dependency in node.depends_on
            if dependency not in _PRIVATE_NODE_IDS
        ],
        "status": node.status.value,
        "required": node.required,
        "attempt": node.attempt,
        "output": output,
        "started_at": node.started_at.isoformat() if node.started_at else None,
        "completed_at": node.completed_at.isoformat() if node.completed_at else None,
    }


def public_plan_nodes(nodes: list[PlanNode]) -> list[dict[str, Any]]:
    return [
        public_plan_node(node)
        for node in nodes
        if node.id not in _PRIVATE_NODE_IDS
        and node.status not in _HIDDEN_NODE_STATUSES
    ]


def public_run_record(run: RunRecord) -> PublicRunRecord:
    """Build the user protocol from an explicit top-level allowlist."""

    return PublicRunRecord(
        id=run.id,
        trace_id=run.trace_id,
        status=run.status,
        risk_level=run.risk_level,
        route=run.route,
        input=PublicRunInput(
            query=run.input.query.split(_INTERVENTION_DIRECTIVE, 1)[0],
            plugin_id=run.input.plugin_id,
            conversation_id=run.input.conversation_id,
            attachment_ids=list(run.input.attachment_ids),
            requested_plugins=list(run.input.requested_plugins),
            requested_skills=list(run.input.requested_skills),
            mode=run.input.mode,
            regenerated_from=run.input.regenerated_from,
        ),
        plan=[
            PublicPlanNode.model_validate(public_plan_node(node))
            for node in run.plan
            if node.id not in _PRIVATE_NODE_IDS
            and node.status not in _HIDDEN_NODE_STATUSES
        ],
        answer=run.answer,
        feedback=run.feedback,
        error_code="run_failed" if run.status == RunStatus.FAILED else None,
        error_message=(
            "本次任务未能完成，可以从检查点重试。"
            if run.status == RunStatus.FAILED
            else None
        ),
        pending_question=run.pending_question,
        pending_approval=run.pending_approval,
        user_inputs=list(run.user_inputs),
        interventions=[
            PublicRunIntervention.model_validate(
                item.model_dump(exclude={"user_id"}),
            )
            for item in run.interventions
        ],
        attempt=run.attempt,
        execution_revision=run.execution_revision,
        budget=PublicRunBudget.model_validate(run.budget.model_dump()),
        context_stats=PublicContextStats.from_internal(run.context_stats),
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def public_event_payload(event: RunEvent) -> dict[str, Any] | None:
    """Return one sanitized public event, or ``None`` for internal events."""

    if event.visibility != "public":
        return None
    node_id = str(event.data.get("node_id") or "")
    agent = str(event.data.get("agent") or "")
    if node_id in _PRIVATE_NODE_IDS or agent in {"DraftAgent", "CriticAgent"}:
        return None
    if event.type == "tool.failed":
        return None
    payload = event.model_dump(mode="json")
    data = _sanitize_data(event.data)
    if isinstance(data.get("source_nodes"), list):
        data["source_nodes"] = [
            item for item in data["source_nodes"]
            if str(item) not in _PRIVATE_NODE_IDS
        ]
    if event.type in {"plan.created", "plan.updated"}:
        nodes = event.data.get("nodes")
        data["nodes"] = [
            public_plan_node(PlanNode.model_validate(node))
            for node in nodes or []
            if str(node.get("id") or "") not in _PRIVATE_NODE_IDS
            and PlanNode.model_validate(node).status not in _HIDDEN_NODE_STATUSES
        ]
    payload["data"] = data
    return payload


def _sanitize_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_data(item)
            for key, item in value.items()
            if key not in _PRIVATE_DATA_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_data(item) for item in value]
    return value

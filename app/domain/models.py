"""Stable domain contracts shared by runtime, API and UI."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    WAITING = "waiting_for_user"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class RiskLevel(StrEnum):
    ROUTINE = "routine"
    COMPLEX = "complex"
    HIGH = "high"
    EMERGENCY = "emergency"


class TaskIntent(StrEnum):
    QUICK_ANSWER = "quick_answer"
    CLINICAL_QNA = "clinical_qna"
    IMAGE_ANALYSIS = "image_analysis"
    AUX_ASSESSMENT = "aux_assessment"
    REPORT_GENERATION = "report_generation"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"


class TaskComplexity(StrEnum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class TaskRoute(BaseModel):
    intent: TaskIntent
    complexity: TaskComplexity
    risk: RiskLevel
    selected_plugins: list[str] = Field(default_factory=list)
    needs_clinical_state: bool = False
    needs_retrieval: bool = False
    needs_imaging: bool = False
    needs_report: bool = False
    reason_code: str


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: f"ev_{uuid4().hex}")
    title: str
    source: str
    excerpt: str
    locator: str | None = None
    published_at: str | None = None
    region: str | None = None
    institution: str | None = None
    version: str | None = None
    population: str | None = None
    source_status: Literal["current", "expired", "superseded", "unknown"] = "unknown"
    superseded_by: str | None = None
    visual_path: str | None = None
    score: float = Field(default=0.0, ge=0.0)
    source_type: Literal["guideline", "record", "web", "knowledge_graph", "user"] = "guideline"
    retrieved_at: datetime = Field(default_factory=utc_now)
    verified: bool = False


class ClinicalFact(BaseModel):
    value: str
    source: str
    confirmed: bool = False
    observed_at: datetime | None = None


class DifferentialDiagnosis(BaseModel):
    name: str
    supporting_evidence: list[str] = Field(default_factory=list)
    opposing_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class ClinicalState(BaseModel):
    chief_complaint: str | None = None
    timeline: list[ClinicalFact] = Field(default_factory=list)
    positives: list[ClinicalFact] = Field(default_factory=list)
    negatives: list[ClinicalFact] = Field(default_factory=list)
    examinations: list[ClinicalFact] = Field(default_factory=list)
    medications: list[ClinicalFact] = Field(default_factory=list)
    allergies: list[ClinicalFact] = Field(default_factory=list)
    red_flags: list[ClinicalFact] = Field(default_factory=list)
    differentials: list[DifferentialDiagnosis] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


class NodeContextCheckpoint(BaseModel):
    """Content-free metadata proving which context a node consumed."""

    id: str
    node_id: str
    attempt: int = Field(default=1, ge=1)
    source_nodes: list[str] = Field(default_factory=list)
    source_hash: str
    tokens_before: int = Field(default=0, ge=0)
    tokens_after: int = Field(default=0, ge=0)
    token_limit: int = Field(default=0, ge=0)
    compressed: bool = False
    compression_reason: str | None = None
    preserved_fields: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class PlanNode(BaseModel):
    id: str
    title: str
    agent: str
    capability: str
    depends_on: list[str] = Field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    required: bool = True
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error_code: str | None = None
    attempt: int = Field(default=0, ge=0)
    context_checkpoint: NodeContextCheckpoint | None = None
    recovery_feedback: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class PluginManifest(BaseModel):
    id: Literal[
        "core",
        "interactive_vqa",
        "lesion_localizer",
        "aux_diagnosis",
        "report_generator",
        "knowledge_base",
    ]
    version: str
    description: str
    accepted_inputs: list[str]
    produced_artifacts: list[str]
    required_capabilities: list[str]
    skills: list[str]
    tools: list[str]
    agent_graph: list[str]
    context_policy: dict[str, Any]
    budget_policy: dict[str, Any]
    safety_policy: dict[str, Any]
    activation: dict[str, Any] = Field(default_factory=dict)
    latency_budget: dict[str, int] = Field(default_factory=dict)
    fallback: dict[str, str] = Field(default_factory=dict)
    permission: str = "user"
    required_nodes: list[str] = Field(default_factory=list)
    optional_nodes: list[str] = Field(default_factory=list)


class RunBudget(BaseModel):
    max_model_calls: int = Field(default=12, ge=1, le=30)
    max_tokens: int = Field(default=32_000, ge=1000, le=200_000)
    max_seconds: int = Field(default=300, ge=10, le=1800)
    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    token_usage_estimated: bool = False
    reserved_output_tokens: int = Field(default=800, ge=0)


class ContextStats(BaseModel):
    """Content-free audit metadata for a run's conversation context."""

    source_turns: int = Field(default=0, ge=0)
    retained_turns: int = Field(default=0, ge=0)
    summarized_turns: int = Field(default=0, ge=0)
    tokens_before: int = Field(default=0, ge=0)
    tokens_after: int = Field(default=0, ge=0)
    cache_hit: bool = False
    source_hash: str | None = None


class RunInput(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    plugin_id: str = "core"
    conversation_id: int | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    document_paths: list[str] = Field(default_factory=list)
    audio_paths: list[str] = Field(default_factory=list)
    attachment_ids: list[str] = Field(default_factory=list)
    requested_plugins: list[str] = Field(default_factory=list)
    requested_skills: list[str] = Field(default_factory=list)
    mode: Literal["auto", "quick", "standard", "deep"] = "auto"
    idempotency_key: str | None = Field(default=None, max_length=128)
    regenerated_from: str | None = None
    clinical_state: ClinicalState = Field(default_factory=ClinicalState)


class RunRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"run_{uuid4().hex}")
    user_id: int
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    status: RunStatus = RunStatus.QUEUED
    input: RunInput
    plugin: PluginManifest
    risk_level: RiskLevel = RiskLevel.ROUTINE
    route: TaskRoute | None = None
    plan: list[PlanNode] = Field(default_factory=list)
    clinical_state: ClinicalState = Field(default_factory=ClinicalState)
    budget: RunBudget = Field(default_factory=RunBudget)
    context_snapshot_id: str | None = None
    context_stats: ContextStats = Field(default_factory=ContextStats)
    answer: str | None = None
    feedback: Literal["up", "down"] | None = None
    error_code: str | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    pending_question: str | None = None
    pending_approval: dict[str, Any] | None = None
    user_inputs: list[str] = Field(default_factory=list)
    attempt: int = 1
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RunEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    sequence: int = Field(default=0, ge=0)
    run_id: str
    trace_id: str
    type: str
    parent_event_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    status: str | None = None
    public_summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: int | None = None
    error_code: str | None = None


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: f"art_{uuid4().hex}")
    run_id: str
    user_id: int
    type: Literal["report", "image", "table", "citation", "document", "audio"]
    title: str
    mime_type: str
    path: str | None = None
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class AttachmentRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"att_{uuid4().hex}")
    user_id: int
    conversation_id: int | None = None
    message_id: int | None = None
    original_filename: str
    stored_path: str
    mime_type: str
    size: int = Field(ge=0)
    checksum: str
    kind: Literal["image", "document", "audio"]
    created_at: datetime = Field(default_factory=utc_now)


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"mem_{uuid4().hex}")
    user_id: int
    category: Literal[
        "preference",
        "history",
        "medication",
        "allergy",
        "follow_up",
        "workspace",
    ]
    content: str
    source: str
    kind: Literal["semantic", "episodic", "procedural"] = "semantic"
    scope: Literal["user"] = "user"
    governance_track: Literal["mutable"] = "mutable"
    authority: Literal["user_context"] = "user_context"
    key: str | None = None
    fingerprint: str | None = None
    conflicts_with: list[str] = Field(default_factory=list)
    confirmation_note: str | None = None
    status: Literal["proposed", "confirmed", "rejected"] = "proposed"
    sensitivity: Literal["normal", "sensitive", "restricted"] = "sensitive"
    expires_at: datetime | None = None
    valid_from: datetime | None = None
    superseded_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_accessed_at: datetime | None = None


class SkillRecord(BaseModel):
    id: str
    version: str
    description: str
    path: str
    capabilities: list[str]
    dependencies: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.ROUTINE
    plugins: list[str]
    status: Literal["candidate", "validated", "enabled", "disabled", "rejected"] = "candidate"
    evaluation: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSource(BaseModel):
    id: str
    title: str
    path: str
    source_type: Literal["guideline", "record", "web", "user"] = "guideline"
    institution: str | None = None
    region: str | None = None
    published_at: str | None = None
    version: str | None = None
    population: str | None = None
    status: Literal["current", "expired", "superseded", "unknown"] = "unknown"
    superseded_by: str | None = None
    imported_by: int | None = None
    imported_at: datetime = Field(default_factory=utc_now)
    verified: bool = False
    checksum: str | None = None


class KnowledgeIndexStatus(BaseModel):
    status: Literal["ready", "degraded", "unavailable", "building"]
    documents: int = 0
    chunks: int = 0
    page_visuals: int = 0
    vectors: int = 0
    embedding_model: str | None = None
    graph_nodes: int = 0
    graph_edges: int = 0
    stale: bool = False
    built_at: datetime | None = None
    detail: str | None = None


class EvolutionProposal(BaseModel):
    id: str = Field(default_factory=lambda: f"evo_{uuid4().hex}")
    provider: Literal["a-evolve", "gepa", "adaptive-auto-harness", "manual"]
    target_failure_cluster: str
    mutation_paths: list[str] = Field(min_length=1)
    expected_behavior_change: str
    risk: str
    activation_condition: str
    base_commit: str
    status: Literal[
        "proposed",
        "isolated",
        "evaluated",
        "accepted",
        "rejected",
        "promoted",
    ] = "proposed"
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationCaseResult(BaseModel):
    case_id: str
    slice: Literal["routine", "complex", "high_risk"]
    score: float
    tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    passed: bool
    safety_passed: bool = True
    citation_passed: bool = True
    component_contract_passed: bool = False
    component_contracts: dict[str, bool] = Field(default_factory=dict)
    critical_errors: list[str] = Field(default_factory=list)


class EvaluationRunResult(BaseModel):
    proposal_id: str
    variant: Literal["baseline", "candidate"] = "candidate"
    phase: Literal[
        "training",
        "proposal_selection",
        "acceptance_validation",
        "sealed_test",
    ]
    commit: str
    cases: list[EvaluationCaseResult]
    command_succeeded: bool = True
    attestation: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PromotionDecision(BaseModel):
    accepted: bool
    mean_difference: float
    confidence_interval_95: tuple[float, float]
    token_ratio: float
    latency_ratio: float
    slice_differences: dict[str, float]
    reasons: list[str] = Field(default_factory=list)


class ContinuousEvolutionCandidate(BaseModel):
    """Content-free improvement work item derived from repeated outcomes."""

    id: str
    kind: Literal["memory_retrieval", "memory_extraction", "skill", "runtime"]
    target: str
    sample_size: int = Field(ge=1)
    negative_rate: float = Field(ge=0, le=1)
    trigger: str
    allowed_mutation_paths: list[str]
    status: Literal[
        "ready_for_offline_evaluation",
        "accepted",
        "rejected",
        "promoted",
    ] = "ready_for_offline_evaluation"
    requires_human_approval: bool = True
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ContinuousEvolutionStatus(BaseModel):
    enabled: bool = True
    mode: Literal["online_adapt_and_gate"] = "online_adapt_and_gate"
    signal_count: int = Field(default=0, ge=0)
    feedback_count: int = Field(default=0, ge=0)
    observed_run_count: int = Field(default=0, ge=0)
    ready_candidate_count: int = Field(default=0, ge=0)
    memory_adaptation: str
    skill_adaptation: str
    production_mutation: Literal["disabled"] = "disabled"
    human_approval_required: bool = True
    candidates: list[ContinuousEvolutionCandidate] = Field(default_factory=list)


class ExperienceRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"exp_{uuid4().hex}")
    proposal_id: str
    failure_pattern: str
    strategy: str
    release_commit: str
    evaluation: dict[str, Any]
    status: Literal["promoted", "retired"] = "promoted"
    created_at: datetime = Field(default_factory=utc_now)


class CapabilityState(BaseModel):
    id: str
    configured: bool
    status: Literal["ready", "degraded", "unavailable", "unknown"]
    provider: str | None = None
    model: str | None = None
    checked_at: datetime = Field(default_factory=utc_now)
    detail: str | None = None
    required: bool = False


class ImageRegion(BaseModel):
    label: str
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    coordinate_space: Literal["pixels", "normalized"]
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_normalized(self) -> ImageRegion:
        if self.coordinate_space == "normalized":
            values = (self.x, self.y, self.width, self.height)
            if any(value > 1 for value in values) or self.x + self.width > 1 or self.y + self.height > 1:
                raise ValueError("normalized coordinates must remain within [0, 1]")
        return self

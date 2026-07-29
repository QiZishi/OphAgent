"""Plugin-to-DAG planning with explicit dependencies."""

from __future__ import annotations

from app.domain.models import (
    PlanNode,
    PluginManifest,
    RiskLevel,
    RunInput,
    TaskComplexity,
    TaskIntent,
    TaskRoute,
)
from app.runtime.routing import route_task


def build_plan(
    plugin: PluginManifest,
    run_input: RunInput,
    risk: RiskLevel,
    route: TaskRoute | None = None,
) -> list[PlanNode]:
    if route is None:
        routed_input = run_input
        if plugin.id != "core" and run_input.plugin_id == "core" and not run_input.requested_plugins:
            routed_input = run_input.model_copy(update={"plugin_id": plugin.id})
        route = route_task(routed_input, risk)
    if route.intent == TaskIntent.QUICK_ANSWER:
        return [
            PlanNode(
                id="answer",
                title="直接回答",
                agent="DirectAnswerAgent",
                capability="main_model",
            ),
        ]

    nodes: list[PlanNode] = []
    dependencies: list[str] = []
    if route.needs_clinical_state:
        nodes.append(
            PlanNode(
                id="clinical",
                title="更新结构化临床状态",
                agent="ClinicalReasoningAgent",
                capability="main_model",
            ),
        )
        dependencies.append("clinical")

    if route.needs_retrieval:
        nodes.append(
            PlanNode(
                id="evidence",
                title="检索可追踪医学证据",
                agent="EvidenceAgent",
                capability="medical_retrieval",
                required=route.intent == TaskIntent.KNOWLEDGE_RETRIEVAL,
            ),
        )
        dependencies.append("evidence")

    if route.needs_imaging:
        nodes.append(
            PlanNode(
                id="imaging",
                title=(
                    "校验并定位可疑影像区域"
                    if "lesion_localizer" in route.selected_plugins
                    else "分析眼科影像"
                ),
                agent="MultimodalOphthalmologyAgent",
                capability="medical_image_analysis",
                required="lesion_localizer" in route.selected_plugins,
                input={
                    "request_regions": "lesion_localizer" in route.selected_plugins,
                },
            ),
        )
        dependencies.append("imaging")

    if run_input.document_paths:
        nodes.append(
            PlanNode(
                id="documents",
                title="解析文档",
                agent="DocumentParser",
                capability="document_parser",
            ),
        )
        dependencies.append("documents")

    if run_input.audio_paths:
        nodes.append(
            PlanNode(
                id="audio",
                title="转写音频",
                agent="SpeechRecognizer",
                capability="asr",
            ),
        )
        dependencies.append("audio")

    if "aux_diagnosis" in route.selected_plugins:
        nodes.append(
            PlanNode(
                id="assessment",
                title="形成结构化鉴别评估",
                agent="DifferentialAssessmentAgent",
                capability="main_model",
                depends_on=dependencies.copy(),
            ),
        )
        dependencies.append("assessment")

    if route.complexity == TaskComplexity.DEEP:
        specialist_dependencies = dependencies.copy()
        for specialty in _select_specialties(run_input.query):
            node_id = f"specialist_{specialty}"
            nodes.append(
                PlanNode(
                    id=node_id,
                    title=f"{_SPECIALTY_LABELS[specialty]}复核",
                    agent="OphthalmologySpecialistAgent",
                    capability="specialist_review",
                    depends_on=specialist_dependencies,
                    required=False,
                    input={"specialty": specialty},
                ),
            )
            dependencies.append(node_id)

    terminal_id = "report" if route.needs_report else "answer"
    terminal_title = "生成结构化报告" if route.needs_report else "生成回答"
    terminal_agent = "ReportAgent" if route.needs_report else "AnswerSynthesizer"

    if risk in {RiskLevel.HIGH, RiskLevel.EMERGENCY}:
        nodes.append(
            PlanNode(
                id="draft",
                title="生成高风险候选稿",
                agent=terminal_agent,
                capability="main_model",
                depends_on=dependencies.copy(),
            ),
        )
        nodes.append(
            PlanNode(
                id="critic",
                title="审查高风险候选稿",
                agent="CriticAgent",
                capability="main_model",
                depends_on=["draft"],
            ),
        )
        dependencies = ["critic"]

    nodes.append(
        PlanNode(
            id=terminal_id,
            title=terminal_title,
            agent=terminal_agent,
            capability="main_model",
            depends_on=dependencies.copy(),
        ),
    )
    allowed_capabilities = {
        "clinical_state",
        "medical_image_analysis",
        "medical_retrieval",
        "web_search",
        "citation_verification",
        "main_model",
        "document_parser",
        "asr",
        "specialist_review",
    }
    unsupported = [
        node.capability
        for node in nodes
        if node.capability not in allowed_capabilities
    ]
    if unsupported:
        raise ValueError(
            f"插件 {plugin.id} 的计划包含清单外能力：{', '.join(sorted(set(unsupported)))}"
        )
    return nodes


_SPECIALTY_LABELS = {
    "retina": "眼底与黄斑专科",
    "glaucoma": "青光眼专科",
    "cornea": "角膜与眼表专科",
    "neuro": "神经眼科",
    "pediatric": "儿童眼病与斜弱视专科",
    "general": "综合眼科",
}

_SPECIALTY_TERMS = {
    "retina": ("眼底", "视网膜", "黄斑", "OCT", "oct", "飞蚊", "闪光", "糖网"),
    "glaucoma": ("青光眼", "眼压", "视野", "房角"),
    "cornea": ("角膜", "眼表", "干眼", "结膜", "接触镜", "红眼"),
    "neuro": ("视神经", "复视", "视野缺损", "瞳孔", "神经"),
    "pediatric": ("儿童", "婴儿", "斜视", "弱视", "近视防控"),
}


def _select_specialties(query: str) -> list[str]:
    selected = [
        specialty
        for specialty, terms in _SPECIALTY_TERMS.items()
        if any(term in query for term in terms)
    ]
    return (selected or ["general"])[:2]

"""Versioned plugin manifests.

Plugins describe composition; they do not contain hidden medical conclusions.
"""

from __future__ import annotations

from app.domain.models import PluginManifest

COMMON_CONTEXT = {
    "clinical_state_is_source_of_truth": True,
    "preserve": ["red_flags", "medications", "allergies", "unresolved_questions"],
}
COMMON_BUDGET = {"max_model_calls": 12, "max_tokens": 32_000, "max_seconds": 300}
COMMON_SAFETY = {
    "medical_disclaimer": True,
    "evidence_required": True,
    "escalate_red_flags": True,
    "no_hidden_chain_of_thought": True,
}


def _manifest(
    plugin_id: str,
    description: str,
    accepted_inputs: list[str],
    produced_artifacts: list[str],
    required_capabilities: list[str],
    skills: list[str],
    tools: list[str],
    agent_graph: list[str],
    required_nodes: list[str],
    optional_nodes: list[str],
) -> PluginManifest:
    return PluginManifest(
        id=plugin_id,
        version="1.0.0",
        description=description,
        accepted_inputs=accepted_inputs,
        produced_artifacts=produced_artifacts,
        required_capabilities=required_capabilities,
        skills=skills,
        tools=tools,
        agent_graph=agent_graph,
        context_policy=COMMON_CONTEXT,
        budget_policy=COMMON_BUDGET,
        safety_policy=COMMON_SAFETY,
        activation={
            "automatic": True,
            "explicit_mention": True,
            "requires_authenticated_user": True,
        },
        latency_budget={"quick": 15, "standard": 60, "deep": 300},
        fallback={
            "main_model": "fail_closed_with_public_error",
            "medical_retrieval": "continue_only_if_local_evidence_exists",
            "medical_image_analysis": "omit_image_conclusion",
            "asr": "preserve_audio_and_request_text",
        },
        permission="authenticated_user",
        required_nodes=required_nodes,
        optional_nodes=optional_nodes,
    )


CORE_MANIFEST = _manifest(
    "core",
    "OphAgent 默认问答与知识检索能力。",
    ["text", "image", "document", "audio", "clinical_state"],
    ["answer", "citations"],
    ["main_model"],
    ["ophthalmic_interview", "red_flag_triage", "guideline_retrieval"],
    [
        "clinical_state",
        "medical_image_analysis",
        "medical_retrieval",
        "web_search",
        "citation_verification",
    ],
    ["SupervisorAgent", "ClinicalReasoningAgent", "EvidenceAgent", "AnswerSynthesizer"],
    ["answer"],
    ["clinical", "evidence", "imaging", "documents", "audio", "specialist_*", "draft", "critic"],
)


MANIFESTS = [
    _manifest(
        "lesion_localizer",
        "在原始眼科影像上标示通过坐标校验的可疑区域，并说明可见依据与局限。",
        ["text", "image", "clinical_state"],
        ["image_observations", "validated_regions", "annotated_preview"],
        ["sub_model"],
        ["ophthalmic_imaging"],
        ["medical_image_analysis", "citation_verification"],
        ["SupervisorAgent", "MultimodalOphthalmologyAgent", "ReportAgent"],
        ["imaging", "answer"],
        ["specialist_*", "draft", "critic"],
    ),
    _manifest(
        "aux_diagnosis",
        "综合病史、影像与证据形成定性鉴别评估，展示支持项、反对项、缺失项和下一步。",
        ["text", "image", "document", "clinical_state"],
        ["clinical_assessment", "citations", "action_list"],
        ["main_model"],
        ["ophthalmic_interview", "red_flag_triage", "evidence_synthesis"],
        ["clinical_state", "medical_image_analysis", "medical_retrieval", "web_search"],
        ["SupervisorAgent", "ClinicalReasoningAgent", "MultimodalOphthalmologyAgent", "EvidenceAgent", "ReportAgent"],
        ["clinical", "answer"],
        ["evidence", "imaging", "documents", "audio", "specialist_*", "draft", "critic"],
    ),
    _manifest(
        "report_generator",
        "按实际检查模态整合既有观察与证据，生成可编辑、可导出的结构化眼科报告。",
        ["text", "image", "document", "clinical_state"],
        ["structured_report", "patient_summary", "citations"],
        ["main_model"],
        ["ophthalmic_report"],
        ["medical_image_analysis", "medical_retrieval", "citation_verification"],
        ["SupervisorAgent", "EvidenceAgent", "ReportAgent"],
        ["report"],
        ["clinical", "evidence", "imaging", "documents", "audio", "specialist_*", "draft", "critic"],
    ),
]


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins = {manifest.id: manifest for manifest in MANIFESTS}

    def list(self) -> list[PluginManifest]:
        return list(self._plugins.values())

    def get(self, plugin_id: str) -> PluginManifest:
        if plugin_id in {"core", "interactive_vqa", "knowledge_base"}:
            return CORE_MANIFEST
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise ValueError(f"未知插件：{plugin_id}") from exc


plugin_registry = PluginRegistry()

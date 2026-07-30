"""Deterministic task routing for Quick, Standard and Deep Work."""

from __future__ import annotations

import re

from app.domain.models import (
    RiskLevel,
    RunInput,
    TaskComplexity,
    TaskIntent,
    TaskRoute,
)

_QUICK_PATTERNS = (
    re.compile(r"^\s*(你好|您好|嗨|hi|hello)[！!。.？?\s]*$", re.IGNORECASE),
    re.compile(r"^\s*\d+(?:\.\d+)?\s*[\+\-×xX*/÷]\s*\d+(?:\.\d+)?(?:\s*等于多少)?[？?\s。]*$"),
)
_REPORT_TERMS = ("报告", "总结成文档", "生成病历", "检查单", "影像报告")
_KNOWLEDGE_TERMS = ("指南", "共识", "文献", "来源", "证据", "最新", "检索")
_ASSESSMENT_TERMS = ("鉴别", "风险", "评估", "下一步", "可能是什么", "诊断", "异常是什么", "考虑什么")
_EDUCATION_PREFIXES = ("什么是", "介绍一下", "解释一下", "科普", "怎么理解", "有哪些类型")
_LOCALIZATION_TERMS = ("定位", "病灶在哪里", "标出", "标注", "框出", "区域", "位置")
_IMAGE_ASSESSMENT_TERMS = ("图像", "影像", "眼底", "oct", "OCT", "异常", "病变", "表现")
_CLINICAL_TERMS = (
    "眼", "视力", "视物", "干涩", "疼", "红", "痒", "分泌物", "飞蚊", "闪光",
    "近视", "远视", "散光", "青光眼", "白内障", "角膜", "结膜", "视网膜", "黄斑",
    "药", "手术", "检查", "症状",
)
_PATIENT_CONTEXT_TERMS = (
    "患者", "本人", "我", "症状", "主诉", "岁", "病史", "用药", "过敏",
    "视力下降", "看不清", "视物模糊", "眼痛", "头痛", "红眼", "眼红",
    "干涩", "瘙痒", "分泌物", "飞蚊", "闪光",
)
_FOLLOW_UP_TERMS = (
    "那", "这个", "它", "上述", "前面", "刚才", "继续", "详细说",
    "怎么办", "为什么", "下一步呢", "需要做什么", "再解释",
)


def is_contextual_follow_up(query: str, previous_route: TaskRoute | None) -> bool:
    normalized = query.strip()
    return bool(
        previous_route
        and len(normalized) <= 120
        and any(term in normalized for term in _FOLLOW_UP_TERMS)
    )


def route_task(
    run_input: RunInput,
    risk: RiskLevel,
    previous_route: TaskRoute | None = None,
) -> TaskRoute:
    public_plugins = {"lesion_localizer", "aux_diagnosis", "report_generator"}
    requested = [
        plugin_id
        for plugin_id in dict.fromkeys([*run_input.requested_plugins, run_input.plugin_id])
        if plugin_id in public_plugins
    ]
    query = run_input.query.strip()
    has_images = bool(run_input.image_paths)
    has_documents = bool(run_input.document_paths)

    explicit_report = (
        "report_generator" in requested
        or any(term in query for term in _REPORT_TERMS)
    )
    explicit_knowledge = (
        any(term in query for term in _KNOWLEDGE_TERMS)
        or (
            any(query.startswith(prefix) for prefix in _EDUCATION_PREFIXES)
            and any(term in query for term in _CLINICAL_TERMS)
        )
    )
    explicit_assessment = (
        "aux_diagnosis" in requested
        or any(term in query for term in _ASSESSMENT_TERMS)
        or (has_images and any(term in query for term in _IMAGE_ASSESSMENT_TERMS))
    )
    explicit_localization = (
        "lesion_localizer" in requested
        or (has_images and any(term in query for term in _LOCALIZATION_TERMS))
    )
    looks_clinical = any(term in query for term in _CLINICAL_TERMS)
    contextual_follow_up = is_contextual_follow_up(query, previous_route)
    matches_quick_pattern = any(pattern.match(query) for pattern in _QUICK_PATTERNS)
    is_quick = (
        risk == RiskLevel.ROUTINE
        and not has_images
        and not has_documents
        and not explicit_report
        and not explicit_knowledge
        and not explicit_assessment
        and not explicit_localization
        and not contextual_follow_up
        and not looks_clinical
        and (
            (run_input.mode == "quick" and (matches_quick_pattern or len(query) <= 80))
            or (
                run_input.mode == "auto"
                and (matches_quick_pattern or len(query) <= 80)
            )
        )
    )

    if is_quick:
        return TaskRoute(
            intent=TaskIntent.QUICK_ANSWER,
            complexity=TaskComplexity.QUICK,
            risk=risk,
            selected_plugins=[],
            reason_code="deterministic_quick",
        )

    if explicit_report:
        intent = TaskIntent.REPORT_GENERATION
    elif explicit_knowledge:
        intent = TaskIntent.KNOWLEDGE_RETRIEVAL
    elif explicit_assessment:
        intent = TaskIntent.AUX_ASSESSMENT
    elif explicit_localization:
        intent = TaskIntent.IMAGE_ANALYSIS
    elif contextual_follow_up and previous_route:
        intent = (
            TaskIntent.KNOWLEDGE_RETRIEVAL
            if previous_route.intent == TaskIntent.KNOWLEDGE_RETRIEVAL
            else TaskIntent.CLINICAL_QNA
        )
    else:
        intent = TaskIntent.CLINICAL_QNA

    selected = list(requested)
    if explicit_localization and "lesion_localizer" not in selected:
        selected.append("lesion_localizer")
    if explicit_assessment and "aux_diagnosis" not in selected:
        selected.append("aux_diagnosis")
    if explicit_report and "report_generator" not in selected:
        selected.append("report_generator")
    # A report based on imaging should consume a structured assessment rather
    # than asking the report model to invent one inside prose.
    if explicit_report and has_images and "aux_diagnosis" not in selected:
        selected.insert(0, "aux_diagnosis")

    deep = (
        run_input.mode == "deep"
        # A composed plugin graph can be substantially heavier than its raw
        # attachment count suggests. Localization + assessment + report must
        # reserve room for each model/tool result and the final artifact.
        or len(selected) >= 2
        # attachment_ids are resolved into the typed path lists before
        # routing; counting both would make one uploaded image look like two
        # independent inputs and incorrectly force Deep mode.
        or len(run_input.image_paths) + len(run_input.document_paths) + len(run_input.audio_paths) > 1
        or len(query) > 800
    )
    complexity = (
        TaskComplexity.DEEP
        if deep or risk in {RiskLevel.HIGH, RiskLevel.EMERGENCY}
        else TaskComplexity.STANDARD
    )
    needs_clinical = intent in {
        TaskIntent.CLINICAL_QNA,
        TaskIntent.AUX_ASSESSMENT,
        TaskIntent.REPORT_GENERATION,
    }
    if (
        intent == TaskIntent.AUX_ASSESSMENT
        and has_images
        and not any(term in query for term in _PATIENT_CONTEXT_TERMS)
    ):
        needs_clinical = False
    needs_retrieval = intent in {
        TaskIntent.KNOWLEDGE_RETRIEVAL,
        TaskIntent.AUX_ASSESSMENT,
        TaskIntent.REPORT_GENERATION,
    }
    if contextual_follow_up and previous_route and previous_route.needs_retrieval:
        needs_retrieval = True
    needs_imaging = "lesion_localizer" in selected or (
        has_images
        and intent in {
            TaskIntent.AUX_ASSESSMENT,
            TaskIntent.REPORT_GENERATION,
            TaskIntent.CLINICAL_QNA,
        }
    )
    return TaskRoute(
        intent=intent,
        complexity=complexity,
        risk=risk,
        selected_plugins=selected,
        needs_clinical_state=needs_clinical,
        needs_retrieval=needs_retrieval,
        needs_imaging=needs_imaging,
        needs_report="report_generator" in selected,
        reason_code=(
            "contextual_follow_up"
            if contextual_follow_up
            else f"deterministic_{intent.value}"
        ),
    )

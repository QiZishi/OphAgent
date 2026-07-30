"""Deterministic medical safety gates."""

from __future__ import annotations

import re

from app.domain.models import ClinicalFact, ClinicalState, RiskLevel

RED_FLAG_PATTERNS: list[tuple[str, str]] = [
    (r"化学|酸液|碱液|清洁剂.*眼|眼.*清洁剂", "疑似眼部化学暴露"),
    (r"突然|突发|急性.{0,6}(看不见|视力下降|视物不清)", "急性视力下降"),
    (r"眼球破裂|穿通伤|开放性眼外伤|异物刺入", "疑似开放性眼外伤"),
    (r"(?:剧烈眼痛.{0,12}(?:恶心|呕吐)|(?:恶心|呕吐).{0,12}剧烈眼痛)", "剧烈眼痛伴恶心/呕吐"),
    (r"幕帘|黑影遮挡|闪光.{0,8}飞蚊|飞蚊.{0,8}闪光", "视网膜裂孔或脱离相关症状"),
    (r"(?:术后.{0,12}(?:眼痛|视力下降)|(?:眼痛|视力下降).{0,12}术后)", "眼科术后急性异常"),
]

_INDIVIDUAL_DIAGNOSIS_PATTERNS = (
    re.compile(
        r"(?:你|患者|该患者|该病例).{0,24}"
        r"(?:已经确诊|可以确诊|可确诊|明确患有|肯定是|就是)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:最终|明确)?诊断\s*[：:]\s*"
        r"(?!待|考虑|可能|疑似|倾向|不能|无法|尚不能)",
        re.IGNORECASE,
    ),
)
_NUMERIC_DISEASE_PROBABILITY = re.compile(
    r"(?:患病|疾病|诊断|青光眼|白内障|视网膜|黄斑|角膜).{0,16}"
    r"\d{1,3}(?:\.\d+)?\s*%|"
    r"\d{1,3}(?:\.\d+)?\s*%.{0,16}(?:概率|可能性|患病)",
    re.IGNORECASE,
)
_DIRECT_MEDICATION_CHANGE = re.compile(
    r"(?:建议|应当|应该|必须|请|立即|马上).{0,16}"
    r"(?:自行)?(?:停药|停用|停服|加量|减量|换药|换用|开始使用|开始服用)"
    r"[^。！？；\n]{0,32}(?:药|滴眼液|mg|毫克|片|胶囊)",
    re.IGNORECASE,
)
_CLINICIAN_DECISION = re.compile(
    r"(?:由|请|需).{0,12}(?:眼科|医生|医师|专科).{0,16}(?:评估|判断|决定|开具)",
    re.IGNORECASE,
)


def apply_red_flag_gate(query: str, state: ClinicalState) -> RiskLevel:
    found: list[str] = []
    for pattern, label in RED_FLAG_PATTERNS:
        if re.search(pattern, query, flags=re.IGNORECASE):
            found.append(label)
    existing = {fact.value for fact in state.red_flags}
    for label in found:
        if label not in existing:
            state.red_flags.append(ClinicalFact(value=label, source="用户本轮输入", confirmed=False))
    if found:
        return RiskLevel.EMERGENCY
    if any(term in query for term in ("儿童", "婴儿", "孕妇", "妊娠", "外伤", "过敏", "用药冲突")):
        return RiskLevel.HIGH
    if len(query) > 800:
        return RiskLevel.COMPLEX
    return RiskLevel.ROUTINE


def emergency_banner(state: ClinicalState) -> str:
    if not state.red_flags:
        return ""
    flags = "、".join(fact.value for fact in state.red_flags)
    return (
        f"⚠️ 检测到需要优先处理的红旗：{flags}。"
        "请立即停止可能继续造成伤害的操作，并尽快前往眼科急诊/急诊评估；"
        "若为化学暴露，应立即持续用大量清水或生理盐水冲洗，并同时寻求急救。"
    )


def validate_public_medical_output(
    text: str,
    *,
    individualized: bool,
) -> list[str]:
    """Detect high-risk public claims before any answer is published.

    This is intentionally a narrow deterministic tripwire, not a substitute
    for clinical evaluation. It catches claims that should never be emitted
    from an individualized assistant response without professional review.
    """
    if not individualized:
        return []
    issues: list[str] = []
    if any(pattern.search(text) for pattern in _INDIVIDUAL_DIAGNOSIS_PATTERNS):
        issues.append("overconfident_individual_diagnosis")
    if _NUMERIC_DISEASE_PROBABILITY.search(text):
        issues.append("fabricated_disease_probability")
    for sentence in re.split(r"(?<=[。！？；\n])", text):
        if (
            _DIRECT_MEDICATION_CHANGE.search(sentence)
            and not _CLINICIAN_DECISION.search(sentence)
        ):
            issues.append("direct_medication_change")
            break
    return issues

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

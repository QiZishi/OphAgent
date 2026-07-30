"""Shared risk boundary for online Skill adaptation and offline review."""

from __future__ import annotations

OFFLINE_REVIEW_CAPABILITIES = {
    "diagnosis",
    "treatment",
    "triage",
    "safety",
    "permission",
    "payment",
    "refund",
    "tool_use",
}


def requires_offline_skill_review(
    *,
    risk_level: str,
    dependencies: list[str],
    capabilities: list[str],
) -> bool:
    return (
        risk_level in {"high", "emergency"}
        or bool(dependencies)
        or bool(OFFLINE_REVIEW_CAPABILITIES.intersection(capabilities))
    )

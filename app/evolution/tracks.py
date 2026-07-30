"""Authoritative mutable/immutable boundaries for self-evolution candidates.

This module is part of the controller-owned evolution package. Candidate
worktrees are never allowed to modify it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

MutationTrack = Literal["mutable", "immutable"]

# Preferences, presentation strategies and bounded retrieval/skill strategies.
MUTABLE_PREFIXES = (
    "app/runtime/strategies/",
    "app/knowledge/strategies/",
    "app/services/memory_strategies/",
    "skills/",
    "frontend/src/",
    "config/mutable/",
)

# Allowed control-plane code and configuration. Changes may be proposed, but
# promotion always requires trusted human approval bound to the frozen commit.
IMMUTABLE_PREFIXES = (
    "app/runtime/",
    "app/knowledge/",
    "app/plugins/",
    "app/services/",
    "config/",
)

EVOLVABLE_PREFIXES = tuple(
    dict.fromkeys((*MUTABLE_PREFIXES, *IMMUTABLE_PREFIXES)),
)

DENIED_PARTS = {
    ".env",
    ".git",
    ".github",
    "tests",
    "data",
    "auth",
    "db",
    "evolution",
    "observability",
}


class TrackPolicyError(ValueError):
    """Raised when a candidate crosses the dual-track trust boundary."""


def _under_prefix(path: str, prefix: str) -> bool:
    return path == prefix.rstrip("/") or path.startswith(prefix)


def normalize_candidate_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise TrackPolicyError(f"非法候选路径：{value}")
    normalized = path.as_posix().lstrip("./")
    if any(part in DENIED_PARTS for part in Path(normalized).parts):
        raise TrackPolicyError(f"禁止修改路径：{value}")
    if not any(_under_prefix(normalized, prefix) for prefix in EVOLVABLE_PREFIXES):
        raise TrackPolicyError(f"路径不在演化白名单：{value}")
    return normalized


def classify_candidate_path(value: str) -> MutationTrack:
    normalized = normalize_candidate_path(value)
    if any(_under_prefix(normalized, prefix) for prefix in MUTABLE_PREFIXES):
        return "mutable"
    return "immutable"


def classify_candidate_paths(values: list[str]) -> MutationTrack:
    if not values:
        raise TrackPolicyError("候选修改路径不能为空")
    tracks = {classify_candidate_path(value) for value in values}
    if len(tracks) != 1:
        raise TrackPolicyError("候选不能混合可变轨与不可变轨修改")
    return tracks.pop()


def human_approval_required(
    track: MutationTrack,
    configured_requirement: bool,
) -> bool:
    """Immutable updates can never disable trusted human review."""
    return track == "immutable" or configured_requirement

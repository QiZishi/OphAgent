"""Privacy-minimized online adaptation with offline gates for risky changes.

The online runtime learns bounded utility adjustments for confirmed,
non-clinical memories and already validated low-risk skills. Content, code,
permissions, clinical facts and safety-policy changes remain offline-gated.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections import defaultdict
from typing import Any

from app.core.config import Settings, settings
from app.domain.models import (
    ContinuousEvolutionCandidate,
    ContinuousEvolutionStatus,
    MemoryRecord,
    RunEvent,
    RunRecord,
    RunStatus,
    utc_now,
)
from app.services.state import atomic_json

SAFE_TOKEN = re.compile(r"[^a-zA-Z0-9_.:-]+")
TERMINAL = {
    RunStatus.COMPLETED,
    RunStatus.COMPLETED_WITH_WARNINGS,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.INTERRUPTED,
}
PROTECTED_SKILLS = {"red_flag_triage"}


def _safe(value: str | None, fallback: str = "unknown") -> str:
    cleaned = SAFE_TOKEN.sub("_", value or "").strip("._:-")
    return cleaned[:120] or fallback


def _opaque(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ContinuousEvolutionController:
    """Collects outcomes and creates bounded improvement candidates.

    No query, answer, attachment, evidence text, user identifier or clinical
    field is persisted here. This controller never edits production code,
    skill content, models, medical facts, permissions or safety policy.
    """

    SCHEMA_VERSION = 1

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        root = config.resolve_path(config.EVOLUTION_STATE_DIR)
        self.state_path = root / "continuous_state.json"
        self.signal_path = root / "signals.jsonl"
        self._lock = asyncio.Lock()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "schema_version": ContinuousEvolutionController.SCHEMA_VERSION,
            "signal_count": 0,
            "feedback_by_run": {},
            "outcomes_by_run": {},
            "memory_actions": [],
            "candidates": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return self._empty()
        try:
            state = json.loads(self.state_path.read_text("utf-8"))
            if int(state.get("schema_version", 0)) != self.SCHEMA_VERSION:
                return self._empty()
            return state
        except (OSError, TypeError, ValueError):
            return self._empty()

    def _save(self, state: dict[str, Any]) -> None:
        limit = max(100, self.config.EVOLUTION_MAX_ONLINE_RECORDS)
        for key in ("feedback_by_run", "outcomes_by_run"):
            records = state.get(key, {})
            if len(records) > limit:
                ordered = sorted(
                    records.items(),
                    key=lambda item: str(item[1].get("updated_at", "")),
                    reverse=True,
                )[:limit]
                state[key] = dict(ordered)
        actions = list(state.get("memory_actions", []))
        state["memory_actions"] = actions[-limit:]
        atomic_json(self.state_path, state)

    def _append_signal(self, signal: dict[str, Any]) -> None:
        self.signal_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "timestamp": utc_now().isoformat(),
            **signal,
        }
        with self.signal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        max_bytes = max(1_000_000, self.config.EVOLUTION_SIGNAL_LOG_MAX_BYTES)
        if self.signal_path.stat().st_size > max_bytes:
            archive = self.signal_path.with_name("signals.previous.jsonl")
            os.replace(self.signal_path, archive)

    @staticmethod
    def _memory_items(events: list[RunEvent]) -> list[dict[str, str]]:
        items: dict[str, str] = {}
        for event in events:
            if event.type != "memory.recalled":
                continue
            for item in event.data.get("memories", []):
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                items[str(item["id"])] = _safe(str(item.get("category") or "unknown"))
        return [
            {"id": memory_id, "category": category}
            for memory_id, category in sorted(items.items())
        ]

    @staticmethod
    def _skill_ids(events: list[RunEvent]) -> list[str]:
        used: set[str] = set()
        for event in events:
            if event.type != "agent.completed":
                continue
            used.update(
                _safe(str(skill_id))
                for skill_id in event.data.get("used_skills", [])
                if skill_id
            )
        return sorted(used)

    @staticmethod
    def _plugin_ids(run: RunRecord) -> list[str]:
        selected = run.route.selected_plugins if run.route else []
        return sorted({_safe(item) for item in (selected or [run.plugin.id])})

    async def record_run_outcome(
        self,
        run: RunRecord,
        events: list[RunEvent],
    ) -> None:
        if run.status not in TERMINAL:
            return
        run_key = _opaque(run.id)
        record = {
            "status": run.status.value,
            "risk": run.risk_level.value,
            "route": _safe(run.route.reason_code if run.route else None),
            "plugins": self._plugin_ids(run),
            "skills": self._skill_ids(events),
            "error_code": _safe(run.error_code) if run.error_code else None,
            "warning_count": len(run.warnings),
            "model_calls": run.budget.model_calls,
            "total_tokens": run.budget.prompt_tokens + run.budget.completion_tokens,
            "updated_at": utc_now().isoformat(),
        }
        async with self._lock:
            state = self._load()
            previous = state["outcomes_by_run"].get(run_key)
            state["outcomes_by_run"][run_key] = record
            if previous != record:
                state["signal_count"] += 1
                self._append_signal(
                    {
                        "type": "run.outcome",
                        "run_fingerprint": run_key,
                        **{key: value for key, value in record.items() if key != "updated_at"},
                    },
                )
            self._refresh_candidates(state)
            self._save(state)

    async def record_feedback(
        self,
        run: RunRecord,
        previous_value: str | None,
        value: str | None,
        events: list[RunEvent],
    ) -> None:
        run_key = _opaque(run.id)
        async with self._lock:
            state = self._load()
            if value not in {"up", "down"}:
                state["feedback_by_run"].pop(run_key, None)
            else:
                state["feedback_by_run"][run_key] = {
                    "value": value,
                    "risk": run.risk_level.value,
                    "route": _safe(run.route.reason_code if run.route else None),
                    "plugins": self._plugin_ids(run),
                    "skills": self._skill_ids(events),
                    "memories": self._memory_items(events),
                    "updated_at": utc_now().isoformat(),
                }
            state["signal_count"] += 1
            self._append_signal(
                {
                    "type": "user.feedback",
                    "run_fingerprint": run_key,
                    "previous": previous_value,
                    "value": value,
                    "risk": run.risk_level.value,
                    "plugins": self._plugin_ids(run),
                    "skills": self._skill_ids(events),
                    "recalled_memory_count": len(self._memory_items(events)),
                },
            )
            self._refresh_candidates(state)
            self._save(state)

    async def record_memory_action(
        self,
        memory: MemoryRecord,
        action: str,
    ) -> None:
        action = _safe(action)
        record = {
            "memory_fingerprint": _opaque(memory.id),
            "category": _safe(memory.category),
            "action": action,
            "timestamp": utc_now().isoformat(),
        }
        async with self._lock:
            state = self._load()
            state["memory_actions"].append(record)
            state["signal_count"] += 1
            self._append_signal({"type": "memory.governance", **record})
            self._refresh_candidates(state)
            self._save(state)

    def memory_utility_factor(self, memory_id: str, category: str) -> float:
        """Continuously adapt low-authority non-clinical memory utility.

        Clinical history, medications and allergies are never re-ranked from
        coarse answer-level feedback. Preference/workspace memory can move
        within a bounded range in either direction as explicit feedback changes.
        """
        if category not in {"preference", "workspace"}:
            return 1.0
        positives = 0
        negatives = 0
        for record in self._load().get("feedback_by_run", {}).values():
            recalled = {
                item.get("id")
                for item in record.get("memories", [])
                if isinstance(item, dict)
            }
            if memory_id not in recalled:
                continue
            if record.get("value") == "up":
                positives += 1
            elif record.get("value") == "down":
                negatives += 1
        sample_size = positives + negatives
        if sample_size < self.config.EVOLUTION_MIN_FEEDBACK_SAMPLES:
            return 1.0
        rate = (positives + 2) / (sample_size + 4)
        bound = self.config.EVOLUTION_MEMORY_RANKING_BOUND
        adjustment = bound * (
            (rate - 0.5)
            / 0.5
        )
        return min(1.0 + bound, max(1.0 - bound, 1.0 + adjustment))

    def skill_utility_factor(
        self,
        skill_id: str,
        risk_level: str = "routine",
    ) -> float:
        """Adapt selection utility for validated low-risk skills only.

        Safety-critical, high-risk and emergency skills stay at neutral utility;
        changing their content or activation requires the offline review path.
        """
        if skill_id in PROTECTED_SKILLS or risk_level in {"high", "emergency"}:
            return 1.0
        positives = 0
        negatives = 0
        safe_id = _safe(skill_id)
        for record in self._load().get("feedback_by_run", {}).values():
            if safe_id not in record.get("skills", []):
                continue
            if record.get("value") == "up":
                positives += 1
            elif record.get("value") == "down":
                negatives += 1
        sample_size = positives + negatives
        if sample_size < self.config.EVOLUTION_MIN_FEEDBACK_SAMPLES:
            return 1.0
        rate = (positives + 2) / (sample_size + 4)
        bound = self.config.EVOLUTION_SKILL_RANKING_BOUND
        adjustment = bound * ((rate - 0.5) / 0.5)
        return min(1.0 + bound, max(1.0 - bound, 1.0 + adjustment))

    @staticmethod
    def _candidate_id(kind: str, target: str) -> str:
        digest = hashlib.sha256(f"{kind}:{target}".encode()).hexdigest()[:24]
        return f"continuous_{digest}"

    def _refresh_candidates(self, state: dict[str, Any]) -> None:
        minimum = self.config.EVOLUTION_MIN_FEEDBACK_SAMPLES
        threshold = self.config.EVOLUTION_NEGATIVE_RATE_THRESHOLD
        now = utc_now()
        aggregates: dict[tuple[str, str], list[str]] = defaultdict(list)
        for record in state.get("feedback_by_run", {}).values():
            value = record.get("value")
            for skill_id in record.get("skills", []):
                aggregates[("skill", _safe(skill_id))].append(value)
            for memory in record.get("memories", []):
                if isinstance(memory, dict):
                    aggregates[
                        ("memory_retrieval", _safe(memory.get("category")))
                    ].append(value)
        memory_actions: dict[str, list[str]] = defaultdict(list)
        for action in state.get("memory_actions", []):
            if action.get("action") in {"confirmed", "rejected"}:
                memory_actions[_safe(action.get("category"))].append(action["action"])
        for category, actions in memory_actions.items():
            aggregates[("memory_extraction", category)].extend(
                "up" if action == "confirmed" else "down"
                for action in actions
            )
        for outcome in state.get("outcomes_by_run", {}).values():
            if outcome.get("status") != RunStatus.FAILED.value:
                continue
            target = _safe(outcome.get("error_code"))
            aggregates[("runtime", target)].append("down")

        candidates = state.setdefault("candidates", {})
        for (kind, target), outcomes in aggregates.items():
            sample_size = len(outcomes)
            negative_rate = outcomes.count("down") / max(sample_size, 1)
            if sample_size < minimum or negative_rate < threshold:
                continue
            identifier = self._candidate_id(kind, target)
            existing = candidates.get(identifier, {})
            if kind == "skill":
                paths = [f"skills/{target}/"]
                trigger = "该技能关联回答的重复负反馈达到候选门槛"
            elif kind == "memory_retrieval":
                paths = ["app/services/state.py"]
                trigger = "该类已确认记忆的召回与重复负反馈相关"
            elif kind == "memory_extraction":
                paths = ["app/services/state.py"]
                trigger = "该类记忆候选被用户重复拒绝"
            else:
                paths = ["app/runtime/"]
                trigger = "相同运行失败码重复出现"
            candidate = ContinuousEvolutionCandidate(
                id=identifier,
                kind=kind,
                target=target,
                sample_size=sample_size,
                negative_rate=negative_rate,
                trigger=trigger,
                allowed_mutation_paths=paths,
                status=existing.get("status", "ready_for_offline_evaluation"),
                requires_human_approval=True,
                created_at=existing.get("created_at", now),
                updated_at=now,
            )
            candidates[identifier] = candidate.model_dump(mode="json")

    async def status(self) -> ContinuousEvolutionStatus:
        async with self._lock:
            state = self._load()
            self._refresh_candidates(state)
            self._save(state)
        candidates = [
            ContinuousEvolutionCandidate.model_validate(item)
            for item in state.get("candidates", {}).values()
        ]
        candidates.sort(key=lambda item: item.updated_at, reverse=True)
        return ContinuousEvolutionStatus(
            signal_count=int(state.get("signal_count", 0)),
            feedback_count=len(state.get("feedback_by_run", {})),
            observed_run_count=len(state.get("outcomes_by_run", {})),
            ready_candidate_count=sum(
                item.status == "ready_for_offline_evaluation"
                for item in candidates
            ),
            memory_adaptation=(
                "已确认偏好/工作区记忆随显式反馈在线双向调整（±"
                f"{self.config.EVOLUTION_MEMORY_RANKING_BOUND:.0%}）；"
                "临床记忆不按粗粒度反馈重排"
            ),
            skill_adaptation=(
                "已验证低风险 Skill 随显式反馈在线排序/有界抑制（±"
                f"{self.config.EVOLUTION_SKILL_RANKING_BOUND:.0%}）；"
                "Skill 内容、权限及高风险变更仍需离线审核"
            ),
            production_mutation="disabled",
            human_approval_required=self.config.EVOLUTION_REQUIRE_HUMAN_APPROVAL,
            candidates=candidates,
        )

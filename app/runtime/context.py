"""Thread-scoped context packing with proactive, auditable compaction.

The harness decides *when* compaction is required. A dedicated model produces
the semantic summary, deterministic validators decide whether it is safe to
use, recent turns remain verbatim, and raw runs remain the recovery source.
ClinicalState and evidence provenance are never replaced by this summary.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.domain.models import (
    ContextStats,
    NodeContextCheckpoint,
    NodeStatus,
    PlanNode,
    RunInput,
    RunRecord,
    RunStatus,
    TaskRoute,
    utc_now,
)
from app.runtime.errors import BudgetExceeded, ContextCompactionError

if TYPE_CHECKING:
    from app.runtime.store import RuntimeStore


_TERMINAL_WITH_ANSWER = {
    RunStatus.COMPLETED,
    RunStatus.COMPLETED_WITH_WARNINGS,
}
_CONTEXT_SOURCE_STATUSES = {
    *_TERMINAL_WITH_ANSWER,
    RunStatus.WAITING,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}
_EVIDENCE_ID = re.compile(r"\[ev_[A-Za-z0-9_-]+\]")
_HIGH_VALUE_USER_TURN = re.compile(
    r"(不是|更正|纠正|改为|撤回|已停|停用|过敏|左眼|右眼|双眼|"
    r"\d+(?:\.\d+)?\s*(?:mg|g|ml|mmHg|次|片|滴|天|周|月|年))",
    re.IGNORECASE,
)
_SUMMARY_CLINICAL_DETAIL = re.compile(
    r"(左眼|右眼|双眼|过敏|已停药|已停用|正在服用|"
    r"\d+(?:\.\d+)?\s*(?:mg|g|ml|mmHg|次|片|滴|天|周|月|年))",
    re.IGNORECASE,
)


def _encoding_for_model(model_name: str):
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def _token_count(text: str, model_name: str) -> int:
    if not text:
        return 0
    return len(_encoding_for_model(model_name).encode(text))


def _truncate(text: str, max_tokens: int, model_name: str) -> str:
    if not text or max_tokens <= 0:
        return ""
    encoding = _encoding_for_model(model_name)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text.strip()
    suffix = "…"
    suffix_tokens = encoding.encode(suffix)
    keep = max(0, max_tokens - len(suffix_tokens))
    return encoding.decode(tokens[:keep]).rstrip() + suffix


class ConversationTurn(BaseModel):
    run_id: str
    query: str
    answer: str
    created_at: datetime
    route: TaskRoute | None = None


class ConversationSummary(BaseModel):
    """Auditable, non-clinical working summary produced by the compactor."""

    version: Literal["v1"] = "v1"
    summary: str = Field(min_length=1)
    user_goals: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    source_run_ids: list[str] = Field(default_factory=list)


class ConversationContextSnapshot(BaseModel):
    id: str
    run_id: str
    user_id: int
    conversation_id: int
    source_hash: str
    prompt_text: str = ""
    clinical_text: str = ""
    source_run_ids: list[str] = Field(default_factory=list)
    retained_source_run_ids: list[str] = Field(default_factory=list)
    previous_run_id: str | None = None
    previous_query: str | None = None
    previous_route: TaskRoute | None = None
    summary: ConversationSummary | None = None
    compaction_status: Literal[
        "not_needed",
        "pending",
        "completed",
        "failed",
    ] = "not_needed"
    compaction_issues: list[str] = Field(default_factory=list)
    stats: ContextStats = Field(default_factory=ContextStats)
    created_at: datetime = Field(default_factory=utc_now)


class ConversationContextManager:
    def __init__(self, store: RuntimeStore, config: Settings) -> None:
        self.store = store
        self.config = config

    async def build(
        self,
        *,
        run_id: str,
        user_id: int,
        run_input: RunInput,
    ) -> ConversationContextSnapshot | None:
        conversation_id = run_input.conversation_id
        if conversation_id is None:
            return None

        excluded = await self._regeneration_ancestors(run_input.regenerated_from)
        runs = await self.store.list_conversation_runs(
            user_id,
            conversation_id,
            limit=self.config.CONTEXT_MAX_SOURCE_TURNS * 3,
        )
        turns = self._latest_answer_versions(runs, excluded)
        if len(turns) > self.config.CONTEXT_MAX_SOURCE_TURNS:
            turns = turns[-self.config.CONTEXT_MAX_SOURCE_TURNS :]

        source_signature = "|".join(
            f"{turn.run_id}:{next(item.version for item in runs if item.id == turn.run_id)}"
            for turn in turns
        )
        source_hash = hashlib.sha256(source_signature.encode("utf-8")).hexdigest()
        cache_key = self._cache_key(user_id, conversation_id, source_hash)
        cached = await self.store.find_context_snapshot(
            user_id,
            conversation_id,
            cache_key,
        )
        if cached is not None and cached.get("compaction_status") in {
            "not_needed",
            "completed",
        }:
            snapshot = ConversationContextSnapshot.model_validate(cached).model_copy(
                update={
                    "id": f"ctx_{run_id.removeprefix('run_')}",
                    "run_id": run_id,
                    "stats": ContextStats.model_validate(cached["stats"]).model_copy(
                        update={"cache_hit": True},
                    ),
                    "created_at": utc_now(),
                },
            )
            return snapshot

        (
            prompt_text,
            retained_source_run_ids,
            compaction_status,
            stats,
        ) = self._pack_initial(turns, source_hash)
        previous = turns[-1] if turns else None
        snapshot = ConversationContextSnapshot(
            id=f"ctx_{run_id.removeprefix('run_')}",
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            source_hash=source_hash,
            prompt_text=prompt_text,
            # ClinicalState, not historical prose, is the clinical fact channel.
            clinical_text="",
            source_run_ids=[turn.run_id for turn in turns],
            retained_source_run_ids=retained_source_run_ids,
            previous_run_id=previous.run_id if previous else None,
            previous_query=previous.query if previous else None,
            previous_route=previous.route if previous else None,
            compaction_status=compaction_status,
            stats=stats,
        )
        return snapshot

    def cache_key(self, snapshot: ConversationContextSnapshot) -> str:
        return self._cache_key(
            snapshot.user_id,
            snapshot.conversation_id,
            snapshot.source_hash,
        )

    def _cache_key(
        self,
        user_id: int,
        conversation_id: int,
        source_hash: str,
    ) -> str:
        return hashlib.sha256(
            (
                f"context-v2:{user_id}:{conversation_id}:{source_hash}:"
                f"{self.config.main_model_name}:"
                f"{self.config.CONVERSATION_CONTEXT_MAX_INPUT_TOKENS}:"
                f"{self.config.CONTEXT_RECENT_TURNS}:"
                f"{self.config.CONTEXT_COMPRESSION_TRIGGER_RATIO}:"
                f"{self.config.CONTEXT_SUMMARY_MAX_TOKENS}"
            ).encode()
        ).hexdigest()

    async def _regeneration_ancestors(self, run_id: str | None) -> set[str]:
        excluded: set[str] = set()
        cursor = run_id
        while cursor and cursor not in excluded:
            excluded.add(cursor)
            run = await self.store.get_run(cursor)
            cursor = run.input.regenerated_from if run is not None else None
        return excluded

    @staticmethod
    def _latest_answer_versions(
        runs: list[RunRecord],
        excluded: set[str],
    ) -> list[ConversationTurn]:
        candidates = [
            run
            for run in runs
            if run.id not in excluded
            and run.status in _CONTEXT_SOURCE_STATUSES
            and bool(run.input.query.strip())
        ]
        by_id = {run.id: run for run in candidates}

        def family_root(run: RunRecord) -> str:
            cursor = run
            seen: set[str] = set()
            while cursor.input.regenerated_from and cursor.input.regenerated_from not in seen:
                seen.add(cursor.id)
                parent = by_id.get(cursor.input.regenerated_from)
                if parent is None:
                    return cursor.input.regenerated_from
                cursor = parent
            return cursor.id

        latest: dict[str, RunRecord] = {}
        for run in candidates:
            root = family_root(run)
            current = latest.get(root)
            if current is None or (run.created_at, run.version) > (
                current.created_at,
                current.version,
            ):
                latest[root] = run
        selected = sorted(latest.values(), key=lambda item: item.created_at)
        return [
            ConversationTurn(
                run_id=run.id,
                query=run.input.query,
                answer=run.answer or "",
                created_at=run.created_at,
                route=run.route,
            )
            for run in selected
        ]

    def _pack_initial(
        self,
        turns: list[ConversationTurn],
        source_hash: str,
    ) -> tuple[str, list[str], Literal["not_needed", "pending"], ContextStats]:
        """Keep full history below the trigger; otherwise stage model compaction."""

        model = self.config.main_model_name
        max_tokens = self.config.CONVERSATION_CONTEXT_MAX_INPUT_TOKENS
        all_text = "\n".join(f"{item.query}\n{item.answer}" for item in turns)
        tokens_before = _token_count(all_text, model)
        prefix = self._history_prefix()
        full_prompt = self._render_history(prefix, None, turns)
        trigger = max(
            256,
            int(
                max_tokens
                * min(0.95, max(0.5, self.config.CONTEXT_COMPRESSION_TRIGGER_RATIO))
            ),
        )
        if _token_count(full_prompt, model) <= trigger:
            prompt_text = full_prompt
            retained = [turn.run_id for turn in turns]
            status: Literal["not_needed", "pending"] = "not_needed"
        else:
            # Select complete recent turns from newest to oldest. A turn is
            # either retained verbatim or summarized; it is never silently cut.
            recent_limit = max(256, int(max_tokens * 0.56))
            recent_ids = {
                turn.run_id
                for turn in turns[-self.config.CONTEXT_RECENT_TURNS :]
            }
            candidates = [
                turn
                for turn in turns
                if turn.run_id in recent_ids or _HIGH_VALUE_USER_TURN.search(turn.query)
            ]
            selected: list[ConversationTurn] = []
            for turn in reversed(candidates):
                candidate = [turn, *selected]
                is_mandatory = bool(_HIGH_VALUE_USER_TURN.search(turn.query))
                if (
                    not is_mandatory
                    and _token_count(self._render_recent(candidate), model) > recent_limit
                ):
                    continue
                selected = candidate
            prompt_text = self._render_history(prefix, None, selected)
            retained = [turn.run_id for turn in selected]
            status = "pending"

        tokens_after = _token_count(prompt_text, model)
        stats = ContextStats(
            source_turns=len(turns),
            retained_turns=len(retained),
            summarized_turns=0,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            cache_hit=False,
            source_hash=source_hash,
            compaction_status=status,
            compaction_method="none",
        )
        return prompt_text, retained, status, stats

    async def compaction_prompt(
        self,
        snapshot: ConversationContextSnapshot,
        *,
        previous_issues: list[str] | None = None,
    ) -> str:
        """Build a bounded source prompt; fail before the provider call if unsafe."""

        turns = await self._source_turns_for_snapshot(snapshot)
        retained = set(snapshot.retained_source_run_ids)
        source_turns = [turn for turn in turns if turn.run_id not in retained]
        source_rows = [
            {
                "run_id": turn.run_id,
                "created_at": turn.created_at.isoformat(),
                "user": turn.query,
                "historical_assistant_unverified": _EVIDENCE_ID.sub("", turn.answer),
            }
            for turn in source_turns
        ]
        source_json = json.dumps(source_rows, ensure_ascii=False, separators=(",", ":"))
        source_tokens = _token_count(source_json, self.config.main_model_name)
        if source_tokens > self.config.CONTEXT_COMPACTION_SOURCE_MAX_TOKENS:
            raise ContextCompactionError(
                "待压缩原始历史超过 compaction 输入上限；需要从原始检查点分段恢复后重试",
                issues=[
                    "compaction_source_overflow",
                    (
                        f"source_tokens={source_tokens},"
                        f"limit={self.config.CONTEXT_COMPACTION_SOURCE_MAX_TOKENS}"
                    ),
                ],
            )
        expected_ids = [turn.run_id for turn in source_turns]
        retained_ids = set(snapshot.retained_source_run_ids)
        retained_turns = [
            turn
            for turn in turns
            if turn.run_id in retained_ids
        ]
        fixed_tokens = _token_count(
            self._render_history(self._history_prefix(), None, retained_turns),
            self.config.main_model_name,
        )
        summary_target = max(
            80,
            min(
                self.config.CONTEXT_SUMMARY_MAX_TOKENS,
                self.config.CONVERSATION_CONTEXT_MAX_INPUT_TOKENS - fixed_tokens - 32,
            ),
        )
        correction = ""
        if previous_issues:
            correction = (
                "\n上一版摘要未通过校验，必须修正以下问题："
                + json.dumps(previous_issues, ensure_ascii=False)
            )
        return (
            "把 <conversation_data> 中的历史压缩为低权限工作摘要。"
            "不得新增、确认或修改临床事实；不得生成 evidence id；"
            "不得把历史助手回答当作事实。必须保留用户目标、明确纠正、"
            "已作决定和未解决事项。source_run_ids 必须与 expected_source_run_ids"
            " 完全相同且顺序一致。"
            f"整个输出 JSON 必须尽量控制在 {summary_target} tokens 以内。"
            "只输出一个 JSON 对象："
            '{"version":"v1","summary":"string","user_goals":["string"],'
            '"decisions":["string"],"unresolved_items":["string"],'
            '"corrections":["string"],"source_run_ids":["run_id"]}'
            f"\nexpected_source_run_ids={json.dumps(expected_ids, ensure_ascii=False)}"
            f"{correction}\n<conversation_data>{source_json}</conversation_data>"
        )

    async def complete_compaction(
        self,
        snapshot: ConversationContextSnapshot,
        raw_summary: dict[str, Any],
        *,
        attempt: int,
    ) -> ConversationContextSnapshot:
        """Validate a generated summary and construct the canonical model input."""

        try:
            summary = ConversationSummary.model_validate(raw_summary)
        except Exception as exc:
            raise ContextCompactionError(
                "摘要不是合法的结构化 JSON",
                issues=["invalid_summary_schema", str(exc)[:300]],
            ) from exc
        turns = await self._source_turns_for_snapshot(snapshot)
        retained_ids = set(snapshot.retained_source_run_ids)
        expected_ids = [
            turn.run_id for turn in turns if turn.run_id not in retained_ids
        ]
        issues: list[str] = []
        if summary.source_run_ids != expected_ids:
            issues.append("source_run_ids_mismatch")
        summary_json = summary.model_dump_json()
        if _EVIDENCE_ID.search(summary_json):
            issues.append("summary_must_not_emit_evidence_ids")
        if _SUMMARY_CLINICAL_DETAIL.search(summary_json):
            issues.append("clinical_detail_must_stay_in_lossless_context")
        summary_tokens = _token_count(summary_json, self.config.main_model_name)
        if summary_tokens > self.config.CONTEXT_SUMMARY_MAX_TOKENS:
            issues.append(
                f"summary_token_overflow:{summary_tokens}>"
                f"{self.config.CONTEXT_SUMMARY_MAX_TOKENS}"
            )
        retained_turns = [
            turn for turn in turns if turn.run_id in retained_ids
        ]
        prompt_text = self._render_history(
            self._history_prefix(),
            summary,
            retained_turns,
        )
        prompt_tokens = _token_count(prompt_text, self.config.main_model_name)
        if prompt_tokens > self.config.CONVERSATION_CONTEXT_MAX_INPUT_TOKENS:
            issues.append(
                f"compacted_context_overflow:{prompt_tokens}>"
                f"{self.config.CONVERSATION_CONTEXT_MAX_INPUT_TOKENS}"
            )
        if issues:
            raise ContextCompactionError(
                "模型摘要未通过确定性校验",
                issues=issues,
            )
        stats = snapshot.stats.model_copy(
            update={
                "retained_turns": len(retained_turns),
                "summarized_turns": len(expected_ids),
                "tokens_after": prompt_tokens,
                "compaction_status": "completed",
                "compaction_method": "model_structured_summary",
                "compaction_attempts": attempt,
            },
        )
        return snapshot.model_copy(
            update={
                "prompt_text": prompt_text,
                "summary": summary,
                "compaction_status": "completed",
                "compaction_issues": [],
                "stats": stats,
                "created_at": utc_now(),
            },
        )

    def mark_compaction_failed(
        self,
        snapshot: ConversationContextSnapshot,
        issues: list[str],
        *,
        attempts: int,
    ) -> ConversationContextSnapshot:
        stats = snapshot.stats.model_copy(
            update={
                "compaction_status": "failed",
                "compaction_attempts": attempts,
            },
        )
        return snapshot.model_copy(
            update={
                "compaction_status": "failed",
                "compaction_issues": issues,
                "stats": stats,
                "created_at": utc_now(),
            },
        )

    async def _source_turns_for_snapshot(
        self,
        snapshot: ConversationContextSnapshot,
    ) -> list[ConversationTurn]:
        runs = await self.store.list_conversation_runs(
            snapshot.user_id,
            snapshot.conversation_id,
            limit=self.config.CONTEXT_MAX_SOURCE_TURNS * 3,
        )
        turns = self._latest_answer_versions(runs, set())
        by_id = {turn.run_id: turn for turn in turns}
        selected = [
            by_id[run_id]
            for run_id in snapshot.source_run_ids
            if run_id in by_id
        ]
        if [turn.run_id for turn in selected] != snapshot.source_run_ids:
            raise ContextCompactionError(
                "压缩源 Run 已变化或缺失，不能使用旧摘要",
                issues=["compaction_source_changed"],
            )
        return selected

    @staticmethod
    def _history_prefix() -> str:
        return (
            "以下是同一会话的历史，只用于理解指代、纠偏与连续任务。"
            "模型摘要和历史助手回答均不是临床事实；临床事实只能来自本轮明确输入、"
            "结构化 ClinicalState 与可追踪证据。"
        )

    @staticmethod
    def _render_recent(turns: list[ConversationTurn]) -> str:
        return "\n\n".join(
            (
                f"[历史原文 run_id={turn.run_id}]\n"
                f"用户：{turn.query}\n"
                f"历史助手回答（待核验）：{_EVIDENCE_ID.sub('', turn.answer)}"
            )
            for turn in turns
        )

    def _render_history(
        self,
        prefix: str,
        summary: ConversationSummary | None,
        retained_turns: list[ConversationTurn],
    ) -> str:
        sections = [prefix]
        if summary is not None:
            sections.append(
                "较早对话的模型压缩摘要（低权限、待核验）：\n"
                + summary.model_dump_json()
            )
        recent_text = self._render_recent(retained_turns)
        if recent_text:
            sections.append("高价值历史原文：\n" + recent_text)
        return "\n\n".join(sections) if retained_turns or summary is not None else ""


class NodeExecutionContext(BaseModel):
    """Bounded dependency context rebuilt deterministically at every node start."""

    payload: dict[str, Any] = Field(default_factory=dict)
    prompt_payload: dict[str, Any] = Field(default_factory=dict)
    checkpoint: NodeContextCheckpoint


_CONTEXT_KEY_PRIORITY = {
    "red_flags": 0,
    "medications": 1,
    "allergies": 2,
    "imaging_observations": 3,
    "examinations": 4,
    "history": 5,
    "timeline": 6,
    "unresolved_questions": 7,
    "id": 8,
    "title": 5,
    "source": 6,
    "locator": 7,
    "verified": 8,
    "summary": 9,
    "observations": 10,
    "limitations": 11,
    "regions": 12,
    "differentials": 13,
    "recommended_actions": 14,
    "evidence": 15,
}

CLINICAL_SAFETY_FIELDS = (
    "chief_complaint",
    "chief_complaint_fact",
    "red_flags",
    "medications",
    "allergies",
    "timeline",
    "history",
    "examinations",
    "imaging_observations",
    "positives",
    "negatives",
    "unresolved_questions",
)


def clinical_safety_payload(state: Any) -> dict[str, Any]:
    """Return the shared, lossless clinical fact channel used by every role."""

    raw = state.model_dump(mode="json") if hasattr(state, "model_dump") else state
    if not isinstance(raw, dict):
        return {}
    return {
        key: raw[key]
        for key in CLINICAL_SAFETY_FIELDS
        if key in raw
    }


def _critical_context(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Extract lossless safety/provenance fields from dependency outputs."""
    critical: dict[str, Any] = {}
    preserved: list[str] = []
    clinical_output = raw.get("clinical")
    if isinstance(clinical_output, dict):
        state = clinical_output.get("clinical_state", clinical_output)
        if isinstance(state, dict):
            kept = {}
            for key in CLINICAL_SAFETY_FIELDS:
                if key in state:
                    kept[key] = state[key]
                    preserved.append(f"clinical.{key}")
            if kept:
                critical["clinical"] = (
                    {"clinical_state": kept}
                    if "clinical_state" in clinical_output
                    else kept
                )
    evidence_output = raw.get("evidence")
    if isinstance(evidence_output, dict) and isinstance(evidence_output.get("evidence"), list):
        items = []
        for item in evidence_output["evidence"]:
            if not isinstance(item, dict):
                continue
            items.append({
                key: item[key]
                for key in ("id", "source", "locator", "verified", "source_status")
                if key in item
            })
        if items:
            critical["evidence"] = {"evidence": items}
            for key in ("id", "source", "locator", "verified", "source_status"):
                if any(key in item for item in items):
                    preserved.append(f"evidence.{key}")
    imaging_output = raw.get("imaging")
    if isinstance(imaging_output, dict) and "regions" in imaging_output:
        critical["imaging"] = {"regions": imaging_output["regions"]}
        preserved.append("imaging.regions")
    return critical, preserved


def _merge_context(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_context(merged[key], value)
        else:
            merged[key] = value
    return merged


def _compact_context_value(
    value: Any,
    max_tokens: int,
    model_name: str,
) -> Any:
    """Compact valid JSON values while retaining safety and provenance keys first."""
    if max_tokens <= 0:
        return None
    serialized = json_dumps(value)
    if _token_count(serialized, model_name) <= max_tokens:
        return value
    if isinstance(value, str):
        return _truncate(value, max_tokens, model_name)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        if not value:
            return []
        result: list[Any] = []
        item_budget = max(12, max_tokens // min(len(value), 8))
        for item in value[:8]:
            compacted = _compact_context_value(item, item_budget, model_name)
            candidate = [*result, compacted]
            if _token_count(json_dumps(candidate), model_name) > max_tokens:
                break
            result.append(compacted)
        return result
    if isinstance(value, dict):
        ordered = sorted(
            value.items(),
            key=lambda item: (_CONTEXT_KEY_PRIORITY.get(str(item[0]), 100), str(item[0])),
        )
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(ordered):
            remaining_keys = max(1, len(ordered) - index)
            used = _token_count(json_dumps(result), model_name)
            remaining = max_tokens - used
            if remaining < 8:
                break
            compacted = _compact_context_value(
                item,
                max(8, remaining // remaining_keys),
                model_name,
            )
            candidate = {**result, str(key): compacted}
            if _token_count(json_dumps(candidate), model_name) <= max_tokens:
                result[str(key)] = compacted
        return result
    return _truncate(str(value), max_tokens, model_name)


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


class ExecutionContextManager:
    """Defines node hand-off, proactive compaction and reproducible checkpoints."""

    def __init__(self, config: Settings) -> None:
        self.config = config

    def build(
        self,
        run: RunRecord,
        node: PlanNode,
        *,
        token_limit: int | None = None,
    ) -> NodeExecutionContext:
        source_nodes = self._ancestor_ids(run, node)
        raw = {
            item.id: item.output
            for item in run.plan
            if item.id in source_nodes
            and item.status == NodeStatus.COMPLETED
            and item.output is not None
        }
        model = self.config.main_model_name
        limit = max(256, token_limit or self.config.CONTEXT_MAX_INPUT_TOKENS)
        trigger_ratio = min(
            0.95,
            max(0.5, self.config.CONTEXT_COMPRESSION_TRIGGER_RATIO),
        )
        soft_limit = max(256, int(limit * trigger_ratio))
        tokens_before = _token_count(json_dumps(raw), model)
        compressed = tokens_before > soft_limit
        prompt_payload = (
            _compact_context_value(raw, soft_limit, model)
            if compressed
            else raw
        )
        if not isinstance(prompt_payload, dict):
            prompt_payload = {}
        critical_payload, preserved_fields = _critical_context(raw)
        prompt_payload = _merge_context(prompt_payload, critical_payload)
        tokens_after = _token_count(json_dumps(prompt_payload), model)
        if tokens_after > soft_limit:
            raise BudgetExceeded(
                "红旗、用药、过敏、未解决问题或证据定位超过上下文安全预算；"
                "不能静默截断关键临床字段",
            )
        source_hash = hashlib.sha256(json_dumps(raw).encode()).hexdigest()
        checkpoint = NodeContextCheckpoint(
            id=(
                f"nctx_{run.id.removeprefix('run_')}_{node.id}_"
                f"{node.attempt}_{source_hash[:12]}"
            ),
            node_id=node.id,
            attempt=node.attempt,
            source_nodes=source_nodes,
            source_hash=source_hash,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            token_limit=limit,
            compressed=compressed,
            compression_reason=(
                "predicted_context_pressure"
                if compressed
                else None
            ),
            preserved_fields=preserved_fields,
        )
        return NodeExecutionContext(
            payload=raw,
            prompt_payload=prompt_payload,
            checkpoint=checkpoint,
        )

    @staticmethod
    def _ancestor_ids(run: RunRecord, node: PlanNode) -> list[str]:
        by_id = {item.id: item for item in run.plan}
        selected: set[str] = set()
        stack = list(node.depends_on)
        while stack:
            dependency = stack.pop()
            if dependency in selected:
                continue
            selected.add(dependency)
            parent = by_id.get(dependency)
            if parent is not None:
                stack.extend(parent.depends_on)
        return [item.id for item in run.plan if item.id in selected]

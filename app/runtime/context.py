"""Thread-scoped context packing with deterministic, auditable compaction.

The model never decides how much history to retain. The harness keeps recent
turns verbatim, compresses older turns extractively, and labels prior assistant
output as unverified history rather than clinical fact.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from app.runtime.store import RuntimeStore


_TERMINAL_WITH_ANSWER = {
    RunStatus.COMPLETED,
    RunStatus.COMPLETED_WITH_WARNINGS,
}
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_EVIDENCE_ID = re.compile(r"\[ev_[A-Za-z0-9_-]+\]")


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


def _compact_answer(answer: str, max_tokens: int, model_name: str) -> str:
    """Keep the first substantive paragraphs; never ask a model to count words."""

    answer = _EVIDENCE_ID.sub("", answer)
    paragraphs = [
        re.sub(r"\s+", " ", item).strip()
        for item in _PARAGRAPH_BREAK.split(answer)
        if item.strip() and not item.lstrip().startswith((">", "## 引用", "## 免责声明"))
    ]
    selected = " ".join(paragraphs[:2]) or re.sub(r"\s+", " ", answer).strip()
    return _truncate(selected, max_tokens, model_name)


class ConversationTurn(BaseModel):
    run_id: str
    query: str
    answer: str
    created_at: datetime
    route: TaskRoute | None = None


class ConversationContextSnapshot(BaseModel):
    id: str
    run_id: str
    user_id: int
    conversation_id: int
    source_hash: str
    prompt_text: str = ""
    clinical_text: str = ""
    source_run_ids: list[str] = Field(default_factory=list)
    previous_run_id: str | None = None
    previous_query: str | None = None
    previous_route: TaskRoute | None = None
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
        cache_key = hashlib.sha256(
            (
                f"{user_id}:{conversation_id}:{source_hash}:"
                f"{self.config.main_model_name}:{self.config.CONTEXT_MAX_INPUT_TOKENS}:"
                f"{self.config.CONTEXT_RECENT_TURNS}"
            ).encode()
        ).hexdigest()
        cached = await self.store.find_context_snapshot(
            user_id,
            conversation_id,
            cache_key,
        )
        if cached is not None:
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

        prompt_text, clinical_text, stats = self._pack(turns, source_hash)
        previous = turns[-1] if turns else None
        snapshot = ConversationContextSnapshot(
            id=f"ctx_{run_id.removeprefix('run_')}",
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            source_hash=source_hash,
            prompt_text=prompt_text,
            clinical_text=clinical_text,
            source_run_ids=[turn.run_id for turn in turns],
            previous_run_id=previous.run_id if previous else None,
            previous_query=previous.query if previous else None,
            previous_route=previous.route if previous else None,
            stats=stats,
        )
        return snapshot

    def cache_key(self, snapshot: ConversationContextSnapshot) -> str:
        return hashlib.sha256(
            (
                f"{snapshot.user_id}:{snapshot.conversation_id}:{snapshot.source_hash}:"
                f"{self.config.main_model_name}:{self.config.CONTEXT_MAX_INPUT_TOKENS}:"
                f"{self.config.CONTEXT_RECENT_TURNS}"
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
            and run.status in _TERMINAL_WITH_ANSWER
            and bool((run.answer or "").strip())
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

    def _pack(
        self,
        turns: list[ConversationTurn],
        source_hash: str,
    ) -> tuple[str, str, ContextStats]:
        model = self.config.main_model_name
        max_tokens = self.config.CONTEXT_MAX_INPUT_TOKENS
        recent_count = min(self.config.CONTEXT_RECENT_TURNS, len(turns))
        older = turns[:-recent_count] if recent_count else turns
        recent = turns[-recent_count:] if recent_count else []
        all_text = "\n".join(f"{item.query}\n{item.answer}" for item in turns)
        tokens_before = _token_count(all_text, model)

        prefix = (
            "以下是同一会话的历史，只用于理解指代、纠偏与连续任务。"
            "历史助手回答不是临床事实；涉及医学结论时必须结合本轮资料重新核验。"
        )
        recent_budget = max(0, int(max_tokens * 0.72) - _token_count(prefix, model))
        summary_budget = max(0, max_tokens - recent_budget - _token_count(prefix, model))

        recent_blocks: list[str] = []
        per_recent = max(220, recent_budget // max(len(recent), 1))
        for index, turn in enumerate(recent, start=max(1, len(turns) - len(recent) + 1)):
            user = _truncate(turn.query, max(80, int(per_recent * 0.34)), model)
            assistant = _truncate(
                _EVIDENCE_ID.sub("", turn.answer),
                max(120, int(per_recent * 0.66)),
                model,
            )
            recent_blocks.append(
                f"[最近第 {index} 轮]\n用户：{user}\n历史助手回答（待核验）：{assistant}"
            )
        recent_text = _truncate("\n\n".join(recent_blocks), recent_budget, model)

        summary_blocks: list[str] = []
        per_summary = max(100, summary_budget // max(len(older), 1))
        for index, turn in enumerate(older, start=1):
            user = _truncate(turn.query, max(40, int(per_summary * 0.45)), model)
            assistant = _compact_answer(
                turn.answer,
                max(50, int(per_summary * 0.55)),
                model,
            )
            summary_blocks.append(
                f"- 第 {index} 轮用户任务：{user}；历史答复摘要（待核验）：{assistant}"
            )
        summary_text = _truncate("\n".join(summary_blocks), summary_budget, model)

        sections = [prefix]
        if summary_text:
            sections.append("较早对话压缩摘要：\n" + summary_text)
        if recent_text:
            sections.append("最近对话原文：\n" + recent_text)
        prompt_text = _truncate("\n\n".join(sections), max_tokens, model) if turns else ""

        clinical_lines = [
            "以下仅是同一会话中的历史用户陈述，不等于已确认临床事实；"
            "抽取时保留来源与不确定状态，不得沿用历史助手的诊断表述。"
        ]
        for turn in turns[-self.config.CONTEXT_RECENT_TURNS :]:
            clinical_lines.append(
                "- " + _truncate(turn.query, 240, model)
            )
        clinical_text = _truncate(
            "\n".join(clinical_lines) if turns else "",
            min(900, max_tokens),
            model,
        )
        tokens_after = _token_count(prompt_text, model)
        stats = ContextStats(
            source_turns=len(turns),
            retained_turns=len(recent),
            summarized_turns=len(older),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            cache_hit=False,
            source_hash=source_hash,
        )
        return prompt_text, clinical_text, stats


class NodeExecutionContext(BaseModel):
    """Bounded dependency context rebuilt deterministically at every node start."""

    payload: dict[str, Any] = Field(default_factory=dict)
    prompt_payload: dict[str, Any] = Field(default_factory=dict)
    checkpoint: NodeContextCheckpoint


_CONTEXT_KEY_PRIORITY = {
    "red_flags": 0,
    "medications": 1,
    "allergies": 2,
    "unresolved_questions": 3,
    "id": 4,
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
_PRESERVED_CONTEXT_FIELDS = [
    "clinical.red_flags",
    "clinical.medications",
    "clinical.allergies",
    "clinical.unresolved_questions",
    "evidence.id",
    "evidence.source",
    "evidence.locator",
    "imaging.regions",
]


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
        tokens_after = _token_count(json_dumps(prompt_payload), model)
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
            preserved_fields=_PRESERVED_CONTEXT_FIELDS,
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

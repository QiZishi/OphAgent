"""Persistent long-term memory and gated Skill registries."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import math
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import frontmatter

from app.core.config import Settings, settings
from app.domain.models import (
    ClinicalState,
    MemoryRecord,
    RiskLevel,
    SkillRecord,
    utc_now,
)
from app.services.memory_evolution import is_runtime_memory_content_allowed
from app.services.skill_policy import (
    SAFETY_CRITICAL_SKILLS,
    requires_offline_skill_review,
)

WORD_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+")
SKILL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")


class PersistentStateError(RuntimeError):
    """A durable state file exists but cannot be safely interpreted."""


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                value,
                temporary,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _tokens(value: str) -> set[str]:
    return {item.casefold() for item in WORD_PATTERN.findall(value)}


class MemoryStore:
    def __init__(self, config: Settings = settings, evolution: object | None = None) -> None:
        self.path = config.resolve_path(config.MEMORY_STATE_PATH)
        self.preference_path = config.resolve_path(config.MEMORY_PREFERENCE_PATH)
        self.evolution = evolution
        self._lock = asyncio.Lock()

    def _load(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []
        try:
            return [
                MemoryRecord.model_validate(item)
                for item in json.loads(self.path.read_text("utf-8"))
            ]
        except (OSError, ValueError, TypeError) as exc:
            raise PersistentStateError(
                f"Memory 状态文件损坏或不可读：{self.path}",
            ) from exc

    def _preferences(self) -> dict[str, bool]:
        if not self.preference_path.exists():
            return {}
        try:
            return {
                str(key): bool(value)
                for key, value in json.loads(
                    self.preference_path.read_text("utf-8"),
                ).items()
            }
        except (OSError, ValueError, TypeError) as exc:
            raise PersistentStateError(
                f"Memory 偏好状态文件损坏或不可读：{self.preference_path}",
            ) from exc

    async def enabled(self, user_id: int) -> bool:
        return self._preferences().get(str(user_id), True)

    async def set_enabled(self, user_id: int, enabled: bool) -> bool:
        async with self._lock:
            preferences = self._preferences()
            preferences[str(user_id)] = enabled
            atomic_json(self.preference_path, preferences)
        return enabled

    async def list(self, user_id: int) -> list[MemoryRecord]:
        return sorted(
            (record for record in self._load() if record.user_id == user_id),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    async def create(self, record: MemoryRecord) -> MemoryRecord:
        if not is_runtime_memory_content_allowed(record.content):
            raise ValueError("Memory 只能记录用户事实和偏好，不能修改系统或业务规则")
        normalized = _normalize(record.content)
        fingerprint = hashlib.sha256(
            f"{record.user_id}:{record.category}:{normalized}".encode(),
        ).hexdigest()
        record = record.model_copy(update={"fingerprint": fingerprint})
        async with self._lock:
            records = self._load()
            duplicate = next(
                (
                    item
                    for item in records
                    if item.user_id == record.user_id
                    and (
                        item.fingerprint == fingerprint
                        or (
                            item.category == record.category
                            and _normalize(item.content) == normalized
                        )
                    )
                ),
                None,
            )
            if duplicate:
                return duplicate
            conflict_ids = [
                item.id
                for item in records
                if record.key
                and item.user_id == record.user_id
                and item.key == record.key
                and item.status != "rejected"
                and _normalize(item.content) != normalized
            ]
            record = record.model_copy(update={"conflicts_with": conflict_ids})
            if conflict_ids:
                for index, existing in enumerate(records):
                    if existing.id in conflict_ids and record.id not in existing.conflicts_with:
                        records[index] = existing.model_copy(
                            update={
                                "conflicts_with": [*existing.conflicts_with, record.id],
                                "updated_at": utc_now(),
                            },
                        )
            records.append(record)
            atomic_json(self.path, [item.model_dump(mode="json") for item in records])
        return record

    async def upsert_mutable(
        self,
        *,
        user_id: int,
        category: str,
        content: str,
        source: str,
        key: str | None = None,
        target: str | None = None,
    ) -> tuple[MemoryRecord, str]:
        """Create or update explicit low-authority preference/workspace memory."""
        if category not in {"preference", "workspace"}:
            raise ValueError("在线 Memory CRUD 只允许偏好和工作区记忆")
        if not is_runtime_memory_content_allowed(content):
            raise ValueError("Memory 只能记录用户事实和偏好，不能修改系统或业务规则")
        normalized = _normalize(content)
        if not normalized:
            raise ValueError("Memory 内容不能为空")
        fingerprint = hashlib.sha256(
            f"{user_id}:{category}:{normalized}".encode(),
        ).hexdigest()
        target_normalized = _normalize(target or "")
        async with self._lock:
            records = self._load()
            existing_index: int | None = None
            for index, item in enumerate(records):
                if (
                    item.user_id != user_id
                    or item.category != category
                    or item.status == "rejected"
                ):
                    continue
                if key and item.key == key:
                    existing_index = index
                    break
                if target_normalized and target_normalized in _normalize(item.content):
                    existing_index = index
                    break
                if item.fingerprint == fingerprint:
                    existing_index = index
                    break
            if existing_index is None:
                record = MemoryRecord(
                    user_id=user_id,
                    category=category,
                    content=content,
                    source=source,
                    key=key,
                    fingerprint=fingerprint,
                    status="confirmed",
                    sensitivity="normal",
                    confirmation_note="用户明确指令在线创建",
                )
                records.append(record)
                action = "created"
            else:
                previous = records[existing_index]
                if (
                    _normalize(previous.content) == normalized
                    and previous.status == "confirmed"
                ):
                    return previous, "unchanged"
                record = previous.model_copy(
                    update={
                        "content": content,
                        "source": source,
                        "key": key or previous.key,
                        "fingerprint": fingerprint,
                        "status": "confirmed",
                        "sensitivity": "normal",
                        "conflicts_with": [],
                        "confirmation_note": "用户明确指令在线更新",
                        "updated_at": utc_now(),
                    },
                )
                records[existing_index] = record
                for index, item in enumerate(records):
                    if record.id in item.conflicts_with:
                        records[index] = item.model_copy(
                            update={
                                "conflicts_with": [
                                    conflict
                                    for conflict in item.conflicts_with
                                    if conflict != record.id
                                ],
                            },
                        )
                action = "updated"
            atomic_json(self.path, [item.model_dump(mode="json") for item in records])
            return record, action

    async def delete_mutable(
        self,
        *,
        user_id: int,
        category: str,
        content: str = "",
        key: str | None = None,
        clear_all: bool = False,
    ) -> list[MemoryRecord]:
        """Delete only low-authority memories selected by explicit user intent."""
        if category not in {"preference", "workspace"}:
            raise ValueError("在线 Memory CRUD 只允许偏好和工作区记忆")
        normalized = _normalize(content)
        async with self._lock:
            records = self._load()
            removed = [
                item
                for item in records
                if item.user_id == user_id
                and item.category == category
                and (
                    clear_all
                    or (key is not None and item.key == key)
                    or (normalized and normalized in _normalize(item.content))
                )
            ]
            if not removed:
                return []
            removed_ids = {item.id for item in removed}
            retained = [
                item.model_copy(
                    update={
                        "conflicts_with": [
                            conflict
                            for conflict in item.conflicts_with
                            if conflict not in removed_ids
                        ],
                    },
                )
                for item in records
                if item.id not in removed_ids
            ]
            atomic_json(self.path, [item.model_dump(mode="json") for item in retained])
            return removed

    async def purge_expired_mutable(self, user_id: int) -> list[MemoryRecord]:
        """Remove expired preference/workspace memory while retaining clinical history."""
        now = utc_now()
        async with self._lock:
            records = self._load()
            removed = [
                item
                for item in records
                if item.user_id == user_id
                and item.category in {"preference", "workspace"}
                and item.expires_at is not None
                and item.expires_at <= now
            ]
            if not removed:
                return []
            removed_ids = {item.id for item in removed}
            retained = [
                item.model_copy(
                    update={
                        "conflicts_with": [
                            conflict
                            for conflict in item.conflicts_with
                            if conflict not in removed_ids
                        ],
                    },
                )
                for item in records
                if item.id not in removed_ids
            ]
            atomic_json(self.path, [item.model_dump(mode="json") for item in retained])
            return removed

    async def update(self, memory_id: str, user_id: int, values: dict) -> MemoryRecord:
        async with self._lock:
            records = self._load()
            for index, record in enumerate(records):
                if record.id == memory_id and record.user_id == user_id:
                    allowed = {
                        key: value
                        for key, value in values.items()
                        if key in {
                            "content",
                            "status",
                            "expires_at",
                            "confirmation_note",
                        }
                    }
                    if "content" in allowed:
                        if not is_runtime_memory_content_allowed(
                            str(allowed["content"]),
                        ):
                            raise ValueError(
                                "Memory 只能记录用户事实和偏好，不能修改系统或业务规则",
                            )
                        normalized = _normalize(str(allowed["content"]))
                        allowed["fingerprint"] = hashlib.sha256(
                            f"{user_id}:{record.category}:{normalized}".encode(),
                        ).hexdigest()
                    updated = record.model_copy(
                        update={**allowed, "updated_at": utc_now()},
                    )
                    records[index] = MemoryRecord.model_validate(updated)
                    if record.key:
                        active = [
                            item
                            for item in records
                            if item.user_id == user_id
                            and item.key == record.key
                            and item.status != "rejected"
                        ]
                        active_ids = {item.id for item in active}
                        for item_index, item in enumerate(records):
                            if item.user_id != user_id or item.key != record.key:
                                continue
                            conflicts = (
                                [
                                    peer.id
                                    for peer in active
                                    if peer.id != item.id
                                    and _normalize(peer.content) != _normalize(item.content)
                                ]
                                if item.id in active_ids
                                else []
                            )
                            records[item_index] = item.model_copy(
                                update={"conflicts_with": conflicts},
                            )
                    atomic_json(
                        self.path,
                        [item.model_dump(mode="json") for item in records],
                    )
                    return records[index]
        raise KeyError(memory_id)

    async def delete(self, memory_id: str, user_id: int) -> None:
        async with self._lock:
            records = self._load()
            filtered = [
                item
                for item in records
                if not (item.id == memory_id and item.user_id == user_id)
            ]
            if len(filtered) == len(records):
                raise KeyError(memory_id)
            filtered = [
                item.model_copy(
                    update={
                        "conflicts_with": [
                            conflict
                            for conflict in item.conflicts_with
                            if conflict != memory_id
                        ],
                    },
                )
                for item in filtered
            ]
            atomic_json(self.path, [item.model_dump(mode="json") for item in filtered])

    async def search(
        self,
        user_id: int,
        query: str,
        *,
        categories: set[str] | None = None,
        limit: int = 8,
        allow_restricted: bool = False,
    ) -> list[MemoryRecord]:
        if not await self.enabled(user_id):
            return []
        now = utc_now()
        query_terms = _tokens(query)
        ranked: list[tuple[float, MemoryRecord]] = []
        records = await self.list(user_id)
        by_id = {record.id: record for record in records}
        for record in records:
            if record.status != "confirmed":
                continue
            if record.expires_at and record.expires_at <= now:
                continue
            if record.sensitivity == "restricted" and not allow_restricted:
                continue
            if categories and record.category not in categories:
                continue
            # Contradictory confirmed medical memories are withheld instead of
            # asking the model to guess which patient fact is current.
            if any(
                by_id.get(conflict_id)
                and by_id[conflict_id].status == "confirmed"
                for conflict_id in record.conflicts_with
            ):
                continue
            memory_terms = _tokens(record.content)
            overlap = (
                len(query_terms & memory_terms) / max(len(query_terms | memory_terms), 1)
                if query_terms
                else 0.0
            )
            age_days = max((now - record.updated_at).total_seconds() / 86400, 0)
            recency = math.exp(-age_days / 365)
            category_bonus = (
                0.22
                if categories and record.category in categories
                else 0.18 if record.category in {"preference", "workspace"} else 0.0
            )
            score = 0.68 * overlap + 0.20 * recency + category_bonus
            utility = getattr(self.evolution, "memory_utility_factor", None)
            if callable(utility):
                # Non-clinical preference/workspace records may move only
                # within a bounded ranking range; CRUD remains user-controlled.
                score *= float(utility(record.id, record.category))
            # Category-scoped recalls deliberately include safety-critical
            # history even when a terse follow-up has little lexical overlap.
            if overlap > 0 or category_bonus > 0:
                ranked.append((score, record))
        selected = [
            record
            for _, record in sorted(
                ranked,
                key=lambda item: (item[0], item[1].updated_at),
                reverse=True,
            )[:limit]
        ]
        if selected:
            selected_ids = {item.id for item in selected}
            async with self._lock:
                records = self._load()
                for index, record in enumerate(records):
                    if record.id in selected_ids:
                        records[index] = record.model_copy(
                            update={"last_accessed_at": now},
                        )
                atomic_json(
                    self.path,
                    [item.model_dump(mode="json") for item in records],
                )
        return selected

    async def propose_from_clinical_state(
        self,
        *,
        user_id: int,
        run_id: str,
        state: ClinicalState,
    ) -> list[MemoryRecord]:
        """Extract only durable medication/allergy candidates.

        Differential diagnoses and model assessments are intentionally excluded.
        """
        if not await self.enabled(user_id):
            return []
        candidates: list[MemoryRecord] = []
        for category, facts, label in (
            ("medication", state.medications, "当前用药"),
            ("allergy", state.allergies, "过敏史"),
        ):
            for fact in facts:
                value = fact.value.strip()
                if not value:
                    continue
                candidate = MemoryRecord(
                    user_id=user_id,
                    category=category,
                    content=f"{label}：{value}",
                    key=f"{category}:{_normalize(value)}",
                    source=f"run:{run_id}; {fact.source}",
                    status="proposed",
                    sensitivity="sensitive",
                )
                candidates.append(await self.create(candidate))
        return candidates


class SkillStore:
    """Skill registry with quarantine, deterministic validation and promotion."""

    EVALUATOR_VERSION = "1.0.0"

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.path = config.resolve_path(config.SKILL_STATE_PATH)
        self.root = config.resolve_path(config.SKILL_ROOT)
        self.candidate_root = self.root / ".candidates"
        self.evaluation_dir = config.resolve_path(config.SKILL_EVALUATION_DIR)
        self._lock = asyncio.Lock()

    def _states(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text("utf-8"))
            return {
                str(key): ({"status": value} if isinstance(value, str) else dict(value))
                for key, value in raw.items()
            }
        except (OSError, ValueError, TypeError) as exc:
            raise PersistentStateError(
                f"Skill 状态文件损坏或不可读：{self.path}",
            ) from exc

    async def list(self) -> list[SkillRecord]:
        states = self._states()
        records: list[SkillRecord] = []
        for skill_md in sorted(self.root.glob("**/SKILL.md")):
            try:
                post = frontmatter.load(skill_md)
                name = str(post.get("name") or skill_md.parent.name)
                risk = RiskLevel(str(post.get("risk_level") or "routine"))
            except (OSError, ValueError, TypeError):
                continue
            relative = skill_md.relative_to(self.root)
            default_status = "candidate" if ".candidates" in relative.parts else "enabled"
            state = states.get(name, {})
            evaluation = self._load_evaluation(name)
            records.append(
                SkillRecord(
                    id=name,
                    version=str(post.get("version") or "1.0.0"),
                    description=str(post.get("description") or ""),
                    path=(
                        str(skill_md.parent.relative_to(self.config.project_root))
                        if self.config.project_root in skill_md.parent.parents
                        else str(skill_md.parent)
                    ),
                    capabilities=list(post.get("capabilities") or []),
                    dependencies=list(post.get("dependencies") or []),
                    risk_level=risk,
                    plugins=list(post.get("plugins") or []),
                    status=state.get("status", default_status),
                    evaluation=evaluation,
                ),
            )
        return records

    def _load_evaluation(self, skill_id: str) -> dict:
        path = self.evaluation_dir / f"{skill_id}.json"
        if not path.is_file():
            return {}
        try:
            return dict(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError, TypeError):
            return {}

    @classmethod
    def _requires_offline_review(cls, skill: SkillRecord) -> bool:
        return requires_offline_skill_review(
            risk_level=skill.risk_level.value,
            dependencies=skill.dependencies,
            capabilities=skill.capabilities,
        )

    async def import_candidate(self, markdown: str) -> SkillRecord:
        if len(markdown.encode("utf-8")) > 100_000:
            raise ValueError("SKILL.md 超过 100 KB")
        try:
            post = frontmatter.loads(markdown)
        except Exception as exc:
            raise ValueError("SKILL.md frontmatter 无法解析") from exc
        skill_id = str(post.get("name") or "")
        version = str(post.get("version") or "")
        if not SKILL_ID_PATTERN.fullmatch(skill_id):
            raise ValueError("skill name 必须为安全的小写标识符")
        if not SEMVER_PATTERN.fullmatch(version):
            raise ValueError("候选 skill 必须提供 SemVer version")
        existing = {record.id for record in await self.list()}
        if skill_id in existing:
            raise ValueError("skill id 已存在；新版本应走离线版本迁移流程")
        target = self.candidate_root / skill_id / version / "SKILL.md"
        resolved_root = self.candidate_root.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if resolved_root not in target.resolve().parents:
            raise ValueError("非法 skill 路径")
        target.write_text(markdown, "utf-8")
        async with self._lock:
            states = self._states()
            states[skill_id] = {"status": "candidate"}
            atomic_json(self.path, states)
        return await self.list_by_id(skill_id)

    async def validate(self, skill_id: str) -> SkillRecord:
        skill = await self.list_by_id(skill_id)
        path = self.config.resolve_path(skill.path) / "SKILL.md"
        content = path.read_text("utf-8")
        known = {item.id for item in await self.list()}
        dependency_checks: dict[str, bool] = {}
        for dependency in skill.dependencies:
            if dependency.startswith("python:"):
                dependency_checks[dependency] = (
                    importlib.util.find_spec(dependency.split(":", 1)[1]) is not None
                )
            else:
                dependency_checks[dependency] = dependency in known
        unsafe_patterns = {
            "allows_canned_diagnosis": r"(?:允许|可以|直接)给出(?:预设|固定|无证据)诊断",
            "allows_fake_citations": r"(?:允许|可以|无需核验).{0,8}(?:伪造|编造)?引用",
            "ignores_safety": r"忽略.{0,8}(?:安全|红旗|急诊)",
            "allows_fake_coordinates": r"(?:允许|可以).{0,8}(?:猜测|伪造)坐标",
        }
        checks: dict[str, bool] = {
            "description_present": bool(skill.description.strip()),
            "content_heading_present": bool(re.search(r"^#\s+\S+", content, re.MULTILINE)),
            "dependencies_available": all(dependency_checks.values()),
            "no_unsafe_instruction": not any(
                re.search(pattern, content)
                for pattern in unsafe_patterns.values()
            ),
            "evidence_or_uncertainty_contract": any(
                token in content
                for token in ("证据", "引用", "不确定", "不能替代", "不得宣称确诊")
            ),
        }
        if skill.risk_level in {RiskLevel.HIGH, RiskLevel.EMERGENCY}:
            checks["high_risk_escalation"] = any(
                token in content for token in ("急诊", "转诊", "线下眼科")
            )
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        report = {
            "evaluator_version": self.EVALUATOR_VERSION,
            "skill_id": skill_id,
            "skill_version": skill.version,
            "checksum": checksum,
            "evaluated_at": datetime.now(UTC).isoformat(),
            "passed": all(checks.values()),
            "offline_review_required": self._requires_offline_review(skill),
            "checks": checks,
            "risks": [
                {
                    "code": key,
                    "message": {
                        "description_present": "缺少用途说明",
                        "content_heading_present": "缺少可识别的正文标题",
                        "dependencies_available": "声明的依赖当前不可用",
                        "no_unsafe_instruction": "检测到可能绕过诊断、引用、红旗或坐标安全规则的指令",
                        "evidence_or_uncertainty_contract": "未声明证据或不确定性约束",
                        "high_risk_escalation": "高风险能力未声明急诊、转诊或线下复核路径",
                    }.get(key, f"安全检查未通过：{key}"),
                }
                for key, passed in checks.items()
                if not passed
            ],
            "dependency_checks": dependency_checks,
            "scope": "结构、依赖与医疗安全静态回归；不等同于完整病例效果评测",
        }
        self.evaluation_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(self.evaluation_dir / f"{skill_id}.json", report)
        async with self._lock:
            states = self._states()
            states[skill_id] = {
                "status": "validated" if report["passed"] else "rejected",
                "checksum": checksum,
            }
            atomic_json(self.path, states)
        return await self.list_by_id(skill_id)

    async def approve_offline(self, skill_id: str, reviewer: str) -> SkillRecord:
        """Bind trusted offline review to the exact validated Skill checksum."""
        reviewer = reviewer.strip()
        if not reviewer or len(reviewer) > 120:
            raise ValueError("离线审批人标识不合法")
        skill = await self.list_by_id(skill_id)
        report = self._load_evaluation(skill_id)
        path = self.config.resolve_path(skill.path) / "SKILL.md"
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if (
            skill.status != "validated"
            or not report.get("passed")
            or report.get("checksum") != checksum
        ):
            raise ValueError("Skill 必须先通过与当前内容匹配的验证")
        if self._requires_offline_review(skill):
            report["offline_approval"] = {
                "reviewer": reviewer,
                "checksum": checksum,
                "approved_at": datetime.now(UTC).isoformat(),
            }
            atomic_json(self.evaluation_dir / f"{skill_id}.json", report)
        return await self.list_by_id(skill_id)

    async def set_status(
        self,
        skill_id: str,
        status: str,
        *,
        force: bool = False,
        approved_by: str | None = None,
        acknowledgement: str | None = None,
    ) -> SkillRecord:
        if status not in {"enabled", "disabled", "rejected"}:
            raise ValueError("validated 状态只能由评测接口写入")
        if skill_id in SAFETY_CRITICAL_SKILLS and status != "enabled":
            raise ValueError("安全关键 Skill 不能通过在线接口停用或拒绝")
        skill = await self.list_by_id(skill_id)
        if status == "enabled":
            is_candidate = ".candidates" in Path(skill.path).parts
            report = self._load_evaluation(skill_id)
            path = self.config.resolve_path(skill.path) / "SKILL.md"
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if is_candidate and (
                not report
                or report.get("checksum") != checksum
            ):
                raise ValueError("候选 skill 必须通过与当前内容匹配的评测")
            offline_approval = report.get("offline_approval")
            has_matching_offline_approval = (
                isinstance(offline_approval, dict)
                and offline_approval.get("checksum") == checksum
                and bool(offline_approval.get("reviewer"))
            )
            user_approval = report.get("user_approval")
            has_matching_user_approval = (
                isinstance(user_approval, dict)
                and user_approval.get("checksum") == checksum
                and bool(user_approval.get("reviewer"))
                and bool(user_approval.get("acknowledgement"))
            )
            needs_risk_approval = is_candidate and (
                not has_matching_user_approval
                and (
                    not report.get("passed")
                    or (
                        self._requires_offline_review(skill)
                        and not has_matching_offline_approval
                    )
                )
            )
            if needs_risk_approval and not force:
                risks = [
                    str(item.get("message"))
                    for item in report.get("risks", [])
                    if isinstance(item, dict) and item.get("message")
                ]
                if self._requires_offline_review(skill):
                    risks.append("该 Skill 涉及高风险能力、外部依赖或工具调用")
                detail = "；".join(dict.fromkeys(risks)) or "检测到需要用户审批的风险"
                raise ValueError(f"{detail}。确认风险后可强制加载")
            if needs_risk_approval and force:
                reviewer = str(approved_by or "").strip()
                note = str(acknowledgement or "").strip()
                if not reviewer or not note:
                    raise ValueError("强制加载必须记录审批用户和风险确认说明")
                report["user_approval"] = {
                    "reviewer": reviewer,
                    "checksum": checksum,
                    "acknowledgement": note,
                    "known_risks": report.get("risks", []),
                    "approved_at": datetime.now(UTC).isoformat(),
                }
                atomic_json(self.evaluation_dir / f"{skill_id}.json", report)
        async with self._lock:
            states = self._states()
            previous = states.get(skill_id, {})
            states[skill_id] = {**previous, "status": status}
            atomic_json(self.path, states)
        return await self.list_by_id(skill_id)

    async def list_by_id(self, skill_id: str) -> SkillRecord:
        for record in await self.list():
            if record.id == skill_id:
                return record
        raise KeyError(skill_id)

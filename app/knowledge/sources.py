"""Source registry and lifecycle metadata for the local evidence corpus."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings, settings
from app.domain.models import KnowledgeSource
from app.services.state import PersistentStateError

YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")
LOW_TRUST_PREFIXES = ("baidubaike_", "xywy_", "dxy_")
GUIDELINE_MARKERS = (
    "指南",
    "专家共识",
    "诊疗规范",
    "操作规范",
    "preferred practice pattern",
    "clinical practice guideline",
    " ppp",
)
_REGISTRY_LOCKS: dict[str, threading.RLock] = {}
_REGISTRY_LOCKS_GUARD = threading.Lock()


def portable_path(path: Path, config: Settings) -> str:
    try:
        return str(path.relative_to(config.project_root))
    except ValueError:
        return str(path)


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
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
            json.dump(value, temporary, ensure_ascii=False, indent=2, default=str)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _registry_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _REGISTRY_LOCKS_GUARD:
        return _REGISTRY_LOCKS.setdefault(key, threading.RLock())


def _infer_metadata(path: Path, config: Settings) -> KnowledgeSource:
    title = path.stem.strip()
    year = YEAR_PATTERN.search(title)
    institution: str | None = None
    region: str | None = None
    lowered = title.lower()
    source_type = (
        "guideline"
        if any(marker in lowered for marker in GUIDELINE_MARKERS)
        else "record"
    )
    if lowered.startswith(LOW_TRUST_PREFIXES):
        source_type = "record"
    if "美国眼科学会" in title or "aao" in lowered:
        institution, region = "美国眼科学会", "美国"
    elif any(marker in title for marker in ("中国", "中华", "国家", "我国")):
        institution, region = "来源文件待进一步核验", "中国"
    return KnowledgeSource(
        id=f"src_{uuid4().hex}",
        title=title,
        path=portable_path(path, config),
        source_type=source_type,
        institution=institution,
        region=region,
        published_at=year.group(0) if year else None,
        version=year.group(0) if year else None,
        status="unknown",
        # Files shipped in the built-in corpus are trusted by the product
        # baseline. User imports take the separate register_upload path and
        # always start private and unverified.
        verified=True,
        checksum=file_checksum(path),
    )


class SourceRegistry:
    """Persist source provenance separately from generated retrieval indexes."""

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.raw_dir = config.resolve_path(config.KNOWLEDGE_RAW_DIR)
        self.index_dir = config.resolve_path(config.KNOWLEDGE_INDEX_DIR)
        self.path = self.index_dir / "sources.json"
        self._lock = _registry_lock(self.path)

    def _load(self) -> list[KnowledgeSource]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text("utf-8"))
            return [KnowledgeSource.model_validate(item) for item in payload]
        except (OSError, ValueError, TypeError) as exc:
            raise PersistentStateError(
                f"知识源注册表损坏或不可读：{self.path}",
            ) from exc

    def list(
        self,
        *,
        refresh: bool = True,
        user_id: int | None = None,
        include_private: bool = False,
    ) -> list[KnowledgeSource]:
        with self._lock:
            records = self._list_unlocked(refresh=refresh)
            if include_private:
                return records
            return [
                record
                for record in records
                if record.imported_by is None or record.imported_by == user_id
            ]

    def _list_unlocked(self, *, refresh: bool = True) -> list[KnowledgeSource]:
        records = self._load()
        if not refresh:
            return records
        by_path = {record.path: record for record in records}
        changed = False
        for path in sorted(self.raw_dir.glob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".pdf"}:
                continue
            relative = portable_path(path, self.config)
            checksum = file_checksum(path)
            existing = by_path.get(relative)
            if existing is None:
                by_path[relative] = _infer_metadata(path, self.config)
                changed = True
            elif existing.checksum != checksum:
                by_path[relative] = existing.model_copy(
                    update={"checksum": checksum, "verified": False},
                )
                changed = True
        active_paths = {
            portable_path(path, self.config)
            for path in self.raw_dir.glob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf"}
        }
        result = sorted(
            (record for path, record in by_path.items() if path in active_paths),
            key=lambda item: item.title,
        )
        if changed or len(result) != len(records):
            self.save(result)
        return result

    def get(self, source_id: str) -> KnowledgeSource:
        with self._lock:
            for record in self._list_unlocked():
                if record.id == source_id:
                    return record
            raise KeyError(source_id)

    def save(self, records: list[KnowledgeSource]) -> None:
        with self._lock:
            _atomic_json(self.path, [record.model_dump(mode="json") for record in records])

    def update(
        self,
        source_id: str,
        values: dict[str, object],
        *,
        verified_by: int | None = None,
    ) -> KnowledgeSource:
        with self._lock:
            records = self._list_unlocked()
            allowed = {
                "title",
                "institution",
                "region",
                "published_at",
                "version",
                "population",
                "status",
                "superseded_by",
                "verified",
                "verification_note",
            }
            for index, record in enumerate(records):
                if record.id != source_id:
                    continue
                changes = {
                    key: value for key, value in values.items() if key in allowed
                }
                prospective = record.model_copy(update=changes)
                if changes.get("verified") is True:
                    if verified_by is None:
                        raise ValueError("核验知识来源必须记录审核者")
                    if not prospective.institution or not (
                        prospective.version or prospective.published_at
                    ):
                        raise ValueError("核验前必须补充机构以及版本或发布日期")
                    note = str(prospective.verification_note or "").strip()
                    if not note:
                        raise ValueError("核验前必须填写核验依据")
                    changes.update(
                        {
                            "verified_by": verified_by,
                            "verified_at": datetime.now(UTC),
                            "verification_note": note,
                        },
                    )
                elif changes.get("verified") is False:
                    changes.update({"verified_by": None, "verified_at": None})
                updated = record.model_copy(update=changes)
                records[index] = KnowledgeSource.model_validate(updated)
                self.save(records)
                return records[index]
            raise KeyError(source_id)

    def register_upload(
        self,
        path: Path,
        *,
        user_id: int,
        title: str | None = None,
        institution: str | None = None,
        region: str | None = None,
        published_at: str | None = None,
    ) -> KnowledgeSource:
        with self._lock:
            records = self._list_unlocked()
            relative = portable_path(path, self.config)
            record = KnowledgeSource(
                id=f"src_{uuid4().hex}",
                title=title or path.stem,
                path=relative,
                source_type="user",
                institution=institution,
                region=region,
                published_at=published_at,
                status="unknown",
                imported_by=user_id,
                verified=False,
                checksum=file_checksum(path),
            )
            records = [item for item in records if item.path != relative]
            records.append(record)
            self.save(sorted(records, key=lambda item: item.title))
            return record

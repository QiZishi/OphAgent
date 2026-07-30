"""Transactional runtime persistence for runs, events, artifacts and attachments.

SQLite WAL is the local research default. Legacy JSON/JSONL records are imported
idempotently on startup and remain untouched as a rollback source.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator, Iterable
from pathlib import Path

from app.core.config import Settings, settings
from app.domain.models import (
    Artifact,
    AttachmentRecord,
    InterventionMode,
    InterventionStatus,
    RunEvent,
    RunIntervention,
    RunRecord,
    RunStatus,
    utc_now,
)

TERMINAL = {
    RunStatus.COMPLETED,
    RunStatus.COMPLETED_WITH_WARNINGS,
    RunStatus.INTERRUPTED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}
FINAL_EVENT_TYPES = {"run.completed", "run.failed", "run.cancelled"}


class RuntimeStore:
    """A small transactional store with deterministic event sequencing."""

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self.run_dir = config.resolve_path(config.RUNTIME_STATE_DIR)
        self.artifact_dir = config.resolve_path(config.ARTIFACT_DIR)
        self.attachment_dir = config.resolve_path(config.ATTACHMENT_DIR)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.attachment_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self._database_path()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._initialize()
        self._import_legacy_records()

    def _database_path(self) -> Path:
        if self.config.ENVIRONMENT == "test":
            return self.run_dir.parent / "runtime.sqlite3"
        prefix = "sqlite:///"
        if self.config.DATABASE_URL.startswith(prefix):
            raw = self.config.DATABASE_URL[len(prefix):]
            return self.config.resolve_path(raw)
        return self.run_dir.parent / "runtime.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_runs (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    conversation_id INTEGER,
                    idempotency_key TEXT,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_runtime_run_idempotency
                    ON runtime_runs(user_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS ix_runtime_run_user_created
                    ON runtime_runs(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS ix_runtime_run_conversation
                    ON runtime_runs(conversation_id, created_at);

                CREATE TABLE IF NOT EXISTS runtime_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, sequence),
                    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_runtime_terminal_event
                    ON runtime_events(run_id, type)
                    WHERE type IN ('run.completed', 'run.failed', 'run.cancelled');

                CREATE TABLE IF NOT EXISTS runtime_artifacts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_runtime_artifact_user
                    ON runtime_artifacts(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS runtime_attachments (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    conversation_id INTEGER,
                    message_id INTEGER,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_provider_configs (
                    user_id INTEGER PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_context_snapshots (
                    run_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    conversation_id INTEGER NOT NULL,
                    cache_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_runtime_context_cache
                    ON runtime_context_snapshots(user_id, conversation_id, cache_key);
                CREATE INDEX IF NOT EXISTS ix_runtime_attachment_user
                    ON runtime_attachments(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS ix_runtime_attachment_conversation
                    ON runtime_attachments(conversation_id);

                CREATE TABLE IF NOT EXISTS runtime_interventions (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected_attempt INTEGER NOT NULL,
                    client_message_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE CASCADE,
                    UNIQUE(run_id, client_message_id)
                );
                CREATE INDEX IF NOT EXISTS ix_runtime_intervention_run_status
                    ON runtime_interventions(run_id, status, created_at);
                """
            )
            # Older prototypes enforced one event per terminal *type* for the
            # whole Run, which prevented a resumed attempt from recording its
            # own failure. Terminal uniqueness is now enforced per attempt in
            # append_event().
            connection.execute("DROP INDEX IF EXISTS ux_runtime_terminal_event")

    async def get_provider_config(self, user_id: int) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runtime_provider_configs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else {}

    async def save_provider_config(self, user_id: int, payload: dict) -> dict:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_provider_configs (user_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, json.dumps(payload, ensure_ascii=False), utc_now().isoformat()),
            )
        return payload

    def _import_legacy_records(self) -> None:
        """Import the previous file store without deleting rollback files."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for path in self.run_dir.glob("run_*.json"):
                    try:
                        run = RunRecord.model_validate_json(path.read_text("utf-8"))
                    except (OSError, ValueError):
                        continue
                    self._insert_run(connection, run, ignore=True)
                    event_path = self.run_dir / f"{run.id}.events.jsonl"
                    if event_path.is_file():
                        for line in event_path.read_text("utf-8").splitlines():
                            try:
                                event = RunEvent.model_validate_json(line)
                            except ValueError:
                                continue
                            connection.execute(
                                """
                                INSERT OR IGNORE INTO runtime_events
                                    (run_id, sequence, event_id, type, payload_json, created_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    event.run_id,
                                    event.sequence,
                                    event.id,
                                    event.type,
                                    event.model_dump_json(),
                                    event.timestamp.isoformat(),
                                ),
                            )
                for path in self.artifact_dir.glob("art_*.json"):
                    try:
                        artifact = Artifact.model_validate_json(path.read_text("utf-8"))
                    except (OSError, ValueError):
                        continue
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO runtime_artifacts
                            (id, run_id, user_id, payload_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            artifact.id,
                            artifact.run_id,
                            artifact.user_id,
                            artifact.model_dump_json(),
                            artifact.created_at.isoformat(),
                        ),
                    )
                for path in self.attachment_dir.glob("att_*.json"):
                    try:
                        attachment = AttachmentRecord.model_validate_json(path.read_text("utf-8"))
                    except (OSError, ValueError):
                        continue
                    self._upsert_attachment(connection, attachment)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _lock(self, run_id: str) -> asyncio.Lock:
        return self._locks.setdefault(run_id, asyncio.Lock())

    def _condition(self, run_id: str) -> asyncio.Condition:
        return self._conditions.setdefault(run_id, asyncio.Condition())

    @staticmethod
    def _insert_run(connection: sqlite3.Connection, run: RunRecord, *, ignore: bool = False) -> None:
        command = "INSERT OR IGNORE" if ignore else "INSERT"
        connection.execute(
            f"""
            {command} INTO runtime_runs
                (id, user_id, conversation_id, idempotency_key, status, version,
                 payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id,
                run.user_id,
                run.input.conversation_id,
                run.input.idempotency_key,
                run.status.value,
                run.version,
                run.model_dump_json(),
                run.created_at.isoformat(),
                run.updated_at.isoformat(),
            ),
        )

    async def create_run(self, run: RunRecord) -> RunRecord:
        async with self._lock(run.id):
            try:
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._insert_run(connection, run)
                    connection.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("run already exists") from exc
        return run

    async def save_run(
        self,
        run: RunRecord,
        *,
        allow_resume: bool = False,
    ) -> bool:
        run.updated_at = utc_now()
        async with self._lock(run.id):
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT version, status, payload_json FROM runtime_runs WHERE id = ?",
                    (run.id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise KeyError(run.id)
                current = RunRecord.model_validate_json(row["payload_json"])
                valid_resume = (
                    allow_resume
                    and current.status
                    in {
                        RunStatus.INTERRUPTED,
                        RunStatus.FAILED,
                        RunStatus.CANCELLED,
                    }
                    and run.status == RunStatus.QUEUED
                    and run.attempt > current.attempt
                )
                if run.version != int(row["version"]) and not valid_resume:
                    connection.rollback()
                    return False
                if current.status in TERMINAL and run.status not in TERMINAL:
                    if not valid_resume:
                        connection.rollback()
                        return False
                if (
                    current.status in TERMINAL
                    and run.status in TERMINAL
                    and current.status != run.status
                ):
                    connection.rollback()
                    return False
                run.version = int(row["version"]) + 1
                connection.execute(
                    """
                    UPDATE runtime_runs
                    SET conversation_id = ?, idempotency_key = ?, status = ?, version = ?,
                        payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        run.input.conversation_id,
                        run.input.idempotency_key,
                        run.status.value,
                        run.version,
                        run.model_dump_json(),
                        run.updated_at.isoformat(),
                        run.id,
                    ),
                )
                connection.commit()
                return True

    async def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runtime_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            run = RunRecord.model_validate_json(row["payload_json"])
            run.interventions = self._load_interventions(connection, run.id)
        return run

    async def list_runs(self, user_id: int, limit: int = 50) -> list[RunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM runtime_runs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            runs = [RunRecord.model_validate_json(row["payload_json"]) for row in rows]
            for run in runs:
                run.interventions = self._load_interventions(connection, run.id)
        return runs

    async def list_conversation_runs(
        self,
        user_id: int,
        conversation_id: int,
        *,
        limit: int = 300,
    ) -> list[RunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM runtime_runs
                WHERE user_id = ? AND conversation_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, conversation_id, limit),
            ).fetchall()
            runs = [
                RunRecord.model_validate_json(row["payload_json"])
                for row in reversed(rows)
            ]
            for run in runs:
                run.interventions = self._load_interventions(connection, run.id)
        return runs

    async def save_context_snapshot(self, snapshot, cache_key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_context_snapshots
                    (run_id, user_id, conversation_id, cache_key, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    cache_key = excluded.cache_key,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (
                    snapshot.run_id,
                    snapshot.user_id,
                    snapshot.conversation_id,
                    cache_key,
                    snapshot.model_dump_json(),
                    snapshot.created_at.isoformat(),
                ),
            )

    async def get_context_snapshot(self, run_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runtime_context_snapshots WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    async def find_context_snapshot(
        self,
        user_id: int,
        conversation_id: int,
        cache_key: str,
    ) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM runtime_context_snapshots
                WHERE user_id = ? AND conversation_id = ? AND cache_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, conversation_id, cache_key),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    async def list_all_runs(self) -> list[RunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM runtime_runs ORDER BY created_at"
            ).fetchall()
            runs = [RunRecord.model_validate_json(row["payload_json"]) for row in rows]
            for run in runs:
                run.interventions = self._load_interventions(connection, run.id)
        return runs

    async def find_run_by_idempotency(
        self,
        user_id: int,
        idempotency_key: str | None,
    ) -> RunRecord | None:
        if not idempotency_key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM runtime_runs
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (user_id, idempotency_key),
            ).fetchone()
            if row is None:
                return None
            run = RunRecord.model_validate_json(row["payload_json"])
            run.interventions = self._load_interventions(connection, run.id)
        return run

    @staticmethod
    def _load_interventions(
        connection: sqlite3.Connection,
        run_id: str,
    ) -> list[RunIntervention]:
        rows = connection.execute(
            """
            SELECT payload_json FROM runtime_interventions
            WHERE run_id = ?
            ORDER BY created_at, id
            """,
            (run_id,),
        ).fetchall()
        return [
            RunIntervention.model_validate_json(row["payload_json"])
            for row in rows
        ]

    async def create_intervention(
        self,
        intervention: RunIntervention,
    ) -> RunIntervention:
        """Append an intervention without racing the worker's Run CAS writes."""

        async with self._lock(intervention.run_id):
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT payload_json FROM runtime_runs WHERE id = ?",
                    (intervention.run_id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise KeyError(intervention.run_id)
                run = RunRecord.model_validate_json(row["payload_json"])
                if run.user_id != intervention.user_id:
                    connection.rollback()
                    raise KeyError(intervention.run_id)
                if run.attempt != intervention.expected_attempt:
                    connection.rollback()
                    raise ValueError(
                        f"任务已进入第 {run.attempt} 次执行，请刷新后重新提交"
                    )
                if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
                    connection.rollback()
                    raise ValueError("当前任务已经不再执行，无法追加要求")
                try:
                    connection.execute(
                        """
                        INSERT INTO runtime_interventions
                            (id, run_id, user_id, mode, status, expected_attempt,
                             client_message_id, payload_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            intervention.id,
                            intervention.run_id,
                            intervention.user_id,
                            intervention.mode.value,
                            intervention.status.value,
                            intervention.expected_attempt,
                            intervention.client_message_id,
                            intervention.model_dump_json(),
                            intervention.created_at.isoformat(),
                            intervention.created_at.isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError:
                    existing = connection.execute(
                        """
                        SELECT payload_json FROM runtime_interventions
                        WHERE run_id = ? AND client_message_id = ?
                        """,
                        (intervention.run_id, intervention.client_message_id),
                    ).fetchone()
                    connection.rollback()
                    if existing is None:
                        raise
                    return RunIntervention.model_validate_json(existing["payload_json"])
                connection.commit()
        async with self._condition(intervention.run_id):
            self._condition(intervention.run_id).notify_all()
        return intervention

    async def list_interventions(
        self,
        run_id: str,
        *,
        status: InterventionStatus | None = None,
        mode: InterventionMode | None = None,
    ) -> list[RunIntervention]:
        with self._connect() as connection:
            query = "SELECT payload_json FROM runtime_interventions WHERE run_id = ?"
            values: list[object] = [run_id]
            if status is not None:
                query += " AND status = ?"
                values.append(status.value)
            if mode is not None:
                query += " AND mode = ?"
                values.append(mode.value)
            query += " ORDER BY created_at, id"
            rows = connection.execute(query, values).fetchall()
        return [
            RunIntervention.model_validate_json(row["payload_json"])
            for row in rows
        ]

    async def update_intervention_status(
        self,
        run_id: str,
        intervention_id: str,
        status: InterventionStatus,
    ) -> RunIntervention:
        async with self._lock(run_id):
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT payload_json FROM runtime_interventions
                    WHERE id = ? AND run_id = ?
                    """,
                    (intervention_id, run_id),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise KeyError(intervention_id)
                intervention = RunIntervention.model_validate_json(row["payload_json"])
                if intervention.status != InterventionStatus.QUEUED:
                    connection.rollback()
                    return intervention
                now = utc_now()
                intervention.status = status
                if status == InterventionStatus.APPLIED:
                    intervention.applied_at = now
                elif status == InterventionStatus.CANCELLED:
                    intervention.cancelled_at = now
                connection.execute(
                    """
                    UPDATE runtime_interventions
                    SET status = ?, payload_json = ?, updated_at = ?
                    WHERE id = ? AND run_id = ?
                    """,
                    (
                        status.value,
                        intervention.model_dump_json(),
                        now.isoformat(),
                        intervention_id,
                        run_id,
                    ),
                )
                connection.commit()
        async with self._condition(run_id):
            self._condition(run_id).notify_all()
        return intervention

    async def append_event(self, event: RunEvent) -> None:
        async with self._lock(event.run_id):
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if event.type in FINAL_EVENT_TYPES:
                    attempt = int(event.data.get("attempt", 1))
                    existing_rows = connection.execute(
                        """
                        SELECT payload_json FROM runtime_events
                        WHERE run_id = ?
                          AND type IN ('run.completed', 'run.failed', 'run.cancelled')
                        """,
                        (event.run_id,),
                    ).fetchall()
                    if any(
                        int(
                            RunEvent.model_validate_json(row["payload_json"]).data.get(
                                "attempt",
                                1,
                            ),
                        )
                        == attempt
                        for row in existing_rows
                    ):
                        connection.rollback()
                        return
                row = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM runtime_events WHERE run_id = ?",
                    (event.run_id,),
                ).fetchone()
                event.sequence = int(row["sequence"]) + 1
                connection.execute(
                    """
                    INSERT INTO runtime_events
                        (run_id, sequence, event_id, type, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.run_id,
                        event.sequence,
                        event.id,
                        event.type,
                        event.model_dump_json(),
                        event.timestamp.isoformat(),
                    ),
                )
                connection.commit()
        async with self._condition(event.run_id):
            self._condition(event.run_id).notify_all()

    async def commit_terminal(
        self,
        run: RunRecord,
        event: RunEvent,
        *,
        public_events: Iterable[RunEvent] = (),
        artifacts: Iterable[Artifact] = (),
    ) -> bool:
        """Atomically publish one terminal revision and all of its public output.

        No answer delta or artifact becomes observable until the Run has won
        the terminal compare-and-swap and no queued intervention remains.
        """
        if run.status not in TERMINAL or event.type not in FINAL_EVENT_TYPES:
            raise ValueError("commit_terminal 只接受终态及终态事件")
        bundled_events = [*public_events, event]
        bundled_artifacts = list(artifacts)
        if any(item.run_id != run.id for item in bundled_events):
            raise ValueError("终态事件必须属于同一个 Run")
        if any(item.run_id != run.id or item.user_id != run.user_id for item in bundled_artifacts):
            raise ValueError("终态产物必须属于同一个 Run 和用户")
        async with self._lock(run.id):
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT version, payload_json FROM runtime_runs WHERE id = ?",
                    (run.id,),
                ).fetchone()
                if row is None:
                    connection.rollback()
                    raise KeyError(run.id)
                current = RunRecord.model_validate_json(row["payload_json"])
                if run.version != int(row["version"]):
                    connection.rollback()
                    return False
                pending_intervention = connection.execute(
                    """
                    SELECT 1 FROM runtime_interventions
                    WHERE run_id = ? AND status = ? AND expected_attempt = ?
                    LIMIT 1
                    """,
                    (
                        run.id,
                        InterventionStatus.QUEUED.value,
                        run.attempt,
                    ),
                ).fetchone()
                if pending_intervention is not None:
                    connection.rollback()
                    return False
                if current.status in TERMINAL and current.status != run.status:
                    connection.rollback()
                    return False
                attempt = int(event.data.get("attempt", run.attempt))
                terminal_rows = connection.execute(
                    """
                    SELECT payload_json FROM runtime_events
                    WHERE run_id = ?
                      AND type IN ('run.completed', 'run.failed', 'run.cancelled')
                    """,
                    (run.id,),
                ).fetchall()
                if any(
                    int(
                        RunEvent.model_validate_json(item["payload_json"]).data.get(
                            "attempt",
                            1,
                        ),
                    )
                    == attempt
                    for item in terminal_rows
                ):
                    connection.rollback()
                    return False
                run.updated_at = utc_now()
                run.version = int(row["version"]) + 1
                sequence_row = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM runtime_events WHERE run_id = ?",
                    (run.id,),
                ).fetchone()
                next_sequence = int(sequence_row["sequence"]) + 1
                connection.execute(
                    """
                    UPDATE runtime_runs
                    SET conversation_id = ?, idempotency_key = ?, status = ?, version = ?,
                        payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        run.input.conversation_id,
                        run.input.idempotency_key,
                        run.status.value,
                        run.version,
                        run.model_dump_json(),
                        run.updated_at.isoformat(),
                        run.id,
                    ),
                )
                for artifact in bundled_artifacts:
                    connection.execute(
                        """
                        INSERT INTO runtime_artifacts
                            (id, run_id, user_id, payload_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json
                        """,
                        (
                            artifact.id,
                            artifact.run_id,
                            artifact.user_id,
                            artifact.model_dump_json(),
                            artifact.created_at.isoformat(),
                        ),
                    )
                for bundled_event in bundled_events:
                    bundled_event.sequence = next_sequence
                    next_sequence += 1
                    connection.execute(
                        """
                        INSERT INTO runtime_events
                            (run_id, sequence, event_id, type, payload_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            bundled_event.run_id,
                            bundled_event.sequence,
                            bundled_event.id,
                            bundled_event.type,
                            bundled_event.model_dump_json(),
                            bundled_event.timestamp.isoformat(),
                        ),
                    )
                connection.commit()
        async with self._condition(event.run_id):
            self._condition(event.run_id).notify_all()
        return True

    async def get_events(self, run_id: str, after: int = 0) -> list[RunEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM runtime_events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence
                """,
                (run_id, after),
            ).fetchall()
        return [RunEvent.model_validate_json(row["payload_json"]) for row in rows]

    async def stream_events(self, run_id: str, after: int = 0) -> AsyncIterator[RunEvent]:
        cursor = after
        while True:
            events = await self.get_events(run_id, cursor)
            for event in events:
                cursor = event.sequence
                yield event
            run = await self.get_run(run_id)
            if run is None or run.status in TERMINAL:
                return
            async with self._condition(run_id):
                try:
                    await asyncio.wait_for(self._condition(run_id).wait(), timeout=15)
                except TimeoutError:
                    continue

    async def save_artifact(self, artifact: Artifact, binary: bytes | None = None) -> Artifact:
        if binary is not None:
            suffix = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "application/pdf": ".pdf",
                "audio/mpeg": ".mp3",
            }.get(artifact.mime_type, ".bin")
            target = self.artifact_dir / f"{artifact.id}{suffix}"
            target.write_bytes(binary)
            try:
                artifact.path = str(target.relative_to(self.config.project_root))
            except ValueError:
                artifact.path = str(target)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_artifacts (id, run_id, user_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (
                    artifact.id,
                    artifact.run_id,
                    artifact.user_id,
                    artifact.model_dump_json(),
                    artifact.created_at.isoformat(),
                ),
            )
        return artifact

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runtime_artifacts WHERE id = ?",
                (artifact_id,),
            ).fetchone()
        return Artifact.model_validate_json(row["payload_json"]) if row else None

    async def list_artifacts(self, user_id: int, run_id: str | None = None) -> list[Artifact]:
        query = "SELECT payload_json FROM runtime_artifacts WHERE user_id = ?"
        values: list[object] = [user_id]
        if run_id is not None:
            query += " AND run_id = ?"
            values.append(run_id)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [Artifact.model_validate_json(row["payload_json"]) for row in rows]

    @staticmethod
    def _upsert_attachment(connection: sqlite3.Connection, attachment: AttachmentRecord) -> None:
        connection.execute(
            """
            INSERT INTO runtime_attachments
                (id, user_id, conversation_id, message_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                conversation_id = excluded.conversation_id,
                message_id = excluded.message_id,
                payload_json = excluded.payload_json
            """,
            (
                attachment.id,
                attachment.user_id,
                attachment.conversation_id,
                attachment.message_id,
                attachment.model_dump_json(),
                attachment.created_at.isoformat(),
            ),
        )

    async def save_attachment(self, attachment: AttachmentRecord) -> AttachmentRecord:
        with self._connect() as connection:
            self._upsert_attachment(connection, attachment)
        return attachment

    async def get_attachment(self, attachment_id: str) -> AttachmentRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runtime_attachments WHERE id = ?",
                (attachment_id,),
            ).fetchone()
        return AttachmentRecord.model_validate_json(row["payload_json"]) if row else None

    async def list_attachments(self, user_id: int) -> list[AttachmentRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM runtime_attachments
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [AttachmentRecord.model_validate_json(row["payload_json"]) for row in rows]

    async def delete_attachment(self, attachment_id: str, user_id: int) -> bool:
        record = await self.get_attachment(attachment_id)
        if record is None or record.user_id != user_id:
            return False
        stored = self.config.resolve_path(record.stored_path)
        if stored.is_file():
            stored.unlink()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM runtime_attachments WHERE id = ? AND user_id = ?",
                (attachment_id, user_id),
            )
        return True

    async def bind_attachments(
        self,
        attachment_ids: list[str],
        user_id: int,
        conversation_id: int,
        message_id: int,
    ) -> None:
        for attachment_id in attachment_ids:
            record = await self.get_attachment(attachment_id)
            if record is None or record.user_id != user_id:
                continue
            record.conversation_id = conversation_id
            record.message_id = message_id
            await self.save_attachment(record)

    async def delete_conversation_resources(self, user_id: int, conversation_id: int) -> None:
        runs = [
            run
            for run in await self.list_runs(user_id, limit=10_000)
            if run.input.conversation_id == conversation_id
        ]
        run_ids = {run.id for run in runs}
        artifacts = await self.list_artifacts(user_id)
        attachments = await self.list_attachments(user_id)
        self._delete_artifact_files(item for item in artifacts if item.run_id in run_ids)
        for attachment in attachments:
            if attachment.conversation_id == conversation_id:
                stored = self.config.resolve_path(attachment.stored_path)
                if stored.is_file():
                    stored.unlink()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM runtime_attachments WHERE user_id = ? AND conversation_id = ?",
                (user_id, conversation_id),
            )
            connection.execute(
                "DELETE FROM runtime_runs WHERE user_id = ? AND conversation_id = ?",
                (user_id, conversation_id),
            )
            connection.commit()

    async def delete_run(self, run_id: str, user_id: int) -> bool:
        run = await self.get_run(run_id)
        if run is None or run.user_id != user_id:
            return False
        artifacts = await self.list_artifacts(user_id, run_id)
        self._delete_artifact_files(artifacts)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM runtime_runs WHERE id = ? AND user_id = ?",
                (run_id, user_id),
            )
        return cursor.rowcount > 0

    def _delete_artifact_files(self, artifacts: Iterable[Artifact]) -> None:
        for artifact in artifacts:
            if not artifact.path:
                continue
            binary = self.config.resolve_path(artifact.path)
            if binary.is_file():
                binary.unlink()

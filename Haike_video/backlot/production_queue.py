"""Durable, cross-project production queue for Backlot.

The queue owns admission and ordering only.  Existing project pipelines remain
the source of truth for media stages, provider task IDs, budgets and recovery.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


QUEUE_SCHEMA_VERSION = 1
DEFAULT_DB_NAME = "production-queue.sqlite3"
QUEUE_KINDS = {"review_preview", "avatar_review_preview", "full_preview", "material_selection", "published_remix", "material_commentary", "commentary_presenter", "studio_graphic", "studio_avatar", "studio_motion"}
QUEUE_SOURCES = {"workbench", "codex", "scheduler", "recovery"}
PRIORITIES = {"priority": 300, "normal": 200, "background": 100}
ACTIVE_STATUSES = {"queued", "running", "paused"}
WAITING_STATUSES = {"awaiting_human", "ambiguous"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
PUBLIC_SECRET_PARTS = ("api_key", "apikey", "secret", "token", "authorization", "cookie")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/])[^\s\"']+")
_AUTH_VALUE = re.compile(
    r"(?i)\b(bearer\s+|(?:x-)?api[-_ ]?key\s*[:=]\s*|authorization\s*[:=]\s*)[^\s,;]+"
)


class ProductionQueueError(ValueError):
    """A queue contract error safe to present to the user."""


class ProductionQueueConflict(ProductionQueueError):
    """A state transition or ownership conflict."""


class ProductionQueueCancelled(ProductionQueueError):
    """Stop a producer before the next stage after explicit user cancellation."""


def _now() -> str:
    # Microseconds preserve FIFO order for bursts submitted within one second.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _future(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(1, seconds))).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _safe_public(value: Any) -> Any:
    """Remove credentials and implementation-only leases from public payloads."""

    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in {"worker_id", "lease_expires_at", "frozen_request"}:
                continue
            if any(part in lowered for part in PUBLIC_SECRET_PARTS):
                continue
            clean[str(key)] = _safe_public(child)
        return clean
    if isinstance(value, list):
        return [_safe_public(child) for child in value]
    if isinstance(value, str):
        value = _AUTH_VALUE.sub(lambda match: match.group(1) + "[REDACTED]", value)
        return _WINDOWS_ABSOLUTE_PATH.sub("[LOCAL_PATH]", value)
    return value


def _validate_identifier(value: Any, label: str, *, maximum: int = 240) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or any(ch in text for ch in "\r\n\x00"):
        raise ProductionQueueError(f"{label}无效")
    return text


class ProductionQueue:
    def __init__(self, db_path: str | Path, projects_root: str | Path):
        self.db_path = Path(db_path)
        self.projects_root = Path(projects_root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        connection = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS production_jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL,
                    project_title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    priority_rank INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    parent_job_id TEXT NOT NULL,
                    frozen_request TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error_json TEXT NOT NULL DEFAULT '{}',
                    safe_resume_point TEXT,
                    retryable INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    worker_id TEXT,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    revision INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS production_jobs_claim_idx
                    ON production_jobs(status, priority_rank DESC, created_at ASC, job_id ASC);
                CREATE INDEX IF NOT EXISTS production_jobs_project_idx
                    ON production_jobs(project_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS production_creation_links (
                    job_id TEXT PRIMARY KEY REFERENCES production_jobs(job_id),
                    creation_id TEXT NOT NULL REFERENCES production_jobs(job_id),
                    previous_job_id TEXT REFERENCES production_jobs(job_id),
                    relation TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS production_creation_family
                    ON production_creation_links(creation_id);
                CREATE TABLE IF NOT EXISTS production_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES production_jobs(job_id) ON DELETE CASCADE
                );
                PRAGMA user_version=1;
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(production_jobs)")}
            if "progress_json" not in columns:
                connection.execute("ALTER TABLE production_jobs ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'")
        finally:
            connection.close()

    def _project_title(self, project_id: str) -> str:
        project_dir = (self.projects_root / project_id).resolve()
        root = os.path.normcase(str(self.projects_root.resolve()))
        candidate = os.path.normcase(str(project_dir))
        try:
            inside_root = os.path.commonpath([root, candidate]) == root
        except ValueError:
            inside_root = False
        if not inside_root or not project_dir.is_dir():
            raise ProductionQueueError("项目不存在或不在工作区内")
        marker = project_dir / "project.json"
        if not marker.is_file():
            raise ProductionQueueError("项目缺少 project.json")
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductionQueueError("项目配置无法读取") from exc
        return str(payload.get("title") or project_id).strip()[:240]

    @staticmethod
    def _job_id(idempotency_key: str) -> str:
        return "PQ-" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        job_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO production_events(job_id,event_type,from_status,to_status,detail_json,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (job_id, event_type, from_status, to_status, _json(detail or {}), _now()),
        )

    def submit(
        self, *, project_id: str, kind: str, source: str, priority: str,
        parent_job_id: str, frozen_request: dict[str, Any] | None,
        idempotency_key: str | None = None, revive: bool = False,
    ) -> dict[str, Any]:
        # Admission shares the archival lock; no new producer can enter mid-delete.
        from backlot.work_catalog import WorkCatalog
        catalog = WorkCatalog(self.projects_root)
        with catalog.transaction() as guard:
            lock = guard.execute("SELECT token FROM work_activity WHERE project=?", (project_id,)).fetchone()
            if lock and lock[0].startswith("cleanup-"):
                raise ProductionQueueConflict("项目正在归档清理，完成或恢复清理后再生产")
            return self._submit(project_id=project_id, kind=kind, source=source, priority=priority,
                                parent_job_id=parent_job_id, frozen_request=frozen_request,
                                idempotency_key=idempotency_key, revive=revive)

    def _submit(
        self,
        *,
        project_id: str,
        kind: str,
        source: str,
        priority: str,
        parent_job_id: str,
        frozen_request: dict[str, Any] | None,
        idempotency_key: str | None = None,
        revive: bool = False,
    ) -> dict[str, Any]:
        project_id = _validate_identifier(project_id, "项目编号", maximum=80)
        kind = _validate_identifier(kind, "生产类型", maximum=64)
        source = _validate_identifier(source, "任务来源", maximum=32)
        priority = _validate_identifier(priority, "优先级", maximum=32)
        parent_job_id = _validate_identifier(parent_job_id, "底层任务编号")
        if kind not in QUEUE_KINDS:
            raise ProductionQueueError("生产类型不在统一队列白名单中")
        if source not in QUEUE_SOURCES:
            raise ProductionQueueError("任务来源无效")
        if priority not in PRIORITIES:
            raise ProductionQueueError("优先级只能是 priority、normal 或 background")
        project_title = self._project_title(project_id)
        key = _validate_identifier(
            idempotency_key or f"{kind}:{project_id}:{parent_job_id}",
            "幂等键",
            maximum=300,
        )
        job_id = self._job_id(key)
        now = _now()
        request = _safe_public(frozen_request or {})
        with self._connection(immediate=True) as connection:
            existing = connection.execute(
                "SELECT * FROM production_jobs WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["project_id"]) != project_id
                    or str(existing["kind"]) != kind
                    or str(existing["parent_job_id"]) != parent_job_id
                ):
                    raise ProductionQueueConflict("幂等键已被另一条生产请求占用")
                if revive and existing["status"] in {"failed", "awaiting_human"}:
                    old = str(existing["status"])
                    connection.execute(
                        "UPDATE production_jobs SET status='queued',stage='等待统一调度',error_json='{}',"
                        "retryable=0,cancel_requested=0,worker_id=NULL,lease_expires_at=NULL,finished_at=NULL,"
                        "updated_at=?,revision=revision+1 WHERE job_id=?",
                        (now, existing["job_id"]),
                    )
                    self._event(connection, existing["job_id"], "requeued", old, "queued")
                return self._public_row(
                    connection.execute(
                        "SELECT * FROM production_jobs WHERE idempotency_key=?", (key,)
                    ).fetchone()
                )
            conflict = connection.execute(
                "SELECT job_id,status FROM production_jobs WHERE project_id=? AND kind=? "
                "AND status IN ('queued','running','paused') LIMIT 1",
                (project_id, kind),
            ).fetchone()
            if conflict is not None:
                raise ProductionQueueConflict(
                    f"该项目已有同类生产任务 {conflict['job_id']}（{conflict['status']}）"
                )
            connection.execute(
                """
                INSERT INTO production_jobs(
                    job_id,idempotency_key,project_id,project_title,kind,source,priority,priority_rank,
                    status,stage,parent_job_id,frozen_request,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id, key, project_id, project_title, kind, source, priority,
                    PRIORITIES[priority], "queued", "等待统一调度", parent_job_id,
                    _json(request), now, now,
                ),
            )
            self._event(connection, job_id, "submitted", None, "queued", {"source": source})
            previous = (request.get('continuation') or {}).get('previous_job_id')
            if previous: self._link_creation(connection, job_id, previous, 'continuation')
            row = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public_row(row)

    def find_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        key = _validate_identifier(idempotency_key, "幂等键", maximum=300)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM production_jobs WHERE idempotency_key=?", (key,)
            ).fetchone()
        return self._public_row(row) if row is not None else None

    def get(self, job_id: str, *, include_private: bool = False) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise ProductionQueueError("生产任务不存在")
        return self._private_row(row) if include_private else self._public_row(row)

    def link_creation(self, job_id: str, previous_job_id: str, relation: str = "continuation") -> dict:
        """Explicit lineage only; titles and similar scripts never imply identity."""
        if relation not in {"continuation", "regeneration", "recomposition", "polish"}:
            raise ProductionQueueError("制作关联类型无效")
        with self._connection(immediate=True) as db:
            return self._link_creation(db, job_id, previous_job_id, relation)

    def _link_creation(self, db, job_id, previous_job_id, relation):
        job = db.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        previous = db.execute("SELECT * FROM production_jobs WHERE job_id=?", (previous_job_id,)).fetchone()
        if not job or not previous or job_id == previous_job_id:
            raise ProductionQueueError("制作关联任务不存在或无效")
        if (job['project_id'], job['kind']) != (previous['project_id'], previous['kind']) or job['created_at'] <= previous['created_at']:
            raise ProductionQueueConflict("只能关联同一项目较早的同类制作记录")
        parent = db.execute("SELECT creation_id FROM production_creation_links WHERE job_id=?", (previous_job_id,)).fetchone()
        root = parent['creation_id'] if parent else previous_job_id
        existing = db.execute("SELECT * FROM production_creation_links WHERE job_id=?", (job_id,)).fetchone()
        if existing:
            if (existing['creation_id'], existing['previous_job_id'], existing['relation']) != (root, previous_job_id, relation):
                raise ProductionQueueConflict("已有制作关联不能覆盖")
        else:
            if db.execute("SELECT 1 FROM production_creation_links WHERE creation_id=?", (job_id,)).fetchone():
                raise ProductionQueueConflict("请先关联较早记录，不能改变已有制作链的根节点")
            db.execute("INSERT INTO production_creation_links VALUES(?,?,?,?,?)", (job_id, root, previous_job_id, relation, _now()))
            self._event(db, job_id, "creation_linked", None, None, {"creation_id": root, "previous_job_id": previous_job_id, "relation": relation})
        return {"creation_id": root, "previous_job_id": previous_job_id, "relation": relation}

    def creation_members(self, job_id: str) -> list[dict]:
        with self._connection() as db:
            link = db.execute("SELECT creation_id FROM production_creation_links WHERE job_id=?", (job_id,)).fetchone()
            root = link['creation_id'] if link else job_id
            rows = db.execute("SELECT j.*, l.previous_job_id,l.relation FROM production_jobs j LEFT JOIN production_creation_links l ON l.job_id=j.job_id WHERE j.job_id=? OR l.creation_id=? ORDER BY j.created_at,j.job_id", (root, root)).fetchall()
        if not rows: raise ProductionQueueError("生产任务不存在")
        return [{**self._private_row(row), "creation_id": root} for row in rows]

    def resume_provider_waits(self, *, minimum_age: int = 30) -> list[str]:
        """Re-enter only the original durable request; never revive legacy failures."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(30, minimum_age))).isoformat(timespec="microseconds").replace("+00:00", "Z")
        resumed = []
        with self._connection(immediate=True) as db:
            rows = db.execute("SELECT * FROM production_jobs WHERE kind='studio_avatar' AND status='ambiguous' AND safe_resume_point='studio_avatar_provider' AND json_extract(error_json,'$.code')='provider_pending' AND updated_at<=? AND cancel_requested=0", (cutoff,)).fetchall()
            for row in rows:
                if db.execute("SELECT 1 FROM production_jobs WHERE project_id=? AND kind=? AND status IN ('queued','running','paused')", (row['project_id'], row['kind'])).fetchone(): continue
                # A superseded attempt must never resume behind a newer version.
                root = db.execute("SELECT creation_id FROM production_creation_links WHERE job_id=?", (row['job_id'],)).fetchone()
                family = root['creation_id'] if root else row['job_id']
                if db.execute("SELECT 1 FROM production_creation_links l JOIN production_jobs j ON j.job_id=l.job_id WHERE l.creation_id=? AND j.created_at>?", (family, row['created_at'])).fetchone(): continue
                db.execute("UPDATE production_jobs SET status='queued',stage='自动查询原数字人请求',error_json='{}',finished_at=NULL,updated_at=?,revision=revision+1 WHERE job_id=?", (_now(), row['job_id']))
                self._event(db, row['job_id'], "provider_recheck", "ambiguous", "queued")
                resumed.append(row['job_id'])
        return resumed

    def list(self, *, project_id: str | None = None, limit: int = 80,
             kinds: tuple[str, ...] | None = None, statuses: tuple[str, ...] | None = None,
             offset: int = 0, result_output_paths: tuple[str, ...] | None = None,
             collapse_creations: bool = False, include_provider_waits: bool = False,
             exclude_provider_waits: bool = False, project_input_issues: bool = False) -> dict[str, Any]:
        limit = min(200, max(1, int(limit)))
        offset = max(0, int(offset))
        clauses, parameters = [], []
        if project_id:
            clauses.append("project_id=?")
            parameters.append(project_id)
        for field, values in (("kind", kinds), ("status", statuses)):
            if values is not None:
                selected_field='display_status' if field=='status' and project_input_issues else field
                clause = f"{selected_field} IN ({','.join('?' for _ in values)})" if values else "0"
                if field == 'status' and include_provider_waits:
                    clause = f"({clause} OR (status='ambiguous' AND json_extract(error_json,'$.code')='provider_pending'))"
                clauses.append(clause)
                parameters.extend(values)
        if exclude_provider_waits:
            clauses.append("NOT (status='ambiguous' AND COALESCE(json_extract(error_json,'$.code'),'')='provider_pending')")
        if result_output_paths is not None:
            clauses.append(f"json_extract(result_json,'$.output_path') IN ({','.join('?' for _ in result_output_paths)})" if result_output_paths else "0")
            parameters.extend(result_output_paths)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        ordering = (
            "CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 WHEN 'paused' THEN 2 "
            "WHEN 'awaiting_human' THEN 3 WHEN 'ambiguous' THEN 3 WHEN 'failed' THEN 4 "
            "WHEN 'completed' THEN 5 ELSE 6 END ASC, "
            "CASE WHEN status='queued' THEN priority_rank ELSE 0 END DESC, "
            "CASE WHEN status IN ('running','queued','paused') THEN created_at END ASC, "
            "created_at DESC,job_id ASC"
        )
        with self._connection() as connection:
            source = "production_jobs"
            if collapse_creations:
                # Collapse BEFORE filtering, counting or paging. Historical failures
                # remain addressable by their exact job IDs in the detail endpoint.
                source = "(SELECT * FROM (SELECT j.*,COALESCE(l.creation_id,j.job_id) AS creation_id,ROW_NUMBER() OVER(PARTITION BY COALESCE(l.creation_id,j.job_id) ORDER BY j.created_at DESC,j.job_id DESC) AS creation_rank FROM production_jobs j LEFT JOIN production_creation_links l ON l.job_id=j.job_id) WHERE creation_rank=1)"
            count_status='status'
            if project_input_issues:
                # UI classification only: never migrate raw history or make a failed job executable.
                issue="kind='studio_avatar' AND status='failed' AND (json_extract(error_json,'$.code') IN ('audio_script_mismatch','audio_check_review','audio_check_stale') OR (COALESCE(json_extract(error_json,'$.code'),'')='' AND stage LIKE '%文案不一致%'))"
                source=f"(SELECT j.*, CASE WHEN {issue} THEN 'awaiting_human' ELSE status END AS display_status FROM {source} j)"
                ordering=ordering.replace('status','display_status')
                count_status='display_status'
            rows = connection.execute(
                f"SELECT * FROM {source}{where} ORDER BY {ordering} LIMIT ? OFFSET ?",
                (*parameters, limit, offset),
            ).fetchall()
            count_rows = connection.execute(
                f"SELECT {count_status} AS status,COUNT(*) AS count,SUM(CASE WHEN status='ambiguous' AND json_extract(error_json,'$.code')='provider_pending' THEN 1 ELSE 0 END) AS provider_waits FROM {source}{where} GROUP BY {count_status}", parameters,
            ).fetchall()
            queued = connection.execute(
                "SELECT job_id FROM production_jobs WHERE status='queued' "
                "ORDER BY priority_rank DESC,created_at ASC,job_id ASC"
            ).fetchall()
        positions = {str(row["job_id"]): index + 1 for index, row in enumerate(queued)}
        tasks = []
        for row in rows:
            task = self._public_row(row)
            task["queue_position"] = positions.get(task["job_id"])
            tasks.append(task)
        summary = self._summary(tasks)
        counts = {str(row["status"]): int(row["count"]) for row in count_rows}
        total = sum(counts.values())
        summary["pagination"] = {"offset": offset, "limit": limit, "total": total, "has_more": offset + len(tasks) < total}
        summary.update(
            {
                "active_count": counts.get("running", 0),
                "queued_count": counts.get("queued", 0),
                "paused_count": counts.get("paused", 0),
                "waiting_count": counts.get("awaiting_human", 0) + counts.get("ambiguous", 0),
                "failure_count": counts.get("failed", 0),
                "completed_count": counts.get("completed", 0),
                "cancelled_count": counts.get("cancelled", 0),
                "provider_wait_count": sum(int(row['provider_waits']) for row in count_rows),
            }
        )
        return summary

    @staticmethod
    def _summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "version": QUEUE_SCHEMA_VERSION,
            "active_count": sum(1 for task in tasks if task["status"] == "running"),
            "queued_count": sum(1 for task in tasks if task["status"] == "queued"),
            "paused_count": sum(1 for task in tasks if task["status"] == "paused"),
            "waiting_count": sum(1 for task in tasks if task["status"] in WAITING_STATUSES),
            "failure_count": sum(1 for task in tasks if task["status"] == "failed"),
            "completed_count": sum(1 for task in tasks if task["status"] == "completed"),
            "tasks": tasks,
        }

    def claim_next(self, worker_id: str, *, lease_seconds: int = 120) -> dict[str, Any] | None:
        worker_id = _validate_identifier(worker_id, "工作者编号", maximum=120)
        now = _now()
        with self._connection(immediate=True) as connection:
            # The queue is deliberately single-lane in V1.  This guard lives
            # in the same write transaction as the claim, so even two server
            # processes cannot each claim a different heavy/paid task.
            running = connection.execute(
                "SELECT job_id FROM production_jobs WHERE status='running' LIMIT 1"
            ).fetchone()
            if running is not None:
                return None
            row = connection.execute(
                "SELECT * FROM production_jobs WHERE status='queued' "
                "ORDER BY priority_rank DESC,created_at ASC,job_id ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            changed = connection.execute(
                "UPDATE production_jobs SET status='running',stage='正在取得生产执行权',worker_id=?,"
                "lease_expires_at=?,started_at=COALESCE(started_at,?),updated_at=?,"
                "attempt_count=attempt_count+1,revision=revision+1 "
                "WHERE job_id=? AND status='queued'",
                (worker_id, _future(lease_seconds), now, now, row["job_id"]),
            ).rowcount
            if changed != 1:
                return None
            self._event(connection, row["job_id"], "claimed", "queued", "running", {"worker_id": worker_id})
            claimed = connection.execute(
                "SELECT * FROM production_jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
        return self._private_row(claimed)

    def heartbeat(self, job_id: str, worker_id: str, *, lease_seconds: int = 120) -> None:
        with self._connection(immediate=True) as connection:
            changed = connection.execute(
                "UPDATE production_jobs SET lease_expires_at=?,updated_at=? "
                "WHERE job_id=? AND status='running' AND worker_id=?",
                (_future(lease_seconds), _now(), job_id, worker_id),
            ).rowcount
            if changed != 1:
                raise ProductionQueueConflict("生产任务租约已经失效")

    def update_stage(self, job_id: str, worker_id: str, stage: str, *, completed: int | None = None,
                     total: int | None = None) -> None:
        stage = _validate_identifier(stage, "任务阶段", maximum=300)
        progress = None
        if completed is not None or total is not None:
            if type(completed) is not int or type(total) is not int or not 0 <= completed <= total <= 10000 or total == 0:
                raise ProductionQueueError("制作进度必须是已完成步骤与实际总步骤")
            progress = {"completed": completed, "total": total, "ratio": completed / total, "basis": "steps"}
        with self._connection(immediate=True) as connection:
            current = connection.execute(
                "SELECT cancel_requested,progress_json FROM production_jobs WHERE job_id=? AND status='running' AND worker_id=?",
                (job_id, worker_id),
            ).fetchone()
            if current is not None and current['cancel_requested']:
                raise ProductionQueueCancelled('用户已取消后续制作，原产物与调用保留')
            previous = _decode(current['progress_json'], {}) if current is not None else {}
            if (progress is not None and previous.get('basis') == 'steps'
                    and previous.get('total') == total and previous.get('completed', 0) > completed):
                # Re-entering a frozen job reads completed caches before polling
                # the original supplier request. That is not lost production.
                return
            changed = connection.execute(
                "UPDATE production_jobs SET stage=?,progress_json=COALESCE(?,progress_json),updated_at=?,revision=revision+1 "
                "WHERE job_id=? AND status='running' AND worker_id=?",
                (stage, _json(progress) if progress is not None else None, _now(), job_id, worker_id),
            ).rowcount
            if changed != 1:
                raise ProductionQueueConflict("生产任务已经不属于当前工作者")
            if progress is not None:
                self._event(connection, job_id, "progress", "running", "running", {"stage": stage, "progress": progress})

    def finish(
        self,
        job_id: str,
        worker_id: str,
        *,
        status: str,
        stage: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        retryable: bool = False,
        safe_resume_point: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"completed", "awaiting_human", "ambiguous", "failed", "cancelled"}:
            raise ProductionQueueError("执行器返回了不受支持的终态")
        now = _now()
        with self._connection(immediate=True) as connection:
            row = connection.execute(
                "SELECT status,cancel_requested FROM production_jobs WHERE job_id=? AND worker_id=?",
                (job_id, worker_id),
            ).fetchone()
            if row is None or row["status"] != "running":
                raise ProductionQueueConflict("生产任务已经不属于当前工作者")
            if status == 'cancelled' and not row['cancel_requested']:
                raise ProductionQueueConflict('任务没有用户取消请求，不能标为已取消')
            effective_status = "cancelled" if bool(row["cancel_requested"]) and status != "ambiguous" else status
            effective_stage = "已在安全任务边界取消后续执行" if effective_status == "cancelled" else stage
            connection.execute(
                "UPDATE production_jobs SET status=?,stage=?,result_json=?,error_json=?,retryable=?,"
                "safe_resume_point=?,worker_id=NULL,lease_expires_at=NULL,finished_at=?,updated_at=?,"
                "revision=revision+1 WHERE job_id=?",
                (
                    effective_status, effective_stage, _json(_safe_public(result or {})),
                    _json(_safe_public(error or {})), int(bool(retryable)), safe_resume_point,
                    now, now, job_id,
                ),
            )
            self._event(connection, job_id, "finished", "running", effective_status)
            final = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public_row(final)

    def set_priority(self, job_id: str, priority: str) -> dict[str, Any]:
        if priority not in PRIORITIES:
            raise ProductionQueueError("优先级只能是 priority、normal 或 background")
        with self._connection(immediate=True) as connection:
            row = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise ProductionQueueError("生产任务不存在")
            if row["status"] not in {"queued", "paused"}:
                raise ProductionQueueConflict("只有待执行或暂停的任务可以调整优先级")
            connection.execute(
                "UPDATE production_jobs SET priority=?,priority_rank=?,updated_at=?,revision=revision+1 "
                "WHERE job_id=?",
                (priority, PRIORITIES[priority], _now(), job_id),
            )
            self._event(connection, job_id, "priority_changed", row["status"], row["status"], {"priority": priority})
            updated = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public_row(updated)

    def pause(self, job_id: str) -> dict[str, Any]:
        current=self.get(job_id)
        if current['status']=='ambiguous' and current.get('error',{}).get('code')=='provider_pending':
            return self._transition(job_id,{'ambiguous'},'paused',
                '后续制作已暂停，已受理的模型请求保留','paused')
        return self._transition(job_id, {"queued"}, "paused", "已暂停，等待恢复", "paused")

    def resume(self, job_id: str) -> dict[str, Any]:
        return self._transition(job_id, {"paused"}, "queued", "等待统一调度", "resumed")

    def continue_actual_usage(self, job_id: str, revision: int) -> dict[str, Any]:
        """Explicitly authorize a budget-blocked video, atomically, on its original ID."""
        if type(revision) is not int or revision < 1:
            raise ProductionQueueConflict('请读取当前制作记录后继续')
        with self._connection(immediate=True) as connection:
            row = connection.execute('SELECT * FROM production_jobs WHERE job_id=?', (job_id,)).fetchone()
            if row is None: raise ProductionQueueError('生产任务不存在')
            frozen = _decode(row['frozen_request'], {})
            receipts = frozen.get('billing_policy_changes', [])
            if any(r.get('queue_revision') == revision and r.get('policy') == 'actual_usage' for r in receipts):
                return self._public_row(row)  # Lost responses cannot enqueue or authorize twice.
            if row['revision'] != revision:
                raise ProductionQueueConflict('制作记录已更新，请刷新后继续')
            if row['kind'] != 'studio_avatar' or row['status'] != 'awaiting_human' or _decode(row['error_json'], {}).get('code') != 'budget_exceeded' or row['cancel_requested']:
                raise ProductionQueueConflict('当前任务无需解除原预算限制，请查看实际制作状态')
            link = connection.execute('SELECT creation_id FROM production_creation_links WHERE job_id=?', (job_id,)).fetchone()
            root = link['creation_id'] if link else job_id
            if connection.execute('SELECT 1 FROM production_creation_links l JOIN production_jobs j ON j.job_id=l.job_id WHERE l.creation_id=? AND j.created_at>?', (root, row['created_at'])).fetchone():
                raise ProductionQueueConflict('这条创作已有更新的制作记录，请继续当前版本')
            now = _now()
            receipt = {'at': now, 'policy': 'actual_usage', 'previous_max_charge_micros': frozen.get('max_charge_micros'), 'queue_revision': revision}
            frozen.update(billing_policy='actual_usage', max_charge_micros=None, billing_policy_changes=[*receipts, receipt])
            connection.execute("UPDATE production_jobs SET frozen_request=?,status='queued',stage='已恢复原任务，等待继续制作',error_json='{}',safe_resume_point=NULL,retryable=0,worker_id=NULL,lease_expires_at=NULL,finished_at=NULL,updated_at=?,revision=revision+1 WHERE job_id=?", (_json(frozen), now, job_id))
            self._event(connection, job_id, 'billing_authorized', row['status'], 'queued', {'stage':'已取消原视频总预算限制，复用已有配音和字幕继续', **receipt})
            updated = connection.execute('SELECT * FROM production_jobs WHERE job_id=?', (job_id,)).fetchone()
        return self._public_row(updated)

    def change_avatar_billing(self, job_id: str, *, revision: int, execution: dict,
                              approval_ref: str) -> dict[str, Any]:
        """Change only future segments; a funding change never reissues an unknown."""
        from backlot.studio import Studio
        from backlot.studio_avatar_app import verify_execution
        approval_ref=_validate_identifier(approval_ref,'扣费方式授权')
        if type(revision) is not int: raise ProductionQueueConflict('请读取当前制作记录')
        with self._connection(immediate=True) as db:
            row=db.execute('SELECT * FROM production_jobs WHERE job_id=?',(job_id,)).fetchone()
            if row is None: raise ProductionQueueError('生产任务不存在')
            frozen=_decode(row['frozen_request'],{})
            changes=frozen.get('avatar_billing_changes',[])
            existing=next((r for r in changes if r['approval_ref']==approval_ref),None)
            if existing:
                if existing['execution']!=execution: raise ProductionQueueConflict('同一次扣费授权不能替换其他配置')
                return self._public_row(row)
            if row['revision']!=revision or row['kind']!='studio_avatar' or row['status'] not in {'ambiguous','paused','awaiting_human'} or row['cancel_requested']:
                raise ProductionQueueConflict('制作状态已改变，未切换进行中的调用')
            if self._latest_creation_job(db,row)!=job_id:
                raise ProductionQueueConflict('这条创作已有更新的制作，请继续当前版本')
            original=frozen.get('avatar_execution') or {}
            if execution.get('billing_mode')!='rh_coins' or execution.get('profile')!=original.get('profile'):
                raise ProductionQueueConflict('仅可将后续分段改用RH币，原应用与制作参数必须保持')
            verify_execution(Studio(self.projects_root),execution)
            now=_now()
            receipt={'at':now,'approval_ref':approval_ref,'queue_revision':revision,'execution':execution}
            frozen.update(avatar_billing_execution=execution,avatar_billing_changes=[*changes,receipt])
            db.execute('UPDATE production_jobs SET frozen_request=?,updated_at=?,revision=revision+1 WHERE job_id=?',
                       (_json(frozen),now,job_id))
            self._event(db,job_id,'avatar_billing_changed',row['status'],row['status'],
                        {'billing_mode':'rh_coins','approval_ref':approval_ref,'new_identity':execution['identity']})
            return self._public_row(db.execute('SELECT * FROM production_jobs WHERE job_id=?',(job_id,)).fetchone())

    def reissue_unknown_avatar_segment(self, job_id: str, *, revision: int, chunk_index: int,
                                       expected_state_sha256: str, approval_ref: str) -> dict[str, Any]:
        """Operator-only, once, with exact state binding; worker journals the replacement."""
        from backlot.studio import Studio
        from backlot.studio_avatar_app import validate_submission_reissue, verify_execution
        from backlot.work_catalog import WorkError
        from lib.bailian_speech import operation_lock
        approval_ref=_validate_identifier(approval_ref,'未知分段重提授权')
        if type(revision) is not int or type(chunk_index) is not int or not isinstance(expected_state_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',expected_state_sha256):
            raise ProductionQueueConflict('重提需要当前记录、原分段及状态摘要')
        with self._connection(immediate=True) as db:
            row=db.execute('SELECT * FROM production_jobs WHERE job_id=?',(job_id,)).fetchone()
            if row is None: raise ProductionQueueError('生产任务不存在')
            frozen=_decode(row['frozen_request'],{})
            existing=frozen.get('avatar_submission_reissue')
            if existing:
                if (existing['approval_ref']==approval_ref and existing['chunk_index']==chunk_index
                    and existing['expected_state_sha256']==expected_state_sha256): return self._public_row(row)
                raise ProductionQueueConflict('本任务已记录一次未知分段重提授权，未再次提交')
            if (row['revision']!=revision or row['kind']!='studio_avatar' or row['status']!='ambiguous'
                or row['cancel_requested'] or _decode(row['error_json'],{}).get('code')!='provider_reconciliation'
                or self._latest_creation_job(db,row)!=job_id):
                raise ProductionQueueConflict('制作状态已改变，请先核对原请求')
            project=(self.projects_root/row['project_id']).resolve()
            render=(project/'renders'/str(frozen.get('render_id',''))).resolve()
            if not project.is_relative_to(self.projects_root.resolve()) or not render.is_relative_to(project/'renders'):
                raise ProductionQueueConflict('原制作目录无效')
            execution=frozen.get('avatar_billing_execution') or {}
            if (frozen.get('avatar_execution') or {}).get('route')!='local-runninghub-ai-app':
                raise ProductionQueueConflict('仅支持原本地AI应用的未知分段恢复')
            verify_execution(Studio(self.projects_root),execution)
            now=_now()
            with operation_lock(render/'avatar-app/state.lock'):
                path=render/'avatar-app/state.json'
                try:
                    raw=path.read_bytes();state=json.loads(raw)
                    receipt={'approval_ref':approval_ref,'chunk_index':chunk_index,
                             'expected_state_sha256':expected_state_sha256,'state_id':state.get('id'),
                             'execution':execution,'authorized_at':now,'queue_revision':revision}
                    if state.get('execution')!=frozen.get('avatar_execution') or (render/'avatar-source.mp4').exists():
                        raise WorkError('原数字人执行记录已改变或已有成片')
                    validate_submission_reissue(state,receipt,hashlib.sha256(raw).hexdigest())
                except (OSError,ValueError,WorkError):
                    raise ProductionQueueConflict('原未知分段状态已改变，请核对后继续；未重复提交') from None
                frozen['avatar_submission_reissue']=receipt
                db.execute("UPDATE production_jobs SET frozen_request=?,status='queued',stage='已授权仅用RH币重提未知分段一次，复用成功片段',error_json='{}',safe_resume_point=NULL,retryable=0,worker_id=NULL,lease_expires_at=NULL,finished_at=NULL,updated_at=?,revision=revision+1 WHERE job_id=?",(_json(frozen),now,job_id))
                self._event(db,job_id,'avatar_segment_reissue_authorized','ambiguous','queued',receipt)
            return self._public_row(db.execute('SELECT * FROM production_jobs WHERE job_id=?',(job_id,)).fetchone())

    def replace_avatar(self, job_id: str, *, revision: int, previous_intent: str,
                       approval_ref: str, maximum: int) -> dict[str, Any]:
        """Operator-only reissue after explicit consent; normal retry never calls this.

        Persist consent in the queue before a worker changes its stage journal.
        Replaying the same human reply cannot authorize a second paid attempt.
        """
        approval_ref = _validate_identifier(approval_ref, '重新生成授权')
        if type(revision) is not int or not re.fullmatch(r'call_[a-f0-9]{32}', previous_intent) or type(maximum) is not int or maximum <= 0:
            raise ProductionQueueConflict('重新生成需要当前记录、原意图和明确报价授权')
        with self._connection(immediate=True) as db:
            row = db.execute('SELECT * FROM production_jobs WHERE job_id=?', (job_id,)).fetchone()
            if row is None: raise ProductionQueueError('生产任务不存在')
            frozen = _decode(row['frozen_request'], {})
            receipts = frozen.get('avatar_replacements', [])
            existing = next((r for r in receipts if r['approval_ref'] == approval_ref), None)
            if existing:
                if existing['previous_intent'] != previous_intent or existing['maximum'] != maximum:
                    raise ProductionQueueConflict('同一次授权不能更换原请求或报价')
                return self._public_row(row)
            if row['revision'] != revision or row['kind'] != 'studio_avatar' or row['status'] != 'ambiguous' or row['cancel_requested'] or _decode(row['error_json'], {}).get('code') != 'provider_pending':
                raise ProductionQueueConflict('制作状态已改变，请核对当前请求后再重新生成')
            if self._latest_creation_job(db, row) != job_id:
                raise ProductionQueueConflict('这条创作已有更新的制作，请继续当前版本')
            project = (self.projects_root / row['project_id']).resolve()
            render = (project / 'renders' / str(frozen.get('render_id', ''))).resolve()
            if not project.is_relative_to(self.projects_root.resolve()) or not render.is_relative_to(project / 'renders'):
                raise ProductionQueueConflict('原制作目录无效')
            state = json.loads((render / 'gateway-state.json').read_text())
            stage = state.get('stages', {}).get('avatar', {})
            job = stage.get('job') or {}
            if stage.get('intent') != previous_intent or job.get('status') != 'submission_unknown' or job.get('upstream_id') or job.get('media_artifact_available') or (job.get('result') or {}).get('video_url') or (render / 'avatar-source.mp4').exists():
                raise ProductionQueueConflict('原请求已改变或已有可查询结果，不应重新付费生成')
            now = _now()
            intent = 'call_' + hashlib.sha256(f'{job_id}:{previous_intent}:{approval_ref}'.encode()).hexdigest()[:32]
            receipt = {'at':now, 'approval_ref':approval_ref, 'previous_intent':previous_intent,
                       'previous_job_id':job['id'], 'intent':intent, 'maximum':maximum}
            frozen['avatar_replacements'] = [*receipts, receipt]
            db.execute("UPDATE production_jobs SET frozen_request=?,status='queued',stage='已授权重新生成一次数字人，复用原配音与字幕',error_json='{}',safe_resume_point=NULL,finished_at=NULL,updated_at=?,revision=revision+1 WHERE job_id=?", (_json(frozen),now,job_id))
            self._event(db, job_id, 'avatar_replacement_authorized', 'ambiguous', 'queued', receipt)
            return self._public_row(db.execute('SELECT * FROM production_jobs WHERE job_id=?', (job_id,)).fetchone())

    def _latest_creation_job(self, db, row):
        link = db.execute('SELECT creation_id FROM production_creation_links WHERE job_id=?', (row['job_id'],)).fetchone()
        root = link['creation_id'] if link else row['job_id']
        latest = db.execute('SELECT j.job_id FROM production_creation_links l JOIN production_jobs j ON j.job_id=l.job_id WHERE l.creation_id=? ORDER BY j.created_at DESC LIMIT 1', (root,)).fetchone()
        return latest['job_id'] if latest else row['job_id']

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._connection(immediate=True) as connection:
            row = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise ProductionQueueError("生产任务不存在")
            status = str(row["status"])
            automatic_wait = status == 'ambiguous' and _decode(row['error_json'], {}).get('code') == 'provider_pending'
            if status in {"queued", "paused", "awaiting_human"} or automatic_wait:
                now = _now()
                connection.execute(
                    "UPDATE production_jobs SET status='cancelled',stage='已取消待执行任务',"
                    "finished_at=?,updated_at=?,revision=revision+1 WHERE job_id=?",
                    (now, now, job_id),
                )
                self._event(connection, job_id, "cancelled", status, "cancelled")
            elif status == "running":
                connection.execute(
                    "UPDATE production_jobs SET cancel_requested=1,stage='已请求在安全任务边界停止',"
                    "updated_at=?,revision=revision+1 WHERE job_id=?",
                    (_now(), job_id),
                )
                self._event(connection, job_id, "cancel_requested", "running", "running")
            else:
                raise ProductionQueueConflict("当前状态不能取消")
            updated = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public_row(updated)

    def retry(self, job_id: str) -> dict[str, Any]:
        with self._connection(immediate=True) as connection:
            row = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise ProductionQueueError("生产任务不存在")
            link = connection.execute("SELECT creation_id FROM production_creation_links WHERE job_id=?", (job_id,)).fetchone()
            root = link['creation_id'] if link else job_id
            if connection.execute("SELECT 1 FROM production_creation_links l JOIN production_jobs j ON j.job_id=l.job_id WHERE l.creation_id=? AND j.created_at>?", (root, row['created_at'])).fetchone():
                raise ProductionQueueConflict('这条创作已有更新的制作记录，请打开当前制作，原记录保持不变')
            if row["status"] == "ambiguous":
                raise ProductionQueueConflict("供应商受理状态不明确，核对原任务后才能恢复")
            material_confirmation = row["status"] == "awaiting_human" and row["kind"] == "studio_avatar" and row["safe_resume_point"] == "studio_avatar_material_rights"
            if row['kind']=='studio_avatar' and _decode(row['error_json'],{}).get('code')=='template_incompatible':
                # Retry replays frozen inputs, so it cannot pick up a repaired
                # draft. Require the normal quote/continuation boundary instead.
                raise ProductionQueueConflict('请返回制作页，使用已保存的草稿继续；原任务保留，不重跑旧模板输入')
            audio_recheck=False
            if (row['kind']=='studio_avatar' and row['status']=='awaiting_human'
                and _decode(row['error_json'],{}).get('code')=='audio_check_review'):
                from backlot.studio_audio_check import generated_clock_ready
                audio_recheck=generated_clock_ready(self.projects_root/row['project_id'],_decode(row['frozen_request'],{}))
            avatar_recheck=False
            if (row['status']=='failed' and row['kind']=='studio_avatar'
                and row['safe_resume_point']=='studio_avatar'
                and _decode(row['error_json'],{}).get('code')=='invalid'):
                # Compatibility with the old producer's blanket failure code.
                # Retry only re-enters the producer; it re-queries the original
                # provider ID before deciding whether short inputs are safe.
                frozen=_decode(row['frozen_request'],{})
                project=(self.projects_root/row['project_id']).resolve()
                render=(project/'renders'/str(frozen.get('render_id',''))).resolve()
                if project.is_relative_to(self.projects_root.resolve()) and render.is_relative_to(project/'renders'):
                    try:
                        from backlot.studio_avatar_app import long_failure_recoverable
                        state=json.loads((render/'avatar-app/state.json').read_text())
                        avatar_recheck=(state.get('execution')==frozen.get('avatar_execution')
                                        and bool(frozen.get('avatar_execution')) and long_failure_recoverable(state))
                    except (OSError,ValueError,KeyError,TypeError): pass
            if not (material_confirmation or avatar_recheck or audio_recheck) and (row["status"] != "failed" or not bool(row["retryable"])):
                raise ProductionQueueConflict("该失败任务没有安全重试条件")
            now = _now()
            connection.execute(
                "UPDATE production_jobs SET status='queued',stage='等待从安全点继续',error_json='{}',"
                "retryable=0,cancel_requested=0,worker_id=NULL,lease_expires_at=NULL,finished_at=NULL,"
                "updated_at=?,revision=revision+1 WHERE job_id=?",
                (now, job_id),
            )
            self._event(connection, job_id, "retried", row["status"], "queued")
            updated = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public_row(updated)

    def expired_running(self) -> list[dict[str, Any]]:
        now = _now()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM production_jobs WHERE status='running' AND lease_expires_at IS NOT NULL "
                "AND lease_expires_at < ? ORDER BY created_at ASC",
                (now,),
            ).fetchall()
        return [self._private_row(row) for row in rows]

    def recover_expired(
        self,
        job_id: str,
        *,
        status: str,
        stage: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        retryable: bool = False,
        safe_resume_point: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"queued", "completed", "awaiting_human", "ambiguous", "failed"}:
            raise ProductionQueueError("恢复状态无效")
        with self._connection(immediate=True) as connection:
            row = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise ProductionQueueError("生产任务不存在")
            if row["status"] != "running":
                return self._public_row(row)
            now = _now()
            connection.execute(
                "UPDATE production_jobs SET status=?,stage=?,result_json=?,error_json=?,retryable=?,"
                "safe_resume_point=?,worker_id=NULL,lease_expires_at=NULL,finished_at=?,updated_at=?,"
                "revision=revision+1 WHERE job_id=?",
                (
                    status, stage, _json(_safe_public(result or {})), _json(_safe_public(error or {})),
                    int(bool(retryable)), safe_resume_point,
                    now if status != "queued" else None, now, job_id,
                ),
            )
            self._event(connection, job_id, "lease_reconciled", "running", status)
            updated = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public_row(updated)

    def events(self, job_id: str) -> list[dict[str, Any]]:
        self.get(job_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT event_type,from_status,to_status,detail_json,created_at "
                "FROM production_events WHERE job_id=? ORDER BY event_id ASC",
                (job_id,),
            ).fetchall()
        return [
            {
                "event_type": row["event_type"], "from_status": row["from_status"],
                "to_status": row["to_status"], "detail": _safe_public(_decode(row["detail_json"], {})),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _transition(
        self,
        job_id: str,
        allowed: set[str],
        target: str,
        stage: str,
        event_type: str,
    ) -> dict[str, Any]:
        with self._connection(immediate=True) as connection:
            row = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise ProductionQueueError("生产任务不存在")
            if row["status"] not in allowed:
                raise ProductionQueueConflict("当前状态不能执行该操作")
            connection.execute(
                "UPDATE production_jobs SET status=?,stage=?,updated_at=?,revision=revision+1 WHERE job_id=?",
                (target, stage, _now(), job_id),
            )
            self._event(connection, job_id, event_type, row["status"], target)
            updated = connection.execute("SELECT * FROM production_jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._public_row(updated)

    @staticmethod
    def _private_row(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["frozen_request"] = _decode(result.pop("frozen_request", "{}"), {})
        result["result"] = _decode(result.pop("result_json", "{}"), {})
        result["error"] = _decode(result.pop("error_json", "{}"), {})
        for key in ("retryable", "cancel_requested"):
            result[key] = bool(result.get(key))
        return result

    @classmethod
    def _public_row(cls, row: sqlite3.Row) -> dict[str, Any]:
        private = cls._private_row(row)
        observed = _decode(private.pop("progress_json", "{}"), {})
        private.pop("idempotency_key", None)
        private.pop("priority_rank", None)
        private.pop("worker_id", None)
        private.pop("lease_expires_at", None)
        private.pop("frozen_request", None)
        private["id"] = private["job_id"]
        private["title"] = {
            "review_preview": "无数字人一键审核预览",
            "avatar_review_preview": "有数字人一键审核预览",
            "full_preview": "合成全片审核预览",
            "published_remix": "成片二剪待审预览",
            "material_commentary": "素材解说待审预览",
            "studio_graphic": "图文视频",
            "studio_avatar": "数字人口播",
            "studio_motion": "动效口播",
        }.get(private["kind"], private["kind"])
        private["progress"] = {
            "completed": 1 if private["status"] == "completed" else 0,
            "total": 1,
            "failed": 1 if private["status"] == "failed" else 0,
            "ratio": 1.0 if private["status"] == "completed" else 0.0,
        }
        if observed and observed.get("basis") == "steps":
            private["progress"] = {**observed, "failed": 1 if private["status"] == "failed" else 0}
            if private["status"] == "completed":
                private["progress"].update(completed=observed["total"], ratio=1.0)
        private["target_view"] = "quality" if private["kind"] == "full_preview" else "review"
        private["wait_reason"] = (
            "等待前序生产任务释放执行资格" if private["status"] == "queued"
            else "任务已暂停" if private["status"] == "paused"
            else "系统自动查询原请求，无需重复提交" if private["status"] == "ambiguous" and private.get('error', {}).get('code') == 'provider_pending'
            else "供应商受理状态需要人工核对" if private["status"] == "ambiguous"
            else "底层生产管线正在等待人工确认" if private["status"] == "awaiting_human"
            else ""
        )
        private["executor"] = "本机统一调度器" if private["status"] == "running" else ""
        return _safe_public(private)

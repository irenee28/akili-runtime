from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class MemoryRecord:
    id: int
    scope: str
    family: str
    version: int
    content: str
    source: str
    status: str
    created_at: str
    content_hash: str
    supersedes_id: int | None

    def to_dict(self) -> dict:
        return asdict(self)


class AkiliStore:
    """Local SQLite reference implementation of governed procedural memory."""

    def __init__(self, path: str | Path = ".akili/akili.db", max_versions_per_family: int = 64):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_versions_per_family = max_versions_per_family
        if max_versions_per_family < 2:
            raise ValueError("max_versions_per_family must be at least 2")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL,
                    family TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('ACTIVE','SUPERSEDED')),
                    created_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    supersedes_id INTEGER,
                    UNIQUE(scope, family, version),
                    FOREIGN KEY(supersedes_id) REFERENCES memories(id)
                );
                CREATE INDEX IF NOT EXISTS idx_memories_active
                ON memories(scope, family, status);

                CREATE TABLE IF NOT EXISTS audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    scope TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL
                );
                """
            )
            if con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0:
                self._append_audit(con, "STORE_CREATED", None, {"path": str(self.path)})

    def _append_audit(self, con: sqlite3.Connection, event: str, scope: str | None, payload: dict) -> None:
        row = con.execute("SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = row[0] if row else "GENESIS"
        created_at = _now()
        body = {"event": event, "scope": scope, "payload": payload, "created_at": created_at, "prev_hash": prev_hash}
        entry_hash = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
        con.execute(
            "INSERT INTO audit(event, scope, payload, created_at, prev_hash, entry_hash) VALUES(?,?,?,?,?,?)",
            (event, scope, _canonical(payload), created_at, prev_hash, entry_hash),
        )

    def remember(self, *, scope: str, family: str, content: str, source: str) -> MemoryRecord:
        scope, family, content, source = [str(v).strip() for v in (scope, family, content, source)]
        if not all((scope, family, content, source)):
            raise ValueError("scope, family, content and source are required")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with self._connect() as con:
            active = con.execute(
                "SELECT * FROM memories WHERE scope=? AND family=? AND status='ACTIVE'", (scope, family)
            ).fetchone()
            if active and active["content_hash"] == content_hash:
                self._append_audit(con, "MEMORY_DUPLICATE", scope, {"family": family, "active_id": active["id"], "source": source})
                return self._row_to_memory(active)

            version = con.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM memories WHERE scope=? AND family=?", (scope, family)
            ).fetchone()[0]
            supersedes_id = active["id"] if active else None
            if active:
                con.execute("UPDATE memories SET status='SUPERSEDED' WHERE id=?", (active["id"],))

            created_at = _now()
            cur = con.execute(
                """INSERT INTO memories(scope,family,version,content,source,status,created_at,content_hash,supersedes_id)
                   VALUES(?,?,?,?,?,'ACTIVE',?,?,?)""",
                (scope, family, version, content, source, created_at, content_hash, supersedes_id),
            )
            memory_id = cur.lastrowid
            self._append_audit(con, "MEMORY_ACTIVATED", scope, {
                "memory_id": memory_id, "family": family, "version": version,
                "content_hash": content_hash, "source": source, "supersedes_id": supersedes_id,
            })
            self._enforce_bound(con, scope, family)
            row = con.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
            return self._row_to_memory(row)

    def _enforce_bound(self, con: sqlite3.Connection, scope: str, family: str) -> None:
        rows = con.execute(
            "SELECT id, version, status FROM memories WHERE scope=? AND family=? ORDER BY version ASC", (scope, family)
        ).fetchall()
        excess = len(rows) - self.max_versions_per_family
        if excess <= 0:
            return
        removable = [r for r in rows if r["status"] == "SUPERSEDED"][:excess]
        if len(removable) < excess:
            raise RuntimeError("version bound exceeded with no safe superseded record to evict")
        for row in removable:
            con.execute("DELETE FROM memories WHERE id=?", (row["id"],))
            self._append_audit(con, "MEMORY_EVICTED", scope, {"family": family, "version": row["version"], "memory_id": row["id"]})

    def retrieve(self, *, scope: str, families: Iterable[str] | None = None) -> list[MemoryRecord]:
        scope = str(scope).strip()
        if not scope:
            raise ValueError("scope is required")
        params: list[object] = [scope]
        sql = "SELECT * FROM memories WHERE scope=? AND status='ACTIVE'"
        family_list = [str(f).strip() for f in (families or []) if str(f).strip()]
        if family_list:
            sql += " AND family IN (" + ",".join("?" for _ in family_list) + ")"
            params.extend(family_list)
        sql += " ORDER BY family"
        with self._connect() as con:
            rows = con.execute(sql, params).fetchall()
            records = [self._row_to_memory(r) for r in rows]
            self._append_audit(con, "MEMORY_RETRIEVED", scope, {"families": family_list, "memory_ids": [r.id for r in records], "count": len(records)})
            return records

    def context_bundle(self, *, scope: str, task: str, families: Iterable[str] | None = None) -> dict:
        task = str(task).strip()
        if not task:
            raise ValueError("task is required")
        records = self.retrieve(scope=scope, families=families)
        lines = ["ACTIVE AKILI PROCEDURES:"]
        if not records:
            lines.append("- none")
        for record in records:
            lines.append(f"- [{record.family} v{record.version}] {record.content} (source={record.source}, sha256={record.content_hash[:12]})")
        prompt = "\n".join(lines)
        return {
            "scope": scope,
            "task": task,
            "active_memories": [r.to_dict() for r in records],
            "memory_prompt": prompt,
            "approx_prompt_tokens": max(1, len(prompt) // 4),
            "note": "v0.1 emits a context bundle; it does not call an LLM.",
        }

    def audit_entries(self, *, scope: str | None = None) -> list[dict]:
        with self._connect() as con:
            if scope:
                rows = con.execute("SELECT * FROM audit WHERE scope=? OR scope IS NULL ORDER BY seq", (scope,)).fetchall()
            else:
                rows = con.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        return [{
            "seq": row["seq"], "event": row["event"], "scope": row["scope"],
            "payload": json.loads(row["payload"]), "created_at": row["created_at"],
            "prev_hash": row["prev_hash"], "entry_hash": row["entry_hash"],
        } for row in rows]

    def validate_audit_chain(self) -> bool:
        prev_hash = "GENESIS"
        for entry in self.audit_entries():
            body = {"event": entry["event"], "scope": entry["scope"], "payload": entry["payload"], "created_at": entry["created_at"], "prev_hash": entry["prev_hash"]}
            expected = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
            if entry["prev_hash"] != prev_hash or entry["entry_hash"] != expected:
                return False
            prev_hash = entry["entry_hash"]
        return True

    @staticmethod
    def _row_to_memory(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"], scope=row["scope"], family=row["family"], version=row["version"],
            content=row["content"], source=row["source"], status=row["status"],
            created_at=row["created_at"], content_hash=row["content_hash"], supersedes_id=row["supersedes_id"],
        )

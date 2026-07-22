from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .hashing import canonical_json, sha256_text


class HashChainAuditLog:
    """Append-only JSONL hash chain.

    The log is tamper-evident, not tamper-proof. Protect the storage and publish
    the final chain head in an independent release manifest for stronger evidence.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else None
        self.entries: List[Dict[str, Any]] = []
        if self.path is not None and self.path.exists():
            self.entries = self._read(self.path)
            if not self.validate(self.entries):
                raise ValueError(f"Invalid audit chain: {self.path}")

    @staticmethod
    def _read(path: Path) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"Audit entry at line {line_number} is not an object")
            entries.append(value)
        return entries

    @staticmethod
    def validate(entries: Iterable[Mapping[str, Any]]) -> bool:
        previous = "GENESIS"
        for expected_index, entry in enumerate(entries):
            if entry.get("index") != expected_index:
                return False
            if entry.get("previous_hash") != previous:
                return False
            body = {key: value for key, value in entry.items() if key != "entry_hash"}
            if sha256_text(canonical_json(body)) != entry.get("entry_hash"):
                return False
            previous = str(entry.get("entry_hash"))
        return True

    def append(self, event: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        previous = self.entries[-1]["entry_hash"] if self.entries else "GENESIS"
        body: Dict[str, Any] = {
            "index": len(self.entries),
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "event": str(event),
            "payload": dict(payload),
            "previous_hash": previous,
        }
        body["entry_hash"] = sha256_text(canonical_json(body))
        self.entries.append(body)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n")
        return body

    @property
    def head(self) -> str:
        return self.entries[-1]["entry_hash"] if self.entries else "GENESIS"

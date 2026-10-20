"""Memória do SO — append-only, sem banco externo (padrão agentic-os)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _default_root() -> Path:
    env = os.environ.get("VEU_DATA_ROOT")
    if env:
        return Path(env)
    return Path.home() / ".veu" / "data"


class Memory:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.log_path = self.root / "audit.jsonl"
        self.decisions_path = self.root / "decisions.jsonl"
        self.sessions_path = self.root / "sessions.jsonl"

    def append(self, kind: str, payload: dict[str, Any], *, sink: str = "audit") -> dict[str, Any]:
        from veu.redact import redact_obj

        safe = redact_obj(payload) if isinstance(payload, dict) else payload
        event = {
            "id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **(safe if isinstance(safe, dict) else {"payload": safe}),
        }
        path = {
            "audit": self.log_path,
            "decisions": self.decisions_path,
            "sessions": self.sessions_path,
        }.get(sink, self.log_path)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def recent(self, *, sink: str = "audit", limit: int = 40) -> list[dict[str, Any]]:
        path = {
            "audit": self.log_path,
            "decisions": self.decisions_path,
            "sessions": self.sessions_path,
        }.get(sink, self.log_path)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        from veu.redact import redact_obj

        for line in lines[-limit:]:
            try:
                out.append(redact_obj(json.loads(line)))
            except json.JSONDecodeError:
                continue
        return out

    def pulse(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "audit_events": self._count(self.log_path),
            "decisions": self._count(self.decisions_path),
            "sessions": self._count(self.sessions_path),
        }

    @staticmethod
    def _count(path: Path) -> int:
        if not path.exists():
            return 0
        return sum(1 for _ in path.open(encoding="utf-8"))


# Alias usado por auth/mcp audit (mesmo store append-only).
MemoryStore = Memory

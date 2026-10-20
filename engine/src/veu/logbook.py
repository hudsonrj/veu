"""Registro estruturado do SO — ring buffer + JSONL + SSE /stream/log."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Literal

from veu.redact import redact_text

Level = Literal["debug", "info", "warn", "error"]
LEVEL_RANK = {"debug": 0, "info": 1, "warn": 2, "error": 3}

RING_SIZE = 2000
JSONL_MAX_BYTES = 2 * 1024 * 1024
HEARTBEAT_SEC = 15.0


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _jsonl_path() -> Path:
    return _root() / "os_log.jsonl"


class LogBook:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seq = 0
        self._ring: deque[dict[str, Any]] = deque(maxlen=RING_SIZE)
        self._subs: dict[int, asyncio.Queue[dict[str, Any]]] = {}
        self._sub_seq = 0

    def subscribe(self) -> tuple[int, asyncio.Queue[dict[str, Any]]]:
        self._sub_seq += 1
        sid = self._sub_seq
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subs[sid] = q
        return sid, q

    def unsubscribe(self, sid: int) -> None:
        self._subs.pop(sid, None)

    def emit(
        self,
        *,
        level: Level = "info",
        source: str,
        message: str,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        if level not in LEVEL_RANK:
            level = "info"
        msg = redact_text(str(message or ""))[:4000]
        src = redact_text(str(source or "host"))[:120]
        with self._lock:
            self._seq += 1
            event = {
                "id": str(self._seq),
                "ts": time.time(),
                "level": level,
                "source": src,
                "message": msg,
            }
            if job_id:
                event["job_id"] = str(job_id)[:80]
            self._ring.append(event)
            self._append_jsonl(event)
        self._fanout(event)
        return event

    def _append_jsonl(self, event: dict[str, Any]) -> None:
        path = _jsonl_path()
        try:
            if path.exists() and path.stat().st_size >= JSONL_MAX_BYTES:
                rotated = path.with_suffix(".jsonl.1")
                try:
                    rotated.unlink(missing_ok=True)
                except OSError:
                    pass
                path.replace(rotated)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _fanout(self, event: dict[str, Any]) -> None:
        dead: list[int] = []
        for sid, q in list(self._subs.items()):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(sid)
        for sid in dead:
            self._subs.pop(sid, None)

    def since(
        self,
        last_id: str | None,
        *,
        level: str | None = None,
        source: str | None = None,
        job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        min_rank = LEVEL_RANK.get((level or "").lower(), 0) if level else None
        src = (source or "").strip() or None
        jid = (job_id or "").strip() or None
        try:
            after = int(last_id) if last_id not in (None, "", "0") else 0
        except ValueError:
            after = 0
        with self._lock:
            rows = list(self._ring)
        out: list[dict[str, Any]] = []
        for ev in rows:
            try:
                eid = int(ev.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if eid <= after:
                continue
            if not _match(ev, min_rank=min_rank, source=src, job_id=jid):
                continue
            out.append(ev)
        return out

    def matches_filters(
        self,
        event: dict[str, Any],
        *,
        level: str | None = None,
        source: str | None = None,
        job_id: str | None = None,
    ) -> bool:
        min_rank = LEVEL_RANK.get((level or "").lower(), 0) if level else None
        return _match(
            event,
            min_rank=min_rank,
            source=(source or "").strip() or None,
            job_id=(job_id or "").strip() or None,
        )


def _match(
    event: dict[str, Any],
    *,
    min_rank: int | None,
    source: str | None,
    job_id: str | None,
) -> bool:
    if min_rank is not None:
        rank = LEVEL_RANK.get(str(event.get("level") or "info"), 1)
        if rank < min_rank:
            return False
    if source and str(event.get("source") or "") != source:
        return False
    if job_id and str(event.get("job_id") or "") != job_id:
        return False
    return True


book = LogBook()


def emit(
    *,
    level: Level = "info",
    source: str,
    message: str,
    job_id: str | None = None,
) -> dict[str, Any]:
    return book.emit(level=level, source=source, message=message, job_id=job_id)


def reset_for_tests() -> None:
    """Reinicia o singleton (só testes)."""
    global book
    book = LogBook()

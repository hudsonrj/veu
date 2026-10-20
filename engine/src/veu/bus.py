"""Event bus interno — publica mudanças para o SSE /stream."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[int, asyncio.Queue[dict[str, Any]]] = {}
        self._seq = 0
        self._last: dict[str, Any] = {}  # type -> last payload snapshot hash/key
        self._lock = asyncio.Lock()

    def subscribe(self) -> tuple[int, asyncio.Queue[dict[str, Any]]]:
        self._seq += 1
        sid = self._seq
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._subs[sid] = q
        return sid, q

    def unsubscribe(self, sid: int) -> None:
        self._subs.pop(sid, None)

    def publish(self, event_type: str, patch: dict[str, Any] | None = None, *, full: Any = None) -> None:
        """Publica evento nomeado. patch = delta; full = snapshot opcional."""
        # fingerprint simples pra não reemitir idle idêntico
        key = json.dumps({"p": patch, "f": full}, sort_keys=True, default=str)[:800]
        if self._last.get(event_type) == key:
            return
        self._last[event_type] = key
        msg = {
            "type": event_type,
            "ts": time.time(),
            "patch": patch or {},
            "full": full,
        }
        dead: list[int] = []
        for sid, q in list(self._subs.items()):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(sid)
        for sid in dead:
            self._subs.pop(sid, None)

    def publish_sync(self, event_type: str, patch: dict[str, Any] | None = None, *, full: Any = None) -> None:
        """Wrapper síncrono — safe a partir de rotas sync FastAPI."""
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(lambda: self.publish(event_type, patch, full=full))
        except RuntimeError:
            self.publish(event_type, patch, full=full)


bus = EventBus()

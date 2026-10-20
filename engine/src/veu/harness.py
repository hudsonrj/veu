"""Harness agêntico — tools ativas sob a respiração (padrão OpenClaw).

Ativado automaticamente quando Jev marca a intenção como agentic
ou quando a rota exige ferramentas (browser, host, mcp, comm, grokbot…).

Histórico persiste em disco — Mission Control não “esquece” o voo após restart.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from veu.redact import redact_text


def _safe_intent(intent: str) -> str:
    return redact_text((intent or "").strip()[:240])


# Tools por rota / superfície
ROUTE_TOOLS: dict[str, list[str]] = {
    "chat": ["memory.read", "memory.write"],
    "openrag": ["openrag.ask", "memory.write"],
    "notion": ["notion.search", "notion.read", "memory.write"],
    "grokbot": ["grokbot.handoff", "grokbot.wait", "memory.write"],
    "comm": ["channel.read", "channel.draft", "channel.send", "memory.write"],
    "browser": ["browser.navigate", "browser.read", "browser.click", "memory.write"],
    "files": ["host.fs.list", "host.fs.read", "host.fs.write", "memory.write"],
    "system": ["host.shell", "host.app.open", "host.app.focus", "memory.write"],
    "mcp": ["mcp.list", "mcp.call", "memory.write"],
}

ALWAYS_ON = ["jev.route", "ecc.match", "policy.risk"]


def _history_path() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "harness.jsonl"


class Harness:
    """Sessão de tools ativas para uma formação/ação agêntica."""

    def __init__(self) -> None:
        self._active: dict[str, Any] | None = None
        self._history: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        path = _history_path()
        if not path.exists():
            return
        rows: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines()[-80:]:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            return
        self._history = rows[-50:]

    def _persist(self, row: dict[str, Any]) -> None:
        path = _history_path()
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def pulse(self) -> dict[str, Any]:
        return {
            "active": bool(self._active),
            "session": self._active,
            "recent": list(reversed(self._history[-16:])),
            "persisted": str(_history_path()),
        }

    def is_agentic(
        self,
        *,
        intent: str,
        kind: str,
        route: str,
        jev: dict[str, Any] | None,
    ) -> bool:
        """Identifica se a intenção exige harness (multi-tool / side-effect)."""
        jev = jev or {}
        if "agentic" in jev:
            noul = float(jev.get("agentic") or 0.0)
            if noul >= 0.55:
                return True
            if noul <= 0.35 and route == "chat" and kind in {"greeting", "question"}:
                return False

        if route in {
            "grokbot",
            "browser",
            "files",
            "system",
            "mcp",
            "comm",
            "notion",
            "openrag",
        }:
            return True
        if kind in {
            "grokbot",
            "browser",
            "files",
            "system",
            "mcp",
            "comm",
            "openrag",
            "workspace",
            "task",
        }:
            return True

        t = intent.lower()
        triggers = (
            "abra",
            "execute",
            "rode",
            "envie",
            "publique",
            "apague",
            "crie",
            "monte",
            "automatize",
            "agente",
            "harness",
            "navegue",
            "terminal",
            "shell",
            "mcp",
            "handoff",
        )
        return any(k in t for k in triggers)

    def activate(
        self,
        *,
        intent: str,
        route: str,
        kind: str,
        breath: str,
        channel: str | None = None,
        extra_tools: list[str] | None = None,
    ) -> dict[str, Any]:
        tools = list(ALWAYS_ON)
        tools.extend(ROUTE_TOOLS.get(route, ROUTE_TOOLS["chat"]))
        if channel:
            tools.append(f"channel.{channel}.read")
            tools.append(f"channel.{channel}.draft")
        if extra_tools:
            tools.extend(extra_tools)
        seen: set[str] = set()
        uniq: list[str] = []
        for t in tools:
            if t not in seen:
                seen.add(t)
                uniq.append(t)

        risk = {
            "guided": "ask",
            "semi": "medium",
            "free": "high",
            "autonomous": "medium",
        }.get(breath, "ask")
        session = {
            "id": f"har-{uuid.uuid4().hex[:10]}",
            "ts": time.time(),
            "intent": _safe_intent(intent),
            "route": route,
            "kind": kind,
            "breath": breath,
            "risk_ceiling": risk,
            "tools": uniq,
            "channel": channel,
            "state": "active",
            "source": "auto",
        }
        self._active = session
        activated = {**session, "state": "running"}
        self._history.append(activated)
        self._persist(activated)
        if len(self._history) > 100:
            self._history = self._history[-50:]
        try:
            from veu.bus import bus

            bus.publish_sync("job", {"harness": session["id"], "state": "running"}, full=activated)
        except Exception:  # noqa: BLE001
            pass
        try:
            from veu import logbook

            logbook.emit(
                level="info",
                source="agente",
                message=f"route · {route} · tools={len(uniq)}",
            )
            logbook.emit(
                level="info",
                source="agente",
                message=f"policy.risk · {risk}",
            )
            for t in uniq[:12]:
                logbook.emit(level="info", source="agente", message=f"tool · {t}")
                if t.startswith("host."):
                    logbook.emit(level="info", source="host", message=f"host.* · {t}")
                if t == "memory.write":
                    logbook.emit(level="info", source="agente", message="memory.write")
        except Exception:  # noqa: BLE001
            pass
        return session

    def deactivate(self, *, reason: str = "done") -> None:
        if self._active:
            state = "done" if reason in {"done", "ok", "completed"} else reason
            if state not in {"done", "failed", "cancelled"}:
                state = "done"
            done = {
                **self._active,
                "state": state,
                "reason": reason,
                "ended": time.time(),
            }
            self._history.append(done)
            self._persist(done)
            self._active = None
            try:
                from veu.bus import bus

                bus.publish_sync("job", {"harness": done.get("id"), "state": state}, full=done)
            except Exception:  # noqa: BLE001
                pass

    def revoke_all(self, *, reason: str = "stop-all") -> int:
        """Revoga sessão ativa e marca recentes ativas como cancelled."""
        n = 0
        if self._active:
            self.deactivate(reason="cancelled")
            n += 1
        for row in self._history:
            if row.get("state") in {"active", "running"}:
                row["state"] = "cancelled"
                row["reason"] = reason
                row["ended"] = time.time()
                n += 1
                self._persist(row)
        return n

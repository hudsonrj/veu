"""Ruflo como espinha dorsal do Véu.

Espelha o meta-harness do ruvnet/ruflo (plugins, swarm, missions, Claude control,
console Orbital, hosts Véu) sem embutir o monorepo. Persistência em
`~/.veu/ruflo/` (ou VEU_HOME). Opcionalmente detecta `npx ruflo` no host.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Literal

ControlLevel = Literal["read", "write", "manage", "full"]
ApprovalMode = Literal["ask", "auto"]
Topology = Literal["hierarchical", "mesh", "ring", "star"]

_HERE = Path(__file__).resolve().parent
_PLUGIN_SEED = _HERE / "data" / "ruflo_plugins.json"

# Níveis alinhados a ADR-444 (Claude controls the console)
CONTROL_RANK = {"read": 0, "write": 1, "manage": 2, "full": 3}

# Ações do cockpit → nível mínimo
ACTION_LEVEL: dict[str, ControlLevel] = {
    "navigate": "read",
    "inspect": "read",
    "mission_create": "write",
    "mission_update": "write",
    "plugin_toggle": "manage",
    "swarm_init": "manage",
    "swarm_stop": "manage",  # quem inicia o swarm consegue parar
    "host_run": "full",
}


def _home() -> Path:
    raw = os.environ.get("VEU_HOME") or os.environ.get("HOME") or "/tmp"
    return Path(raw) / ".veu" / "ruflo"


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _seed_plugins() -> list[dict[str, Any]]:
    raw = _load_json(_PLUGIN_SEED, [])
    if isinstance(raw, list) and raw:
        return raw
    # fallback mínimo
    return [
        {
            "id": "ruflo-core",
            "name": "ruflo-core",
            "category": "core",
            "description": "MCP foundation — memory, agents, swarm",
            "enabled": True,
        },
        {
            "id": "ruflo-console",
            "name": "ruflo-console",
            "category": "core",
            "description": "Agent cockpit / Orbital console",
            "enabled": True,
        },
        {
            "id": "ruflo-swarm",
            "name": "ruflo-swarm",
            "category": "core",
            "description": "Swarm topologies",
            "enabled": True,
        },
        {
            "id": "ruflo-ruos",
            "name": "ruflo-ruos",
            "category": "domain",
            "description": "ruOS desktops as swarm hosts",
            "enabled": True,
        },
    ]


class RufloSpine:
    """Estado vivo do harness Ruflo dentro do kernel Véu."""

    def __init__(self) -> None:
        self.root = _home()
        self.root.mkdir(parents=True, exist_ok=True)
        self._plugins_path = self.root / "plugins.json"
        self._state_path = self.root / "state.json"
        self._missions_path = self.root / "missions.json"
        self._events_path = self.root / "events.jsonl"
        self._ensure()

    def _ensure(self) -> None:
        if not self._plugins_path.is_file():
            _save_json(self._plugins_path, _seed_plugins())
        if not self._state_path.is_file():
            _save_json(
                self._state_path,
                {
                    "topology": "hierarchical",
                    "theme": "orbital",
                    "palette": "arctic",
                    "control": {"level": "read", "approval": "ask", "active": False},
                    "swarm": {"active": False, "agents": [], "started_at": None},
                    "ruos": {
                        "configured": bool(
                            os.environ.get("RUOS_MCP_URL")
                            and os.environ.get("RUOS_MCP_TOKEN")
                        ),
                        "hosts": [],
                        "mcp": "https://ruos.cognitum.one/mcp",
                    },
                    "cli": self._detect_cli(),
                    "boot": time.time(),
                },
            )
        if not self._missions_path.is_file():
            _save_json(self._missions_path, {"missions": []})

    def _detect_cli(self) -> dict[str, Any]:
        npx = shutil.which("npx")
        node = shutil.which("node")
        version = None
        if npx:
            try:
                out = subprocess.run(
                    [npx, "-y", "ruflo@latest", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=25,
                    check=False,
                )
                line = (out.stdout or out.stderr or "").strip().splitlines()
                version = line[0][:80] if line else None
            except Exception:  # noqa: BLE001
                version = None
        return {
            "npx": bool(npx),
            "node": bool(node),
            "version": version,
            "available": bool(npx and version),
        }

    def _log(self, kind: str, **extra: Any) -> None:
        row = {"ts": time.time(), "kind": kind, **extra}
        try:
            with self._events_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    def plugins(self) -> list[dict[str, Any]]:
        seeded = {p["id"]: p for p in _seed_plugins()}
        cur = _load_json(self._plugins_path, [])
        by_id: dict[str, dict[str, Any]] = {}
        if isinstance(cur, list):
            for p in cur:
                if isinstance(p, dict) and p.get("id"):
                    by_id[str(p["id"])] = p
        # merge novos plugins do seed
        for pid, p in seeded.items():
            if pid not in by_id:
                by_id[pid] = dict(p)
            else:
                by_id[pid]["description"] = p.get("description") or by_id[pid].get(
                    "description"
                )
                by_id[pid]["category"] = p.get("category") or by_id[pid].get("category")
                by_id[pid]["name"] = p.get("name") or by_id[pid].get("name")
        out = list(by_id.values())
        out.sort(key=lambda x: (str(x.get("category") or ""), str(x.get("id") or "")))
        return out

    def set_plugin(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        plugs = self.plugins()
        found = False
        for p in plugs:
            if p.get("id") == plugin_id:
                p["enabled"] = bool(enabled)
                found = True
                break
        if not found:
            return {"ok": False, "error": "unknown_plugin"}
        _save_json(self._plugins_path, plugs)
        self._log("plugin_toggle", plugin=plugin_id, enabled=enabled)
        return {"ok": True, "plugin": plugin_id, "enabled": enabled}

    def state(self) -> dict[str, Any]:
        st = _load_json(self._state_path, {})
        if not isinstance(st, dict):
            st = {}
        return st

    def _save_state(self, st: dict[str, Any]) -> None:
        _save_json(self._state_path, st)

    def set_theme(self, theme: str, palette: str | None = None) -> dict[str, Any]:
        st = self.state()
        if theme in {"orbital", "bbs", "plain", "arctic", "synthwave"}:
            st["theme"] = theme if theme in {"orbital", "bbs", "plain"} else "orbital"
        if palette:
            st["palette"] = palette
        elif theme in {"arctic", "synthwave", "emerald", "moonlight", "amber-crt", "solar-flare"}:
            st["palette"] = theme
            st["theme"] = "orbital"
        self._save_state(st)
        return {"ok": True, "theme": st.get("theme"), "palette": st.get("palette")}

    def set_control(
        self,
        *,
        level: ControlLevel | None = None,
        approval: ApprovalMode | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        st = self.state()
        ctrl = dict(st.get("control") or {})
        if level in CONTROL_RANK:
            ctrl["level"] = level
        if approval in {"ask", "auto"}:
            ctrl["approval"] = approval
        if active is not None:
            ctrl["active"] = bool(active)
        st["control"] = ctrl
        self._save_state(st)
        self._log("control", **ctrl)
        return {"ok": True, "control": ctrl}

    def authorize(self, action: str) -> dict[str, Any]:
        """Gate estilo ADR-444 — recusa se nível insuficiente ou controle off."""
        st = self.state()
        ctrl = st.get("control") or {}
        need = ACTION_LEVEL.get(action, "full")
        have = str(ctrl.get("level") or "read")
        if not ctrl.get("active") and action not in {"navigate", "inspect"}:
            return {
                "ok": False,
                "allowed": False,
                "error": "control_inactive",
                "detail": "Ative Claude control no cockpit Ruflo",
                "need": need,
                "have": have,
            }
        if CONTROL_RANK.get(have, 0) < CONTROL_RANK.get(need, 3):
            return {
                "ok": False,
                "allowed": False,
                "error": "insufficient_level",
                "need": need,
                "have": have,
            }
        if ctrl.get("approval") == "ask" and action not in {"navigate", "inspect"}:
            return {
                "ok": True,
                "allowed": True,
                "needs_confirm": True,
                "need": need,
                "have": have,
            }
        return {"ok": True, "allowed": True, "needs_confirm": False, "need": need, "have": have}

    def swarm_init(self, topology: Topology = "hierarchical") -> dict[str, Any]:
        gate = self.authorize("swarm_init")
        if not gate.get("allowed"):
            return gate
        st = self.state()
        agents = [
            {"id": "router", "role": "router", "status": "live"},
            {"id": "researcher", "role": "researcher", "status": "live"},
            {"id": "coder", "role": "coder", "status": "live"},
            {"id": "reviewer", "role": "reviewer", "status": "idle"},
            {"id": "memory", "role": "memory", "status": "live"},
        ]
        if topology == "mesh":
            agents.append({"id": "peer-a", "role": "peer", "status": "live"})
            agents.append({"id": "peer-b", "role": "peer", "status": "live"})
        st["topology"] = topology
        st["swarm"] = {
            "active": True,
            "agents": agents,
            "started_at": time.time(),
            "topology": topology,
        }
        self._save_state(st)
        self._log("swarm_init", topology=topology)
        return {"ok": True, "swarm": st["swarm"], "gate": gate}

    def swarm_stop(self) -> dict[str, Any]:
        gate = self.authorize("swarm_stop")
        if not gate.get("allowed"):
            return gate
        st = self.state()
        st["swarm"] = {"active": False, "agents": [], "started_at": None}
        self._save_state(st)
        self._log("swarm_stop")
        return {"ok": True, "swarm": st["swarm"], "gate": gate}

    def missions(self) -> list[dict[str, Any]]:
        data = _load_json(self._missions_path, {"missions": []})
        rows = data.get("missions") if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return []
        return sorted(rows, key=lambda m: float(m.get("ts") or 0), reverse=True)[:40]

    def mission_create(self, goal: str, *, confirm: bool = False) -> dict[str, Any]:
        gate = self.authorize("mission_create")
        if not gate.get("allowed"):
            return gate
        if gate.get("needs_confirm") and not confirm:
            return {
                "ok": False,
                "error": "needs_confirm",
                "detail": "Confirme a criação da missão (approval=ask)",
                "gate": gate,
                "pending": {"goal": goal[:400]},
            }
        goal = (goal or "").strip()[:400]
        if not goal:
            return {"ok": False, "error": "empty_goal"}
        mid = f"m-{uuid.uuid4().hex[:10]}"
        row = {
            "id": mid,
            "goal": goal,
            "status": "open",
            "ts": time.time(),
            "source": "ruflo-console",
        }
        rows = self.missions()
        rows.insert(0, row)
        _save_json(self._missions_path, {"missions": rows[:40]})
        self._log("mission_create", id=mid, goal=goal[:80])
        return {"ok": True, "mission": row, "gate": gate}

    def mission_update(self, mission_id: str, status: str) -> dict[str, Any]:
        gate = self.authorize("mission_update")
        if not gate.get("allowed"):
            return gate
        rows = self.missions()
        hit = None
        for m in rows:
            if m.get("id") == mission_id:
                m["status"] = status[:40]
                m["updated"] = time.time()
                hit = m
                break
        if not hit:
            return {"ok": False, "error": "not_found"}
        _save_json(self._missions_path, {"missions": rows})
        return {"ok": True, "mission": hit}

    def architecture(self) -> dict[str, Any]:
        """Diagrama textual: Ruflo no centro do Véu."""
        plugs = self.plugins()
        enabled = [p["id"] for p in plugs if p.get("enabled")]
        return {
            "spine": "ruflo",
            "model": "Agent = Model + Harness",
            "flow": [
                "User / Véu Desktop",
                "Ruflo Spine (console · plugins · control)",
                "Router / Swarm",
                "Agents (ECC · GrokBot · Hermes · Clone)",
                "Memory (OpenRAG · AgentDB · decisions)",
                "LLM providers + hosts Véu",
            ],
            "ruos": {
                "role": "desktop que se governa — janelas no SO, frota MCP",
                "mcp": "https://ruos.cognitum.one/mcp",
                "plugin": "ruflo-ruos", "brand": "Véu",
            },
            "plugins_enabled": enabled,
            "source": "https://github.com/ruvnet/ruflo",
        }

    def pulse(self, *, runtime_pulse: dict[str, Any] | None = None) -> dict[str, Any]:
        st = self.state()
        plugs = self.plugins()
        enabled = [p for p in plugs if p.get("enabled")]
        by_cat: dict[str, int] = {}
        for p in enabled:
            c = str(p.get("category") or "other")
            by_cat[c] = by_cat.get(c, 0) + 1
        swarm = st.get("swarm") or {}
        return {
            "ok": True,
            "spine": "ruflo",
            "theme": st.get("theme") or "orbital",
            "palette": st.get("palette") or "arctic",
            "control": st.get("control") or {},
            "topology": st.get("topology") or "hierarchical",
            "swarm": swarm,
            "plugins": {
                "total": len(plugs),
                "enabled": len(enabled),
                "by_category": by_cat,
                "core": [p["id"] for p in enabled if p.get("category") == "core"],
            },
            "missions": {
                "open": sum(1 for m in self.missions() if m.get("status") == "open"),
                "total": len(self.missions()),
            },
            "ruos": st.get("ruos") or {},
            "cli": st.get("cli") or self._detect_cli(),
            "architecture": self.architecture()["flow"],
            "runtime": {
                "harness": (runtime_pulse or {}).get("harness"),
                "memory": (runtime_pulse or {}).get("memory"),
                "llm": (runtime_pulse or {}).get("llm"),
            },
            "assets": {
                "ruos": "/ruflo/ruos-animated.svg",
                "tui": "/ruflo/ruflo-tui-compact.svg",
                "learning": "/ruflo/learning-cinematic-compact.svg",
                "neon": "/ruflo/ruflo-neon-header.svg",
            },
            "ts": time.time(),
        }

    def snapshot(self, *, runtime_pulse: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "pulse": self.pulse(runtime_pulse=runtime_pulse),
            "plugins": self.plugins(),
            "missions": self.missions(),
            "architecture": self.architecture(),
            "events": self.recent_events(24),
        }

    def recent_events(self, limit: int = 24) -> list[dict[str, Any]]:
        if not self._events_path.is_file():
            return []
        try:
            lines = self._events_path.read_text(encoding="utf-8").splitlines()[-limit:]
            out = []
            for ln in lines:
                try:
                    out.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    continue
            return list(reversed(out))
        except Exception:  # noqa: BLE001
            return []


spine = RufloSpine()

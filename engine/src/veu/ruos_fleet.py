"""Frota de desktops Véu — desktops cloud, Lite browser, Mac/Linux, RustDesk.

Espelha o painel Desktops de ruos.cognitum.one: estados asleep/ready/running,
snapshots, enrollment one-shot (15 min), Véu Lite e provisionamento.
Integra com Ruflo spine (plugin ruflo-ruos) e, se houver, RUOS_MCP_URL/TOKEN.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Literal

DesktopKind = Literal["cloud", "lite", "mac", "linux", "rustdesk"]
DesktopState = Literal["asleep", "starting", "ready", "running", "stopped", "error"]
Profile = Literal["desktop", "phone", "gpu"]

ENROLL_TTL = 15 * 60


def _home() -> Path:
    raw = os.environ.get("VEU_HOME") or os.environ.get("HOME") or "/tmp"
    return Path(raw) / ".veu" / "ruos"


def _load(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return default


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class RuosFleet:
    def __init__(self) -> None:
        self.root = _home()
        self.root.mkdir(parents=True, exist_ok=True)
        self._fleet = self.root / "fleet.json"
        self._snaps = self.root / "snapshots.json"
        self._enroll = self.root / "enroll.json"
        self._lite = self.root / "lite.json"
        self._ensure()

    def _ensure(self) -> None:
        if not self._fleet.is_file():
            now = time.time()
            seed = [
                {
                    "id": "veu-desktop",
                    "name": "Véu Desktop",
                    "kind": "cloud",
                    "profile": "desktop",
                    "state": "asleep",
                    "host": "Véu Cloud",
                    "viewer": None,
                    "heartbeat_at": None,
                    "stop_at_hint": "auto-stop weekday 23:00",
                    "agents": 0,
                    "session_min": 0,
                    "created_at": now,
                    "updated_at": now,
                    "tags": ["cloud", "primary"],
                },
                {
                    "id": "veu-lite",
                    "name": "Browser · no Véu",
                    "kind": "lite",
                    "profile": "desktop",
                    "state": "ready",
                    "host": "janela do SO",
                    "viewer": "in-os",
                    "heartbeat_at": now,
                    "stop_at_hint": "fecha com a janela",
                    "agents": 0,
                    "session_min": 0,
                    "created_at": now,
                    "updated_at": now,
                    "tags": ["lite", "browser"],
                    "lite": {
                        "web_apps_only": True,
                        "no_terminal": True,
                        "no_files": True,
                        "persist_days": 30,
                        "encrypted_browser": True,
                        "caches_kept": False,
                    },
                },
            ]
            _save(self._fleet, {"desktops": seed})
        else:
            self._migrate_brand()
        if not self._snaps.is_file():
            _save(self._snaps, {"snapshots": []})
        if not self._enroll.is_file():
            _save(self._enroll, {"tokens": []})
        if not self._lite.is_file():
            _save(
                self._lite,
                {
                    "active": False,
                    "tabs": [],
                    "apps_open": [],
                    "started_at": None,
                    "ai_control": False,
                    "search": "https://duckduckgo.com/?q=%s",
                },
            )

    def _migrate_brand(self) -> None:
        """Renomeia ids/labels legados ruos-* → Véu (sem apagar frota)."""
        rows = self._desktops()
        changed = False
        for d in rows:
            oid = str(d.get("id") or "")
            if oid == "ruos-desktop":
                d["id"] = "veu-desktop"
                d["name"] = "Véu Desktop"
                d["host"] = "Véu Cloud"
                changed = True
            elif oid == "ruos-lite":
                d["id"] = "veu-lite"
                d["name"] = "Browser · no Véu"
                d["host"] = "janela do SO"
                changed = True
            name = str(d.get("name") or "")
            if "ruOS" in name or name.startswith("ruos"):
                d["name"] = name.replace("ruOS", "Véu").replace("ruos", "Véu")
                changed = True
            if "Lite" in name or name.startswith("Véu Lite"):
                d["name"] = "Browser · no Véu"
                d["host"] = "janela do SO"
                changed = True
            host = str(d.get("host") or "")
            if "ruOS" in host:
                d["host"] = host.replace("ruOS", "Véu")
                changed = True
        if changed:
            self._save_desktops(rows)

    def _desktops(self) -> list[dict[str, Any]]:
        data = _load(self._fleet, {"desktops": []})
        rows = data.get("desktops") if isinstance(data, dict) else []
        return list(rows) if isinstance(rows, list) else []

    def _save_desktops(self, rows: list[dict[str, Any]]) -> None:
        _save(self._fleet, {"desktops": rows})

    def _get(self, desktop_id: str) -> dict[str, Any] | None:
        for d in self._desktops():
            if d.get("id") == desktop_id:
                return d
        return None

    def mcp_configured(self) -> bool:
        return bool(os.environ.get("RUOS_MCP_URL") and os.environ.get("RUOS_MCP_TOKEN"))

    def board(self, query: str = "") -> dict[str, Any]:
        q = (query or "").strip().lower()
        rows = self._desktops()
        if q:
            rows = [
                d
                for d in rows
                if q in str(d.get("name") or "").lower()
                or q in str(d.get("kind") or "").lower()
                or q in str(d.get("state") or "").lower()
                or q in " ".join(d.get("tags") or []).lower()
            ]
        lite = _load(self._lite, {})
        counts = {
            "total": len(self._desktops()),
            "asleep": sum(1 for d in self._desktops() if d.get("state") == "asleep"),
            "running": sum(
                1 for d in self._desktops() if d.get("state") in {"running", "ready"}
            ),
            "lite": sum(1 for d in self._desktops() if d.get("kind") == "lite"),
        }
        return {
            "ok": True,
            "desktops": rows,
            "counts": counts,
            "lite_session": lite,
            "mcp": {
                "url": os.environ.get("RUOS_MCP_URL") or "https://ruos.cognitum.one/mcp",
                "configured": self.mcp_configured(),
            },
            "actions": [
                "add_desktop",
                "snapshots",
                "reconnect",
                "full_screen",
                "provision_cloud",
                "add_mac",
                "add_linux",
                "add_rustdesk",
                "resume_lite",
            ],
            "copy": {
                "lite": (
                    "Browser do Véu — janela web no SO. Apps nativos (Chat, Missão) "
                    "ou web Cognitum quando for melhor (ChatGPT, Claude, VS Code…). "
                    "LLM shared Cognitum em Keys. Terminal/SSH no Console."
                ),
                "linux": (
                    "Adicione uma máquina Debian/Ubuntu (x86_64) sua — workstation, lab ou "
                    "servidor com sessão gráfica. Instala RustDesk, entra no relay Véu e "
                    "aparece na frota. Rode a linha abaixo com sudo (pede senha)."
                ),
                "mac": (
                    "Adicione um Mac (ou workstation) via Véu Connect — Tailscale opcional + "
                    "RustDesk — e ele entra na frota."
                ),
                "cloud": (
                    "Provisiona um desktop cloud Véu — Ubuntu GNOME com stack de agentes, "
                    "acessível pelo browser."
                ),
                "rustdesk": (
                    "Já tem máquina no RustDesk apontando pro relay? Adicione pelo ID."
                ),
                "snapshot": (
                    "Snapshot captura o volume do desktop (ajustes, apps e arquivos). "
                    "Marque como template ou duplique numa desktop nova."
                ),
            },
        }

    def set_state(self, desktop_id: str, state: DesktopState) -> dict[str, Any]:
        rows = self._desktops()
        hit = None
        for d in rows:
            if d.get("id") == desktop_id:
                d["state"] = state
                d["updated_at"] = time.time()
                if state in {"running", "ready"}:
                    d["heartbeat_at"] = time.time()
                hit = d
                break
        if not hit:
            return {"ok": False, "error": "not_found"}
        self._save_desktops(rows)
        return {"ok": True, "desktop": hit}

    def start(self, desktop_id: str) -> dict[str, Any]:
        d = self._get(desktop_id)
        if not d:
            return {"ok": False, "error": "not_found"}
        if d.get("kind") == "lite":
            return self.resume_lite()
        self.set_state(desktop_id, "starting")
        # simulação rápida → running (cloud real exigiria RUOS MCP)
        return self.set_state(desktop_id, "running")

    def stop(self, desktop_id: str) -> dict[str, Any]:
        d = self._get(desktop_id)
        if not d:
            return {"ok": False, "error": "not_found"}
        if d.get("kind") == "lite":
            lite = _load(self._lite, {})
            lite["active"] = False
            lite["started_at"] = None
            _save(self._lite, lite)
        return self.set_state(desktop_id, "asleep")

    def reconnect(self, desktop_id: str) -> dict[str, Any]:
        d = self._get(desktop_id)
        if not d:
            return {"ok": False, "error": "not_found"}
        d = dict(d)
        d["viewer"] = "reconnect"
        d["heartbeat_at"] = time.time()
        d["updated_at"] = time.time()
        if d.get("state") == "asleep":
            d["state"] = "ready"
        rows = [d if x.get("id") == desktop_id else x for x in self._desktops()]
        self._save_desktops(rows)
        return {"ok": True, "desktop": d, "detail": "viewer reconnect queued"}

    def provision_cloud(self, profile: Profile = "desktop") -> dict[str, Any]:
        now = time.time()
        row = {
            "id": _new_id("cloud"),
            "name": f"Véu Cloud · {profile}",
            "kind": "cloud",
            "profile": profile,
            "state": "starting",
            "host": "Véu Cloud · provisioning",
            "viewer": None,
            "heartbeat_at": None,
            "stop_at_hint": "23:00 America/Toronto (weekdays)",
            "agents": 0,
            "session_min": 0,
            "created_at": now,
            "updated_at": now,
            "tags": ["cloud", profile],
            "billable": profile == "gpu",
            "note": (
                "GPU rents real hardware ~$0.30–$0.50/hr"
                if profile == "gpu"
                else "Ubuntu GNOME + ruvnet stack"
            ),
        }
        rows = self._desktops()
        rows.append(row)
        self._save_desktops(rows)
        # marca ready após "boot"
        return self.set_state(row["id"], "ready")

    def add_rustdesk(self, rustdesk_id: str, label: str = "") -> dict[str, Any]:
        rid = (rustdesk_id or "").strip()
        if len(rid) < 6:
            return {"ok": False, "error": "invalid_id"}
        now = time.time()
        row = {
            "id": _new_id("rd"),
            "name": label.strip() or f"RustDesk · {rid[-4:]}",
            "kind": "rustdesk",
            "profile": "desktop",
            "state": "ready",
            "host": f"RustDesk · {rid}",
            "viewer": "veu-connect",
            "rustdesk_id": rid,
            "heartbeat_at": now,
            "created_at": now,
            "updated_at": now,
            "tags": ["rustdesk", "owned"],
        }
        rows = self._desktops()
        rows.append(row)
        self._save_desktops(rows)
        return {"ok": True, "desktop": row}

    def generate_enroll(
        self, platform: Literal["linux", "mac"]
    ) -> dict[str, Any]:
        token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:24]
        exp = time.time() + ENROLL_TTL
        entry = {
            "id": _new_id("enr"),
            "platform": platform,
            "token_hash": token_hash,
            "expires_at": exp,
            "created_at": time.time(),
            "used": False,
        }
        data = _load(self._enroll, {"tokens": []})
        tokens = [t for t in (data.get("tokens") or []) if float(t.get("expires_at") or 0) > time.time()]
        tokens.append(entry)
        _save(self._enroll, {"tokens": tokens[-20:]})

        # Formato Cognitum install (compatível) (install/*.sh + env vars no sudo/sh).
        relay = os.environ.get("RUOS_RELAY") or "34.130.229.22"
        fleet_api = os.environ.get("RUOS_FLEET_API") or "https://fleet.cognitum.one"
        rustdesk_key = os.environ.get("RUOS_RUSTDESK_KEY") or ""
        install_base = (
            os.environ.get("RUOS_INSTALL_BASE") or "https://ruos.cognitum.one/install"
        )
        key_part = (
            f" RUOS_RUSTDESK_KEY='{rustdesk_key}'" if rustdesk_key else ""
        )
        if platform == "linux":
            cmd = (
                f"curl -fsSL {install_base}/linux.sh | sudo "
                f"RUOS_ENROLL_TOKEN={token} "
                f"RUOS_FLEET_API={fleet_api} "
                f"RUOS_RELAY={relay}{key_part} sh"
            )
            notes = (
                "The command carries a short-lived (15 min) enrollment token — not your login. "
                "Root is required: it installs RustDesk from a checksum-pinned .deb, points it "
                "at the Véu relay, and sets a permanent password (kept root-only in "
                "/root/.ruos-rustdesk-password). Tailscale is only read — an existing login is "
                "left as it is. RustDesk can't capture a Wayland session unattended; the "
                "installer warns if your login screen isn't set to X11 but doesn't change it."
            )
        else:
            cmd = (
                f"curl -fsSL {install_base}/mac.sh | "
                f"RUOS_ENROLL_TOKEN={token} "
                f"RUOS_FLEET_API={fleet_api} "
                f"RUOS_RELAY={relay}{key_part} bash"
            )
            notes = (
                "The command carries a short-lived (15 min) enrollment token — not your login. "
                "On first connect, macOS will ask to grant RustDesk Screen Recording + "
                "Accessibility (System Settings → Privacy & Security)."
            )
        return {
            "ok": True,
            "platform": platform,
            "expires_at": exp,
            "ttl_sec": ENROLL_TTL,
            "command": cmd,
            "notes": notes,
            "enroll_id": entry["id"],
            "fleet_api": fleet_api,
            "relay": relay,
            "install_base": install_base,
        }

    def claim_enroll(self, token: str, *, host_name: str = "", rustdesk_id: str = "") -> dict[str, Any]:
        th = hashlib.sha256((token or "").encode()).hexdigest()[:24]
        data = _load(self._enroll, {"tokens": []})
        tokens = list(data.get("tokens") or [])
        hit = None
        for t in tokens:
            if t.get("token_hash") == th and not t.get("used") and float(t.get("expires_at") or 0) > time.time():
                hit = t
                break
        if not hit:
            return {"ok": False, "error": "invalid_or_expired"}
        hit["used"] = True
        _save(self._enroll, {"tokens": tokens})
        kind = "mac" if hit.get("platform") == "mac" else "linux"
        now = time.time()
        row = {
            "id": _new_id(kind),
            "name": host_name.strip() or f"Véu {kind} · enrolled",
            "kind": kind,
            "profile": "desktop",
            "state": "ready",
            "host": host_name or f"enrolled · {kind}",
            "viewer": "veu-connect",
            "rustdesk_id": rustdesk_id or None,
            "heartbeat_at": now,
            "created_at": now,
            "updated_at": now,
            "tags": [kind, "enrolled", "owned"],
            "enroll_id": hit.get("id"),
        }
        rows = self._desktops()
        rows.append(row)
        self._save_desktops(rows)
        return {"ok": True, "desktop": row}

    def snapshots(self, desktop_id: str | None = None) -> dict[str, Any]:
        data = _load(self._snaps, {"snapshots": []})
        rows = list(data.get("snapshots") or [])
        if desktop_id:
            rows = [s for s in rows if s.get("desktop_id") == desktop_id]
        return {"ok": True, "snapshots": rows, "copy": self.board()["copy"]["snapshot"]}

    def take_snapshot(self, desktop_id: str, label: str = "", *, as_template: bool = False) -> dict[str, Any]:
        d = self._get(desktop_id)
        if not d:
            return {"ok": False, "error": "not_found"}
        snap = {
            "id": _new_id("snap"),
            "desktop_id": desktop_id,
            "desktop_name": d.get("name"),
            "label": label.strip() or f"snapshot · {time.strftime('%Y-%m-%d %H:%M')}",
            "template": bool(as_template),
            "ts": time.time(),
            "size_hint": "volume",
        }
        data = _load(self._snaps, {"snapshots": []})
        rows = list(data.get("snapshots") or [])
        rows.insert(0, snap)
        _save(self._snaps, {"snapshots": rows[:40]})
        return {"ok": True, "snapshot": snap}

    def duplicate_snapshot(self, snap_id: str) -> dict[str, Any]:
        data = _load(self._snaps, {"snapshots": []})
        rows = list(data.get("snapshots") or [])
        src = next((s for s in rows if s.get("id") == snap_id), None)
        if not src:
            return {"ok": False, "error": "not_found"}
        now = time.time()
        row = {
            "id": _new_id("cloud"),
            "name": f"{src.get('desktop_name') or 'desktop'} · from snapshot",
            "kind": "cloud",
            "profile": "desktop",
            "state": "ready",
            "host": "Véu Cloud · from template",
            "viewer": None,
            "heartbeat_at": now,
            "created_at": now,
            "updated_at": now,
            "tags": ["cloud", "from-snapshot"],
            "from_snapshot": snap_id,
        }
        desks = self._desktops()
        desks.append(row)
        self._save_desktops(desks)
        return {"ok": True, "desktop": row}

    def resume_lite(self) -> dict[str, Any]:
        now = time.time()
        lite = _load(self._lite, {})
        lite["active"] = True
        lite["started_at"] = now
        if not lite.get("apps_open"):
            lite["apps_open"] = ["welcome", "chatgpt", "vscode"]
        _save(self._lite, lite)
        # ensure lite desktop row is ready/running
        rows = self._desktops()
        for d in rows:
            if d.get("kind") == "lite":
                d["state"] = "running"
                d["heartbeat_at"] = now
                d["updated_at"] = now
        self._save_desktops(rows)
        return {
            "ok": True,
            "lite": lite,
            "surface": "browser",
            "open_app": "browser",
            "detail": "Véu Lite session resumed in-OS",
        }

    def lite_set_ai(self, enabled: bool) -> dict[str, Any]:
        lite = _load(self._lite, {})
        lite["ai_control"] = bool(enabled)
        _save(self._lite, lite)
        return {"ok": True, "lite": lite}

    def enroll_script(self) -> str:
        """Script one-liner target — stub seguro (não baixa .deb real sem token válido)."""
        return """#!/usr/bin/env bash
set -euo pipefail
# Véu enrollment stub — token short-lived; real .deb pin happens on Cognitum fleet.
TOKEN=""; RELAY="relay.ruos.cognitum.one"; PLATFORM="linux"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --token) TOKEN="$2"; shift 2;;
    --relay) RELAY="$2"; shift 2;;
    --platform) PLATFORM="$2"; shift 2;;
    *) shift;;
  esac
done
if [[ -z "$TOKEN" ]]; then echo "missing --token"; exit 2; fi
echo "Véu enroll · platform=$PLATFORM relay=$RELAY"
echo "(stub) Install RustDesk, join relay, register with Véu fleet."
echo "Token accepted locally — complete claim via API if kernel reachable."
HOSTNAME_F=$(hostname 2>/dev/null || echo enrolled-host)
echo "Done · host=$HOSTNAME_F"
"""


fleet_ruos = RuosFleet()

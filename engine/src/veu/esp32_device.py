"""Véu · dispositivos ESP32 (placa amarela CYD) — estado compacto + eventos.

A placa não roda o React OS: ela é um nervo físico do Véu — TFT/touch/WiFi/RGB/LDR
sincronizados com o kernel via token de dispositivo.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "esp32_devices.json"


def _default() -> dict[str, Any]:
    return {"version": 1, "devices": {}, "events": []}


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return _default()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default()
    base = _default()
    base.update({k: v for k, v in data.items() if k in base})
    return base


def _save(data: dict[str, Any]) -> None:
    _path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _env_token() -> str:
    return (os.environ.get("VEU_ESP32_TOKEN") or "").strip()


def verify_token(token: str | None) -> dict[str, Any] | None:
    tok = (token or "").strip()
    if not tok:
        return None
    env = _env_token()
    if env and secrets.compare_digest(tok, env):
        return {"id": "env", "label": "VEU_ESP32_TOKEN", "via": "env"}
    data = _load()
    for did, row in (data.get("devices") or {}).items():
        if secrets.compare_digest(str(row.get("token") or ""), tok):
            return {"id": did, **row, "via": "store"}
    return None


def enroll(*, label: str = "placa amarela", model: str = "ESP32-2432S028R") -> dict[str, Any]:
    data = _load()
    did = f"cyd-{secrets.token_hex(3)}"
    token = secrets.token_urlsafe(24)
    row = {
        "id": did,
        "label": label or "placa amarela",
        "model": model,
        "token": token,
        "created": int(time.time()),
        "last_seen": 0,
        "meta": {
            "tft": "ILI9341 240×320",
            "touch": "XPT2046",
            "sku": "61115",
            "aka": "Cheap Yellow Display / placa amarela",
        },
    }
    data.setdefault("devices", {})[did] = row
    _save(data)
    return {
        "ok": True,
        "device": {k: v for k, v in row.items() if k != "token"},
        "token": token,
        "portal": {
            "ssid": "veu-placa",
            "password": "veuvela1",
            "url": "http://192.168.4.1",
            "hint": "No AP, cole a URL do Véu + este token",
        },
        "firmware": "device/esp32-cyd",
    }


def list_devices() -> dict[str, Any]:
    data = _load()
    out = []
    for row in (data.get("devices") or {}).values():
        out.append({k: v for k, v in row.items() if k != "token"})
    return {"ok": True, "devices": out, "env_token_set": bool(_env_token())}


def board_info() -> dict[str, Any]:
    """Ficha técnica da placa alvo (sem device cadastrado)."""
    return {
        "ok": True,
        "product": "Véu Placa",
        "board": {
            "name": "Cheap Yellow Display (placa amarela)",
            "model": "ESP32-2432S028R",
            "sku": "61115",
            "mcu": "ESP32-WROOM-32 dual-core 240 MHz",
            "memory": "520KB SRAM · 4MB flash",
            "display": {
                "size": "2.8 inch",
                "resolution": "240×320",
                "driver": "ILI9341",
                "bus": "SPI HSPI",
                "pins": {
                    "MISO": 12,
                    "MOSI": 13,
                    "SCLK": 14,
                    "CS": 15,
                    "DC": 2,
                    "RST": -1,
                    "BL": 21,
                },
            },
            "touch": {
                "driver": "XPT2046 resistive",
                "bus": "SPI VSPI",
                "pins": {"IRQ": 36, "MOSI": 32, "MISO": 39, "CLK": 25, "CS": 33},
            },
            "extras": {
                "wifi": True,
                "bluetooth": True,
                "rgb_led": {"R": 4, "G": 16, "B": 17, "active": "LOW"},
                "ldr": 34,
                "microsd": {"MISO": 19, "MOSI": 23, "SCK": 18, "CS": 5},
                "gpio_free": [22, 27, 35],
            },
        },
        "firmware_path": "device/esp32-cyd",
        "potential": [
            "UI táctil do SO (missão, inbox, fôlego, captura)",
            "LED RGB = saúde do kernel",
            "LDR = brilho automático do TFT",
            "WiFi sync contínuo com veu.ch8ai.com.br",
            "Portal AP veu-placa sem cabo serial",
            "microSD pronto para cache/offline (próximo)",
        ],
    }


def touch_seen(device_id: str | None) -> None:
    if not device_id:
        return
    data = _load()
    row = (data.get("devices") or {}).get(device_id)
    if not row:
        return
    row["last_seen"] = int(time.time())
    data["devices"][device_id] = row
    _save(data)


def compact_state(rt: Any, *, device: dict[str, Any] | None = None) -> dict[str, Any]:
    """Payload mínimo pro TFT 320×240."""
    if device:
        touch_seen(str(device.get("id")))

    pulse: dict[str, Any] = {}
    try:
        pulse = rt.pulse() if hasattr(rt, "pulse") else {}
    except Exception:  # noqa: BLE001
        pulse = {}

    mission_title = ""
    mission_status = ""
    try:
        snap = rt.mission() if hasattr(rt, "mission") else {}
        # harness mission shape varies — pick readable fields
        if isinstance(snap, dict):
            mission_title = str(
                snap.get("title")
                or snap.get("goal")
                or (snap.get("mission") or {}).get("title")
                or ""
            )[:80]
            mission_status = str(
                snap.get("status")
                or (snap.get("mission") or {}).get("status")
                or snap.get("breath")
                or ""
            )[:40]
            if not mission_title:
                jobs = snap.get("jobs") or []
                if jobs and isinstance(jobs, list):
                    j0 = jobs[0] if isinstance(jobs[0], dict) else {}
                    mission_title = str(j0.get("title") or j0.get("label") or "")[:80]
                    mission_status = str(j0.get("state") or j0.get("status") or "")[:40]
    except Exception:  # noqa: BLE001
        pass

    unread = 0
    msgs = 0
    try:
        side = rt.bridges.grokbot.sideboard()
        hoje = (side or {}).get("hoje") or (side or {}).get("today") or {}
        if isinstance(hoje, dict):
            unread = int(hoje.get("unread") or hoje.get("nao_lidas") or 0)
            msgs = int(hoje.get("msgs") or hoje.get("messages") or 0)
    except Exception:  # noqa: BLE001
        pass

    running = 0
    queued = 0
    try:
        from veu import jobs as veu_jobs

        board = veu_jobs.store.board(limit=24)
        counts = board.get("counts") or {}
        running = int(counts.get("running") or counts.get("active") or 0)
        queued = int(counts.get("queued") or counts.get("pending") or 0)
    except Exception:  # noqa: BLE001
        pass

    breath = "guided"
    try:
        breath = str(getattr(rt.harness, "breath", None) or "guided")
    except Exception:  # noqa: BLE001
        pass

    clock = time.strftime("%H:%M")
    note = ""
    try:
        if pulse.get("status"):
            note = f"pulse · {pulse.get('status')}"
        elif pulse.get("product"):
            note = str(pulse.get("product"))
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "kernel": True,
        "product": pulse.get("product") or "véu",
        "breath": breath,
        "mission": {"title": mission_title or "Véu · em órbita", "status": mission_status or "ok"},
        "inbox": {"unread": unread, "msgs": msgs},
        "jobs": {"running": running, "queued": queued},
        "clock": clock,
        "note": note[:60],
        "device": {
            "id": (device or {}).get("id"),
            "label": (device or {}).get("label"),
            "model": (device or {}).get("model") or "ESP32-2432S028R",
        },
    }


def handle_event(
    rt: Any,
    *,
    device: dict[str, Any] | None,
    typ: str,
    payload: str = "",
) -> dict[str, Any]:
    typ = (typ or "").strip().lower()
    payload = (payload or "").strip()
    data = _load()
    ev = {
        "ts": int(time.time()),
        "device_id": (device or {}).get("id"),
        "type": typ,
        "payload": payload[:500],
    }
    events = list(data.get("events") or [])
    events.append(ev)
    data["events"] = events[-200:]
    _save(data)

    if device:
        touch_seen(str(device.get("id")))

    if typ == "breath":
        mapping = {
            "guided": "guided",
            "guiado": "guided",
            "semi": "semi",
            "free": "free",
            "livre": "free",
            "auto": "auto",
            "autonomo": "auto",
            "autônomo": "auto",
        }
        breath = mapping.get(payload, payload)
        try:
            if hasattr(rt, "harness") and hasattr(rt.harness, "set_breath"):
                rt.harness.set_breath(breath)
            elif hasattr(rt, "harness"):
                setattr(rt.harness, "breath", breath)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:200], "event": ev}
        return {"ok": True, "breath": breath, "event": ev}

    if typ == "capture":
        try:
            from veu import capture as veu_capture

            text = payload or "nota da placa amarela"
            if hasattr(veu_capture, "quick"):
                veu_capture.quick(text)
            elif hasattr(veu_capture, "add"):
                veu_capture.add(text)
            else:
                # fallback memory audit
                rt.memory.append("esp32_capture", {"text": text}, sink="audit")
        except Exception:  # noqa: BLE001
            try:
                rt.memory.append("esp32_capture", {"text": payload}, sink="audit")
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "captured": True, "event": ev}

    if typ == "ping":
        return {"ok": True, "pong": True, "event": ev}

    return {"ok": True, "event": ev}


def recent_events(limit: int = 30) -> dict[str, Any]:
    data = _load()
    ev = list(data.get("events") or [])[-max(1, min(limit, 100)) :]
    return {"ok": True, "events": list(reversed(ev))}

"""11.3 — Workspaces salvos: conjunto de janelas por nome/empresa."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

_SLUG = re.compile(r"[^a-z0-9\-]+")


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "os_workspaces.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return {"workspaces": {}, "active_id": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"workspaces": {}, "active_id": None}


def _save(data: dict[str, Any]) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _slug(name: str) -> str:
    s = (name or "").strip().lower().replace(" ", "-")
    s = _SLUG.sub("", s)
    return s[:48] or f"ws-{uuid.uuid4().hex[:8]}"


def list_workspaces() -> dict[str, Any]:
    data = _load()
    rows = sorted(
        (data.get("workspaces") or {}).values(),
        key=lambda w: float(w.get("updated") or 0),
        reverse=True,
    )
    return {
        "ok": True,
        "active_id": data.get("active_id"),
        "workspaces": rows,
        "count": len(rows),
    }


def get_workspace(ws_id: str) -> dict[str, Any]:
    data = _load()
    ws = (data.get("workspaces") or {}).get(ws_id)
    if not ws:
        return {"ok": False, "error": "workspace não encontrado"}
    return {"ok": True, "workspace": ws, "active_id": data.get("active_id")}


def save_workspace(
    *,
    name: str,
    windows: list[dict[str, Any]],
    company: str | None = None,
    browser_tabs: list[dict[str, Any]] | None = None,
    ws_id: str | None = None,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "nome obrigatório"}
    if not isinstance(windows, list):
        return {"ok": False, "error": "windows deve ser lista"}

    clean_wins: list[dict[str, Any]] = []
    for w in windows[:40]:
        if not isinstance(w, dict):
            continue
        app = str(w.get("app") or "").strip()
        if not app:
            continue
        clean_wins.append(
            {
                "app": app,
                "title": str(w.get("title") or app)[:80],
                "x": int(w.get("x") or 40),
                "y": int(w.get("y") or 40),
                "w": max(280, int(w.get("w") or 720)),
                "h": max(200, int(w.get("h") or 480)),
                "z": int(w.get("z") or 10),
                "minimized": bool(w.get("minimized")),
            }
        )

    data = _load()
    wid = ws_id or _slug(name)
    now = time.time()
    prev = (data.get("workspaces") or {}).get(wid) or {}
    row = {
        "id": wid,
        "name": name[:80],
        "company": (company or prev.get("company") or "").strip()[:80] or None,
        "windows": clean_wins,
        "browser_tabs": (browser_tabs or prev.get("browser_tabs") or [])[:20],
        "created": prev.get("created") or now,
        "updated": now,
    }
    data.setdefault("workspaces", {})[wid] = row
    data["active_id"] = wid
    _save(data)
    return {"ok": True, "workspace": row, "active_id": wid}


def activate(ws_id: str) -> dict[str, Any]:
    data = _load()
    ws = (data.get("workspaces") or {}).get(ws_id)
    if not ws:
        return {"ok": False, "error": "workspace não encontrado"}
    data["active_id"] = ws_id
    ws["updated"] = time.time()
    data["workspaces"][ws_id] = ws
    _save(data)
    return {"ok": True, "workspace": ws, "active_id": ws_id}


def delete_workspace(ws_id: str) -> dict[str, Any]:
    data = _load()
    if ws_id not in (data.get("workspaces") or {}):
        return {"ok": False, "error": "workspace não encontrado"}
    data["workspaces"].pop(ws_id, None)
    if data.get("active_id") == ws_id:
        data["active_id"] = next(iter(data["workspaces"]), None)
    _save(data)
    return {"ok": True, "active_id": data.get("active_id")}

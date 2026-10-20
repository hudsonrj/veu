"""Rotinas simples — gatilho cron → enfileira job."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from veu.bus import bus

# "0 9 * * 1-5" style — subset: minute hour dow(0=Sun or 1-5)
_CRON_RE = re.compile(
    r"^(\*|\d{1,2})\s+(\*|\d{1,2})\s+\*\s+\*\s+(\*|[\d,\-]+)$"
)


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "routines.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"routines": [], "runs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"routines": [], "runs": []}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def list_routines() -> dict[str, Any]:
    data = _load()
    return {
        "ok": True,
        "routines": data.get("routines") or [],
        "runs": (data.get("runs") or [])[:20],
        "count": len(data.get("routines") or []),
    }


def upsert(
    *,
    routine_id: str | None = None,
    title: str,
    cron: str,
    intent: str,
    breath: str = "guided",
    enabled: bool = True,
) -> dict[str, Any]:
    cron = cron.strip()
    if not _CRON_RE.match(cron):
        return {
            "ok": False,
            "error": "cron inválido — use 'min hour * * dow' (ex: 0 9 * * 1-5)",
        }
    data = _load()
    routines = data.get("routines") or []
    rid = routine_id or f"rtn-{uuid.uuid4().hex[:8]}"
    row = {
        "id": rid,
        "title": title.strip()[:120],
        "cron": cron,
        "intent": intent.strip()[:500],
        "breath": breath,
        "enabled": bool(enabled),
        "updated_at": time.time(),
        "last_run": None,
    }
    replaced = False
    for i, r in enumerate(routines):
        if r.get("id") == rid:
            row["last_run"] = r.get("last_run")
            row["created_at"] = r.get("created_at") or time.time()
            routines[i] = row
            replaced = True
            break
    if not replaced:
        row["created_at"] = time.time()
        routines.insert(0, row)
    data["routines"] = routines[:80]
    _save(data)
    bus.publish_sync("routine", {"id": rid}, full=list_routines())
    return {"ok": True, "routine": row}


def delete(routine_id: str) -> dict[str, Any]:
    data = _load()
    before = len(data.get("routines") or [])
    data["routines"] = [r for r in (data.get("routines") or []) if r.get("id") != routine_id]
    _save(data)
    return {"ok": True, "removed": before - len(data["routines"])}


def _dow_match(spec: str, dow: int) -> bool:
    """dow: 0=Mon … 6=Sun (time.localtime tm_wday)."""
    if spec == "*":
        return True
    parts = []
    for chunk in spec.split(","):
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            parts.extend(range(int(a), int(b) + 1))
        else:
            parts.append(int(chunk))
    # aceita 0-6 (Mon-Sun) e também 1-7 estilo legado
    return dow in parts or (dow + 1) in parts


def _should_fire(cron: str, now: time.struct_time, last_run: float | None) -> bool:
    m_s, h_s, _, _, dow_s = cron.split()
    if m_s != "*" and int(m_s) != now.tm_min:
        return False
    if h_s != "*" and int(h_s) != now.tm_hour:
        return False
    if not _dow_match(dow_s, now.tm_wday):
        return False
    # evita disparar 2x no mesmo minuto
    if last_run and (time.time() - last_run) < 60:
        return False
    return True


def tick() -> list[dict[str, Any]]:
    """Avalia rotinas e dispara jobs. Chamado pelo worker."""
    from veu import jobs

    data = _load()
    now = time.localtime()
    fired: list[dict[str, Any]] = []
    changed = False
    for r in data.get("routines") or []:
        if not r.get("enabled"):
            continue
        if not _should_fire(str(r.get("cron") or ""), now, r.get("last_run")):
            continue
        job = jobs.store.enqueue(
            intent=str(r.get("intent") or r.get("title") or "rotina"),
            route="chat",
            breath=str(r.get("breath") or "guided"),
            meta={"routine_id": r.get("id")},
        )
        r["last_run"] = time.time()
        changed = True
        run = {
            "routine_id": r.get("id"),
            "title": r.get("title"),
            "job_id": job.get("id"),
            "ts": time.time(),
        }
        runs = data.get("runs") or []
        runs.insert(0, run)
        data["runs"] = runs[:50]
        fired.append(run)
    if changed:
        _save(data)
        bus.publish_sync("routine", {"fired": len(fired)}, full=list_routines())
    return fired


_worker_started = False


def ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    _worker_started = True

    def loop() -> None:
        while True:
            try:
                tick()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(20)

    threading.Thread(target=loop, name="veu-routines", daemon=True).start()

"""Quadro de ações — propostas do modo autônomo, marcadas como feitas/atualizadas."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from veu.bus import bus

STATUSES = ("open", "done", "dismissed", "updated", "in_progress")


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "actions.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"actions": [], "updated": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"actions": [], "updated": 0}
    if not isinstance(data, dict):
        return {"actions": [], "updated": 0}
    data.setdefault("actions", [])
    return data


def _save(data: dict[str, Any]) -> None:
    data["updated"] = time.time()
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _fingerprint(source: str, ref: str) -> str:
    return f"{source}:{ref}".strip().lower()[:180]


def upsert(
    *,
    source: str,
    ref: str,
    title: str,
    help_text: str,
    suggested: str = "act",
    company: str = "",
    project: str = "",
    subject: str = "",
    meta: dict[str, Any] | None = None,
    priority: str = "normal",
) -> dict[str, Any]:
    """Cria ou atualiza ação aberta com o mesmo fingerprint (não duplica)."""
    data = _load()
    fp = _fingerprint(source, ref or title)
    now = time.time()
    for row in data["actions"]:
        if row.get("fingerprint") == fp and row.get("status") in {
            "open",
            "in_progress",
            "updated",
        }:
            row["title"] = title[:200]
            row["help"] = help_text[:800]
            row["suggested"] = suggested[:40]
            row["company"] = company[:80]
            row["project"] = project[:80]
            row["subject"] = subject[:120]
            row["priority"] = priority
            row["meta"] = {**(row.get("meta") or {}), **(meta or {})}
            row["updated"] = now
            hist = row.setdefault("history", [])
            hist.insert(0, {"ts": now, "status": "updated", "note": "scan refresh"})
            row["history"] = hist[:20]
            row["status"] = "updated" if row.get("status") == "done" else row.get("status") or "open"
            if row["status"] == "updated":
                # reabriu com novo contexto
                row["status"] = "open"
            _save(data)
            return row

    item = {
        "id": f"act-{uuid.uuid4().hex[:10]}",
        "fingerprint": fp,
        "source": source,
        "ref": ref[:120],
        "title": title[:200],
        "help": help_text[:800],
        "suggested": suggested[:40],
        "status": "open",
        "company": company[:80],
        "project": project[:80],
        "subject": subject[:120],
        "priority": priority,
        "meta": meta or {},
        "created": now,
        "updated": now,
        "history": [{"ts": now, "status": "open", "note": "criada pelo scan autônomo"}],
    }
    data["actions"].insert(0, item)
    data["actions"] = data["actions"][:200]
    _save(data)
    bus.publish_sync("action", {"id": item["id"], "status": "open"}, full=board())
    return item


def set_status(
    action_id: str,
    *,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    status = (status or "").lower().strip()
    if status not in STATUSES:
        return {"ok": False, "error": f"status inválido: {status}"}
    data = _load()
    found = None
    for row in data["actions"]:
        if row.get("id") == action_id:
            found = row
            break
    if not found:
        return {"ok": False, "error": "ação não encontrada"}

    now = time.time()
    found["status"] = status
    found["updated"] = now
    hist = found.setdefault("history", [])
    hist.insert(0, {"ts": now, "status": status, "note": (note or "")[:300]})
    found["history"] = hist[:30]
    _save(data)

    # espelha no diário de decisões
    try:
        mem = _root() / "decisions.jsonl"
        with mem.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": now,
                        "kind": "action",
                        "id": action_id,
                        "title": found.get("title"),
                        "status": status,
                        "note": note,
                        "source": found.get("source"),
                        "company": found.get("company"),
                        "subject": found.get("subject"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass

    bus.publish_sync("action", {"id": action_id, "status": status}, full=board())
    return {"ok": True, "action": found}


def board(*, status: str | None = None, limit: int = 80) -> dict[str, Any]:
    data = _load()
    rows = list(data.get("actions") or [])
    if status:
        rows = [r for r in rows if r.get("status") == status]
    # prioridade: high primeiro, depois normal; ECC/agent no fim
    prio = {"high": 0, "normal": 1, "low": 2}

    def _sort_key(r: dict[str, Any]) -> tuple:
        src = str(r.get("source") or "")
        noise = 1 if src in {"ecc", "agent"} else 0
        return (
            prio.get(str(r.get("priority") or "normal"), 1),
            noise,
            -float(r.get("updated") or r.get("created") or 0),
        )

    rows = sorted(rows, key=_sort_key)
    open_n = sum(1 for r in (data.get("actions") or []) if r.get("status") in {"open", "updated", "in_progress"})
    done_n = sum(1 for r in (data.get("actions") or []) if r.get("status") == "done")
    return {
        "ok": True,
        "actions": rows[:limit],
        "counts": {
            "open": open_n,
            "done": done_n,
            "total": len(data.get("actions") or []),
        },
        "updated": data.get("updated") or 0,
    }


def dismiss_noise(*, sources: tuple[str, ...] = ("ecc", "agent")) -> dict[str, Any]:
    """Arquiva propostas de agentes ECC em massa (limpa o quadro)."""
    data = _load()
    now = time.time()
    n = 0
    for row in data.get("actions") or []:
        if row.get("source") in sources and row.get("status") in {"open", "updated", "in_progress"}:
            row["status"] = "dismissed"
            row["updated"] = now
            hist = row.setdefault("history", [])
            hist.insert(0, {"ts": now, "status": "dismissed", "note": "limpeza · ruído de agentes"})
            row["history"] = hist[:20]
            n += 1
    _save(data)
    return {"ok": True, "dismissed": n, **board()}


def get(action_id: str) -> dict[str, Any] | None:
    for row in _load().get("actions") or []:
        if row.get("id") == action_id:
            return row
    return None

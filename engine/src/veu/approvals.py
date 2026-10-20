"""Fila de aprovação por risco — amarrada à respiração guiado/semi/livre/autônomo."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from veu.bus import bus

HIGH_TOOLS = {
    "host.shell",
    "host.fs.write",
    "channel.send",
    "mcp.call",
    "servers.ssh",
    "studio.run",
}
MED_TOOLS = {
    "browser.navigate",
    "browser.click",
    "host.app.open",
    "grokbot.handoff",
    "notion.search",
}


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "approvals.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"pending": [], "log": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pending": [], "log": []}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def classify_risk(tools: list[str] | None = None, *, intent: str = "") -> str:
    tools = tools or []
    if any(t in HIGH_TOOLS for t in tools):
        return "high"
    if any(t in MED_TOOLS for t in tools):
        return "medium"
    low = intent.lower()
    if any(k in low for k in ("apague", "delete", "ssh", "envie", "publique", "shell")):
        return "high"
    if any(k in low for k in ("abra", "navegue", "handoff", "crie")):
        return "medium"
    return "low"


def needs_approval(*, breath: str, risk: str) -> bool:
    b = (breath or "guided").lower()
    r = (risk or "low").lower()
    if b == "free":
        return False
    if b == "autonomous":
        # Autônomo prepara e propõe — só bloqueia alto risco na execução
        return r == "high"
    if b == "semi":
        return r == "high"
    # guided
    return r in {"medium", "high"}


def enqueue(
    *,
    intent: str,
    breath: str,
    tools: list[str] | None = None,
    route: str = "chat",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk = classify_risk(tools, intent=intent)
    if not needs_approval(breath=breath, risk=risk):
        return {
            "ok": True,
            "needs_approval": False,
            "risk": risk,
            "breath": breath,
            "audited": breath == "free",
        }

    data = _load()
    item = {
        "id": f"apr-{uuid.uuid4().hex[:10]}",
        "intent": intent.strip()[:500],
        "breath": breath,
        "risk": risk,
        "route": route,
        "tools": tools or [],
        "context": context or {},
        "created": time.time(),
        "status": "pending",
    }
    data["pending"].insert(0, item)
    data["pending"] = data["pending"][:80]
    _save(data)
    bus.publish_sync("approval", {"id": item["id"], "status": "pending"}, full=board())
    try:
        from veu import push as veu_push

        veu_push.notify_event("approval", {"id": item["id"]})
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "needs_approval": True, "risk": risk, "item": item}


def decide(approval_id: str, *, approve: bool, note: str = "") -> dict[str, Any]:
    data = _load()
    pending = data.get("pending") or []
    found = None
    rest = []
    for row in pending:
        if row.get("id") == approval_id:
            found = row
        else:
            rest.append(row)
    if not found:
        return {"ok": False, "error": "aprovação não encontrada"}

    found["status"] = "approved" if approve else "rejected"
    found["decided_at"] = time.time()
    found["note"] = note[:300]
    data["pending"] = rest
    log = data.get("log") or []
    log.insert(0, found)
    data["log"] = log[:200]
    _save(data)

    job = None
    send = None
    ctx = found.get("context") or {}
    draft_id = str(ctx.get("draft_id") or "")
    tools = found.get("tools") or []

    if approve and draft_id and "channel.send" in tools:
        # Aprovação de envio de inbox → despacha de verdade via GrokBot
        from veu import inbox as veu_inbox

        send = veu_inbox.decide_draft(draft_id, approve=True)
    elif approve:
        from veu import jobs

        job = jobs.store.enqueue(
            intent=str(found.get("intent") or ""),
            route=str(found.get("route") or "chat"),
            breath=str(found.get("breath") or "guided"),
            risk=str(found.get("risk") or "medium"),
            meta={"from_approval": approval_id},
        )
    elif draft_id and "channel.send" in tools:
        from veu import inbox as veu_inbox

        send = veu_inbox.decide_draft(draft_id, approve=False)

    # diário de decisões
    try:
        mem_path = _root() / "decisions.jsonl"
        with mem_path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "kind": "approval",
                        "approved": approve,
                        "intent": found.get("intent"),
                        "risk": found.get("risk"),
                        "note": note,
                        "draft_id": draft_id or None,
                        "sent": bool(send and send.get("ok") and (send.get("send") or {}).get("ok")),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass

    bus.publish_sync(
        "approval",
        {"id": approval_id, "status": found["status"]},
        full=board(),
    )
    try:
        from veu import push as veu_push

        veu_push.notify_event("approval", {"id": approval_id, "approved": approve})
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "item": found, "job": job, "send": send}


def board() -> dict[str, Any]:
    data = _load()
    pending = data.get("pending") or []
    return {
        "ok": True,
        "pending": pending,
        "count": len(pending),
        "recent": (data.get("log") or [])[:20],
    }

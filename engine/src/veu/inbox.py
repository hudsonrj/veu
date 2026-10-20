"""Inbox unificada — canais do live.json numa fila só + rascunhos pra aprovação."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from veu.bus import bus


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _drafts_path() -> Path:
    return _root() / "inbox_drafts.json"


def _load_drafts() -> dict[str, Any]:
    path = _drafts_path()
    if not path.exists():
        return {"drafts": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"drafts": []}


def _save_drafts(data: dict[str, Any]) -> None:
    path = _drafts_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def unified(*, channel: str | None = None, limit: int = 40) -> dict[str, Any]:
    from veu.bridges import control_live

    raw = control_live.load_raw() or {}
    inbox = list(raw.get("inbox") or [])
    items: list[dict[str, Any]] = []
    by_channel: dict[str, int] = {}
    for m in inbox:
        ch = str(m.get("channel") or m.get("source") or "other").lower()
        # normalize
        if "outlook" in ch or ch == "email":
            ch = "outlook"
        elif "team" in ch:
            ch = "teams"
        elif "gmail" in ch:
            ch = "gmail"
        elif "slack" in ch:
            ch = "slack"
        elif "whats" in ch or ch in {"wa", "wpp"}:
            ch = "whatsapp"
        by_channel[ch] = by_channel.get(ch, 0) + 1
        if channel and ch != channel.lower():
            continue
        items.append(
            {
                "id": m.get("id") or f"in-{uuid.uuid4().hex[:8]}",
                "at": m.get("at"),
                "channel": ch,
                "company": m.get("company") or "",
                "sender": m.get("sender") or "",
                "subject": m.get("subject") or m.get("preview") or "",
                "preview": (m.get("bodyPreview") or m.get("preview") or m.get("body") or "")[:280],
                "unread": bool(m.get("unread")),
                "needsApproval": bool(m.get("needsApproval")),
                "why": (m.get("whyImportant") or "")[:160],
                "action": m.get("suggestedAction") or "",
                "draft": m.get("draftReply") or m.get("suggestedReply") or "",
            }
        )

    def score(m: dict[str, Any]) -> tuple:
        return (
            0 if m.get("needsApproval") else 1,
            0 if m.get("unread") else 1,
            str(m.get("at") or ""),
        )

    items = sorted(items, key=score)[:limit]
    drafts = [d for d in (_load_drafts().get("drafts") or []) if d.get("status") == "pending"]
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "channels": by_channel,
        "pending_drafts": drafts[:20],
        "pending_drafts_count": len(drafts),
        "updatedAt": raw.get("updatedAt"),
    }


def create_draft(*, item_id: str, channel: str, subject: str, body: str, to: str = "") -> dict[str, Any]:
    data = _load_drafts()
    draft = {
        "id": f"drf-{uuid.uuid4().hex[:10]}",
        "item_id": item_id,
        "channel": channel,
        "to": to,
        "subject": subject[:300],
        "body": body[:4000],
        "status": "pending",
        "created": time.time(),
    }
    drafts = data.get("drafts") or []
    drafts.insert(0, draft)
    data["drafts"] = drafts[:100]
    _save_drafts(data)

    # amarra na fila de aprovação (risco médio = envio)
    from veu import approvals

    gate = approvals.enqueue(
        intent=f"enviar resposta {channel}: {subject[:80]}",
        breath="guided",
        route="comm",
        tools=["channel.send"],
        context={"draft_id": draft["id"], "channel": channel},
    )
    bus.publish_sync("inbox", {"draft": draft["id"]}, full=None)
    return {"ok": True, "draft": draft, "approval": gate}


def _dispatch_send(draft: dict[str, Any]) -> dict[str, Any]:
    """Envia via GrokBot (já lê Outlook/Teams/Gmail/WA na nuvem)."""
    channel = str(draft.get("channel") or "canal")
    to = str(draft.get("to") or "").strip()
    subject = str(draft.get("subject") or "").strip()
    body = str(draft.get("body") or "").strip()
    intent = (
        f"ENVIO APROVADO NO VÉU — execute agora no canal {channel}.\n"
        f"Para: {to or '(mesmo thread/contato da mensagem original)'}\n"
        f"Assunto: {subject}\n"
        f"Corpo:\n{body}\n\n"
        "Se precisar de mais contexto, use a inbox/live do Control. "
        "Confirme quando enviar (ou diga o bloqueio)."
    )
    try:
        from veu.bridges.grokbot import GrokBotBridge

        result = GrokBotBridge().ask(
            intent=intent,
            breath="guided",
            agent="inbox",
            via="inbox.send",
            priority="high",
        )
        return {
            "ok": bool(result.get("ok")),
            "via": "grokbot",
            "delivered": bool(result.get("delivered") or result.get("ok")),
            "result": {
                k: result.get(k)
                for k in ("ok", "delivered", "message", "job_id", "id", "error")
                if k in result
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "via": "grokbot", "error": str(exc)[:200]}


def decide_draft(draft_id: str, *, approve: bool) -> dict[str, Any]:
    data = _load_drafts()
    found = None
    for d in data.get("drafts") or []:
        if d.get("id") == draft_id:
            found = d
            break
    if not found:
        return {"ok": False, "error": "rascunho não encontrado"}
    if found.get("status") in {"sent", "approved", "rejected"} and found.get("send"):
        return {
            "ok": True,
            "draft": found,
            "send": found.get("send"),
            "note": "já processado",
            "idempotent": True,
        }
    found["status"] = "approved" if approve else "rejected"
    found["decided_at"] = time.time()
    send: dict[str, Any] | None = None
    if approve:
        send = _dispatch_send(found)
        found["send"] = {
            "ok": send.get("ok"),
            "via": send.get("via"),
            "at": time.time(),
            "error": send.get("error"),
        }
        if send.get("ok"):
            found["status"] = "sent"
    _save_drafts(data)
    mem = _root() / "decisions.jsonl"
    try:
        with mem.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "kind": "inbox.draft",
                        "approved": approve,
                        "draft_id": draft_id,
                        "channel": found.get("channel"),
                        "subject": found.get("subject"),
                        "sent": bool(send and send.get("ok")),
                        "send_via": (send or {}).get("via"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass
    bus.publish_sync("inbox", {"draft": draft_id, "status": found["status"]}, full=None)
    try:
        from veu import push as veu_push

        if approve:
            veu_push.notify(
                "Envio pedido",
                f"{found.get('channel')}: {found.get('subject') or 'rascunho'}"[:120],
                url="/?app=inbox",
                tag="inbox-send",
            )
    except Exception:  # noqa: BLE001
        pass
    if not approve:
        note = "rascunho recusado"
    elif send and send.get("ok"):
        note = f"enviado via Grok Bot ({found.get('channel')})"
    else:
        note = (
            "aprovado, mas o Grok Bot não confirmou entrega — "
            f"{(send or {}).get('error') or 'cheque o webhook'}"
        )
    return {"ok": True, "draft": found, "send": send, "note": note}

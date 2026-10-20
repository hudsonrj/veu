"""Importador da exportação oficial do ChatGPT (.zip)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from veu import projects as proj


def _parse_ts(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        # ChatGPT sometimes uses seconds or ms
        v = float(value)
        if v > 1e12:
            return v / 1000.0
        return v
    s = str(value)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _conversation_title(conv: dict[str, Any]) -> str:
    return str(conv.get("title") or conv.get("name") or "sem título")[:200]


def _conversation_id(conv: dict[str, Any]) -> str:
    return str(conv.get("id") or conv.get("conversation_id") or "")


def _extract_messages(conv: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = conv.get("mapping") or {}
    out: list[dict[str, Any]] = []
    if isinstance(mapping, dict):
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            msg = node.get("message") or {}
            if not isinstance(msg, dict):
                continue
            author = ((msg.get("author") or {}).get("role")) or ""
            content = msg.get("content") or {}
            parts = content.get("parts") if isinstance(content, dict) else None
            text = ""
            if isinstance(parts, list):
                text = " ".join(str(p) for p in parts if isinstance(p, str))
            elif isinstance(content, str):
                text = content
            if not text.strip():
                continue
            out.append(
                {
                    "role": author,
                    "text": text,
                    "ts": _parse_ts(msg.get("create_time")),
                }
            )
    # formato alternativo: messages[]
    for msg in conv.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        text = str(msg.get("content") or msg.get("text") or "")
        if not text.strip():
            continue
        out.append(
            {
                "role": str(msg.get("role") or ""),
                "text": text,
                "ts": _parse_ts(msg.get("create_time") or msg.get("timestamp")),
            }
        )
    out.sort(key=lambda m: m.get("ts") or 0)
    return out


def preview_zip(data: bytes) -> dict[str, Any]:
    """Prévia opt-in: contagem + intervalo de datas. Não grava."""
    conversations, errors = _load_conversations(data)
    times: list[float] = []
    for c in conversations:
        t = _parse_ts(c.get("create_time") or c.get("update_time"))
        if t:
            times.append(t)
        for m in _extract_messages(c):
            if m.get("ts"):
                times.append(float(m["ts"]))
    return {
        "ok": True,
        "conversations": len(conversations),
        "errors": errors[:20],
        "error_count": len(errors),
        "date_min": datetime.fromtimestamp(min(times), tz=timezone.utc).isoformat() if times else None,
        "date_max": datetime.fromtimestamp(max(times), tz=timezone.utc).isoformat() if times else None,
        "preview": True,
    }


def _load_conversations(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    conversations: list[dict[str, Any]] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        return [], [f"zip inválido: {exc}"]

    # conversations.json (raiz ou aninhado)
    names = zf.namelist()
    target = None
    for n in names:
        if n.endswith("conversations.json"):
            target = n
            break
    if not target:
        # às vezes é um único json
        for n in names:
            if n.endswith(".json") and "conversation" in n.lower():
                target = n
                break
    if not target:
        return [], ["conversations.json não encontrado"]

    try:
        raw = zf.read(target)
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return [], [f"falha ao ler conversations.json: {exc}"]

    if isinstance(payload, list):
        conversations = [c for c in payload if isinstance(c, dict)]
    elif isinstance(payload, dict):
        if isinstance(payload.get("conversations"), list):
            conversations = [c for c in payload["conversations"] if isinstance(c, dict)]
        else:
            conversations = [payload]
    else:
        errors.append("formato inesperado em conversations.json")
    return conversations, errors


def import_zip(data: bytes, *, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        return preview_zip(data)

    conversations, errors = _load_conversations(data)
    created_projects = 0
    created_items = 0
    skipped = 0

    for conv in conversations:
        try:
            cid = _conversation_id(conv) or _conversation_title(conv)
            title = _conversation_title(conv)
            messages = _extract_messages(conv)
            h = proj.hash_origem("chatgpt", cid, title)
            # projeto = conversa (ChatGPT export não tem "projects" estáveis sempre)
            existing = None
            for p in proj.list_projects(fonte="chatgpt", q=title, limit=50):
                if p.get("hash_origem") == h:
                    existing = p
                    break
            if existing:
                project = existing
                skipped += 1
            else:
                ts = _parse_ts(conv.get("update_time") or conv.get("create_time"))
                snippet = ""
                if messages:
                    snippet = messages[-1]["text"][:400]
                project = proj.create_project(
                    {
                        "nome": title,
                        "fonte": "chatgpt",
                        "resumo": snippet,
                        "ultima_atividade": ts or None,
                        "hash_origem": h,
                        "caminho_ou_url": f"chatgpt://conversation/{cid}" if cid else None,
                        "tags": ["chatgpt", "import"],
                    }
                )
                created_projects += 1

            # itens = mensagens agrupadas em trechos (não explode 1:1 se milhares)
            # cria até 1 item resumo + últimos N
            if messages:
                first_h = proj.hash_origem("chatgpt-item", cid, "first")
                item = proj.add_item(
                    project["id"],
                    {
                        "tipo": "conversa",
                        "titulo": title,
                        "ts": messages[0].get("ts") or project.get("ultima_atividade"),
                        "trecho": messages[0]["text"][:500],
                        "ref": cid,
                        "hash_origem": first_h,
                    },
                )
                if item.get("hash_origem") == first_h:
                    # may be existing; count only if newly meaningful — use created check via n
                    created_items += 1
                if len(messages) > 1:
                    last = messages[-1]
                    last_h = proj.hash_origem("chatgpt-item", cid, "last", str(last.get("ts")))
                    proj.add_item(
                        project["id"],
                        {
                            "tipo": "conversa",
                            "titulo": f"{title} · fim",
                            "ts": last.get("ts"),
                            "trecho": last["text"][:500],
                            "ref": cid,
                            "hash_origem": last_h,
                        },
                    )
                    created_items += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{_conversation_title(conv)}: {exc}")

    # zip não é guardado (só bytes em memória)
    proj.set_sync("chatgpt", f"import confirm · {created_projects} projetos")
    return {
        "ok": True,
        "projects_created": created_projects,
        "items_created": created_items,
        "skipped_existing": skipped,
        "total_conversations": len(conversations),
        "errors": errors[:40],
        "error_count": len(errors),
        "zip_stored": False,
    }

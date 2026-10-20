"""Importador da exportação da conta Claude (.zip) + coletor Claude Code."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from veu import projects as proj

ReadText = Callable[[str], str | None]
ListDir = Callable[[str], list[dict[str, Any]]]


def _parse_ts(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e12 else v
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def preview_zip(data: bytes) -> dict[str, Any]:
    convs, errors = _load_claude_export(data)
    times = [_parse_ts(c.get("created_at") or c.get("updated_at")) for c in convs]
    times = [t for t in times if t]
    return {
        "ok": True,
        "conversations": len(convs),
        "errors": errors[:20],
        "error_count": len(errors),
        "date_min": datetime.fromtimestamp(min(times), tz=timezone.utc).isoformat() if times else None,
        "date_max": datetime.fromtimestamp(max(times), tz=timezone.utc).isoformat() if times else None,
        "preview": True,
    }


def _load_claude_export(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        return [], [f"zip inválido: {exc}"]

    conversations: list[dict[str, Any]] = []
    for name in zf.namelist():
        low = name.lower()
        if name.endswith("/") or low.endswith((".png", ".jpg", ".jpeg", ".gif", ".pdf", ".bin", ".zip")):
            continue  # ignora anexos binários
        if not low.endswith(".json"):
            continue
        try:
            payload = json.loads(zf.read(name).decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and (
                    "chat_messages" in item or "messages" in item or "uuid" in item or "name" in item
                ):
                    conversations.append(item)
        elif isinstance(payload, dict):
            if "conversations" in payload and isinstance(payload["conversations"], list):
                conversations.extend([c for c in payload["conversations"] if isinstance(c, dict)])
            elif "chat_messages" in payload or "messages" in payload or "uuid" in payload:
                conversations.append(payload)
    return conversations, errors


def import_zip(data: bytes, *, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        return preview_zip(data)
    convs, errors = _load_claude_export(data)
    created_p = 0
    created_i = 0
    skipped = 0
    for conv in convs:
        try:
            cid = str(conv.get("uuid") or conv.get("id") or conv.get("name") or "")
            title = str(conv.get("name") or conv.get("title") or "Claude")[:200]
            h = proj.hash_origem("claude", cid, title)
            existing = next((p for p in proj.list_projects(fonte="claude", limit=500) if p.get("hash_origem") == h), None)
            msgs = conv.get("chat_messages") or conv.get("messages") or []
            snippet = ""
            last_ts = _parse_ts(conv.get("updated_at") or conv.get("created_at"))
            if isinstance(msgs, list) and msgs:
                last = msgs[-1] if isinstance(msgs[-1], dict) else {}
                snippet = str(last.get("text") or last.get("content") or "")[:400]
                last_ts = _parse_ts(last.get("created_at") or last.get("updated_at")) or last_ts
            if existing:
                project = existing
                skipped += 1
            else:
                project = proj.create_project(
                    {
                        "nome": title,
                        "fonte": "claude",
                        "resumo": snippet,
                        "ultima_atividade": last_ts or None,
                        "hash_origem": h,
                        "tags": ["claude", "import"],
                        "caminho_ou_url": f"claude://conversation/{cid}" if cid else None,
                    }
                )
                created_p += 1
            # até 2 itens
            if isinstance(msgs, list) and msgs:
                first = msgs[0] if isinstance(msgs[0], dict) else {}
                text = str(first.get("text") or first.get("content") or "")
                ih = proj.hash_origem("claude-item", cid, "first")
                proj.add_item(
                    project["id"],
                    {
                        "tipo": "conversa",
                        "titulo": title,
                        "ts": _parse_ts(first.get("created_at")) or last_ts,
                        "trecho": text[:500],
                        "ref": cid,
                        "hash_origem": ih,
                    },
                )
                created_i += 1
                if len(msgs) > 1:
                    last = msgs[-1] if isinstance(msgs[-1], dict) else {}
                    proj.add_item(
                        project["id"],
                        {
                            "tipo": "conversa",
                            "titulo": f"{title} · fim",
                            "ts": _parse_ts(last.get("created_at")) or last_ts,
                            "trecho": str(last.get("text") or last.get("content") or "")[:500],
                            "ref": cid,
                            "hash_origem": proj.hash_origem("claude-item", cid, "last"),
                        },
                    )
                    created_i += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc)[:200])

    proj.set_sync("claude", f"import · {created_p} projetos")
    return {
        "ok": True,
        "projects_created": created_p,
        "items_created": created_i,
        "skipped_existing": skipped,
        "total_conversations": len(convs),
        "errors": errors[:40],
        "error_count": len(errors),
        "zip_stored": False,
    }


def _default_list_dir(path: str) -> list[dict[str, Any]]:
    p = Path(path).expanduser()
    if not p.is_dir():
        return []
    out = []
    for child in sorted(p.iterdir()):
        out.append(
            {
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "mtime": child.stat().st_mtime if child.exists() else 0,
            }
        )
    return out


def _default_read_text(path: str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    # ignora binários grosseiros
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".bin"}:
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return None


def collect_claude_code(
    *,
    root: str | None = None,
    list_dir: ListDir | None = None,
    read_text: ReadText | None = None,
) -> dict[str, Any]:
    """Lê ~/.claude/projects/<pasta>/*.jsonl — só pastas permitidas."""
    list_dir = list_dir or _default_list_dir
    read_text = read_text or _default_read_text
    base = str(Path(root or "~/.claude/projects").expanduser())
    allowed = proj.list_allowed_folders("claude-code")
    if not allowed:
        return {
            "ok": True,
            "projects_created": 0,
            "ignored": True,
            "message": "nenhuma pasta permitida — marque pastas antes de sincronizar",
        }

    allowed_paths = {str(Path(a["path"]).expanduser()) for a in allowed}
    created_p = 0
    created_i = 0
    ignored_folders = 0

    for entry in list_dir(base):
        if not entry.get("is_dir"):
            continue
        folder = str(entry.get("path") or "")
        folder_name = Path(folder).name
        ok = folder in allowed_paths or any(
            folder.startswith(ap.rstrip("/") + "/")
            or ap == folder
            or Path(ap).name == folder_name
            for ap in allowed_paths
        )
        if not ok:
            ignored_folders += 1
            continue

        sessions: list[dict[str, Any]] = []
        for f in list_dir(folder):
            name = str(f.get("name") or "")
            if not name.endswith(".jsonl"):
                continue
            text = read_text(str(f.get("path") or ""))
            if text is None:
                continue
            lines = []
            last_ts = float(f.get("mtime") or 0)
            last_summary = ""
            for line in text.splitlines()[-200:]:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lines.append(obj)
                ts = _parse_ts(obj.get("timestamp") or obj.get("ts"))
                if ts:
                    last_ts = max(last_ts, ts)
                content = obj.get("message") or obj.get("content") or obj.get("text") or ""
                if isinstance(content, dict):
                    content = content.get("text") or json.dumps(content, ensure_ascii=False)[:200]
                if content:
                    last_summary = str(content)[:400]
            sessions.append(
                {
                    "file": name,
                    "path": f.get("path"),
                    "n": len(lines),
                    "ts": last_ts,
                    "summary": last_summary,
                }
            )

        if not sessions:
            continue

        folder_name = Path(folder).name
        h = proj.hash_origem("claude-code", folder)
        existing = next(
            (p for p in proj.list_projects(fonte="claude-code", limit=500) if p.get("hash_origem") == h),
            None,
        )
        sessions.sort(key=lambda s: s.get("ts") or 0)
        last = sessions[-1]
        if existing:
            project = existing
        else:
            project = proj.create_project(
                {
                    "nome": folder_name,
                    "fonte": "claude-code",
                    "caminho_ou_url": folder,
                    "resumo": last.get("summary") or f"{len(sessions)} sessões",
                    "ultima_atividade": last.get("ts"),
                    "hash_origem": h,
                    "tags": ["claude-code"],
                }
            )
            created_p += 1

        for s in sessions:
            ih = proj.hash_origem("claude-code-session", folder, str(s.get("file")))
            before = proj.get_project(project["id"])
            n_before = len((before or {}).get("itens") or [])
            proj.add_item(
                project["id"],
                {
                    "tipo": "sessao",
                    "titulo": str(s.get("file")),
                    "ts": s.get("ts"),
                    "trecho": s.get("summary") or "",
                    "ref": s.get("path"),
                    "hash_origem": ih,
                },
            )
            after = proj.get_project(project["id"])
            if len((after or {}).get("itens") or []) > n_before:
                created_i += 1

    proj.set_sync("claude-code", f"sync · +{created_p} projetos")
    return {
        "ok": True,
        "projects_created": created_p,
        "items_created": created_i,
        "ignored_folders": ignored_folders,
    }

"""Coletor Cursor — somente leitura via host; tolera schema SQLite desconhecido."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from veu import projects as proj

ListDir = Callable[[str], list[dict[str, Any]]]
ReadText = Callable[[str], str | None]


def _default_list_dir(path: str) -> list[dict[str, Any]]:
    p = Path(path).expanduser()
    if not p.is_dir():
        return []
    out = []
    for child in sorted(p.iterdir()):
        try:
            st = child.stat()
            mtime = st.st_mtime
        except OSError:
            mtime = 0
        out.append(
            {
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "mtime": mtime,
            }
        )
    return out


def _default_read_text(path: str) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:100_000]
    except OSError:
        return None


def _git_last_commit(folder: Path) -> str:
    git = folder / ".git" / "logs" / "HEAD"
    if not git.is_file():
        return ""
    try:
        lines = git.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            return ""
        # formato: ... commit message
        last = lines[-1]
        if "\t" in last:
            return last.split("\t", 1)[-1][:200]
        return last[-200:]
    except OSError:
        return ""


def _read_rules(folder: Path, read_text: ReadText) -> str:
    rules_dir = folder / ".cursor" / "rules"
    bits: list[str] = []
    if rules_dir.is_dir():
        for f in sorted(rules_dir.glob("*"))[:8]:
            if f.is_file():
                t = read_text(str(f))
                if t:
                    bits.append(f"# {f.name}\n{t[:400]}")
    readme = folder / "README.md"
    if readme.is_file():
        t = read_text(str(readme))
        if t:
            bits.append(t[:500])
    return "\n".join(bits)[:1200]


def read_cursor_chat_db(db_path: str) -> dict[str, Any]:
    """Somente leitura. Qualquer schema desconhecido → histórico indisponível."""
    path = Path(db_path)
    if not path.is_file():
        return {"ok": False, "available": False, "note": "histórico indisponível", "messages": []}
    try:
        # URI read-only
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        # heurística: procura tabela com colunas textuais
        messages: list[dict[str, Any]] = []
        note = ""
        for table in tables:
            try:
                cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            except sqlite3.Error:
                continue
            colset = {c.lower() for c in cols}
            text_cols = [c for c in cols if c.lower() in {"text", "content", "message", "body", "value"}]
            if not text_cols:
                continue
            # tenta ler poucas linhas
            try:
                rows = conn.execute(f"SELECT * FROM {table} LIMIT 5").fetchall()
            except sqlite3.Error:
                continue
            for row in rows:
                d = dict(row)
                text = ""
                for tc in text_cols:
                    if d.get(tc):
                        text = str(d[tc])
                        break
                if text:
                    messages.append({"table": table, "text": text[:300]})
            if messages:
                note = f"lido de {table}"
                break
        if not messages:
            note = "histórico indisponível"
        conn.close()
        return {"ok": True, "available": bool(messages), "note": note, "messages": messages, "tables": tables}
    except Exception as exc:  # noqa: BLE001 — schema muda; nunca quebrar
        return {
            "ok": True,
            "available": False,
            "note": "histórico indisponível",
            "error": str(exc)[:200],
            "messages": [],
        }


def collect_cursor(
    *,
    workspace_roots: list[str] | None = None,
    list_dir: ListDir | None = None,
    read_text: ReadText | None = None,
    chat_db_path: str | None = None,
) -> dict[str, Any]:
    """Cria Projeto por pasta permitida (fonte cursor). Nunca escreve no Cursor."""
    list_dir = list_dir or _default_list_dir
    read_text = read_text or _default_read_text
    allowed = proj.list_allowed_folders("cursor")
    if not allowed and not workspace_roots:
        return {
            "ok": True,
            "projects_created": 0,
            "ignored": True,
            "message": "nenhuma pasta Cursor permitida",
        }

    folders: list[str] = []
    if workspace_roots:
        folders.extend(workspace_roots)
    for a in allowed:
        folders.append(a["path"])

    # dedup
    seen: set[str] = set()
    uniq: list[str] = []
    for f in folders:
        p = str(Path(f).expanduser())
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)

    created = 0
    history_note = "histórico indisponível"
    chat = None
    if chat_db_path:
        chat = read_cursor_chat_db(chat_db_path)
        history_note = chat.get("note") or history_note

    for folder in uniq:
        # enforce allow list when present
        if allowed and not proj.is_path_allowed(folder, "cursor"):
            continue
        if allowed and folder not in {str(Path(a["path"]).expanduser()) for a in allowed}:
            # still allow exact listed
            if not any(folder.startswith(str(Path(a["path"]).expanduser())) for a in allowed):
                continue
        p = Path(folder)
        if not p.exists() and list_dir is _default_list_dir:
            # for injected list_dir tests, folder may be virtual — still create by name
            pass
        name = p.name or folder
        h = proj.hash_origem("cursor", folder)
        existing = next(
            (x for x in proj.list_projects(fonte="cursor", limit=500) if x.get("hash_origem") == h),
            None,
        )
        rules = ""
        commit = ""
        if p.is_dir():
            rules = _read_rules(p, read_text)
            commit = _git_last_commit(p)
        resumo_bits = [b for b in (commit, rules[:300]) if b]
        resumo = " · ".join(resumo_bits) or f"workspace Cursor · {history_note}"
        if existing:
            project = existing
            proj.patch_project(project["id"], {"resumo": resumo})
        else:
            project = proj.create_project(
                {
                    "nome": name,
                    "fonte": "cursor",
                    "caminho_ou_url": folder,
                    "resumo": resumo,
                    "hash_origem": h,
                    "tags": ["cursor"],
                    "meta": {"history": history_note},
                }
            )
            created += 1

        # regras como item
        if rules:
            proj.add_item(
                project["id"],
                {
                    "tipo": "arquivo",
                    "titulo": ".cursor/rules",
                    "trecho": rules[:500],
                    "ref": str(p / ".cursor" / "rules"),
                    "hash_origem": proj.hash_origem("cursor-rules", folder),
                },
            )
        if chat and chat.get("messages"):
            for i, m in enumerate(chat["messages"][:3]):
                proj.add_item(
                    project["id"],
                    {
                        "tipo": "conversa",
                        "titulo": f"chat · {m.get('table')}",
                        "trecho": m.get("text") or "",
                        "hash_origem": proj.hash_origem("cursor-chat", folder, str(i), str(m.get("text"))[:40]),
                    },
                )

    proj.set_sync("cursor", f"sync · +{created} · {history_note}")
    return {
        "ok": True,
        "projects_created": created,
        "history": history_note,
        "chat": {"available": bool(chat and chat.get("available"))} if chat else None,
    }

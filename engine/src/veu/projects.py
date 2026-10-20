"""Inventário unificado de Projetos + Itens de contexto (todas as IAs)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from veu.redact import redact_text

Source = Literal[
    "chatgpt",
    "claude",
    "claude-code",
    "cursor",
    "codex",
    "grok",
    "hermes",
    "manual",
]

ItemTipo = Literal["conversa", "sessao", "nota", "arquivo"]


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _db_path() -> Path:
    return _root() / "projects.sqlite"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projetos (
            id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            empresa TEXT,
            fonte TEXT NOT NULL,
            caminho_ou_url TEXT,
            resumo TEXT,
            ultima_atividade REAL,
            n_itens INTEGER DEFAULT 0,
            tags_json TEXT DEFAULT '[]',
            hash_origem TEXT,
            meta_json TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_proj_fonte ON projetos(fonte);
        CREATE INDEX IF NOT EXISTS idx_proj_empresa ON projetos(empresa);
        CREATE INDEX IF NOT EXISTS idx_proj_hash ON projetos(hash_origem);

        CREATE TABLE IF NOT EXISTS itens (
            id TEXT PRIMARY KEY,
            projeto_id TEXT NOT NULL,
            tipo TEXT NOT NULL,
            titulo TEXT,
            ts REAL,
            trecho_mascarado TEXT,
            ref TEXT,
            hash_origem TEXT,
            FOREIGN KEY(projeto_id) REFERENCES projetos(id)
        );
        CREATE INDEX IF NOT EXISTS idx_itens_proj ON itens(projeto_id);
        CREATE INDEX IF NOT EXISTS idx_itens_hash ON itens(hash_origem);

        CREATE TABLE IF NOT EXISTS sync_state (
            fonte TEXT PRIMARY KEY,
            last_sync REAL,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS allowed_folders (
            path TEXT PRIMARY KEY,
            fonte TEXT NOT NULL,
            enabled INTEGER DEFAULT 1
        );
        """
    )
    conn.commit()


def _now() -> float:
    return time.time()


def _tags_load(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        return [str(x) for x in data] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _row_project(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "nome": r["nome"],
        "empresa": r["empresa"],
        "fonte": r["fonte"],
        "caminho_ou_url": r["caminho_ou_url"],
        "resumo": r["resumo"],
        "ultima_atividade": r["ultima_atividade"],
        "n_itens": r["n_itens"],
        "tags": _tags_load(r["tags_json"]),
        "hash_origem": r["hash_origem"],
        "meta": json.loads(r["meta_json"] or "{}"),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def _row_item(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "projeto_id": r["projeto_id"],
        "tipo": r["tipo"],
        "titulo": r["titulo"],
        "ts": r["ts"],
        "trecho_mascarado": r["trecho_mascarado"],
        "ref": r["ref"],
        "hash_origem": r["hash_origem"],
    }


def mask_trecho(text: str, *, limit: int = 600) -> str:
    return redact_text((text or "")[:limit])


def hash_origem(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:40]


def list_projects(
    *,
    fonte: str | None = None,
    empresa: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    args: list[Any] = []
    if fonte:
        clauses.append("fonte = ?")
        args.append(fonte)
    if empresa:
        clauses.append("empresa = ?")
        args.append(empresa)
    if q:
        clauses.append("(nome LIKE ? OR resumo LIKE ? OR tags_json LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like, like])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM projetos{where} ORDER BY ultima_atividade DESC NULLS LAST, updated_at DESC LIMIT ?"
    args.append(min(500, max(1, limit)))
    with _conn() as conn:
        # SQLite NULLS LAST not always available — fallback
        try:
            rows = conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            sql2 = f"SELECT * FROM projetos{where} ORDER BY COALESCE(ultima_atividade,0) DESC, updated_at DESC LIMIT ?"
            rows = conn.execute(sql2, args).fetchall()
        return [_row_project(r) for r in rows]


def get_project(project_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        r = conn.execute("SELECT * FROM projetos WHERE id = ?", (project_id,)).fetchone()
        if not r:
            return None
        proj = _row_project(r)
        items = conn.execute(
            "SELECT * FROM itens WHERE projeto_id = ? ORDER BY ts DESC",
            (project_id,),
        ).fetchall()
        proj["itens"] = [_row_item(i) for i in items]
        return proj


def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    fonte = str(payload.get("fonte") or "manual")
    nome = mask_trecho(str(payload.get("nome") or "").strip(), limit=200)
    if not nome:
        raise ValueError("nome obrigatório")
    tags = payload.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    h = payload.get("hash_origem")
    if h:
        with _conn() as conn:
            existing = conn.execute(
                "SELECT * FROM projetos WHERE hash_origem = ?", (h,)
            ).fetchone()
            if existing:
                return _row_project(existing)
    pid = str(payload.get("id") or uuid.uuid4())
    row = {
        "id": pid,
        "nome": nome[:200],
        "empresa": (str(payload.get("empresa") or "").strip() or None),
        "fonte": fonte,
        "caminho_ou_url": (str(payload.get("caminho_ou_url") or "").strip() or None),
        "resumo": mask_trecho(str(payload.get("resumo") or ""), limit=1200),
        "ultima_atividade": float(payload.get("ultima_atividade") or now),
        "n_itens": int(payload.get("n_itens") or 0),
        "tags_json": json.dumps([str(t)[:40] for t in tags][:20], ensure_ascii=False),
        "hash_origem": h,
        "meta_json": json.dumps(payload.get("meta") or {}, ensure_ascii=False),
        "created_at": now,
        "updated_at": now,
    }
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO projetos
            (id, nome, empresa, fonte, caminho_ou_url, resumo, ultima_atividade,
             n_itens, tags_json, hash_origem, meta_json, created_at, updated_at)
            VALUES
            (:id, :nome, :empresa, :fonte, :caminho_ou_url, :resumo, :ultima_atividade,
             :n_itens, :tags_json, :hash_origem, :meta_json, :created_at, :updated_at)
            """,
            row,
        )
        conn.commit()
    return {**{k: row[k] for k in row if k not in {"tags_json", "meta_json"}}, "tags": tags, "meta": payload.get("meta") or {}}


def patch_project(project_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with _conn() as conn:
        r = conn.execute("SELECT * FROM projetos WHERE id = ?", (project_id,)).fetchone()
        if not r:
            raise KeyError("projeto não encontrado")
        fields = []
        args: dict[str, Any] = {"id": project_id}
        if "empresa" in patch:
            fields.append("empresa = :empresa")
            args["empresa"] = (str(patch.get("empresa") or "").strip() or None)
        if "tags" in patch:
            tags = patch.get("tags") or []
            fields.append("tags_json = :tags_json")
            args["tags_json"] = json.dumps([str(t)[:40] for t in tags][:20], ensure_ascii=False)
        if "resumo" in patch:
            fields.append("resumo = :resumo")
            args["resumo"] = mask_trecho(str(patch.get("resumo") or ""), limit=1200)
        if "nome" in patch and str(patch.get("nome") or "").strip():
            fields.append("nome = :nome")
            args["nome"] = str(patch["nome"]).strip()[:200]
        if not fields:
            return _row_project(r)
        fields.append("updated_at = :updated_at")
        args["updated_at"] = _now()
        conn.execute(f"UPDATE projetos SET {', '.join(fields)} WHERE id = :id", args)
        conn.commit()
        r2 = conn.execute("SELECT * FROM projetos WHERE id = ?", (project_id,)).fetchone()
        return _row_project(r2)


def add_item(projeto_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    h = payload.get("hash_origem")
    with _conn() as conn:
        if h:
            ex = conn.execute("SELECT * FROM itens WHERE hash_origem = ?", (h,)).fetchone()
            if ex:
                return _row_item(ex)
        proj = conn.execute("SELECT id FROM projetos WHERE id = ?", (projeto_id,)).fetchone()
        if not proj:
            raise KeyError("projeto não encontrado")
        item = {
            "id": str(payload.get("id") or uuid.uuid4()),
            "projeto_id": projeto_id,
            "tipo": str(payload.get("tipo") or "nota"),
            "titulo": str(payload.get("titulo") or "")[:200],
            "ts": float(payload.get("ts") or _now()),
            "trecho_mascarado": mask_trecho(str(payload.get("trecho") or payload.get("trecho_mascarado") or "")),
            "ref": (str(payload.get("ref") or "").strip() or None),
            "hash_origem": h,
        }
        conn.execute(
            """
            INSERT INTO itens (id, projeto_id, tipo, titulo, ts, trecho_mascarado, ref, hash_origem)
            VALUES (:id, :projeto_id, :tipo, :titulo, :ts, :trecho_mascarado, :ref, :hash_origem)
            """,
            item,
        )
        conn.execute(
            """
            UPDATE projetos SET
              n_itens = (SELECT COUNT(*) FROM itens WHERE projeto_id = :pid),
              ultima_atividade = CASE
                WHEN COALESCE(ultima_atividade, 0) > :ts THEN ultima_atividade
                ELSE :ts
              END,
              updated_at = :now
            WHERE id = :pid
            """,
            {"pid": projeto_id, "ts": item["ts"], "now": _now()},
        )
        conn.commit()
        return item


def set_sync(fonte: str, note: str = "") -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO sync_state (fonte, last_sync, note) VALUES (?, ?, ?)
            ON CONFLICT(fonte) DO UPDATE SET last_sync = excluded.last_sync, note = excluded.note
            """,
            (fonte, _now(), note[:300]),
        )
        conn.commit()


def sync_status() -> dict[str, Any]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM sync_state").fetchall()
        return {
            r["fonte"]: {"last_sync": r["last_sync"], "note": r["note"]} for r in rows
        }


def list_allowed_folders(fonte: str | None = None) -> list[dict[str, Any]]:
    with _conn() as conn:
        if fonte:
            rows = conn.execute(
                "SELECT * FROM allowed_folders WHERE fonte = ? AND enabled = 1", (fonte,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM allowed_folders WHERE enabled = 1").fetchall()
        return [{"path": r["path"], "fonte": r["fonte"]} for r in rows]


def allow_folder(path: str, fonte: str) -> dict[str, Any]:
    p = str(Path(path).expanduser())
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO allowed_folders (path, fonte, enabled) VALUES (?, ?, 1)
            ON CONFLICT(path) DO UPDATE SET enabled = 1, fonte = excluded.fonte
            """,
            (p, fonte),
        )
        conn.commit()
    return {"ok": True, "path": p, "fonte": fonte}


def deny_folder(path: str) -> dict[str, Any]:
    p = str(Path(path).expanduser())
    with _conn() as conn:
        conn.execute("UPDATE allowed_folders SET enabled = 0 WHERE path = ?", (p,))
        conn.commit()
    return {"ok": True, "path": p}


def is_path_allowed(path: str, fonte: str) -> bool:
    p = str(Path(path).expanduser().resolve()) if Path(path).exists() else str(Path(path).expanduser())
    allowed = list_allowed_folders(fonte)
    if not allowed:
        return False
    for a in allowed:
        ap = str(Path(a["path"]).expanduser())
        if p == ap or p.startswith(ap.rstrip("/") + "/") or ap == p:
            return True
        # also allow if path is under allowed as prefix string
        if p.startswith(ap):
            return True
    return False


def ask_about_project(project_id: str, question: str) -> dict[str, Any]:
    """Consulta OpenRAG só com itens do projeto (contexto local embutido)."""
    proj = get_project(project_id)
    if not proj:
        return {"ok": False, "error": "projeto não encontrado"}
    items = proj.get("itens") or []
    ctx_bits = []
    sources = []
    for it in items[:40]:
        bit = f"[{it.get('tipo')}] {it.get('titulo')}: {it.get('trecho_mascarado') or ''}"
        ctx_bits.append(bit[:400])
        sources.append(
            {
                "title": it.get("titulo"),
                "kind": it.get("tipo"),
                "ref": it.get("ref"),
                "fonte": proj.get("fonte"),
            }
        )
    prompt = (
        f"Projeto: {proj.get('nome')} (fonte {proj.get('fonte')})\n"
        f"Resumo: {proj.get('resumo') or ''}\n"
        f"Contexto:\n" + "\n".join(ctx_bits) + "\n\n"
        f"Pergunta: {question}\n"
        "Responda em português e cite a fonte (ferramenta/item)."
    )
    try:
        from veu.connectors.openrag import OpenRAGAdapter

        rag = OpenRAGAdapter()
        result = rag.ask(prompt, limit=6)
        if result.get("ok"):
            # merge local sources
            result["sources"] = (result.get("sources") or []) + sources[:8]
            result["project_id"] = project_id
            return result
        # fallback local sem LLM externo
        return {
            "ok": True,
            "answer": (
                f"Contexto local do projeto «{proj.get('nome')}» ({len(items)} itens, "
                f"fonte {proj.get('fonte')}). OpenRAG indisponível — use os trechos listados."
            ),
            "sources": sources,
            "project_id": project_id,
            "fallback": True,
            "message": result.get("message"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": True,
            "answer": f"Contexto local · {proj.get('nome')} · {len(items)} itens.",
            "sources": sources,
            "project_id": project_id,
            "fallback": True,
            "error": str(exc)[:200],
        }

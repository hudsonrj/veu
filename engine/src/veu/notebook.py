"""Notebook++ — documentos texto/código com persistência e ajuda de IA."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

LANGS = {
    "txt": "texto",
    "md": "markdown",
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "tsx": "tsx",
    "json": "json",
    "html": "html",
    "css": "css",
    "sh": "shell",
    "sql": "sql",
    "yml": "yaml",
    "yaml": "yaml",
}


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    nb = root / "notebook"
    nb.mkdir(parents=True, exist_ok=True)
    return nb


def _safe_id(doc_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (doc_id or "").strip())[:80]
    return s or f"doc-{uuid.uuid4().hex[:10]}"


def _meta_path(doc_id: str) -> Path:
    return _root() / f"{_safe_id(doc_id)}.meta.json"


def _body_path(doc_id: str) -> Path:
    return _root() / f"{_safe_id(doc_id)}.body"


def list_docs(limit: int = 80) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for meta in _root().glob("*.meta.json"):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        body = _body_path(str(data.get("id") or meta.stem.replace(".meta", "")))
        size = body.stat().st_size if body.exists() else 0
        items.append(
            {
                "id": data.get("id"),
                "title": data.get("title") or "sem título",
                "lang": data.get("lang") or "txt",
                "updated": data.get("updated") or 0,
                "created": data.get("created") or 0,
                "chars": data.get("chars") or size,
                "pinned": bool(data.get("pinned")),
            }
        )
    items.sort(key=lambda x: (not x.get("pinned"), -float(x.get("updated") or 0)))
    return {"ok": True, "docs": items[:limit], "count": len(items[:limit]), "root": str(_root())}


def get_doc(doc_id: str) -> dict[str, Any]:
    mid = _safe_id(doc_id)
    meta_p = _meta_path(mid)
    body_p = _body_path(mid)
    if not meta_p.exists() and not body_p.exists():
        return {"ok": False, "error": "documento não encontrado"}
    meta: dict[str, Any] = {"id": mid, "title": mid, "lang": "txt"}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    body = ""
    if body_p.exists():
        try:
            body = body_p.read_text(encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": str(e)[:160]}
    return {"ok": True, "doc": {**meta, "body": body}}


def save_doc(
    *,
    doc_id: str | None = None,
    title: str = "",
    lang: str = "txt",
    body: str = "",
    pinned: bool | None = None,
) -> dict[str, Any]:
    mid = _safe_id(doc_id or f"nb-{uuid.uuid4().hex[:10]}")
    now = time.time()
    prev = {}
    mp = _meta_path(mid)
    if mp.exists():
        try:
            prev = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
    lang = (lang or "txt").lower().strip()
    if lang not in LANGS:
        lang = "txt"
    title = (title or prev.get("title") or "sem título").strip()[:160]
    meta = {
        "id": mid,
        "title": title,
        "lang": lang,
        "created": float(prev.get("created") or now),
        "updated": now,
        "chars": len(body or ""),
        "pinned": bool(pinned) if pinned is not None else bool(prev.get("pinned")),
        "lang_label": LANGS.get(lang, lang),
    }
    _body_path(mid).write_text(body or "", encoding="utf-8")
    tmp = mp.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(mp)
    return {"ok": True, "doc": {**meta, "body": body or ""}}


def delete_doc(doc_id: str) -> dict[str, Any]:
    mid = _safe_id(doc_id)
    for p in (_meta_path(mid), _body_path(mid)):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "deleted": mid}


def ai_assist(
    *,
    mode: str,
    body: str,
    selection: str = "",
    lang: str = "txt",
    instruction: str = "",
    llm: Any | None = None,
) -> dict[str, Any]:
    """complete | generate | explain | refactor — usa LLM (+ Clone se ativo)."""
    mode = (mode or "complete").lower().strip()
    lang_l = LANGS.get((lang or "txt").lower(), lang or "texto")
    sel = (selection or "").strip()
    full = body or ""
    instr = (instruction or "").strip()

    if mode == "complete":
        focus = sel or full[-1200:]
        prompt = (
            f"Idioma/arquivo: {lang_l}.\n"
            "Continue o texto/código a partir do ponto final — só a continuação, "
            "sem explicação, sem markdown fence.\n\n"
            f"Contexto:\n{focus}\n"
        )
        if instr:
            prompt += f"\nPedido extra: {instr}\n"
    elif mode == "generate":
        prompt = (
            f"Gere {lang_l} conforme o pedido. Só o conteúdo final, sem prefácio.\n"
            f"Pedido: {instr or 'escreva um rascunho útil'}\n"
            + (f"\nSeleção atual (pode usar):\n{sel}\n" if sel else "")
            + (f"\nDocumento (trecho):\n{full[:2000]}\n" if full and not sel else "")
        )
    elif mode == "explain":
        prompt = (
            f"Explique em português, claro e curto, este trecho ({lang_l}):\n"
            f"{sel or full[:3000]}\n"
        )
    elif mode == "refactor":
        prompt = (
            f"Refatore este trecho ({lang_l}). Devolva só o código/texto novo, "
            "sem explicação.\n"
            f"{sel or full[:4000]}\n"
            + (f"\nInstrução: {instr}\n" if instr else "")
        )
    else:
        return {"ok": False, "error": f"modo inválido: {mode}"}

    text = ""
    err = None
    if llm is not None:
        try:
            from veu.llm import SYSTEM_OS
            from veu import voice_mode as veu_voice

            system = veu_voice.compose_system(
                SYSTEM_OS
                + "\nVocê é o assistente do Notebook++ do Véu. "
                "Respeite o modo pedido. Não invente cercas ```."
            )
            result = llm.complete(
                prompt,
                system=system,
                purpose="notebook",
                allow_handoff=False,
                fallback_local=True,
            )
            if result.ok and result.text:
                text = str(result.text).strip()
                # strip accidental fences
                if text.startswith("```"):
                    text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
                    text = re.sub(r"\n?```$", "", text)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:200]

    if not text:
        # fallback local mínimo
        if mode == "complete":
            text = "\n# …continuar (IA offline — tente de novo)"
        elif mode == "generate":
            text = f"# rascunho\n# {instr or 'sem pedido'}\n"
        elif mode == "explain":
            text = "IA offline — não consegui explicar agora."
        else:
            text = sel or full[:500]

    return {
        "ok": True,
        "mode": mode,
        "text": text[:12000],
        "llm_note": err,
    }

"""9.4/9.5 — pacote Véu To Go (sem segredos) para o front cifrar/gravar."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

SECRET_NAME_HINTS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    ".env",
    "credential",
    "private",
    "bearer",
)


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_secretish(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in SECRET_NAME_HINTS)


def _read_jsonl_safe(path: Path, *, limit: int = 5000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    from veu.redact import redact_obj

    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(redact_obj(json.loads(line)))
        except json.JSONDecodeError:
            continue
    return out


def pack_export(*, include_skills: bool = True) -> dict[str, Any]:
    """
    Monta arquivos lógicos (paths → conteúdo texto/bytes b64) sem .env/tokens.
    O front cifra a memória e grava via showDirectoryPicker.
    """
    root = _root()
    files: dict[str, str] = {}

    # config não secreta
    config = {
        "exported_at": time.time(),
        "veu": "to-go",
        "version": 1,
        "note": "sem segredos — tokens ficam no aparelho de origem",
    }
    files["config.json"] = json.dumps(config, ensure_ascii=False, indent=2) + "\n"

    # memória (será cifrada no front)
    memory = {
        "decisions": _read_jsonl_safe(root / "decisions.jsonl"),
        "sessions": _read_jsonl_safe(root / "sessions.jsonl"),
        "captures": _read_jsonl_safe(root / "captures.jsonl"),
        "briefings": _read_jsonl_safe(root / "briefings.jsonl", limit=200),
    }
    files["memory.json"] = json.dumps(memory, ensure_ascii=False) + "\n"

    # agentes / skills escolhidos (metadados)
    agents: dict[str, Any] = {"agents": [], "skills": []}
    try:
        from veu.runtime import Runtime

        rt = Runtime()
        snap = rt.mission() if hasattr(rt, "mission") else {}
        agents["agents"] = (snap.get("agents") or [])[:40]
        if include_skills:
            agents["skills"] = (snap.get("skills") or [])[:80]
    except Exception:  # noqa: BLE001
        agents["note"] = "runtime indisponível no pack"
    files["agents.json"] = json.dumps(agents, ensure_ascii=False, indent=2) + "\n"

    # MCP públicos (sem secrets)
    try:
        from veu.mcp import store

        pubs = []
        for s in store.list_servers():
            pubs.append(
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "transport": s.get("transport"),
                    "url": s.get("url") or "",
                    "command": s.get("command") or "",
                    "args": s.get("args") or [],
                    "env_keys": s.get("env_keys") or [],  # só nomes
                    "status": "unverified",
                }
            )
        files["mcp.json"] = json.dumps({"servers": pubs}, ensure_ascii=False, indent=2) + "\n"
    except Exception:  # noqa: BLE001
        files["mcp.json"] = '{"servers":[]}\n'

    # manifesto com SHA-256
    manifest_files: dict[str, str] = {}
    total_bytes = 0
    for rel, content in files.items():
        if _is_secretish(rel):
            continue
        raw = content.encode("utf-8")
        total_bytes += len(raw)
        manifest_files[rel] = hashlib.sha256(raw).hexdigest()

    manifest = {
        "veu_to_go": 1,
        "created_at": time.time(),
        "files": manifest_files,
        "encrypted": ["memory.json"],
        "total_bytes": total_bytes,
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    # re-hash manifest itself is listed separately after write — front recalcula

    return {
        "ok": True,
        "files": files,
        "manifest": manifest,
        "total_bytes": total_bytes,
        "secrets_excluded": True,
    }


def verify_files(files: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    """Confere SHA-256; 1 byte alterado → recusa."""
    expected = manifest.get("files") or {}
    missing: list[str] = []
    mismatch: list[str] = []
    for rel, digest in expected.items():
        if rel not in files:
            missing.append(rel)
            continue
        got = hashlib.sha256(files[rel].encode("utf-8")).hexdigest()
        if got != digest:
            mismatch.append(rel)
    ok = not missing and not mismatch
    return {
        "ok": ok,
        "missing": missing,
        "mismatch": mismatch,
        "checked": len(expected),
    }


def import_preview(files: dict[str, Any]) -> dict[str, Any]:
    """O que mudaria se aplicasse — sem gravar."""
    mem = {}
    raw = files.get("memory.json")
    if isinstance(raw, str):
        try:
            mem = json.loads(raw)
        except json.JSONDecodeError:
            mem = {}
    elif isinstance(raw, dict):
        mem = raw
    return {
        "ok": True,
        "will_add": {
            "decisions": len(mem.get("decisions") or []),
            "sessions": len(mem.get("sessions") or []),
            "captures": len(mem.get("captures") or []),
            "briefings": len(mem.get("briefings") or []),
        },
        "note": "nada aplicado até confirmação",
    }


def apply_import(files: dict[str, Any]) -> dict[str, Any]:
    """Aplica memória importada (append) — sem secrets."""
    root = _root()
    prev = import_preview(files)
    mem_raw = files.get("memory.json")
    if isinstance(mem_raw, str):
        try:
            mem = json.loads(mem_raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": "memory.json inválido"}
    elif isinstance(mem_raw, dict):
        mem = mem_raw
    else:
        return {"ok": False, "error": "sem memory.json"}

    written = 0
    for sink, name in (
        ("decisions", "decisions.jsonl"),
        ("sessions", "sessions.jsonl"),
        ("captures", "captures.jsonl"),
        ("briefings", "briefings.jsonl"),
    ):
        rows = mem.get(sink) or []
        if not rows:
            continue
        path = root / name
        with path.open("a", encoding="utf-8") as f:
            for row in rows:
                if isinstance(row, dict):
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    written += 1
    return {"ok": True, "written": written, "preview": prev.get("will_add")}

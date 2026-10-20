"""Selo de integridade SHA-256 — manifesto ao lado do artefato."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


def _data_root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def manifest_path_for(artifact: Path) -> Path:
    """manifest.json ao lado do artefato (ou pasta .veu-manifests se arquivo solto)."""
    if artifact.is_dir():
        return artifact / "manifest.json"
    sibling = artifact.parent / "manifest.json"
    return sibling


def seal_artifact(
    path: str | Path,
    *,
    job_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calcula SHA-256 e grava/atualiza manifest.json ao lado."""
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    digest = sha256_file(p)
    entry = {
        "nome": p.name,
        "path": str(p),
        "tamanho": p.stat().st_size,
        "sha256": digest,
        "job_id": job_id or "",
        "ts": time.time(),
    }
    if extra:
        entry.update(extra)

    man_path = manifest_path_for(p)
    manifest: dict[str, Any] = {"version": 1, "artifacts": []}
    if man_path.exists():
        try:
            manifest = json.loads(man_path.read_text(encoding="utf-8"))
            if not isinstance(manifest.get("artifacts"), list):
                manifest["artifacts"] = []
        except (OSError, json.JSONDecodeError):
            manifest = {"version": 1, "artifacts": []}

    arts: list[dict[str, Any]] = list(manifest.get("artifacts") or [])
    arts = [a for a in arts if a.get("nome") != p.name and a.get("path") != str(p)]
    arts.append(entry)
    manifest["artifacts"] = arts
    manifest["updated"] = time.time()
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "entry": entry, "manifest": str(man_path)}


def verify(path: str) -> dict[str, Any]:
    """Recalcula e compara. Devolve ok | alterado | ausente."""
    raw = (path or "").strip()
    if not raw:
        return {"ok": False, "status": "ausente", "error": "path vazio"}

    p = Path(raw)
    if not p.is_absolute():
        # relativo à data root / studio
        cand = _data_root() / raw
        if not cand.exists():
            cand = _data_root() / "studio" / "out" / raw
        p = cand

    if not p.exists() or not p.is_file():
        return {"ok": False, "status": "ausente", "path": str(p)}

    man_path = manifest_path_for(p)
    if not man_path.exists():
        return {
            "ok": False,
            "status": "ausente",
            "path": str(p),
            "reason": "sem manifest.json",
        }

    try:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "status": "ausente", "path": str(p), "reason": "manifest inválido"}

    entry = None
    for a in manifest.get("artifacts") or []:
        if a.get("path") == str(p.resolve()) or a.get("nome") == p.name:
            entry = a
            break
    if not entry:
        return {"ok": False, "status": "ausente", "path": str(p), "reason": "não listado no manifest"}

    current = sha256_file(p)
    expected = str(entry.get("sha256") or "")
    if current == expected:
        return {
            "ok": True,
            "status": "ok",
            "path": str(p),
            "sha256": current,
            "tamanho": p.stat().st_size,
            "selo": "íntegro",
        }
    return {
        "ok": False,
        "status": "alterado",
        "path": str(p),
        "sha256": current,
        "expected": expected,
        "tamanho": p.stat().st_size,
        "selo": "alterado",
    }


def status_for_paths(paths: list[str]) -> list[dict[str, Any]]:
    return [verify(p) for p in paths]

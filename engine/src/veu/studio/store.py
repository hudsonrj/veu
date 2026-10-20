"""Persistência de assets e jobs do Studio."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def _root() -> Path:
    base = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root = base / "studio"
    root.mkdir(parents=True, exist_ok=True)
    (root / "files").mkdir(exist_ok=True)
    (root / "out").mkdir(exist_ok=True)
    return root


def files_dir() -> Path:
    return _root() / "files"


def out_dir() -> Path:
    return _root() / "out"


def _jobs_path() -> Path:
    return _root() / "jobs.jsonl"


def save_upload(
    *,
    filename: str,
    data: bytes,
    content_type: str = "",
) -> dict[str, Any]:
    aid = f"ast-{uuid.uuid4().hex[:12]}"
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:120] or "file"
    path = files_dir() / f"{aid}_{safe}"
    path.write_bytes(data)
    kind = classify(filename, content_type)
    meta = {
        "id": aid,
        "filename": filename,
        "path": str(path),
        "bytes": len(data),
        "content_type": content_type or "",
        "kind": kind,
        "ts": time.time(),
    }
    index = _root() / "assets.jsonl"
    with index.open("a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    try:
        from veu.integrity import seal_artifact

        seal = seal_artifact(path, job_id=aid)
        meta["sha256"] = (seal.get("entry") or {}).get("sha256")
        meta["integrity"] = "íntegro"
    except Exception:  # noqa: BLE001
        pass
    return meta


def classify(filename: str, content_type: str = "") -> str:
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if any(name.endswith(x) for x in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")) or ct.startswith(
        "image/"
    ):
        return "image"
    if any(name.endswith(x) for x in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm")) or ct.startswith(
        "audio/"
    ):
        return "audio"
    if name.endswith(".pdf") or "pdf" in ct:
        return "pdf"
    if any(name.endswith(x) for x in (".xlsx", ".xls", ".csv", ".tsv")) or "spreadsheet" in ct or "csv" in ct:
        return "sheet"
    if any(name.endswith(x) for x in (".doc", ".docx", ".odt", ".rtf")):
        return "doc"
    if any(name.endswith(x) for x in (".ppt", ".pptx", ".odp")):
        return "slides"
    if any(name.endswith(x) for x in (".md", ".txt", ".json", ".yaml", ".yml", ".html")):
        return "text"
    return "binary"


def list_assets(limit: int = 40) -> list[dict[str, Any]]:
    path = _root() / "assets.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))


def get_asset(asset_id: str) -> dict[str, Any] | None:
    for a in list_assets(200):
        if a.get("id") == asset_id:
            return a
    return None


def append_job(job: dict[str, Any]) -> None:
    with _jobs_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(job, ensure_ascii=False) + "\n")


def list_jobs(limit: int = 30) -> list[dict[str, Any]]:
    path = _jobs_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))

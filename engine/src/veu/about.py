"""9.6 — GET /about: versão verificável do Véu."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    # engine/src/veu/about.py → repo
    return Path(__file__).resolve().parents[3]


def _git_commit() -> str:
    env = (os.environ.get("VEU_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "").strip()
    if env:
        return env[:40]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_repo_root()),
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return out.decode().strip()[:40]
    except Exception:  # noqa: BLE001
        return "unknown"


def _build_date() -> str:
    return (os.environ.get("VEU_BUILD_DATE") or "").strip() or "unknown"


def _front_bundle_sha() -> str | None:
    """SHA-256 do bundle JS principal em desktop/dist, se existir."""
    dist = _repo_root() / "desktop" / "dist" / "assets"
    if not dist.is_dir():
        env = (os.environ.get("VEU_FRONT_BUNDLE_SHA256") or "").strip()
        return env or None
    candidates = sorted(dist.glob("index-*.js"))
    if not candidates:
        candidates = sorted(dist.glob("*.js"))
    if not candidates:
        return None
    h = hashlib.sha256()
    h.update(candidates[0].read_bytes())
    return h.hexdigest()


def _ecc_version() -> str:
    env = (os.environ.get("VEU_ECC_VERSION") or "").strip()
    if env:
        return env
    # procura pin em CONTINUIDADE / env / pasta ecc
    ecc_dir = _repo_root() / "desktop" / "public" / "ruflo"
    if ecc_dir.is_dir():
        return "vendored"
    return "unknown"


def about() -> dict[str, Any]:
    from veu import __version__

    return {
        "ok": True,
        "name": "Véu",
        "version": __version__,
        "commit": _git_commit(),
        "build_date": _build_date(),
        "front_bundle_sha256": _front_bundle_sha(),
        "ecc_version": _ecc_version(),
        "kernel": "fastapi",
    }

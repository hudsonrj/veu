"""9.6 — checagem de atualização opt-in com manifesto ed25519."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _prev_path() -> Path:
    return _root() / "previous_version.json"


def _pubkey_bytes() -> bytes | None:
    raw = (os.environ.get("VEU_UPDATE_PUBLIC_KEY") or "").strip()
    if not raw:
        return None
    # aceita hex ou base64
    try:
        if all(c in "0123456789abcdefABCDEF" for c in raw) and len(raw) in {64}:
            return bytes.fromhex(raw)
        pad = "=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(raw + pad)
    except Exception:  # noqa: BLE001
        try:
            return base64.b64decode(raw)
        except Exception:  # noqa: BLE001
            return None


def canonical_manifest(manifest: dict[str, Any]) -> bytes:
    """Bytes assinados: JSON canônico sem o campo signature."""
    body = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def verify_manifest_signature(manifest: dict[str, Any], *, public_key: bytes | None = None) -> bool:
    """Valida assinatura ed25519 do manifesto. Sem chave pública → False."""
    pub = public_key if public_key is not None else _pubkey_bytes()
    if not pub:
        return False
    sig_b64 = str(manifest.get("signature") or "").strip()
    if not sig_b64:
        return False
    try:
        pad = "=" * (-len(sig_b64) % 4)
        sig = base64.urlsafe_b64decode(sig_b64 + pad)
    except Exception:  # noqa: BLE001
        try:
            sig = base64.b64decode(sig_b64)
        except Exception:  # noqa: BLE001
            return False
    msg = canonical_manifest(manifest)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature

        key = Ed25519PublicKey.from_public_bytes(pub)
        key.verify(sig, msg)
        return True
    except Exception:  # noqa: BLE001 — InvalidSignature ou key inválida
        return False


def save_previous(version_info: dict[str, Any]) -> None:
    path = _prev_path()
    payload = {
        "saved_at": time.time(),
        "version": version_info.get("version"),
        "commit": version_info.get("commit"),
        "front_bundle_sha256": version_info.get("front_bundle_sha256"),
        "build_date": version_info.get("build_date"),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def previous_version() -> dict[str, Any] | None:
    path = _prev_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def check_update(
    *,
    manifest: dict[str, Any] | None = None,
    manifest_url: str | None = None,
    enabled: bool = False,
) -> dict[str, Any]:
    """
    Opt-in: se enabled=False, não consulta rede.
    Só envia a versão atual (além do que o HTTP já exige).
    """
    from veu import about as veu_about

    current = veu_about.about()
    if not enabled:
        return {
            "ok": True,
            "checked": False,
            "reason": "checagem desligada (opt-in)",
            "current": {
                "version": current.get("version"),
                "commit": current.get("commit"),
            },
            "update": None,
            "previous": previous_version(),
        }

    remote = manifest
    if remote is None:
        url = (manifest_url or os.environ.get("VEU_UPDATE_MANIFEST_URL") or "").strip()
        if not url:
            return {
                "ok": False,
                "checked": False,
                "error": "sem manifesto nem VEU_UPDATE_MANIFEST_URL",
                "current": {"version": current.get("version")},
            }
        try:
            import httpx

            # mínimo: só versão na query
            r = httpx.get(
                url,
                params={"v": str(current.get("version") or "")},
                timeout=12.0,
            )
            if r.status_code >= 400:
                return {
                    "ok": False,
                    "checked": True,
                    "error": f"HTTP {r.status_code}",
                    "current": {"version": current.get("version")},
                }
            remote = r.json()
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "checked": True,
                "error": str(exc)[:300],
                "current": {"version": current.get("version")},
            }

    if not isinstance(remote, dict):
        return {"ok": False, "checked": True, "error": "manifesto inválido"}

    if not verify_manifest_signature(remote):
        return {
            "ok": False,
            "checked": True,
            "error": "assinatura inválida — manifesto rejeitado",
            "current": {"version": current.get("version")},
            "update": None,
        }

    remote_ver = str(remote.get("version") or "")
    cur_ver = str(current.get("version") or "")
    newer = remote_ver != cur_ver and bool(remote_ver)
    # guarda versão atual como "anterior" antes de sugerir update
    if newer:
        save_previous(current)

    return {
        "ok": True,
        "checked": True,
        "signature_valid": True,
        "current": {
            "version": cur_ver,
            "commit": current.get("commit"),
        },
        "update": {
            "available": newer,
            "version": remote_ver,
            "commit": remote.get("commit"),
            "notes": remote.get("notes") or "",
            "url": remote.get("url") or "",
            "sha256": remote.get("sha256") or remote.get("front_bundle_sha256") or "",
        }
        if newer
        else None,
        "previous": previous_version(),
    }


def sign_manifest_for_tests(manifest: dict[str, Any], private_key_bytes: bytes) -> dict[str, Any]:
    """Helper de teste: assina e devolve cópia com signature."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    body = {k: v for k, v in manifest.items() if k != "signature"}
    msg = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    sig = key.sign(msg)
    out = dict(body)
    out["signature"] = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return out


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

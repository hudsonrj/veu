"""Web Push (PWA) — VAPID + subscriptions + envio em eventos do bus."""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _subs_path() -> Path:
    return _root() / "push_subscriptions.json"


def _load_subs() -> list[dict[str, Any]]:
    path = _subs_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("subscriptions") or [])
    except (OSError, json.JSONDecodeError):
        return []


def _save_subs(subs: list[dict[str, Any]]) -> None:
    path = _subs_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"subscriptions": subs[-40:], "updated": time.time()}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def ensure_vapid() -> dict[str, str]:
    """Garante par VAPID no .env (gera se faltar)."""
    pub = (os.environ.get("VEU_VAPID_PUBLIC") or "").strip()
    priv = (os.environ.get("VEU_VAPID_PRIVATE") or "").strip()
    subject = (os.environ.get("VEU_VAPID_SUBJECT") or "mailto:hudsonrj@gmail.com").strip()
    if pub and priv:
        return {"publicKey": pub, "privateKey": priv, "subject": subject}

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:
        raise RuntimeError("cryptography necessário pra gerar VAPID") from exc

    key = ec.generate_private_key(ec.SECP256R1())
    priv_bytes = key.private_numbers().private_value.to_bytes(32, "big")
    pub_point = key.public_key().public_numbers()
    # uncompressed point 0x04 || x || y → urlsafe b64 without padding (applicationServerKey)
    x = pub_point.x.to_bytes(32, "big")
    y = pub_point.y.to_bytes(32, "big")
    pub_raw = b"\x04" + x + y
    pub_b64 = base64.urlsafe_b64encode(pub_raw).decode().rstrip("=")
    # private as urlsafe b64 of 32 bytes (compatible with pywebpush vapid_private_key)
    priv_b64 = base64.urlsafe_b64encode(priv_bytes).decode().rstrip("=")

    # also store PEM for pywebpush which often wants PEM
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    from veu.subscriptions import resolve_env_file, upsert_env

    upsert_env(
        resolve_env_file(),
        {
            "VEU_VAPID_PUBLIC": pub_b64,
            "VEU_VAPID_PRIVATE": priv_b64,
            "VEU_VAPID_PRIVATE_PEM": pem.replace("\n", "\\n"),
            "VEU_VAPID_SUBJECT": subject,
        },
    )
    os.environ["VEU_VAPID_PUBLIC"] = pub_b64
    os.environ["VEU_VAPID_PRIVATE"] = priv_b64
    os.environ["VEU_VAPID_PRIVATE_PEM"] = pem
    os.environ["VEU_VAPID_SUBJECT"] = subject
    return {"publicKey": pub_b64, "privateKey": priv_b64, "subject": subject}


def public_key() -> str:
    return ensure_vapid()["publicKey"]


def subscribe(subscription: dict[str, Any]) -> dict[str, Any]:
    endpoint = str((subscription or {}).get("endpoint") or "").strip()
    keys = (subscription or {}).get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return {"ok": False, "error": "subscription incompleta"}
    subs = _load_subs()
    subs = [s for s in subs if s.get("endpoint") != endpoint]
    row = {
        "endpoint": endpoint,
        "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]},
        "created": time.time(),
        "ua": str((subscription or {}).get("ua") or "")[:120],
    }
    subs.append(row)
    _save_subs(subs)
    return {"ok": True, "count": len(subs)}


def unsubscribe(endpoint: str) -> dict[str, Any]:
    ep = (endpoint or "").strip()
    subs = [s for s in _load_subs() if s.get("endpoint") != ep]
    _save_subs(subs)
    return {"ok": True, "count": len(subs)}


def notify(title: str, body: str, *, url: str = "/", tag: str = "veu") -> dict[str, Any]:
    """Envia push pra todas as subscriptions. Falhas individuais não derrubam."""
    vapid = ensure_vapid()
    pem = (os.environ.get("VEU_VAPID_PRIVATE_PEM") or "").replace("\\n", "\n").strip()
    if not pem:
        # rebuild PEM from raw private if possible — pywebpush prefers PEM
        pem = vapid["privateKey"]

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return {"ok": False, "error": "pywebpush não instalado", "sent": 0}

    payload = json.dumps(
        {"title": title[:80], "body": body[:180], "url": url, "tag": tag},
        ensure_ascii=False,
    )
    sent = 0
    errors: list[str] = []
    keep: list[dict[str, Any]] = []
    for sub in _load_subs():
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": sub["keys"],
                },
                data=payload,
                vapid_private_key=pem,
                vapid_claims={"sub": vapid["subject"]},
            )
            sent += 1
            keep.append(sub)
        except WebPushException as exc:  # type: ignore[name-defined]
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                continue  # gone
            errors.append(str(exc)[:120])
            keep.append(sub)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc)[:120])
            keep.append(sub)
    _save_subs(keep)
    return {"ok": sent > 0 or not errors, "sent": sent, "errors": errors[:5], "remaining": len(keep)}


def notify_event(kind: str, detail: dict[str, Any] | None = None) -> None:
    """Hook leve pra bus — não levanta."""
    detail = detail or {}
    try:
        if kind == "approval":
            notify(
                "Aprovação no Véu",
                "Há uma ação pedindo o seu ok",
                url="/?app=approvals",
                tag="approval",
            )
        elif kind == "inbox":
            notify(
                "Inbox Véu",
                "Rascunho ou mensagem nova na fila",
                url="/?app=inbox",
                tag="inbox",
            )
        elif kind == "job" and detail.get("status") in {"failed", "done"}:
            notify(
                "Job Véu",
                f"Job {detail.get('status')}",
                url="/?app=mission",
                tag="job",
            )
    except Exception:  # noqa: BLE001
        pass

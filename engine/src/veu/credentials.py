"""Cofre de health de credenciais — status por conta + alerta único via WhatsApp."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from veu.bus import bus

# idade-limite default (horas) antes de stale
DEFAULT_LIMIT_H = {
    "outlook": 24,
    "teams": 24,
    "gmail": 48,
    "google": 48,
    "allied": 12,
    "vale": 24,
    "hatkg": 24,
    "notion": 168,
    "whatsapp": 72,
}


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state_path() -> Path:
    return _root() / "credentials_health.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"accounts": {}, "alerts_sent": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"accounts": {}, "alerts_sent": {}}


def _save_state(data: dict[str, Any]) -> None:
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _limit_h(account_id: str, provider: str) -> float:
    key = (account_id or provider or "").lower()
    for k, v in DEFAULT_LIMIT_H.items():
        if k in key:
            return float(v)
    env = os.environ.get("VEU_CRED_STALE_HOURS")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return 48.0


def _status_for(*, age_h: float | None, needs_login: bool, limit_h: float) -> str:
    if needs_login:
        return "needs_login"
    if age_h is None:
        return "ok"
    if age_h >= limit_h:
        return "stale"
    if age_h >= limit_h * 0.75:
        return "expiring"
    return "ok"


def refresh_from_live() -> dict[str, Any]:
    """Recalcula health a partir do live.json / sideboard."""
    state = _load_state()
    accounts: dict[str, Any] = dict(state.get("accounts") or {})
    now = time.time()

    needs: list[str] = []
    try:
        from veu.bridges import control_live

        raw = control_live.load_raw() or {}
        needs = list(raw.get("needs_login") or [])
        # tokens / ages se existirem
        tokens = raw.get("tokens") or raw.get("accounts") or {}
        if isinstance(tokens, dict):
            for key, meta in tokens.items():
                if not isinstance(meta, dict):
                    continue
                age_h = meta.get("age_h")
                if age_h is None and meta.get("last_ok"):
                    try:
                        age_h = (now - float(meta["last_ok"])) / 3600.0
                    except (TypeError, ValueError):
                        age_h = None
                aid = str(key)
                provider = str(meta.get("provider") or aid).lower()
                limit = _limit_h(aid, provider)
                needs_login = bool(meta.get("needs_login") or meta.get("needsAuth"))
                st = _status_for(age_h=float(age_h) if age_h is not None else None, needs_login=needs_login, limit_h=limit)
                accounts[aid] = {
                    "id": aid,
                    "provider": provider,
                    "status": st,
                    "last_ok": meta.get("last_ok"),
                    "age_h": round(float(age_h), 2) if age_h is not None else None,
                    "limit_h": limit,
                    "relogin_url": meta.get("relogin_url") or meta.get("login_url") or "",
                    "updated_at": now,
                }
    except Exception:  # noqa: BLE001
        raw = {}

    # needs_login strings → contas sintéticas
    for i, line in enumerate(needs[:12]):
        text = str(line)
        low = text.lower()
        aid = None
        for hint in ("allied", "vale", "hatkg", "cpqd", "outlook", "teams", "gmail"):
            if hint in low:
                aid = hint
                break
        aid = aid or f"needs-{i}"
        prev = accounts.get(aid) or {}
        age_h = prev.get("age_h")
        # Allied ~369h no review — se só aparece em needs_login, marca needs_login
        accounts[aid] = {
            "id": aid,
            "provider": aid,
            "status": "needs_login",
            "last_ok": prev.get("last_ok"),
            "age_h": age_h,
            "limit_h": _limit_h(aid, aid),
            "relogin_url": prev.get("relogin_url") or "",
            "note": text[:160],
            "updated_at": now,
        }

    # freshness do live.json
    freshness = {"path": None, "age_h": None, "status": "unknown"}
    try:
        from veu.bridges import control_live

        raw = control_live.load_raw() or {}
        mtime = raw.get("_mtime")
        path = raw.get("_path")
        if mtime:
            age_h = (now - float(mtime)) / 3600.0
            freshness = {
                "path": path,
                "age_h": round(age_h, 2),
                "status": "ok" if age_h < 2 else ("expiring" if age_h < 6 else "stale"),
            }
    except Exception:  # noqa: BLE001
        pass

    alerts_sent = dict(state.get("alerts_sent") or {})
    new_alerts: list[dict[str, Any]] = []
    for aid, acc in accounts.items():
        st = acc.get("status")
        if st not in {"needs_login", "stale", "expiring"}:
            # reset alert latch when healthy
            alerts_sent.pop(aid, None)
            continue
        # um alerta por ciclo de problema
        latch = alerts_sent.get(aid)
        if latch and latch.get("status") == st:
            continue
        alert = {
            "account": aid,
            "status": st,
            "age_h": acc.get("age_h"),
            "note": acc.get("note") or "",
            "relogin_url": acc.get("relogin_url") or "",
            "ts": now,
        }
        new_alerts.append(alert)
        alerts_sent[aid] = {"status": st, "ts": now}
        _notify_whatsapp(alert)

    state = {"accounts": accounts, "alerts_sent": alerts_sent, "freshness": freshness, "updated_at": now}
    _save_state(state)
    bus.publish_sync(
        "credentials",
        {"counts": _counts(accounts), "alerts": len(new_alerts)},
        full=board(),
    )
    return board()


def _counts(accounts: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in accounts.values():
        s = str(a.get("status") or "ok")
        out[s] = out.get(s, 0) + 1
    return out


def _notify_whatsapp(alert: dict[str, Any]) -> None:
    """Tenta avisar via bridge WhatsApp / host — best-effort, sem senha."""
    age = alert.get("age_h")
    age_bit = f" · {age}h" if age is not None else ""
    msg = (
        f"Véu · credencial {alert.get('account')} → {alert.get('status')}{age_bit}. "
        "Re-logue no painel Credenciais."
    )
    # registro em memória/audit; envio real depende do host/bridge
    try:
        from veu.runtime import Runtime  # lazy — pode ser pesado; preferir memory direto

        pass
    except Exception:  # noqa: BLE001
        pass
    try:
        path = _root() / "credential_alerts.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"msg": msg, **alert}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # webhook opcional
    url = (os.environ.get("VEU_WHATSAPP_ALERT_WEBHOOK") or "").strip()
    if url:
        try:
            import httpx

            httpx.post(url, json={"text": msg}, timeout=8.0)
        except Exception:  # noqa: BLE001
            pass


def board() -> dict[str, Any]:
    state = _load_state()
    accounts = list((state.get("accounts") or {}).values())
    accounts.sort(key=lambda a: (0 if a.get("status") != "ok" else 1, str(a.get("id"))))
    return {
        "ok": True,
        "accounts": accounts,
        "counts": _counts(state.get("accounts") or {}),
        "freshness": state.get("freshness") or {},
        "updated_at": state.get("updated_at"),
    }


def mark_relogin_ok(account_id: str) -> dict[str, Any]:
    state = _load_state()
    acc = (state.get("accounts") or {}).get(account_id)
    if not acc:
        return {"ok": False, "error": "conta não encontrada"}
    acc["status"] = "ok"
    acc["last_ok"] = time.time()
    acc["age_h"] = 0
    acc["updated_at"] = time.time()
    state["accounts"][account_id] = acc
    (state.get("alerts_sent") or {}).pop(account_id, None)
    _save_state(state)
    bus.publish_sync("credentials", {"id": account_id, "status": "ok"}, full=board())
    return {"ok": True, "account": acc}

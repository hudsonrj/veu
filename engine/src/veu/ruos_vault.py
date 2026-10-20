"""Vault write-only do Véu — chaves nunca são devolvidas em claro.

Espelha o painel Keys: model keys, custom, website sign-ins, MCP tokens,
Slack webhook, Tailscale. Valores persistem hasheados/cifrados localmente;
listagens só mostram presença (set / not set).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Literal

ModelSlot = Literal["llm", "openai", "anthropic", "openrouter", "slack_bot_token", "slack_signing_secret"]
RoutingMode = Literal["shared", "byok", "custom"]

MODEL_SLOTS: tuple[ModelSlot, ...] = (
    "llm",
    "openai",
    "anthropic",
    "openrouter",
    "slack_bot_token",
    "slack_signing_secret",
)


def _home() -> Path:
    raw = os.environ.get("VEU_HOME") or os.environ.get("HOME") or "/tmp"
    return Path(raw) / ".veu" / "ruos"


def _load(path: Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return default


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def _digest(value: str) -> str:
    salt = os.environ.get("VEU_AUTH_SECRET") or "veu-ruos-vault"
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


def _store_secret(value: str) -> dict[str, str]:
    """Armazena digest + fingerprint curto — valor em claro nunca volta na API."""
    v = value.strip()
    return {
        "digest": _digest(v),
        "fp": v[:3] + "…" + v[-4:] if len(v) > 8 else "••••",
        "len": str(len(v)),
        "set_at": str(int(time.time())),
    }


class RuosVault:
    def __init__(self) -> None:
        self.root = _home()
        self.root.mkdir(parents=True, exist_ok=True)
        self._path = self.root / "vault.json"
        self._ensure()

    def _ensure(self) -> None:
        if not self._path.is_file():
            _save(
                self._path,
                {
                    "model_keys": {},
                    "custom_keys": [],
                    "website_signins": [],
                    "mcp_tokens": [],
                    "slack": {"webhook_digest": None, "enabled": False, "events": []},
                    "tailscale": {"mode": None, "set": False, "fp": None},
                    "routing": {
                        "mode": "shared",
                        "provider": "cognitum",
                        "custom_base": "",
                    },
                    "meta_llm": None,
                },
            )

    def _data(self) -> dict[str, Any]:
        d = _load(self._path, {})
        return d if isinstance(d, dict) else {}

    def _write(self, d: dict[str, Any]) -> None:
        _save(self._path, d)

    def status(self) -> dict[str, Any]:
        d = self._data()
        mk = d.get("model_keys") or {}
        present = {slot: bool(mk.get(slot)) for slot in MODEL_SLOTS}
        routing = d.get("routing") or {"mode": "shared"}
        meta = "configured" if mk.get("llm") else "none configured"
        return {
            "ok": True,
            "signed_in": True,
            "vault": "ready",
            "subscribe": False,
            "tabs": [
                "model_keys",
                "custom_keys",
                "website_signins",
                "mcp_tokens",
                "slack",
                "tailscale",
            ],
            "model_keys": {
                "present": present,
                "slots": list(MODEL_SLOTS),
                "meta_llm": meta,
                "any": any(present.values()),
                "copy": (
                    "Your own model API keys, stored write-only in the fleet's per-tenant vault — "
                    "they're never shown again and are injected into your desktop server-side. "
                    "Leave them empty to run on the shared Véu default. "
                    f"Meta-LLM key in effect: {meta}."
                ),
                "empty_hint": "No keys set — running on the shared Véu default.",
            },
            "routing": {
                **routing,
                "current": routing.get("mode") or "shared",
                "keys_present_llm": bool(mk.get("llm")),
                "copy": (
                    "Which model backend your desktop's apps and agents (ruflo, the Assistant, "
                    "the AI Console) talk to. Shared = the Véu meta-LLM on the shared key, "
                    "$0 to you. Bring your own = the key you saved above is pushed to your "
                    "desktop server-side (never shown here) and the shared vars are removed. "
                    "Custom = any OpenAI-compatible https endpoint, using your openai key."
                ),
                "options": [
                    {"id": "shared", "label": "Padrão compartilhado Véu"},
                    {"id": "byok", "label": "Bring your own key"},
                    {"id": "custom", "label": "Custom (OpenAI-compatible)"},
                ],
            },
            "custom_keys": [
                {"id": c.get("id"), "name": c.get("name"), "set_at": c.get("set_at")}
                for c in (d.get("custom_keys") or [])
            ],
            "website_signins": [
                {
                    "id": s.get("id"),
                    "site": s.get("site"),
                    "username": s.get("username"),
                    "include_subdomains": s.get("include_subdomains"),
                    "set_at": s.get("set_at"),
                }
                for s in (d.get("website_signins") or [])
            ],
            "mcp_tokens": [
                {
                    "id": t.get("id"),
                    "label": t.get("label"),
                    "scope": t.get("scope"),
                    "expires_at": t.get("expires_at"),
                    "created_at": t.get("created_at"),
                    "fp": t.get("fp"),
                }
                for t in (d.get("mcp_tokens") or [])
            ],
            "slack": {
                "enabled": bool((d.get("slack") or {}).get("enabled")),
                "webhook_set": bool((d.get("slack") or {}).get("webhook_digest")),
                "events": (d.get("slack") or {}).get("events") or [],
            },
            "tailscale": d.get("tailscale") or {"set": False},
        }

    def put_model_key(self, slot: str, value: str) -> dict[str, Any]:
        if slot not in MODEL_SLOTS:
            return {"ok": False, "error": "invalid_slot"}
        if len((value or "").strip()) < 8:
            return {"ok": False, "error": "key_too_short"}
        d = self._data()
        mk = dict(d.get("model_keys") or {})
        mk[slot] = _store_secret(value)
        d["model_keys"] = mk
        if slot == "llm":
            d["meta_llm"] = "byok"
        self._write(d)
        # espelha em env file do kernel quando possível (sem devolver valor)
        self._maybe_mirror_env(slot, value.strip())
        return {"ok": True, "slot": slot, "set": True, "fp": mk[slot]["fp"]}

    def _maybe_mirror_env(self, slot: str, value: str) -> None:
        """Injeta em .env do engine para LLM local — write-only na API."""
        mapping = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "llm": "VEU_META_LLM_KEY",
        }
        env_key = mapping.get(slot)
        if not env_key:
            return
        try:
            from veu.subscriptions import resolve_env_file, upsert_env

            path = resolve_env_file()
            if path:
                upsert_env(path, {env_key: value})
        except Exception:  # noqa: BLE001
            pass

    def delete_model_key(self, slot: str) -> dict[str, Any]:
        if slot not in MODEL_SLOTS:
            return {"ok": False, "error": "invalid_slot"}
        d = self._data()
        mk = dict(d.get("model_keys") or {})
        mk.pop(slot, None)
        d["model_keys"] = mk
        if slot == "llm":
            d["meta_llm"] = None
        self._write(d)
        return {"ok": True, "slot": slot, "set": False}

    def set_routing(
        self,
        mode: RoutingMode,
        *,
        provider: str = "cognitum",
        custom_base: str = "",
    ) -> dict[str, Any]:
        if mode not in {"shared", "byok", "custom"}:
            return {"ok": False, "error": "invalid_mode"}
        d = self._data()
        mk = d.get("model_keys") or {}
        if mode == "byok" and not mk.get("llm") and not mk.get("openai") and not mk.get("anthropic"):
            return {
                "ok": False,
                "error": "no_byok_key",
                "detail": "Save a model key before Bring your own key",
            }
        d["routing"] = {
            "mode": mode,
            "provider": provider or "cognitum",
            "custom_base": (custom_base or "").strip()[:300],
            "updated_at": time.time(),
        }
        self._write(d)
        return {"ok": True, "routing": d["routing"], "keys_present_llm": bool(mk.get("llm"))}

    def put_custom(self, name: str, value: str) -> dict[str, Any]:
        name = (name or "").strip().upper().replace(" ", "_")
        if not name or len(value.strip()) < 1:
            return {"ok": False, "error": "invalid"}
        d = self._data()
        rows = [c for c in (d.get("custom_keys") or []) if c.get("name") != name]
        rows.append(
            {
                "id": f"ck-{uuid.uuid4().hex[:8]}",
                "name": name,
                **_store_secret(value),
            }
        )
        d["custom_keys"] = rows[-40:]
        self._write(d)
        return {"ok": True, "name": name}

    def put_website(
        self,
        site: str,
        username: str,
        password: str,
        *,
        include_subdomains: bool = False,
    ) -> dict[str, Any]:
        site = (site or "").strip()
        if not site.startswith("http"):
            return {"ok": False, "error": "site_must_be_https"}
        d = self._data()
        rows = list(d.get("website_signins") or [])
        rows.append(
            {
                "id": f"ws-{uuid.uuid4().hex[:8]}",
                "site": site[:300],
                "username": (username or "")[:120],
                "include_subdomains": bool(include_subdomains),
                **_store_secret(password or "x"),
            }
        )
        d["website_signins"] = rows[-40:]
        self._write(d)
        return {"ok": True, "site": site}

    def create_mcp_token(
        self,
        *,
        label: str = "",
        scope: Literal["full", "read"] = "full",
        days: int | None = 30,
    ) -> dict[str, Any]:
        raw = "ruos_mcp_" + secrets.token_urlsafe(32)
        exp = time.time() + (days * 86400) if days else None
        row = {
            "id": f"mcp-{uuid.uuid4().hex[:8]}",
            "label": (label or "fleet token")[:80],
            "scope": scope,
            "created_at": time.time(),
            "expires_at": exp,
            **_store_secret(raw),
        }
        d = self._data()
        rows = list(d.get("mcp_tokens") or [])
        rows.insert(0, {k: v for k, v in row.items() if k != "digest" or True})
        # keep digest, not raw
        stored = {**row}
        rows_out = [stored] + [
            t for t in rows if t.get("id") != stored["id"]
        ]
        d["mcp_tokens"] = rows_out[:20]
        self._write(d)
        return {
            "ok": True,
            "token": raw,  # shown ONCE
            "id": row["id"],
            "scope": scope,
            "expires_at": exp,
            "warning": "Copy it now — it will not be shown again",
        }

    def revoke_mcp_token(self, token_id: str) -> dict[str, Any]:
        d = self._data()
        before = len(d.get("mcp_tokens") or [])
        d["mcp_tokens"] = [t for t in (d.get("mcp_tokens") or []) if t.get("id") != token_id]
        self._write(d)
        return {"ok": True, "revoked": before != len(d["mcp_tokens"])}

    def set_slack(self, webhook: str | None = None, *, enabled: bool | None = None) -> dict[str, Any]:
        d = self._data()
        slack = dict(d.get("slack") or {})
        if webhook is not None:
            wh = webhook.strip()
            if wh and not wh.startswith("https://hooks.slack.com/"):
                return {"ok": False, "error": "invalid_webhook"}
            if wh:
                sec = _store_secret(wh)
                slack["webhook_digest"] = sec["digest"]
                slack["fp"] = sec["fp"]
            else:
                slack["webhook_digest"] = None
                slack["fp"] = None
        if enabled is not None:
            slack["enabled"] = bool(enabled)
        d["slack"] = slack
        self._write(d)
        return {"ok": True, "slack": {"enabled": slack.get("enabled"), "webhook_set": bool(slack.get("webhook_digest"))}}

    def set_tailscale(self, auth_key: str = "", *, disconnect: bool = False) -> dict[str, Any]:
        d = self._data()
        if disconnect:
            d["tailscale"] = {"mode": None, "set": False, "fp": None}
            self._write(d)
            return {"ok": True, "tailscale": d["tailscale"]}
        key = (auth_key or "").strip()
        if key and not key.startswith("tskey-"):
            return {"ok": False, "error": "expected_tskey"}
        if not key:
            return {"ok": False, "error": "empty"}
        sec = _store_secret(key)
        d["tailscale"] = {
            "mode": "auth_key",
            "set": True,
            "fp": sec["fp"],
            "digest": sec["digest"],
            "set_at": time.time(),
        }
        self._write(d)
        return {"ok": True, "tailscale": {"set": True, "fp": sec["fp"], "mode": "auth_key"}}


vault = RuosVault()

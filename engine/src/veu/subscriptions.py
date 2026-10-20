"""Assinaturas de modelos — OpenAI · Claude · Grok (xAI).

Dois caminhos por provedor:
  - api_key      → OPENAI_API_KEY / ANTHROPIC_API_KEY / XAI_API_KEY
  - subscription → conta logada (ChatGPT Plus, Claude Pro, Grok)
                   via login no browser + confirmação no Véu
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Literal

ProviderId = Literal["openai", "claude", "xai"]
AuthMode = Literal["api_key", "subscription", "both"]

# login_url = página de autenticação da assinatura (NUNCA a home do chat)
# chat_url  = onde o compose/handoff cola o prompt depois que a conta está ligada
PROVIDERS: dict[ProviderId, dict[str, str]] = {
    "openai": {
        "name": "OpenAI",
        "product": "ChatGPT",
        "key_env": "OPENAI_API_KEY",
        "model_env": "VEU_OPENAI_MODEL",
        "mode_env": "VEU_OPENAI_AUTH_MODE",
        "sub_env": "VEU_OPENAI_SUB_STATUS",
        "sub_ts_env": "VEU_OPENAI_SUB_TS",
        "default_model": "gpt-5.4-nano",
        "chat_url": "https://chatgpt.com/",
        "login_url": "https://chatgpt.com/auth/login",
        "hint_key": "platform.openai.com → API keys",
        "hint_sub": "ChatGPT Plus — login em chatgpt.com/auth/login (não a home do chat)",
    },
    "claude": {
        "name": "Claude",
        "product": "Claude.ai",
        "key_env": "ANTHROPIC_API_KEY",
        "model_env": "VEU_CLAUDE_MODEL",
        "mode_env": "VEU_CLAUDE_AUTH_MODE",
        "sub_env": "VEU_CLAUDE_SUB_STATUS",
        "sub_ts_env": "VEU_CLAUDE_SUB_TS",
        "default_model": "claude-sonnet-4-5",
        "chat_url": "https://claude.ai/new",
        "login_url": "https://claude.ai/login",
        "hint_key": "console.anthropic.com → API keys",
        "hint_sub": "Claude Pro/Max — login em claude.ai/login (não a home do chat)",
    },
    "xai": {
        "name": "Grok",
        "product": "Grok",
        "key_env": "XAI_API_KEY",
        "model_env": "VEU_XAI_MODEL",
        "mode_env": "VEU_XAI_AUTH_MODE",
        "sub_env": "VEU_XAI_SUB_STATUS",
        "sub_ts_env": "VEU_XAI_SUB_TS",
        "default_model": "grok-3-mini",
        "chat_url": "https://grok.com/",
        "login_url": "https://accounts.x.ai/sign-in",
        "hint_key": "console.x.ai → API keys (Grok)",
        "hint_sub": "Grok/SuperGrok — login em accounts.x.ai/sign-in · chat em grok.com",
    },
}


def _env_paths() -> list[Path]:
    return [
        Path("/root/veu/engine/.env"),
        Path(__file__).resolve().parents[2] / ".env",
    ]


def resolve_env_file() -> Path:
    for p in _env_paths():
        if p.is_file():
            return p
    deploy = Path("/root/veu/engine/.env")
    try:
        deploy.parent.mkdir(parents=True, exist_ok=True)
        if not deploy.exists():
            deploy.write_text("", encoding="utf-8")
        return deploy
    except OSError:
        local = Path(__file__).resolve().parents[2] / ".env"
        local.parent.mkdir(parents=True, exist_ok=True)
        if not local.exists():
            local.write_text("", encoding="utf-8")
        return local


def _mask(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 10:
        return "••••"
    return f"{k[:4]}…{k[-4:]}"


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = text.splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if m and m.group(1) in updates:
            key = m.group(1)
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    for key, val in updates.items():
        if val == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def _sub_status(meta: dict[str, str]) -> str:
    raw = os.environ.get(meta["sub_env"], "").strip().lower()
    if raw in {"linked", "pending", "off"}:
        return raw
    return "off"


def _auth_mode(meta: dict[str, str], has_key: bool, sub: str) -> AuthMode:
    raw = os.environ.get(meta["mode_env"], "").strip().lower()
    if raw in {"api_key", "subscription", "both"}:
        return raw  # type: ignore[return-value]
    # Inferência
    if has_key and sub == "linked":
        return "both"
    if sub == "linked":
        return "subscription"
    if has_key:
        return "api_key"
    return "api_key"


def _configured(has_key: bool, sub: str) -> bool:
    return has_key or sub == "linked"


def status_snapshot() -> dict[str, Any]:
    slots = []
    for pid, meta in PROVIDERS.items():
        key = os.environ.get(meta["key_env"], "").strip()
        has_key = bool(key)
        sub = _sub_status(meta)
        mode = _auth_mode(meta, has_key, sub)
        model = os.environ.get(meta["model_env"], "").strip() or meta["default_model"]
        live = _configured(has_key, sub)
        slots.append(
            {
                "id": pid,
                "name": meta["name"],
                "product": meta["product"],
                "status": "live" if live else ("pending" if sub == "pending" else "ready"),
                "configured": live,
                "auth_mode": mode,
                "modes": {
                    "api_key": {
                        "available": True,
                        "configured": has_key,
                        "key_env": meta["key_env"],
                        "key_masked": _mask(key),
                        "hint": meta["hint_key"],
                    },
                    "subscription": {
                        "available": True,
                        "status": sub,
                        "configured": sub == "linked",
                        "login_url": meta["login_url"],
                        "hint": meta["hint_sub"],
                        "linked_at": os.environ.get(meta["sub_ts_env"], "") or None,
                    },
                },
                "model_env": meta["model_env"],
                "model": model,
                # compat UI antiga
                "key_env": meta["key_env"],
                "key_masked": _mask(key),
                "hint": f"{meta['hint_key']} · ou · {meta['hint_sub']}",
            }
        )
    return {
        "subscriptions": slots,
        "count": len(slots),
        "note": "Cada IA aceita API key e/ou assinatura de conta (login no browser).",
    }


def connect_api_key(provider: str, api_key: str, model: str | None = None) -> dict[str, Any]:
    pid = provider.strip().lower()
    if pid not in PROVIDERS:
        raise ValueError(f"provedor desconhecido: {provider}")
    key = (api_key or "").strip()
    if len(key) < 12:
        raise ValueError("api_key inválida ou curta demais")
    meta = PROVIDERS[pid]  # type: ignore[index]
    sub = _sub_status(meta)
    mode: AuthMode = "both" if sub == "linked" else "api_key"
    updates = {
        meta["key_env"]: key,
        meta["mode_env"]: mode,
    }
    if model and model.strip():
        updates[meta["model_env"]] = model.strip()
    path = resolve_env_file()
    upsert_env(path, updates)
    return {
        "ok": True,
        "provider": pid,
        "auth_mode": mode,
        "path": "api_key",
        "env_file": str(path),
        "slot": next(s for s in status_snapshot()["subscriptions"] if s["id"] == pid),
    }


# Alias legado
def connect(provider: str, api_key: str, model: str | None = None) -> dict[str, Any]:
    return connect_api_key(provider, api_key, model)


def begin_subscription_link(provider: str) -> dict[str, Any]:
    """Inicia ligação por assinatura — abre login no browser; usuário confirma depois."""
    pid = provider.strip().lower()
    if pid not in PROVIDERS:
        raise ValueError(f"provedor desconhecido: {provider}")
    meta = PROVIDERS[pid]  # type: ignore[index]
    has_key = bool(os.environ.get(meta["key_env"], "").strip())
    mode: AuthMode = "both" if has_key else "subscription"
    path = resolve_env_file()
    upsert_env(
        path,
        {
            meta["sub_env"]: "pending",
            meta["mode_env"]: mode,
        },
    )
    return {
        "ok": True,
        "provider": pid,
        "path": "subscription",
        "action": "open_url",
        "url": meta["login_url"],  # sempre auth/login — nunca a home do chat
        "chat_url": meta.get("chat_url", ""),
        "message": (
            f"Abrindo login de {meta['product']} ({meta['login_url']}). "
            f"Entre com a assinatura e volte aqui para confirmar a ligação."
        ),
        "slot": next(s for s in status_snapshot()["subscriptions"] if s["id"] == pid),
    }


def confirm_subscription(provider: str) -> dict[str, Any]:
    """Usuário confirma que a conta/assinatura está logada no browser."""
    pid = provider.strip().lower()
    if pid not in PROVIDERS:
        raise ValueError(f"provedor desconhecido: {provider}")
    meta = PROVIDERS[pid]  # type: ignore[index]
    has_key = bool(os.environ.get(meta["key_env"], "").strip())
    mode: AuthMode = "both" if has_key else "subscription"
    path = resolve_env_file()
    upsert_env(
        path,
        {
            meta["sub_env"]: "linked",
            meta["sub_ts_env"]: str(int(time.time())),
            meta["mode_env"]: mode,
        },
    )
    return {
        "ok": True,
        "provider": pid,
        "path": "subscription",
        "auth_mode": mode,
        "message": f"{meta['name']} ligado via assinatura ({meta['product']})",
        "slot": next(s for s in status_snapshot()["subscriptions"] if s["id"] == pid),
    }


def disconnect(provider: str, path: str | None = None) -> dict[str, Any]:
    """Remove api_key, subscription, ou ambos."""
    pid = provider.strip().lower()
    if pid not in PROVIDERS:
        raise ValueError(f"provedor desconhecido: {provider}")
    meta = PROVIDERS[pid]  # type: ignore[index]
    which = (path or "both").strip().lower()
    env_path = resolve_env_file()
    updates: dict[str, str] = {}
    if which in {"api_key", "both", "all"}:
        updates[meta["key_env"]] = ""
    if which in {"subscription", "both", "all"}:
        updates[meta["sub_env"]] = "off"
        updates[meta["sub_ts_env"]] = ""
    # Recalcula mode depois
    upsert_env(env_path, updates)
    has_key = bool(os.environ.get(meta["key_env"], "").strip())
    sub = _sub_status(meta)
    if has_key and sub == "linked":
        mode = "both"
    elif sub == "linked":
        mode = "subscription"
    else:
        mode = "api_key"
    upsert_env(env_path, {meta["mode_env"]: mode})
    return {
        "ok": True,
        "provider": pid,
        "cleared": which,
        "slot": next(s for s in status_snapshot()["subscriptions"] if s["id"] == pid),
    }


def provider_available(provider: ProviderId) -> dict[str, Any]:
    """Usado pelo HybridLLM — key API e/ou assinatura ligada."""
    meta = PROVIDERS[provider]
    has_key = bool(os.environ.get(meta["key_env"], "").strip())
    sub = _sub_status(meta)
    return {
        "api_key": has_key,
        "subscription": sub == "linked",
        "any": has_key or sub == "linked",
        "login_url": meta["login_url"],
        "auth_mode": _auth_mode(meta, has_key, sub),
    }


def compose_subscription(
    provider: str,
    message: str,
    *,
    surface: str | None = None,
) -> dict[str, Any]:
    """Monta URL + app Host pra usar a assinatura (sessão logada), sem API key.

    A conversa no Véu dispara o pedido; a resposta nasce na conta Plus/Pro/Grok.
    """
    from urllib.parse import quote

    pid = provider.strip().lower()
    # surface aliases
    if pid in {"chatgpt", "codex"}:
        pid = "openai"
    if pid in {"claudeai", "claude-work", "claude_work"}:
        pid = "claude"
    if pid in {"grok"}:
        pid = "xai"
    if pid not in PROVIDERS:
        raise ValueError(f"provedor desconhecido: {provider}")

    meta = PROVIDERS[pid]  # type: ignore[index]
    sub = _sub_status(meta)
    text = (message or "").strip()
    if not text:
        raise ValueError("mensagem vazia")

    surf = (surface or "").strip().lower()
    q = quote(text[:4000])

    if pid == "openai":
        if surf in {"codex"} or "codex" in surf:
            url = f"https://chatgpt.com/codex?q={q}"
            app = "chatgpt"
            product = "Codex"
        else:
            url = f"https://chatgpt.com/?q={q}"
            app = "chatgpt"
            product = "ChatGPT"
    elif pid == "claude":
        if surf in {"claude-work", "work", "projects"}:
            url = f"https://claude.ai/projects?q={q}"
            app = "claude"
            product = "Claude Work"
        else:
            url = f"https://claude.ai/new?q={q}"
            app = "claude"
            product = "Claude"
    else:  # xai → grok.com (oficial; não grok.x.ai / x.ai)
        url = f"https://grok.com/?q={q}"
        app = "grok"
        product = "Grok"

    return {
        "ok": True,
        "provider": pid,
        "product": product,
        "subscription": sub,
        "subscription_linked": sub == "linked",
        "url": url,
        "app": app,
        "message": text[:200],
        "actions": [
            {"type": "focus_app", "app": app},
            {"type": "open_url", "url": url},
        ],
        # NÃO usar como resposta do chat — o desktop lê a aba e traz o texto pra janela
        "status": "composed",
        "hint": f"Pedido montado pra {product} · o Véu lê a resposta na aba e devolve aqui.",
    }

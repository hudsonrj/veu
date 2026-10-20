"""Aceita JSON de MCP no formato Cursor / Claude Desktop / servidor único."""

from __future__ import annotations

import json
import re
from typing import Any

# 9.7 — comandos permitidos para stdio
ALLOWED_COMMANDS = frozenset({"npx", "uvx", "node", "python", "python3"})
SHELL_META = re.compile(r"[;&|`$<>(){}]|\\n|\\r")


class McpCommandForbidden(ValueError):
    """Comando fora da allowlist ou com metacaracteres."""


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (name or "").strip().lower()).strip("-")
    return (s or "mcp")[:48]


def assert_command_allowed(command: str, args: list[str] | None = None) -> None:
    """Recusa comando fora da lista ou com metacaracteres de shell."""
    cmd = (command or "").strip()
    if not cmd:
        return
    base = cmd.split("/")[-1].split("\\")[-1]
    if base not in ALLOWED_COMMANDS:
        raise McpCommandForbidden(
            f"comando '{base}' fora da lista permitida ({', '.join(sorted(ALLOWED_COMMANDS))})"
        )
    if SHELL_META.search(cmd):
        raise McpCommandForbidden("comando com metacaracteres de shell bloqueado")
    for a in args or []:
        if SHELL_META.search(str(a)):
            raise McpCommandForbidden("args com metacaracteres de shell bloqueados")


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        # extrai bloco ```json ... ``` se vier no chat
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text, re.I)
        if m:
            text = m.group(1).strip()
        # ou primeiro { ... } balanceado grosseiro
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        return json.loads(text)
    raise ValueError("JSON inválido — espere objeto ou string JSON")


def _normalize_one(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        raise ValueError(f"servidor '{name}': config deve ser objeto")

    url = (
        cfg.get("url")
        or cfg.get("serverUrl")
        or cfg.get("sse")
        or cfg.get("endpoint")
        or ""
    )
    url = str(url).strip() if url else ""
    command = str(cfg.get("command") or "").strip()
    args = cfg.get("args") or []
    if not isinstance(args, list):
        raise ValueError(f"servidor '{name}': args deve ser lista")
    args = [str(a) for a in args]
    env = cfg.get("env") or {}
    if not isinstance(env, dict):
        raise ValueError(f"servidor '{name}': env deve ser objeto")
    env = {str(k): str(v) for k, v in env.items()}
    headers = cfg.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    headers = {str(k): str(v) for k, v in headers.items()}

    transport = str(cfg.get("transport") or cfg.get("type") or "").strip().lower()
    if not transport:
        if url:
            transport = "http"
        elif command:
            transport = "stdio"
        else:
            raise ValueError(
                f"servidor '{name}': informe url (HTTP) ou command (stdio)"
            )
    if transport in {"sse", "streamable-http", "streamable_http", "http"}:
        transport = "http"
    if transport not in {"http", "stdio"}:
        raise ValueError(f"servidor '{name}': transport deve ser http ou stdio")

    if transport == "http" and not url:
        raise ValueError(f"servidor '{name}': HTTP precisa de url")
    if transport == "stdio" and not command:
        raise ValueError(f"servidor '{name}': stdio precisa de command")
    # allowlist é aplicada em bus.preview_import / import_json (não aqui),
    # para a prévia poder listar o erro sem abortar o parse.

    return {
        "id": _slug(str(cfg.get("id") or name)),
        "name": str(cfg.get("name") or name).strip() or name,
        "transport": transport,
        "url": url,
        "command": command,
        "args": args,
        "env": env,
        "headers": headers,
        "cwd": str(cfg.get("cwd") or "").strip() or None,
        "notes": str(cfg.get("notes") or "").strip(),
    }


def preview_server(cfg: dict[str, Any]) -> dict[str, Any]:
    """Prévia segura: comando/args/URL + env só como referência ao .env."""
    env_in = cfg.get("env") or {}
    env_preview: dict[str, str] = {}
    for k, v in env_in.items():
        val = str(v)
        if re.search(r"(sk-|hf_|ghp_|xox|Bearer |token|secret)", val, re.I) or len(val) > 24:
            env_preview[str(k)] = f"${{{k}}} → .env"
        else:
            env_preview[str(k)] = val
    return {
        "id": cfg.get("id"),
        "name": cfg.get("name"),
        "transport": cfg.get("transport"),
        "url": cfg.get("url") or "",
        "command": cfg.get("command") or "",
        "args": list(cfg.get("args") or []),
        "env": env_preview,
        "cwd": cfg.get("cwd"),
        "notes": cfg.get("notes") or "",
    }


def parse_mcp_json(raw: Any) -> list[dict[str, Any]]:
    """Retorna lista de servidores normalizados a partir de qualquer JSON MCP comum."""
    data = _as_dict(raw)

    # Cursor / Claude: { "mcpServers": { "name": {...} } }
    if isinstance(data.get("mcpServers"), dict):
        out = []
        for name, cfg in data["mcpServers"].items():
            out.append(_normalize_one(str(name), cfg if isinstance(cfg, dict) else {}))
        if not out:
            raise ValueError("mcpServers vazio")
        return out

    # { "servers": [ {...}, ... ] }
    if isinstance(data.get("servers"), list):
        out = []
        for i, cfg in enumerate(data["servers"]):
            if not isinstance(cfg, dict):
                continue
            name = str(cfg.get("name") or cfg.get("id") or f"mcp-{i+1}")
            out.append(_normalize_one(name, cfg))
        if not out:
            raise ValueError("servers vazio")
        return out

    # servidor único
    if data.get("command") or data.get("url") or data.get("serverUrl"):
        name = str(data.get("name") or data.get("id") or "mcp")
        return [_normalize_one(name, data)]

    raise ValueError(
        "JSON não reconhecido. Use {\"mcpServers\":{...}} (Cursor/Claude) "
        "ou um objeto com url/command."
    )


def extract_json_from_text(text: str) -> Any | None:
    """Se a mensagem do chat trouxer JSON MCP, devolve o objeto; senão None."""
    if not text or "{" not in text:
        return None
    try:
        parsed = parse_mcp_json(text)
        # re-wrap as importable structure
        return {"mcpServers": {p["id"]: p for p in parsed}}
    except Exception:
        return None

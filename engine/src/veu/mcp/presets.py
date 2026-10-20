"""Presets MCP conhecidos — token/URL no chat bastam, sem JSON."""

from __future__ import annotations

import re
from typing import Any

# nome canônico → aliases + fábrica de config
_PRESETS: dict[str, dict[str, Any]] = {
    "rea": {
        "aliases": (
            "rea",
            "rea-agents",
            "rea tools",
            "rea.tools",
            "morluto/rea",
            "mcp rea",
            "mcp do rea",
        ),
        "no_token": True,
        "token_re": re.compile(r"(?!x)x"),
        "build": lambda _token="": {
            "id": "rea",
            "name": "REA · reverse engineer anything",
            "transport": "stdio",
            "url": "",
            "command": "npx",
            "args": ["-y", "rea-agents@latest", "--mcp"],
            "env": {},
            "headers": {},
            "notes": "https://github.com/morluto/rea · https://rea.tools",
        },
    },
    "huggingface": {
        "aliases": (
            "huggingface",
            "hugging face",
            "hugginface",  # typo comum
            "huggingfase",
            "hf.co",
            "hf mcp",
            "mcp do hf",
            "mcp huggingface",
        ),
        "token_re": re.compile(r"\b(hf_[A-Za-z0-9]{20,})\b"),
        "build": lambda token: {
            "id": "huggingface",
            "name": "Hugging Face",
            "transport": "http",
            "url": "https://huggingface.co/mcp",
            "command": "",
            "args": [],
            "env": {},
            "headers": {"Authorization": f"Bearer {token}"},
            "notes": "MCP oficial HF · https://huggingface.co/mcp",
        },
    },
}


def detect_preset_config(text: str) -> dict[str, Any] | None:
    """Se a mensagem pedir ligar um MCP conhecido + token, devolve config."""
    lower = text.lower()
    # só configuração — não intercepta "liste tools do mcp huggingface"
    wants = any(
        k in lower
        for k in (
            "configura",
            "configure",
            "liga o mcp",
            "ligar o mcp",
            "liga mcp",
            "conecta",
            "conectar",
            "adiciona",
            "instala",
            "crie o mcp",
            "cria o mcp",
            "criar mcp",
            "criar o mcp",
            "cadastra",
            "cadastrar",
        )
    )
    has_token = bool(re.search(r"\bhf_[A-Za-z0-9]{20,}\b", text))
    for name, meta in _PRESETS.items():
        if not any(a in lower for a in meta["aliases"]):
            continue
        m = meta["token_re"].search(text)
        token = m.group(1) if m else None
        if not token:
            m2 = re.search(
                r"(?:token|bearer|auth|chave)\s*[:=]?\s*[`'\"]?(hf_[A-Za-z0-9]{20,})",
                text,
                re.I,
            )
            token = m2.group(1) if m2 else None
        if meta.get("no_token") and wants:
            return meta["build"]("")
        if token and (wants or "token" in lower or "bearer" in lower):
            return meta["build"](token)
        if wants and not token:
            return {
                "_need_token": True,
                "id": name,
                "name": meta["build"]("x")["name"],
                "hint": "Manda o token Hugging Face (começa com hf_) na mesma mensagem.",
            }
        # token sozinho + nome do serviço (sem verbo) ainda liga
        if token and has_token and any(a in lower for a in meta["aliases"]):
            return meta["build"](token)
    return None

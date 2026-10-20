"""Padrões OpenClaw no Véu — gateway de canais + harness de tools.

OpenClaw é o harness multi-canal self-hosted. No Véu não rodamos o runtime;
espelhamos a semântica: session → channel → tools sob política de risco.
"""

from __future__ import annotations

import os
from typing import Any


class OpenClawBridge:
    """Gateway lógico: classifica canal e monta harness de tools."""

    CHANNELS = {
        "slack": ["slack", "canal", "#"],
        "discord": ["discord"],
        "teams": ["teams", "microsoft teams"],
        "telegram": ["telegram", "tg"],
        "whatsapp": ["whatsapp", "zap", "wpp"],
        "imessage": ["imessage", "imsg"],
    }

    def __init__(self) -> None:
        self.home = os.environ.get("OPENCLAW_HOME", "").strip()
        self.gateway_url = os.environ.get("VEU_OPENCLAW_GATEWAY_URL", "").strip()

    def status(self) -> str:
        if self.gateway_url or self.home:
            return "ready"
        return "planned"

    def pulse(self) -> dict[str, Any]:
        return {
            "id": "openclaw",
            "name": "OpenClaw",
            "role": "channel-gateway-harness",
            "status": self.status(),
            "gateway_configured": bool(self.gateway_url),
            "home_configured": bool(self.home),
            "patterns": ["channel-dispatch", "tool-harness", "persona-soul"],
            "ecc_skills": ["openclaw-persona-forge"],
        }

    def detect_channel(self, intent: str) -> str | None:
        t = intent.lower()
        for channel, tokens in self.CHANNELS.items():
            if any(tok in t for tok in tokens):
                return channel
        return None

    def plan_dispatch(self, intent: str, breath: str = "guided") -> dict[str, Any]:
        channel = self.detect_channel(intent)
        tools = self._harness_for(intent, channel)
        return {
            "ok": True,
            "bridge": "openclaw",
            "mode": "channel-dispatch",
            "channel": channel or "unspecified",
            "breath": breath,
            "tools": tools,
            "risk_ceiling": {"guided": "ask", "semi": "medium", "free": "high"}.get(
                breath, "ask"
            ),
            "message": (
                f"Gateway OpenClaw: canal={channel or 'a definir'}, "
                f"{len(tools)} tools no harness."
            ),
            "next": (
                "Conecte VEU_OPENCLAW_GATEWAY_URL para despacho real, "
                "ou use nervos Slack/Teams/WhatsApp do Véu."
            ),
        }

    def _harness_for(self, intent: str, channel: str | None) -> list[str]:
        tools = ["memory.read", "memory.write", "ecc.match"]
        lower = intent.lower()
        if channel:
            tools.append(f"channel.{channel}.send")
            tools.append(f"channel.{channel}.read")
        if any(k in lower for k in ("browser", "página", "site", "web")):
            tools.append("browser.navigate")
        if any(k in lower for k in ("shell", "terminal", "arquivo", "host")):
            tools.append("host.bridge")
        if "mcp" in lower:
            tools.append("mcp.call")
        return tools

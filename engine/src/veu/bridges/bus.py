"""Barramento unificado das pontes externas."""

from __future__ import annotations

from typing import Any

from .grokbot import GrokBotBridge
from .hermes import HermesBridge
from .openclaw import OpenClawBridge


class BridgeBus:
    def __init__(self) -> None:
        self.openclaw = OpenClawBridge()
        self.hermes = HermesBridge()
        self.grokbot = GrokBotBridge()

    def pulse(self) -> dict[str, Any]:
        return {
            "openclaw": self.openclaw.pulse(),
            "hermes": self.hermes.pulse(),
            "grokbot": self.grokbot.pulse(),
        }

    def route_intent(self, intent: str, breath: str = "guided") -> dict[str, Any] | None:
        """Detecta se a intenção pede uma ponte específica."""
        t = intent.lower()

        if any(
            k in t
            for k in (
                "grokbot",
                "grok bot",
                "handoff grok",
                "mandar pro grok",
                "enviar ao grok",
                "teammate cloud",
                "always-on",
                "always on",
            )
        ):
            return {
                "bridge": "grokbot",
                "action": "handoff",
                "plan": None,
            }

        if any(k in t for k in ("openclaw", "clawhub", "gateway openclaw")):
            return {
                "bridge": "openclaw",
                "action": "dispatch",
                "plan": self.openclaw.plan_dispatch(intent, breath),
            }

        if any(k in t for k in ("hermes", "learning loop", "distilar skill", "criar skill")):
            proposal = self.hermes.maybe_propose(min_repeats=1)  # explicit ask
            return {
                "bridge": "hermes",
                "action": "propose",
                "plan": {
                    "ok": True,
                    "pulse": self.hermes.pulse(),
                    "proposal": proposal,
                    "message": (
                        proposal["message"]
                        if proposal
                        else "Hermes: ainda sem padrão repetido — continue formando."
                    ),
                },
            }

        return None

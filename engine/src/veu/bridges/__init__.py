"""Pontes para runtimes externos: OpenClaw, Hermes, Grok Bot."""

from __future__ import annotations

from .bus import BridgeBus
from .grokbot import GrokBotBridge
from .hermes import HermesBridge
from .openclaw import OpenClawBridge

__all__ = [
    "BridgeBus",
    "GrokBotBridge",
    "HermesBridge",
    "OpenClawBridge",
]

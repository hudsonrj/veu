"""Jev (TypeSafe System One) — decide *para onde* vai o pedido do chat.

Pin: jev-1.13.0. Key via TYPESAFE_API_KEY (nunca no git).
Uma chamada, perguntas em paralelo: kind + route.
"""

from __future__ import annotations

import os
from typing import Any


JEV_MODEL = os.environ.get("VEU_JEV_MODEL", "jev-1.13.0")

INTENT_CRITERIA = {
    "greeting": "Hello, hi, ola, oi, bom dia — social chat, no task",
    "question": "Asking for information or explanation",
    "comm": "Messaging, email, WhatsApp, Teams, Slack, Gmail, Outlook",
    "workspace": "Notion pages, databases, wiki editing",
    "openrag": "Company knowledge base, documents, meeting notes, RAG search",
    "browser": "Web page, site, URL, browse",
    "files": "Local files, folders on disk",
    "system": "OS admin, shell, terminal, host apps",
    "grokbot": "Long cloud job, always-on teammate, handoff while user is away",
    "openclaw": "OpenClaw channel gateway",
    "hermes": "Learn/distill a reusable skill",
    "task": "Concrete job not clearly one of the above",
}

# Destino do chat central — Jev escolhe; o kernel executa e espera.
ROUTE_CRITERIA = {
    "chat": "Answer locally in the Véu chat (greetings, tiny clarifications)",
    "openrag": "Query the OpenRAG / document knowledge base and return the answer",
    "notion": "Search or operate Notion workspace",
    "grokbot": "Hand off to Grok Bot cloud teammate and wait for callback",
    "comm": "Messaging / email nerves",
    "browser": "Browse the web",
    "files": "Local files on the host",
    "system": "Host OS / shell / apps",
    "mcp": "MCP tools bus",
}


class JevRouter:
    """Roteador tipado do chat central."""

    def __init__(self) -> None:
        self.api_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        self.model = JEV_MODEL
        self._client = None
        if self.api_key:
            try:
                from typesafe_sdk import TypeSafeClient  # type: ignore

                self._client = TypeSafeClient(api_key=self.api_key, model=self.model)
            except Exception:  # noqa: BLE001
                self._client = None

    def status(self) -> str:
        # Honestidade de voo: live só com SDK instanciado de verdade
        if self._client is not None:
            return "live"
        if self.api_key:
            return "ready"  # key presente, SDK falhou ou não carregou
        return "planned"

    def pulse(self) -> dict[str, Any]:
        return {
            "id": "jev",
            "name": "Jev",
            "role": "system-one-router",
            "status": self.status(),
            "model": self.model,
            "key_configured": bool(self.api_key),
            "sdk": self._client is not None,
        }

    def classify(self, intent: str) -> dict[str, Any]:
        """Return {kind, route, confidence, route_confidence, model, source}."""
        text = (intent or "").strip()
        if not text:
            return {
                "kind": "greeting",
                "route": "chat",
                "agentic": 0.0,
                "agentic_flag": False,
                "confidence": 1.0,
                "route_confidence": 1.0,
                "model": self.model,
                "source": "empty",
            }

        if self._client is not None:
            try:
                from typesafe_sdk import Choice, Noul  # type: ignore

                r = self._client.system_one(
                    {"message": text[:2000]},
                    {
                        "intent_kind": Choice(
                            instructions=(
                                "What kind of user intent is this for an "
                                "AI-administered operating system chat?"
                            ),
                            criteria=INTENT_CRITERIA,
                        ),
                        "route": Choice(
                            instructions=(
                                "Which subsystem should handle this message end-to-end? "
                                "Pick the best single destination. The chat will wait "
                                "for that subsystem's result before answering the user."
                            ),
                            criteria=ROUTE_CRITERIA,
                        ),
                        "agentic": Noul(
                            instructions=(
                                "This message requires an agentic tool harness: "
                                "multi-step actions, side effects, browsing, shell, "
                                "messaging, MCP, cloud handoff, or writing to external systems "
                                "(not a pure greeting or one-shot Q&A)."
                            )
                        ),
                    },
                )
                kind_ans = r.answers["intent_kind"]
                route_ans = r.answers["route"]
                agentic_ans = r.answers["agentic"]
                kind = str(kind_ans.choice or "task")
                route = str(route_ans.choice or "chat")
                if kind not in INTENT_CRITERIA:
                    kind = "task"
                if route not in ROUTE_CRITERIA:
                    route = "chat"
                agentic_noul = float(getattr(agentic_ans, "noul", 0.0) or 0.0)
                return {
                    "kind": kind,
                    "route": route,
                    "agentic": agentic_noul,
                    "agentic_flag": agentic_noul >= 0.55,
                    "confidence": float(getattr(kind_ans, "confidence", 0.0) or 0.0),
                    "route_confidence": float(
                        getattr(route_ans, "confidence", 0.0) or 0.0
                    ),
                    "model": getattr(r, "model", self.model),
                    "source": "jev",
                }
            except Exception as exc:  # noqa: BLE001
                h = self._heuristic(text)
                h["error"] = str(exc)[:200]
                h["source"] = "heuristic+jev_error"
                return h

        return self._heuristic(text)

    def _heuristic(self, text: str) -> dict[str, Any]:
        t = text.lower().strip()
        def _pack(kind: str, route: str, conf: float, agentic: float) -> dict[str, Any]:
            return {
                "kind": kind,
                "route": route,
                "agentic": agentic,
                "agentic_flag": agentic >= 0.55,
                "confidence": conf,
                "route_confidence": conf,
                "model": None,
                "source": "heuristic",
            }

        if t in {
            "oi",
            "olá",
            "ola",
            "hey",
            "hi",
            "hello",
            "bom dia",
            "boa tarde",
            "boa noite",
        }:
            return _pack("greeting", "chat", 0.9, 0.05)
        if any(k in t for k in ("grokbot", "grok bot", "handoff", "mandar pro grok", "na nuvem")):
            return _pack("grokbot", "grokbot", 0.85, 0.9)
        if any(k in t for k in ("openrag", "ragpro", "na base", "base documental")):
            return _pack("openrag", "openrag", 0.85, 0.7)
        if "notion" in t:
            return _pack("workspace", "notion", 0.85, 0.75)
        if any(k in t for k in ("whatsapp", "gmail", "outlook", "teams", "slack", "email")):
            return _pack("comm", "comm", 0.8, 0.85)
        if any(
            k in t
            for k in (
                "http://",
                "https://",
                "www.",
                "acesse",
                "acessar",
                "abra o site",
                "abrir o site",
                "navegue",
                ".com",
                ".br",
            )
        ) and any(
            k in t
            for k in ("http", "www.", "site", "acesse", "acessar", "abra", "abrir", "link", ".com", ".br")
        ):
            return _pack("browser", "browser", 0.88, 0.75)
        if any(k in t for k in ("abra", "execute", "navegue", "terminal", "shell", "mcp", "automatize")):
            return _pack("task", "system", 0.7, 0.9)
        if "?" in t or t.startswith(("o que", "como", "quando", "por que", "porque", "qual")):
            return _pack("question", "openrag", 0.65, 0.45)
        return _pack("task", "chat", 0.5, 0.4)

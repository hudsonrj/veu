"""Nervo OpenRAG — memória documental (ragpro / openrag)."""

from __future__ import annotations

import os
from typing import Any

import httpx


class OpenRAGAdapter:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("OPENRAG_API_KEY", "")
            or os.environ.get("ORAG_API_KEY", "")
        ).strip()
        self.base_url = (
            base_url
            or os.environ.get("OPENRAG_URL", "")
            or os.environ.get("OPENRAG_BASE_URL", "")
            or "https://ragpro.ch8ai.com.br"
        ).rstrip("/")

    @property
    def live(self) -> bool:
        return bool(self.api_key and self.base_url)

    def status(self) -> str:
        return "live" if self.live else "planned"

    def pulse(self) -> dict[str, Any]:
        return {
            "id": "openrag",
            "status": self.status(),
            "base_url": self.base_url if self.live else None,
            "key_configured": bool(self.api_key),
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

    def ask(self, message: str, *, limit: int = 8) -> dict[str, Any]:
        if not self.live:
            return {
                "ok": False,
                "status": "planned",
                "message": "OpenRAG sem chave — defina OPENRAG_API_KEY",
                "answer": "",
                "sources": [],
            }
        try:
            with httpx.Client(timeout=45.0) as client:
                r = client.post(
                    f"{self.base_url}/api/v1/chat",
                    headers=self._headers(),
                    json={
                        "message": message.strip(),
                        "stream": False,
                        "limit": limit,
                    },
                )
                if r.status_code >= 400:
                    return {
                        "ok": False,
                        "status": "error",
                        "message": r.text[:400],
                        "answer": "",
                        "sources": [],
                    }
                data = r.json() if r.content else {}
                answer = (
                    data.get("response")
                    or data.get("answer")
                    or data.get("message")
                    or ""
                )
                sources = data.get("sources") or []
                return {
                    "ok": True,
                    "status": "live",
                    "message": "consulta OpenRAG ok",
                    "answer": str(answer).strip(),
                    "sources": sources,
                    "chat_id": data.get("chat_id"),
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "status": "error",
                "message": str(exc)[:300],
                "answer": "",
                "sources": [],
            }

    def execute(self, intent: str) -> dict[str, Any]:
        q = intent
        for noise in ("openrag", "rag", "na base", "documentos", "memória", "memoria"):
            q = q.replace(noise, " ")
        q = " ".join(q.split()) or intent
        return self.ask(q)

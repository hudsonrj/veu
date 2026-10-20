"""Nervo Notion — API oficial quando NOTION_TOKEN estiver presente."""

from __future__ import annotations

import os
from typing import Any

import httpx


class NotionAdapter:
    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("NOTION_TOKEN", "").strip()
        self.version = os.environ.get("NOTION_VERSION", "2022-06-28")

    @property
    def live(self) -> bool:
        return bool(self.token)

    def status(self) -> str:
        return "live" if self.live else "ready"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

    def search(self, query: str, *, page_size: int = 5) -> dict[str, Any]:
        if not self.live:
            return {
                "ok": False,
                "status": "ready",
                "message": "Notion pronto — defina NOTION_TOKEN para operar de verdade",
                "results": [],
            }
        with httpx.Client(timeout=20.0) as client:
            r = client.post(
                "https://api.notion.com/v1/search",
                headers=self._headers(),
                json={"query": query, "page_size": page_size},
            )
            if r.status_code >= 400:
                return {"ok": False, "status": "error", "message": r.text[:400], "results": []}
            data = r.json()
            results = []
            for item in data.get("results", []):
                title = _title_of(item)
                results.append(
                    {
                        "id": item.get("id"),
                        "object": item.get("object"),
                        "title": title,
                        "url": item.get("url"),
                    }
                )
            return {
                "ok": True,
                "status": "live",
                "message": f"{len(results)} resultado(s) no Notion",
                "results": results,
            }

    def execute(self, intent: str) -> dict[str, Any]:
        # Por enquanto: busca. Escrita/páginas entram depois com política de risco.
        q = intent.lower()
        for noise in ("notion", "no notion", "abra", "busca", "procure", "wiki"):
            q = q.replace(noise, " ")
        q = " ".join(q.split()) or intent
        return self.search(q)


def _title_of(item: dict[str, Any]) -> str:
    props = item.get("properties") or {}
    for value in props.values():
        if not isinstance(value, dict):
            continue
        if value.get("type") == "title":
            parts = value.get("title") or []
            text = "".join(p.get("plain_text", "") for p in parts)
            if text:
                return text
    # database / page title fallbacks
    title = item.get("title")
    if isinstance(title, list):
        return "".join(p.get("plain_text", "") for p in title) or "(sem título)"
    return "(sem título)"

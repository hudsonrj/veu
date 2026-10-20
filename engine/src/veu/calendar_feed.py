"""Calendário real — ICS + eventos capturados do Host (Google/Outlook)."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.request import Request, urlopen

_HOST_EVENTS: list[dict[str, Any]] = []
_HOST_TS = 0.0


def ingest_host_events(
    *,
    source: str,
    items: list[str],
    url: str | None = None,
) -> dict[str, Any]:
    """Recebe linhas scrapadas da aba Calendar/Outlook no Host."""
    global _HOST_EVENTS, _HOST_TS
    now = time.time()
    source = (source or "calendar").strip().lower()
    if source in {"agenda", "google"}:
        source = "google"
    if source not in {"google", "outlook", "calendar"}:
        source = "calendar"
    label = "google" if source in {"google", "calendar"} else "outlook"

    fresh: list[dict[str, Any]] = []
    for raw in items or []:
        text = str(raw or "").strip()
        if len(text) < 3:
            continue
        fresh.append(
            {
                "id": f"cal-{label}-{abs(hash(text)) % 10_000_000}",
                "title": text[:200],
                "kind": "calendar",
                "source": label,
                "ts": now,
                "state": "scheduled",
                "agent": label,
                "message": text[:400],
                "url": url,
                "priority": "calendar",
            }
        )
    # merge: novos na frente, dedupe por title
    seen = {e["title"] for e in fresh}
    kept = [e for e in _HOST_EVENTS if e.get("title") not in seen][:80]
    _HOST_EVENTS = (fresh + kept)[:120]
    _HOST_TS = now
    return {
        "ok": True,
        "source": label,
        "ingested": len(fresh),
        "total": len(_HOST_EVENTS),
        "ts": now,
    }


def host_events(limit: int = 40) -> list[dict[str, Any]]:
    return list(_HOST_EVENTS)[:limit]


def _parse_ics(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    blocks = re.split(r"BEGIN:VEVENT", body, flags=re.I)
    now = time.time()
    for block in blocks[1:]:
        def field(name: str) -> str:
            m = re.search(
                rf"^{name}[^:]*:(.+)$",
                block,
                flags=re.I | re.M,
            )
            if not m:
                return ""
            return m.group(1).strip().replace("\\n", " ").replace("\\,", ",")

        summary = field("SUMMARY") or "evento"
        dtstart = field("DTSTART")
        description = field("DESCRIPTION")
        ts = now
        if dtstart:
            raw = dtstart.split(";")[-1] if ";" in dtstart else dtstart
            raw = raw.strip()
            try:
                if re.match(r"^\d{8}T\d{6}Z?$", raw):
                    fmt = "%Y%m%dT%H%M%SZ" if raw.endswith("Z") else "%Y%m%dT%H%M%S"
                    ts = datetime.strptime(raw.replace("Z", ""), fmt.replace("Z", "")).replace(
                        tzinfo=timezone.utc if "Z" in raw else None
                    ).timestamp()
                elif re.match(r"^\d{8}$", raw):
                    ts = datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp()
                else:
                    ts = parsedate_to_datetime(raw).timestamp()
            except Exception:  # noqa: BLE001
                ts = now
        events.append(
            {
                "id": f"ics-{abs(hash(summary + str(ts))) % 10_000_000}",
                "title": summary[:200],
                "kind": "calendar",
                "source": "ics",
                "ts": ts,
                "state": "scheduled",
                "agent": "ics",
                "message": (description or "")[:400],
                "priority": "calendar",
            }
        )
    events.sort(key=lambda e: float(e.get("ts") or 0))
    return events


def fetch_ics(limit: int = 40) -> list[dict[str, Any]]:
    url = (os.environ.get("VEU_CALENDAR_ICS_URL") or "").strip()
    if not url:
        return []
    try:
        req = Request(url, headers={"User-Agent": "veu-calendar/1.0"})
        with urlopen(req, timeout=8) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
        return _parse_ics(body)[:limit]
    except Exception:  # noqa: BLE001
        return []


def collect(range_key: str = "day", limit: int = 60) -> dict[str, Any]:
    now = time.time()
    spans = {"day": 86_400, "week": 7 * 86_400, "month": 31 * 86_400}
    span = spans.get(range_key, spans["day"])
    start = now - span * 0.15  # inclui um pouco do passado
    end = now + span

    items = host_events(80) + fetch_ics(80)
    filtered = [
        e
        for e in items
        if start <= float(e.get("ts") or now) <= end
        or e.get("source") in {"google", "outlook"}  # host scrape: ts = captura
    ]
    # host events always show in day if recently captured
    if range_key == "day":
        recent_host = [
            e
            for e in host_events(40)
            if now - float(e.get("ts") or 0) < 86_400
        ]
        titles = {e["title"] for e in filtered}
        for e in recent_host:
            if e["title"] not in titles:
                filtered.append(e)

    filtered.sort(key=lambda e: float(e.get("ts") or 0))
    return {
        "ok": True,
        "range": range_key,
        "items": filtered[:limit],
        "ics_configured": bool((os.environ.get("VEU_CALENDAR_ICS_URL") or "").strip()),
        "host_cached": len(_HOST_EVENTS),
        "host_ts": _HOST_TS or None,
        "tip": (
            "Calendário ICS ligado."
            if (os.environ.get("VEU_CALENDAR_ICS_URL") or "").strip()
            else "Puxe Google/Outlook pela extensão Host, ou defina VEU_CALENDAR_ICS_URL no .env."
        ),
    }

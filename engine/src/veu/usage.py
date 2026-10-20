"""Instrumentação de custo/uso LLM — JSONL append-only + agregações."""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# USD por 1M tokens (aprox.) — barato por padrão / override via env JSON
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "gpt-5.4-nano": {"in": 0.10, "out": 0.40},
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4o": {"in": 2.50, "out": 10.0},
    "claude-sonnet": {"in": 3.0, "out": 15.0},
    "jev-1.13.0": {"in": 0.50, "out": 1.50},
    "default": {"in": 1.0, "out": 3.0},
}


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _log_path() -> Path:
    return _root() / "usage.jsonl"


def _prices() -> dict[str, dict[str, float]]:
    raw = (os.environ.get("VEU_LLM_PRICES_JSON") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {**DEFAULT_PRICES, **data}
        except json.JSONDecodeError:
            pass
    return DEFAULT_PRICES


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    prices = _prices()
    key = model if model in prices else "default"
    for k in prices:
        if k != "default" and k in (model or ""):
            key = k
            break
    p = prices.get(key) or prices["default"]
    return (tokens_in / 1_000_000.0) * float(p.get("in") or 0) + (
        tokens_out / 1_000_000.0
    ) * float(p.get("out") or 0)


def record(
    *,
    provider: str,
    model: str,
    agent: str | None = None,
    skill: str | None = None,
    job_id: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: float | None = None,
    company: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "ts": time.time(),
        "provider": provider,
        "model": model,
        "agent": agent,
        "skill": skill,
        "job_id": job_id,
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "cost_usd": round(estimate_cost(model, int(tokens_in or 0), int(tokens_out or 0)), 6),
        "latency_ms": latency_ms,
        "company": company,
        "meta": meta or {},
    }
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return row


def _iter_rows(*, since: float | None = None) -> list[dict[str, Any]]:
    path = _log_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-20_000:]:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since is not None and float(row.get("ts") or 0) < since:
                continue
            rows.append(row)
    except OSError:
        return []
    return rows


def summarize(period: str = "today") -> dict[str, Any]:
    now = time.time()
    spans = {"today": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
    span = spans.get(period, spans["today"])
    since = now - span
    rows = _iter_rows(since=since)

    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    by_agent: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    by_company: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    total_cost = 0.0
    total_tokens = 0
    series: dict[str, float] = defaultdict(float)

    for r in rows:
        cost = float(r.get("cost_usd") or 0)
        toks = int(r.get("tokens_in") or 0) + int(r.get("tokens_out") or 0)
        total_cost += cost
        total_tokens += toks
        m = str(r.get("model") or "unknown")
        by_model[m]["calls"] += 1
        by_model[m]["tokens"] += toks
        by_model[m]["cost"] += cost
        a = str(r.get("agent") or "—")
        by_agent[a]["calls"] += 1
        by_agent[a]["tokens"] += toks
        by_agent[a]["cost"] += cost
        c = str(r.get("company") or "—")
        by_company[c]["calls"] += 1
        by_company[c]["tokens"] += toks
        by_company[c]["cost"] += cost
        day = time.strftime("%Y-%m-%d", time.localtime(float(r.get("ts") or now)))
        series[day] += cost

    ranking = sorted(
        [{"agent": k, **v} for k, v in by_agent.items()],
        key=lambda x: x["cost"],
        reverse=True,
    )[:12]

    budget = float(os.environ.get("VEU_USAGE_BUDGET_USD") or 0) or None
    alert = None
    if budget and total_cost >= budget:
        alert = {"ok": False, "budget_usd": budget, "spent_usd": round(total_cost, 4)}

    return {
        "ok": True,
        "period": period,
        "calls": len(rows),
        "tokens": total_tokens,
        "cost_usd": round(total_cost, 4),
        "by_model": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_model.items()},
        "by_agent": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_agent.items()},
        "by_company": {k: {**v, "cost": round(v["cost"], 4)} for k, v in by_company.items()},
        "ranking": [{**r, "cost": round(r["cost"], 4)} for r in ranking],
        "series": [{"day": d, "cost_usd": round(c, 4)} for d, c in sorted(series.items())],
        "budget": alert,
    }

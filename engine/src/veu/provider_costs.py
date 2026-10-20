"""Coletores opcionais de uso/custo oficial dos provedores + reconciliação."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Env admin keys (nunca logar)
# OPENAI_ADMIN_KEY → GET https://api.openai.com/v1/organization/costs
# ANTHROPIC_ADMIN_KEY → GET https://api.anthropic.com/v1/organizations/cost_report
# XAI_MANAGEMENT_KEY → POST management API historical usage


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _store_path() -> Path:
    return _root() / "provider_costs.jsonl"


def _meta_path() -> Path:
    return _root() / "provider_costs_meta.json"


def _append_lines(rows: list[dict[str, Any]]) -> None:
    path = _store_path()
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_meta() -> dict[str, Any]:
    path = _meta_path()
    if not path.exists():
        return {"providers": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"providers": {}}


def _save_meta(data: dict[str, Any]) -> None:
    path = _meta_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def provider_status() -> dict[str, Any]:
    """Sem chave admin → manual."""
    return {
        "openai": {
            "mode": "admin" if (os.environ.get("OPENAI_ADMIN_KEY") or "").strip() else "manual",
            "key_env": "OPENAI_ADMIN_KEY",
        },
        "anthropic": {
            "mode": "admin" if (os.environ.get("ANTHROPIC_ADMIN_KEY") or "").strip() else "manual",
            "key_env": "ANTHROPIC_ADMIN_KEY",
        },
        "xai": {
            "mode": "admin" if (os.environ.get("XAI_MANAGEMENT_KEY") or "").strip() else "manual",
            "key_env": "XAI_MANAGEMENT_KEY",
        },
    }


def parse_openai_costs_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normaliza resposta de exemplo/oficial → linhas diárias por modelo."""
    lines: list[dict[str, Any]] = []
    # formato Costs API: data[].amount / line_item / project_id / start_time
    for bucket in payload.get("data") or []:
        start = bucket.get("start_time") or bucket.get("date") or bucket.get("day")
        if isinstance(start, (int, float)):
            day = datetime.fromtimestamp(int(start), tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            day = str(start or date.today().isoformat())[:10]
        amount = bucket.get("amount") or {}
        if isinstance(amount, dict):
            cost = float(amount.get("value") or amount.get("amount") or 0)
            currency = str(amount.get("currency") or "usd").upper()
        else:
            cost = float(amount or bucket.get("cost") or 0)
            currency = "USD"
        model = str(
            bucket.get("line_item")
            or bucket.get("model")
            or (bucket.get("results") or [{}])[0].get("model")
            if isinstance(bucket.get("results"), list)
            else bucket.get("model")
            or "unknown"
        )
        # results nested (usage completions style)
        results = bucket.get("results")
        if isinstance(results, list) and results:
            for res in results:
                m = str(res.get("model") or model or "unknown")
                c = float(res.get("amount", {}).get("value") if isinstance(res.get("amount"), dict) else res.get("cost") or cost or 0)
                lines.append(
                    {
                        "provider": "openai",
                        "day": day,
                        "model": m,
                        "cost_usd": round(c if currency == "USD" else c, 6),
                        "tokens_in": int(res.get("input_tokens") or res.get("n_context_tokens_total") or 0),
                        "tokens_out": int(res.get("output_tokens") or res.get("n_generated_tokens_total") or 0),
                        "source": "provider",
                    }
                )
        else:
            lines.append(
                {
                    "provider": "openai",
                    "day": day,
                    "model": model,
                    "cost_usd": round(cost, 6),
                    "tokens_in": int(bucket.get("input_tokens") or 0),
                    "tokens_out": int(bucket.get("output_tokens") or 0),
                    "source": "provider",
                }
            )
    return lines


def parse_anthropic_cost_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for bucket in payload.get("data") or payload.get("results") or []:
        day = str(bucket.get("starting_at") or bucket.get("date") or bucket.get("day") or "")[:10]
        if not day and bucket.get("start_time"):
            day = datetime.fromtimestamp(int(bucket["start_time"]), tz=timezone.utc).strftime("%Y-%m-%d")
        day = day or date.today().isoformat()
        model = str(bucket.get("model") or bucket.get("workspace_id") or "claude")
        amount = bucket.get("amount") or bucket.get("cost") or {}
        if isinstance(amount, dict):
            cost = float(amount.get("amount") or amount.get("value") or 0) / (
                100.0 if amount.get("currency") == "usd" and float(amount.get("amount") or 0) > 1000 else 1.0
            )
            # Anthropic cost report often returns cents as string amount
            raw = amount.get("amount")
            if isinstance(raw, str):
                try:
                    cost = float(raw) / 100.0
                except ValueError:
                    cost = 0.0
        else:
            cost = float(amount or 0)
        lines.append(
            {
                "provider": "anthropic",
                "day": day,
                "model": model,
                "cost_usd": round(cost, 6),
                "tokens_in": int(bucket.get("uncached_input_tokens") or bucket.get("input_tokens") or 0),
                "tokens_out": int(bucket.get("output_tokens") or 0),
                "source": "provider",
            }
        )
    return lines


def parse_xai_usage_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for bucket in payload.get("usage") or payload.get("data") or payload.get("items") or []:
        day = str(bucket.get("date") or bucket.get("day") or bucket.get("period") or date.today().isoformat())[:10]
        model = str(bucket.get("model") or "grok")
        cost = float(bucket.get("cost") or bucket.get("amount") or bucket.get("spend") or 0)
        lines.append(
            {
                "provider": "xai",
                "day": day,
                "model": model,
                "cost_usd": round(cost, 6),
                "tokens_in": int(bucket.get("prompt_tokens") or bucket.get("input_tokens") or 0),
                "tokens_out": int(bucket.get("completion_tokens") or bucket.get("output_tokens") or 0),
                "source": "provider",
            }
        )
    return lines


def ingest_provider_sample(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Teste / manual: resposta de exemplo → linhas diárias."""
    pid = provider.lower().strip()
    if pid == "openai":
        lines = parse_openai_costs_response(payload)
    elif pid in {"anthropic", "claude"}:
        lines = parse_anthropic_cost_response(payload)
    elif pid in {"xai", "grok"}:
        lines = parse_xai_usage_response(payload)
    else:
        raise ValueError(f"provedor desconhecido: {provider}")
    for line in lines:
        line["ingested_at"] = time.time()
    if lines:
        _append_lines(lines)
    meta = _load_meta()
    meta.setdefault("providers", {})[pid if pid != "claude" else "anthropic"] = {
        "last_sync": time.time(),
        "mode": "sample",
        "lines": len(lines),
    }
    _save_meta(meta)
    return {"ok": True, "provider": pid, "lines": lines, "count": len(lines)}


def collect_openai(*, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    key = (os.environ.get("OPENAI_ADMIN_KEY") or "").strip()
    if not key:
        return {"ok": False, "provider": "openai", "mode": "manual", "error": "sem OPENAI_ADMIN_KEY"}
    end = end or date.today()
    start = start or date.fromordinal(end.toordinal() - 7)
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                "https://api.openai.com/v1/organization/costs",
                headers={"Authorization": f"Bearer {key}"},
                params={
                    "start_time": int(datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp()),
                    "end_time": int(datetime.combine(end, datetime.max.time()).replace(tzinfo=timezone.utc).timestamp()),
                    "bucket_width": "1d",
                    "group_by": ["line_item"],
                },
            )
            if r.status_code >= 400:
                return {"ok": False, "provider": "openai", "mode": "admin", "error": r.text[:300]}
            return ingest_provider_sample("openai", r.json())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "provider": "openai", "error": str(exc)[:300]}


def collect_anthropic(*, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    key = (os.environ.get("ANTHROPIC_ADMIN_KEY") or "").strip()
    if not key:
        return {"ok": False, "provider": "anthropic", "mode": "manual", "error": "sem ANTHROPIC_ADMIN_KEY"}
    end = end or date.today()
    start = start or date.fromordinal(end.toordinal() - 7)
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                "https://api.anthropic.com/v1/organizations/cost_report",
                headers={
                    "X-Api-Key": key,
                    "anthropic-version": "2023-06-01",
                },
                params={
                    "starting_at": start.isoformat() + "T00:00:00Z",
                    "ending_at": end.isoformat() + "T23:59:59Z",
                    "bucket_width": "1d",
                    "group_by[]": "model",
                },
            )
            if r.status_code >= 400:
                return {"ok": False, "provider": "anthropic", "mode": "admin", "error": r.text[:300]}
            return ingest_provider_sample("anthropic", r.json())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "provider": "anthropic", "error": str(exc)[:300]}


def collect_xai(*, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    key = (os.environ.get("XAI_MANAGEMENT_KEY") or "").strip()
    team = (os.environ.get("XAI_TEAM_ID") or "").strip()
    if not key:
        return {"ok": False, "provider": "xai", "mode": "manual", "error": "sem XAI_MANAGEMENT_KEY"}
    if not team:
        return {"ok": False, "provider": "xai", "mode": "manual", "error": "sem XAI_TEAM_ID"}
    end = end or date.today()
    start = start or date.fromordinal(end.toordinal() - 7)
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"https://management-api.x.ai/auth/teams/{team}/historical-usage",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                },
            )
            if r.status_code >= 400:
                return {"ok": False, "provider": "xai", "mode": "admin", "error": r.text[:300]}
            return ingest_provider_sample("xai", r.json())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "provider": "xai", "error": str(exc)[:300]}


def collect_all() -> dict[str, Any]:
    """Sob demanda / diário — nunca em loop."""
    results = {
        "openai": collect_openai(),
        "anthropic": collect_anthropic(),
        "xai": collect_xai(),
        "status": provider_status(),
        "ts": time.time(),
    }
    meta = _load_meta()
    meta["last_collect_all"] = time.time()
    _save_meta(meta)
    return results


def _iter_provider_rows(*, since_day: str | None = None) -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-20_000:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since_day and str(row.get("day") or "") < since_day:
            continue
        rows.append(row)
    return rows


def reconcile(*, days: int = 30) -> dict[str, Any]:
    """Compara gasto interno (usage.py) vs cobrado pelo provedor."""
    from veu import usage as veu_usage

    since = time.time() - days * 86400
    internal = veu_usage._iter_rows(since=since)  # noqa: SLF001
    since_day = date.fromtimestamp(since).isoformat()
    provider_rows = _iter_provider_rows(since_day=since_day)

    int_by_prov: dict[str, float] = {}
    for r in internal:
        p = str(r.get("provider") or "unknown").lower()
        if p in {"claude"}:
            p = "anthropic"
        if p in {"grok"}:
            p = "xai"
        int_by_prov[p] = int_by_prov.get(p, 0) + float(r.get("cost_usd") or 0)

    prov_by: dict[str, float] = {}
    for r in provider_rows:
        p = str(r.get("provider") or "unknown").lower()
        prov_by[p] = prov_by.get(p, 0) + float(r.get("cost_usd") or 0)

    keys = sorted(set(int_by_prov) | set(prov_by))
    diff = []
    for k in keys:
        a = round(int_by_prov.get(k, 0), 4)
        b = round(prov_by.get(k, 0), 4)
        diff.append(
            {
                "provider": k,
                "veu_usd": a,
                "provider_usd": b,
                "delta_usd": round(b - a, 4),  # positivo = uso fora do Véu
                "mode": provider_status().get(k, {}).get("mode", "manual"),
            }
        )
    return {
        "ok": True,
        "days": days,
        "diff": diff,
        "provider_lines": len(provider_rows),
        "internal_calls": len(internal),
        "status": provider_status(),
    }

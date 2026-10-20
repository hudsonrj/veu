"""Alertas de assinaturas/custos — WhatsApp/push com dedup por ciclo."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "billing_alerts_sent.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"sent": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sent": {}}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dedup_key(kind: str, entity: str, cycle: str) -> str:
    return f"{kind}|{entity}|{cycle}"


def _already_sent(sent: dict[str, Any], key: str) -> bool:
    return key in sent


def _mark(sent: dict[str, Any], key: str) -> None:
    sent[key] = {"ts": time.time()}


def _notify(title: str, body: str, *, tag: str) -> None:
    try:
        from veu import push as veu_push

        veu_push.notify(title, body, url="/", tag=tag)
    except Exception:  # noqa: BLE001
        pass
    # WhatsApp webhook opcional (mesmo padrão de credentials)
    url = (os.environ.get("VEU_WHATSAPP_ALERT_WEBHOOK") or "").strip()
    if url:
        try:
            import httpx

            httpx.post(url, json={"title": title, "body": body, "tag": tag}, timeout=8.0)
        except Exception:  # noqa: BLE001
            pass
    try:
        log = _root() / "billing_alert_log.jsonl"
        with log.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"ts": time.time(), "title": title, "body": body, "tag": tag},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass


def evaluate_alerts(*, now: date | None = None) -> dict[str, Any]:
    """Gera alertas: renovação 7d, orçamento, reajuste, sem uso 30d. Dedupado."""
    from veu import billing
    from veu import receipt_scan
    from veu import usage as veu_usage

    today = now or date.today()
    cycle = today.strftime("%Y-%m")
    store = _load()
    sent: dict[str, Any] = dict(store.get("sent") or {})
    fired: list[dict[str, Any]] = []

    # 1) renovação em ≤7 dias
    for row in billing.list_subscriptions():
        if row.get("status") != "ativa":
            continue
        raw = row.get("proxima_renovacao")
        if not raw:
            continue
        try:
            d = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        days = (d - today).days
        if 0 <= days <= 7:
            key = _dedup_key("renewal", str(row.get("id")), f"{cycle}-{raw[:10]}")
            if not _already_sent(sent, key):
                alert = {
                    "kind": "renewal",
                    "subscription_id": row.get("id"),
                    "servico": row.get("servico"),
                    "dias": days,
                    "message": f"Renovação de {row.get('servico')} em {days} dia(s)",
                }
                _notify("Véu · renovação", alert["message"], tag=f"billing-renewal-{row.get('id')}")
                _mark(sent, key)
                fired.append(alert)

    # 2) orçamento mensal (usage USD + billing BRL opcional)
    budget = float(os.environ.get("VEU_USAGE_BUDGET_USD") or 0) or None
    if budget:
        summary = veu_usage.summarize("30d")
        spent = float(summary.get("cost_usd") or 0)
        if spent >= budget:
            key = _dedup_key("budget", "usage", cycle)
            if not _already_sent(sent, key):
                alert = {
                    "kind": "budget",
                    "spent_usd": spent,
                    "budget_usd": budget,
                    "message": f"Orçamento mensal estourado: ${spent:.2f} / ${budget:.2f}",
                }
                _notify("Véu · orçamento", alert["message"], tag="billing-budget")
                _mark(sent, key)
                fired.append(alert)

    # 3) reajuste de preço (receipt_scan)
    for a in receipt_scan.list_alerts(open_only=True):
        if a.get("kind") != "price_bump":
            continue
        key = _dedup_key("price_bump", str(a.get("servico")), cycle)
        if _already_sent(sent, key):
            continue
        alert = {
            "kind": "price_bump",
            "servico": a.get("servico"),
            "from_valor": a.get("from_valor"),
            "to_valor": a.get("to_valor"),
            "message": f"Preço reajustado: {a.get('servico')} {a.get('from_valor')} → {a.get('to_valor')}",
        }
        _notify("Véu · reajuste", alert["message"], tag=f"billing-bump-{a.get('servico')}")
        _mark(sent, key)
        fired.append(alert)

    # 4) assinatura ativa sem uso interno há 30d (quando houver matching provider)
    usage_rows = veu_usage._iter_rows(since=time.time() - 30 * 86400)  # noqa: SLF001
    used_models = " ".join(str(r.get("provider") or "") + " " + str(r.get("model") or "") for r in usage_rows).lower()
    for row in billing.list_subscriptions():
        if row.get("status") != "ativa":
            continue
        svc = str(row.get("servico") or "").lower()
        needles = [w for w in ("openai", "chatgpt", "claude", "anthropic", "cursor", "grok", "xai") if w in svc]
        if not needles:
            continue
        if any(n in used_models for n in needles):
            continue
        key = _dedup_key("unused", str(row.get("id")), cycle)
        if _already_sent(sent, key):
            continue
        alert = {
            "kind": "unused",
            "subscription_id": row.get("id"),
            "servico": row.get("servico"),
            "message": f"Assinatura sem uso há 30 dias: {row.get('servico')}",
        }
        _notify("Véu · sem uso", alert["message"], tag=f"billing-unused-{row.get('id')}")
        _mark(sent, key)
        fired.append(alert)

    store["sent"] = sent
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(store)
    return {"ok": True, "fired": fired, "count": len(fired)}

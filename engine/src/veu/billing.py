"""Assinaturas de serviços (billing) — distinto de /subscriptions (login LLM)."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

Currency = Literal["BRL", "USD", "EUR"]
Cycle = Literal["mensal", "anual"]
Status = Literal["ativa", "pausada", "cancelada", "em_decisao"]

CATEGORIES = ("IA", "infra", "produtividade", "outros")

_SERVICE_CATEGORY: dict[str, str] = {
    "chatgpt": "IA",
    "openai": "IA",
    "claude": "IA",
    "anthropic": "IA",
    "cursor": "IA",
    "grok": "IA",
    "xai": "IA",
    "notion": "produtividade",
    "github": "produtividade",
    "vps": "infra",
    "domínio": "infra",
    "dominio": "infra",
    "hetzner": "infra",
    "digitalocean": "infra",
    "aws": "infra",
}


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _store_path() -> Path:
    return _root() / "billing_subscriptions.json"


def _fx_cache_path() -> Path:
    return _root() / "fx_brl_cache.json"


def _load() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"subscriptions": [], "updated_at": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"subscriptions": [], "updated_at": None}


def _save(data: dict[str, Any]) -> None:
    data["updated_at"] = time.time()
    path = _store_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def infer_category(servico: str, categoria: str | None = None) -> str:
    if categoria and categoria in CATEGORIES:
        return categoria
    low = (servico or "").lower()
    for key, cat in _SERVICE_CATEGORY.items():
        if key in low:
            return cat
    return "outros"


def fetch_fx_to_brl(*, force: bool = False) -> dict[str, float]:
    """Cotação diária USD/EUR → BRL (cache 24h). API pública AwesomeAPI."""
    cache_path = _fx_cache_path()
    now = time.time()
    if not force and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if now - float(cached.get("ts") or 0) < 86400 and cached.get("rates"):
                return {k: float(v) for k, v in cached["rates"].items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    rates = {"BRL": 1.0, "USD": 5.0, "EUR": 5.5}  # fallback conservador
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get("https://economia.awesomeapi.com.br/json/last/USD-BRL,EUR-BRL")
            if r.status_code < 400:
                data = r.json()
                if "USDBRL" in data:
                    rates["USD"] = float(data["USDBRL"]["bid"])
                if "EURBRL" in data:
                    rates["EUR"] = float(data["EURBRL"]["bid"])
    except Exception:  # noqa: BLE001
        pass

    try:
        cache_path.write_text(
            json.dumps({"ts": now, "rates": rates, "day": date.today().isoformat()}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return rates


def to_brl(valor: float, moeda: str, rates: dict[str, float] | None = None) -> float:
    fx = rates or fetch_fx_to_brl()
    m = (moeda or "BRL").upper()
    if m == "BRL":
        return float(valor)
    return float(valor) * float(fx.get(m) or fx.get("USD") or 5.0)


def monthly_normalized(valor: float, ciclo: str) -> float:
    c = (ciclo or "mensal").lower()
    if c == "anual":
        return float(valor) / 12.0
    return float(valor)


def enrich(row: dict[str, Any], rates: dict[str, float] | None = None) -> dict[str, Any]:
    fx = rates or fetch_fx_to_brl()
    valor = float(row.get("valor") or 0)
    moeda = str(row.get("moeda") or "BRL").upper()
    ciclo = str(row.get("ciclo") or "mensal")
    valor_brl = to_brl(valor, moeda, fx)
    mensal_orig = monthly_normalized(valor, ciclo)
    mensal_brl = monthly_normalized(valor_brl, ciclo)
    out = dict(row)
    out["categoria"] = infer_category(str(row.get("servico") or ""), row.get("categoria"))
    out["valor_brl"] = round(valor_brl, 4)
    out["mensal_original"] = round(mensal_orig, 4)
    out["mensal_brl"] = round(mensal_brl, 4)
    out["cotacao"] = {k: round(v, 4) for k, v in fx.items()}
    return out


def list_subscriptions(*, status: str | None = None) -> list[dict[str, Any]]:
    rates = fetch_fx_to_brl()
    rows = []
    for row in _load().get("subscriptions") or []:
        if status and str(row.get("status")) != status:
            continue
        rows.append(enrich(row, rates))
    return rows


def get_subscription(sub_id: str) -> dict[str, Any] | None:
    for row in _load().get("subscriptions") or []:
        if row.get("id") == sub_id:
            return enrich(row)
    return None


def create_subscription(payload: dict[str, Any]) -> dict[str, Any]:
    data = _load()
    moeda = str(payload.get("moeda") or "BRL").upper()
    if moeda not in {"BRL", "USD", "EUR"}:
        raise ValueError("moeda deve ser BRL|USD|EUR")
    ciclo = str(payload.get("ciclo") or "mensal").lower()
    if ciclo not in {"mensal", "anual"}:
        raise ValueError("ciclo deve ser mensal|anual")
    status = str(payload.get("status") or "ativa").lower()
    if status not in {"ativa", "pausada", "cancelada", "em_decisao"}:
        raise ValueError("status inválido")
    # NUNCA número de cartão — só apelido
    meio = str(payload.get("meio_de_pagamento") or "")[:80]
    row = {
        "id": str(payload.get("id") or uuid.uuid4()),
        "servico": str(payload.get("servico") or "").strip()[:120],
        "plano": str(payload.get("plano") or "").strip()[:80],
        "valor": float(payload.get("valor") or 0),
        "moeda": moeda,
        "ciclo": ciclo,
        "proxima_renovacao": str(payload.get("proxima_renovacao") or "")[:32] or None,
        "pago_por": str(payload.get("pago_por") or "eu")[:120],
        "reembolsavel": bool(payload.get("reembolsavel") or False),
        "meio_de_pagamento": meio,
        "link_de_gestao": str(payload.get("link_de_gestao") or "")[:500],
        "status": status,
        "notas": str(payload.get("notas") or "")[:2000],
        "categoria": infer_category(str(payload.get("servico") or ""), payload.get("categoria")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if not row["servico"]:
        raise ValueError("serviço obrigatório")
    data.setdefault("subscriptions", []).append(row)
    _save(data)
    return enrich(row)


def update_subscription(sub_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    data = _load()
    found = None
    for row in data.get("subscriptions") or []:
        if row.get("id") == sub_id:
            found = row
            break
    if not found:
        raise KeyError("assinatura não encontrada")
    allowed = {
        "servico",
        "plano",
        "valor",
        "moeda",
        "ciclo",
        "proxima_renovacao",
        "pago_por",
        "reembolsavel",
        "meio_de_pagamento",
        "link_de_gestao",
        "status",
        "notas",
        "categoria",
    }
    for k, v in patch.items():
        if k not in allowed:
            continue
        if k == "moeda" and str(v).upper() not in {"BRL", "USD", "EUR"}:
            raise ValueError("moeda inválida")
        if k == "ciclo" and str(v).lower() not in {"mensal", "anual"}:
            raise ValueError("ciclo inválido")
        if k == "status" and str(v).lower() not in {"ativa", "pausada", "cancelada", "em_decisao"}:
            raise ValueError("status inválido")
        if k == "valor":
            found[k] = float(v)
        elif k == "reembolsavel":
            found[k] = bool(v)
        elif k == "moeda":
            found[k] = str(v).upper()
        elif k == "ciclo" or k == "status":
            found[k] = str(v).lower()
        else:
            found[k] = v
    found["categoria"] = infer_category(str(found.get("servico") or ""), found.get("categoria"))
    found["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(data)
    return enrich(found)


def delete_subscription(sub_id: str) -> bool:
    data = _load()
    before = len(data.get("subscriptions") or [])
    data["subscriptions"] = [r for r in (data.get("subscriptions") or []) if r.get("id") != sub_id]
    if len(data["subscriptions"]) == before:
        return False
    _save(data)
    return True


def mark_decision(sub_id: str, action: Literal["pausar", "cancelar"]) -> dict[str, Any]:
    """Só marca em_decisão e devolve link — nunca cancela sozinho."""
    row = update_subscription(sub_id, {"status": "em_decisao"})
    return {
        "ok": True,
        "action": action,
        "status": "em_decisao",
        "link_de_gestao": row.get("link_de_gestao") or "",
        "subscription": row,
        "message": "Abra o link de gestão. O Véu não cancela sozinho.",
    }


def dashboard() -> dict[str, Any]:
    rates = fetch_fx_to_brl()
    rows = [enrich(r, rates) for r in (_load().get("subscriptions") or [])]
    ativas = [r for r in rows if r.get("status") in {"ativa", "em_decisao", "pausada"}]
    total_mensal = sum(float(r.get("mensal_brl") or 0) for r in ativas if r.get("status") == "ativa")

    by_empresa: dict[str, float] = {}
    by_cat: dict[str, float] = {}
    for r in ativas:
        if r.get("status") != "ativa":
            continue
        emp = str(r.get("pago_por") or "eu")
        by_empresa[emp] = by_empresa.get(emp, 0) + float(r.get("mensal_brl") or 0)
        cat = str(r.get("categoria") or "outros")
        by_cat[cat] = by_cat.get(cat, 0) + float(r.get("mensal_brl") or 0)

    today = date.today()
    renewals = []
    for r in ativas:
        raw = r.get("proxima_renovacao")
        if not raw:
            continue
        try:
            d = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        days = (d - today).days
        if 0 <= days <= 30:
            renewals.append({**r, "dias": days})
    renewals.sort(key=lambda x: x.get("dias", 99))

    # variação MoM: soma renovadas no mês corrente vs mês anterior (heurística por valor)
    this_month = today.strftime("%Y-%m")
    prev = date(today.year, today.month, 1)
    if prev.month == 1:
        prev_m = f"{prev.year - 1}-12"
    else:
        prev_m = f"{prev.year}-{prev.month - 1:02d}"
    # sem histórico de fatura: variação = 0 se não houver snapshot
    hist_path = _root() / "billing_monthly_snapshot.json"
    prev_total = 0.0
    try:
        if hist_path.exists():
            snap = json.loads(hist_path.read_text(encoding="utf-8"))
            prev_total = float((snap.get("months") or {}).get(prev_m) or 0)
            months = dict(snap.get("months") or {})
            months[this_month] = total_mensal
            hist_path.write_text(
                json.dumps({"months": months}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            hist_path.write_text(
                json.dumps({"months": {this_month: total_mensal}}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except OSError:
        pass
    var = None
    if prev_total:
        var = round(((total_mensal - prev_total) / prev_total) * 100.0, 2)

    return {
        "ok": True,
        "total_mensal_brl": round(total_mensal, 2),
        "por_empresa": {k: round(v, 2) for k, v in by_empresa.items()},
        "por_categoria": {k: round(v, 2) for k, v in by_cat.items()},
        "variacao_mom_pct": var,
        "renovacoes_30d": renewals,
        "cotacao": {k: round(v, 4) for k, v in rates.items()},
        "count": len(rows),
    }


def export_csv() -> str:
    rows = list_subscriptions()
    headers = [
        "id",
        "servico",
        "plano",
        "valor",
        "moeda",
        "valor_brl",
        "ciclo",
        "mensal_brl",
        "proxima_renovacao",
        "pago_por",
        "categoria",
        "status",
        "meio_de_pagamento",
        "link_de_gestao",
    ]
    lines = [",".join(headers)]
    for r in rows:
        cells = []
        for h in headers:
            v = r.get(h)
            s = "" if v is None else str(v).replace('"', '""')
            if "," in s or '"' in s:
                s = f'"{s}"'
            cells.append(s)
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"

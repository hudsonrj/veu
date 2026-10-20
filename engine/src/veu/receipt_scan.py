"""Varredor de recibos de e-mail → sugestões de assinatura (opt-in)."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KNOWN_SENDERS: dict[str, str] = {
    "openai.com": "OpenAI / ChatGPT",
    "anthropic.com": "Anthropic / Claude",
    "cursor.com": "Cursor",
    "anysphere": "Cursor",
    "x.ai": "xAI / Grok",
    "google.com": "Google",
    "notion.so": "Notion",
    "notion.com": "Notion",
    "github.com": "GitHub",
    "stripe.com": "Stripe",
    "apple.com": "Apple",
}

_AMOUNT_RE = re.compile(
    r"(?:USD|US\$|\$|R\$|EUR|€)\s*([0-9]+(?:[.,][0-9]{2})?)"
    r"|([0-9]+(?:[.,][0-9]{2})?)\s*(?:USD|US\$|EUR|BRL)",
    re.I,
)
_CURRENCY_HINT = re.compile(r"(R\$|BRL|USD|US\$|\$|EUR|€)", re.I)


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "billing_suggestions.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"suggestions": [], "alerts": [], "seen_hashes": {}, "last_prices": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"suggestions": [], "alerts": [], "seen_hashes": {}, "last_prices": {}}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _service_from_from(from_addr: str) -> str | None:
    low = (from_addr or "").lower()
    for needle, name in KNOWN_SENDERS.items():
        if needle in low:
            return name
    return None


def _parse_amount(text: str) -> tuple[float | None, str | None]:
    blob = text or ""
    m = _AMOUNT_RE.search(blob)
    if not m:
        return None, None
    raw = (m.group(1) or m.group(2) or "").replace(",", ".")
    try:
        valor = float(raw)
    except ValueError:
        return None, None
    cur_m = _CURRENCY_HINT.search(blob)
    cur = "USD"
    if cur_m:
        t = cur_m.group(1).upper()
        if t in {"R$", "BRL"}:
            cur = "BRL"
        elif t in {"EUR", "€"}:
            cur = "EUR"
        else:
            cur = "USD"
    return valor, cur


def _fingerprint(servico: str, valor: float | None, moeda: str | None, date_s: str) -> str:
    return f"{servico}|{valor}|{moeda}|{date_s[:10]}"


def parse_receipt_meta(
    *,
    from_addr: str,
    subject: str,
    snippet: str,
    date_s: str = "",
    message_id: str = "",
) -> dict[str, Any] | None:
    """Extrai só metadados — sem guardar corpo do e-mail."""
    servico = _service_from_from(from_addr)
    subj = (subject or "").lower()
    if not servico:
        # subject hints
        for needle, name in KNOWN_SENDERS.items():
            if needle.split(".")[0] in subj:
                servico = name
                break
    if not servico:
        return None
    # só recibos/faturas
    hints = ("receipt", "invoice", "recibo", "fatura", "payment", "cobrança", "cobranca", "billing")
    blob = f"{subject} {snippet}".lower()
    if not any(h in blob for h in hints) and "openai" not in blob and "anthropic" not in blob:
        # ainda aceita se remetente conhecido + valor
        pass
    valor, moeda = _parse_amount(f"{subject} {snippet}")
    return {
        "servico": servico,
        "valor": valor,
        "moeda": moeda,
        "date": date_s or "",
        "from": from_addr[:160],
        "subject": (subject or "")[:200],
        "message_id": message_id,
        # NÃO guarda snippet longo / corpo
    }


def ingest_receipts(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Processa lista de mensagens (já sem corpo). Dedup + reajuste."""
    data = _load()
    suggestions = list(data.get("suggestions") or [])
    alerts = list(data.get("alerts") or [])
    seen = dict(data.get("seen_hashes") or {})
    last_prices: dict[str, float] = {
        k: float(v) for k, v in (data.get("last_prices") or {}).items()
    }
    created = 0
    bumps = 0

    for msg in messages:
        meta = parse_receipt_meta(
            from_addr=str(msg.get("from") or ""),
            subject=str(msg.get("subject") or ""),
            snippet=str(msg.get("snippet") or ""),
            date_s=str(msg.get("date") or ""),
            message_id=str(msg.get("id") or ""),
        )
        if not meta or not meta.get("servico"):
            continue
        servico = str(meta["servico"])
        fp = _fingerprint(servico, meta.get("valor"), meta.get("moeda"), str(meta.get("date") or ""))
        mid = meta.get("message_id") or fp
        if mid in seen or fp in seen:
            # mesmo recibo — ignora
            continue

        # dedup por serviço: se já há sugestão pendente do mesmo serviço, atualiza
        pending = next(
            (
                s
                for s in suggestions
                if s.get("servico") == servico and s.get("status") == "pending"
            ),
            None,
        )
        valor = meta.get("valor")
        if valor is not None and servico in last_prices:
            prev = last_prices[servico]
            if float(valor) > prev * 1.01:  # reajuste >1%
                alert = {
                    "id": str(uuid.uuid4()),
                    "kind": "price_bump",
                    "servico": servico,
                    "from_valor": prev,
                    "to_valor": float(valor),
                    "moeda": meta.get("moeda"),
                    "ts": time.time(),
                    "acked": False,
                }
                alerts.insert(0, alert)
                bumps += 1

        if pending:
            pending["valor"] = valor
            pending["moeda"] = meta.get("moeda")
            pending["date"] = meta.get("date")
            pending["subject"] = meta.get("subject")
            pending["updated_at"] = datetime.now(timezone.utc).isoformat()
            # não cria segunda sugestão
        else:
            suggestions.append(
                {
                    "id": str(uuid.uuid4()),
                    "servico": servico,
                    "plano": "",
                    "valor": valor,
                    "moeda": meta.get("moeda") or "USD",
                    "ciclo": "mensal",
                    "date": meta.get("date"),
                    "subject": meta.get("subject"),
                    "from": meta.get("from"),
                    "status": "pending",  # pending|approved|ignored
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            created += 1

        seen[str(mid)] = time.time()
        seen[fp] = time.time()
        if valor is not None:
            last_prices[servico] = float(valor)

    data["suggestions"] = suggestions[-200:]
    data["alerts"] = alerts[:100]
    data["seen_hashes"] = {k: v for k, v in list(seen.items())[-500:]}
    data["last_prices"] = last_prices
    _save(data)
    return {
        "ok": True,
        "suggestions_created": created,
        "price_bumps": bumps,
        "pending": [s for s in suggestions if s.get("status") == "pending"],
        "alerts": [a for a in alerts if not a.get("acked")],
    }


def scan_connected_email(*, limit: int = 40) -> dict[str, Any]:
    """Opt-in: só roda quando chamado. Lê Gmail metadata (sem corpo)."""
    from veu import google_workspace as gw

    # query restrita a remetentes / assuntos de recibo
    senders = " OR ".join(f"from:{d}" for d in ("openai.com", "anthropic.com", "cursor.com", "x.ai", "notion.so", "google.com"))
    q = f"({senders}) (receipt OR invoice OR fatura OR recibo OR payment OR billing)"
    try:
        data = gw._get(  # noqa: SLF001 — reusa cliente autenticado
            "/gmail/v1/users/me/messages",
            params={"maxResults": min(50, max(1, limit)), "q": q},
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300], "suggestions_created": 0}

    messages: list[dict[str, Any]] = []
    for msg in (data.get("messages") or [])[:limit]:
        mid = msg.get("id")
        if not mid:
            continue
        try:
            detail = gw._get(  # noqa: SLF001
                f"/gmail/v1/users/me/messages/{mid}",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
        except Exception:  # noqa: BLE001
            continue
        headers = {
            h.get("name"): h.get("value")
            for h in ((detail.get("payload") or {}).get("headers") or [])
        }
        messages.append(
            {
                "id": mid,
                "from": headers.get("From") or "",
                "subject": headers.get("Subject") or "",
                "date": headers.get("Date") or "",
                "snippet": (detail.get("snippet") or "")[:180],
            }
        )
    result = ingest_receipts(messages)
    result["scanned"] = len(messages)
    # confirma que não persistimos corpos
    result["bodies_stored"] = False
    return result


def list_suggestions(*, status: str | None = "pending") -> list[dict[str, Any]]:
    rows = _load().get("suggestions") or []
    if status:
        return [s for s in rows if s.get("status") == status]
    return list(rows)


def list_alerts(*, open_only: bool = True) -> list[dict[str, Any]]:
    rows = _load().get("alerts") or []
    if open_only:
        return [a for a in rows if not a.get("acked")]
    return list(rows)


def decide_suggestion(suggestion_id: str, action: str) -> dict[str, Any]:
    data = _load()
    found = None
    for s in data.get("suggestions") or []:
        if s.get("id") == suggestion_id:
            found = s
            break
    if not found:
        return {"ok": False, "error": "sugestão não encontrada"}
    act = action.lower().strip()
    if act == "ignore":
        found["status"] = "ignored"
        _save(data)
        return {"ok": True, "suggestion": found}
    if act == "approve":
        from veu import billing

        sub = billing.create_subscription(
            {
                "servico": found.get("servico"),
                "plano": found.get("plano") or "detectado por e-mail",
                "valor": found.get("valor") or 0,
                "moeda": found.get("moeda") or "USD",
                "ciclo": found.get("ciclo") or "mensal",
                "notas": f"aprovado de recibo · {found.get('subject') or ''}"[:500],
            }
        )
        found["status"] = "approved"
        found["subscription_id"] = sub["id"]
        _save(data)
        return {"ok": True, "suggestion": found, "subscription": sub}
    return {"ok": False, "error": "ação deve ser approve|ignore"}

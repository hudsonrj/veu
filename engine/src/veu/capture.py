"""11.4 — Captura rápida: classifica nota / tarefa / lembrete."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "captures.jsonl"


_TASK_HINTS = (
    "ligar",
    "ligar para",
    "ligar pra",
    "fazer",
    "enviar",
    "comprar",
    "agendar",
    "resolver",
    "entregar",
    "ligar ao",
    "chamar",
    "marcar",
)
_REMINDER_HINTS = ("lembrar", "lembrete", "não esquecer", "nao esquecer", "avise")
_DATE_WORDS = {
    "hoje": 0,
    "amanhã": 1,
    "amanha": 1,
    "depois de amanhã": 2,
    "depois de amanha": 2,
}


def classify(text: str) -> dict[str, Any]:
    """Sugere tipo + data a partir do texto (sem LLM)."""
    raw = (text or "").strip()
    lower = raw.lower()
    kind = "nota"
    if any(h in lower for h in _REMINDER_HINTS):
        kind = "lembrete"
    elif any(h in lower for h in _TASK_HINTS) or re.search(
        r"\b(prazo|deadline|até|ate)\b", lower
    ):
        kind = "tarefa"
    elif "?" in raw:
        kind = "pergunta"

    due: str | None = None
    due_label: str | None = None
    now = datetime.now(timezone.utc)
    for word, days in _DATE_WORDS.items():
        if word in lower:
            due_dt = (now + timedelta(days=days)).date()
            due = due_dt.isoformat()
            due_label = word
            break
    # "dia DD" grosseiro
    m = re.search(r"\bdia\s+(\d{1,2})\b", lower)
    if m and not due:
        day = int(m.group(1))
        try:
            due_dt = now.replace(day=min(day, 28)).date()
            if due_dt < now.date():
                # próximo mês
                month = now.month + 1 if now.month < 12 else 1
                year = now.year if now.month < 12 else now.year + 1
                due_dt = due_dt.replace(year=year, month=month)
            due = due_dt.isoformat()
            due_label = f"dia {day}"
        except ValueError:
            pass

    title = raw[:160]
    # limpando verbos comuns no começo
    title = re.sub(
        r"^(lembrar de |lembrete[:\s]+|nota[:\s]+|tarefa[:\s]+)",
        "",
        title,
        flags=re.I,
    ).strip() or raw[:160]

    return {
        "kind": kind,
        "title": title,
        "due": due,
        "due_label": due_label,
        "text": raw,
    }


def preview(text: str, *, company: str = "") -> dict[str, Any]:
    suggestion = classify(text)
    suggestion["company"] = (company or "").strip()
    return {"ok": True, "suggestion": suggestion, "needs_confirm": True}


def confirm(
    text: str,
    *,
    kind: str | None = None,
    company: str = "",
    title: str | None = None,
    due: str | None = None,
) -> dict[str, Any]:
    suggestion = classify(text)
    if kind in {"nota", "tarefa", "lembrete", "pergunta"}:
        suggestion["kind"] = kind
    if title:
        suggestion["title"] = title[:200]
    if due:
        suggestion["due"] = due
    suggestion["company"] = (company or "").strip()

    item = {
        "id": str(uuid.uuid4()),
        "ts": time.time(),
        "iso": datetime.now(timezone.utc).isoformat(),
        **suggestion,
    }
    with _path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # tarefas/lembretes também viram ação no quadro
    if item["kind"] in {"tarefa", "lembrete"}:
        try:
            from veu import actions as veu_actions

            veu_actions.upsert(
                source="capture",
                ref=item["id"],
                title=item["title"],
                help_text=item.get("text") or "",
                suggested="act",
                company=item.get("company") or "",
                meta={"due": item.get("due"), "kind": item["kind"]},
            )
        except Exception:  # noqa: BLE001
            pass

    # memória / inventário de contexto
    try:
        from veu.memory import Memory

        Memory().append(
            "capture",
            {
                "id": item["id"],
                "kind": item["kind"],
                "title": item["title"],
                "company": item.get("company"),
                "due": item.get("due"),
            },
            sink="sessions",
        )
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "item": item}


def search(q: str, *, limit: int = 20) -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    needle = (q or "").lower().strip()
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        blob = f"{row.get('title')} {row.get('text')} {row.get('company')}".lower()
        if not needle or needle in blob:
            out.append(row)
    return out[-limit:]

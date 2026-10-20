"""Briefing diário — manhã / noite a partir de companies + day + sideboard."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "briefings.jsonl"


def build(kind: str = "morning") -> dict[str, Any]:
    """Monta briefing citando dados reais do dia (sem LLM caro por padrão)."""
    kind = "evening" if kind in {"evening", "night", "close"} else "morning"
    agenda: list[Any] = []
    companies: list[Any] = []
    inbox_n = 0
    tasks_n = 0
    meetings: list[Any] = []
    needs_login = 0

    try:
        from veu.bridges import control_live

        sb = control_live.sideboard()
        agenda = list(sb.get("agenda") or [])[:8]
        meetings = list(sb.get("meetings") or [])[:6]
        inbox_n = int((sb.get("metrics") or {}).get("inbox") or len(sb.get("inbox") or []) or 0)
        tasks_n = int((sb.get("metrics") or {}).get("tasks") or len(sb.get("tasks") or []) or 0)
        needs_login = int(sb.get("needs_login_count") or 0)
        tree = control_live.companies_tree()
        companies = list((tree or {}).get("companies") or [])[:8]
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200], "kind": kind}

    lines: list[str] = []
    sources: list[dict[str, str]] = []
    if kind == "morning":
        lines.append("Bom dia — o que importa hoje:")
        if agenda:
            lines.append(f"· Agenda: {len(agenda)} compromisso(s)")
            for a in agenda[:4]:
                title = str(a.get("title") or a.get("subject") or "item")
                when = str(a.get("when") or a.get("start") or "")
                lines.append(f"  – {title}" + (f" ({when})" if when else ""))
                sources.append({"kind": "agenda", "title": title})
        else:
            lines.append("· Agenda: vazia no live.json")
        if meetings:
            lines.append(f"· Reuniões com nota: {len(meetings)}")
            for m in meetings[:3]:
                sources.append({"kind": "meeting", "title": str(m.get("title") or "")})
        lines.append(f"· Inbox: {inbox_n} · Tarefas: {tasks_n}")
        if companies:
            lines.append("· Empresas em foco:")
            for c in companies[:5]:
                name = str(c.get("name") or c.get("id"))
                counts = c.get("counts") or {}
                lines.append(
                    f"  – {name}: {counts.get('tasks', 0)} tarefas · "
                    f"{counts.get('meetings', 0)} reuniões · {counts.get('messages', 0)} msgs"
                )
                sources.append({"kind": "company", "title": name})
        if needs_login:
            lines.append(f"· Atenção: {needs_login} re-login(s) pendente(s)")
    else:
        lines.append("Fechamento — o que avançou / ficou:")
        lines.append(f"· Inbox residual: {inbox_n}")
        lines.append(f"· Tarefas abertas: {tasks_n}")
        if meetings:
            lines.append(f"· Reuniões do dia registradas: {len(meetings)}")
            for m in meetings[:4]:
                title = str(m.get("title") or "")
                summary = str(m.get("summary") or "")[:120]
                lines.append(f"  – {title}" + (f": {summary}" if summary else ""))
                sources.append({"kind": "meeting", "title": title})
        if companies:
            hot = sorted(
                companies,
                key=lambda c: int((c.get("counts") or {}).get("tasks") or 0),
                reverse=True,
            )[:3]
            lines.append("· Onde ficou carga:")
            for c in hot:
                name = str(c.get("name") or c.get("id"))
                lines.append(f"  – {name}: {(c.get('counts') or {}).get('tasks', 0)} tarefas")
                sources.append({"kind": "company", "title": name})

    text = "\n".join(lines)
    row = {
        "ok": True,
        "kind": kind,
        "ts": time.time(),
        "text": text,
        "sources": sources,
        "metrics": {
            "agenda": len(agenda),
            "meetings": len(meetings),
            "inbox": inbox_n,
            "tasks": tasks_n,
            "companies": len(companies),
            "needs_login": needs_login,
        },
    }
    try:
        with _path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return row


def _schedule_path() -> Path:
    return _root() / "briefing_schedule.json"


def get_schedule() -> dict[str, Any]:
    p = _schedule_path()
    if not p.exists():
        return {
            "ok": True,
            "enabled": False,
            "morning_hour": 7,
            "evening_hour": 20,
            "tz": "America/Sao_Paulo",
            "last_morning": None,
            "last_evening": None,
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data["ok"] = True
        return data
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "schedule corrompido"}


def set_schedule(
    *,
    enabled: bool | None = None,
    morning_hour: int | None = None,
    evening_hour: int | None = None,
    tz: str | None = None,
) -> dict[str, Any]:
    cur = get_schedule()
    if enabled is not None:
        cur["enabled"] = bool(enabled)
    if morning_hour is not None:
        cur["morning_hour"] = max(0, min(23, int(morning_hour)))
    if evening_hour is not None:
        cur["evening_hour"] = max(0, min(23, int(evening_hour)))
    if tz:
        cur["tz"] = str(tz)[:64]
    cur.pop("error", None)
    cur["ok"] = True
    try:
        _schedule_path().write_text(
            json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        return {"ok": False, "error": str(e)[:160]}
    return cur


def tick_schedule(*, now_ts: float | None = None) -> dict[str, Any]:
    """Se habilitado e na hora certa, gera briefing (idempotente por dia+kind)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    sch = get_schedule()
    if not sch.get("enabled"):
        return {"ok": True, "skipped": True, "reason": "disabled"}

    tz_name = str(sch.get("tz") or "America/Sao_Paulo")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("UTC")
    now = datetime.fromtimestamp(now_ts or time.time(), tz=tz)
    day_key = now.strftime("%Y-%m-%d")
    hour = now.hour
    built: list[str] = []

    def _due(kind: str, hour_cfg: int, last_key: str) -> bool:
        if hour != int(hour_cfg):
            return False
        last = sch.get(last_key)
        return last != f"{day_key}:{kind}"

    morning_h = int(sch.get("morning_hour") or 7)
    evening_h = int(sch.get("evening_hour") or 20)

    if _due("morning", morning_h, "last_morning"):
        build("morning")
        sch["last_morning"] = f"{day_key}:morning"
        built.append("morning")
    if _due("evening", evening_h, "last_evening"):
        build("evening")
        sch["last_evening"] = f"{day_key}:evening"
        built.append("evening")

    if built:
        try:
            _schedule_path().write_text(
                json.dumps(sch, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        return {"ok": True, "built": built, "day": day_key}
    return {"ok": True, "skipped": True, "reason": "not_due", "hour": hour}


def latest(kind: str | None = None) -> dict[str, Any] | None:
    path = _path()
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines[-40:]):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if kind and row.get("kind") != kind:
            continue
        return row
    return None


def ask_life(question: str, *, limit: int = 8) -> dict[str, Any]:
    """RAG com citação obrigatória — sem fonte, não responde."""
    q = (question or "").strip()
    if not q:
        return {"ok": False, "error": "pergunta vazia", "answer": "", "sources": []}

    # inclui decisões locais como contexto leve
    decisions_bits: list[str] = []
    try:
        dec = _root() / "decisions.jsonl"
        if dec.exists():
            for line in dec.read_text(encoding="utf-8").splitlines()[-20:]:
                try:
                    d = json.loads(line)
                    decisions_bits.append(str(d.get("intent") or d.get("kind") or "")[:120])
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    enriched = q
    if decisions_bits:
        enriched = (
            f"{q}\n\n(Contexto de decisões recentes do Véu: "
            + "; ".join(decisions_bits[:6])
            + ")"
        )

    from veu.connectors.openrag import OpenRAGAdapter

    rag = OpenRAGAdapter()
    result = rag.ask(enriched, limit=limit)
    sources = list(result.get("sources") or [])
    answer = str(result.get("answer") or "").strip()

    # exigir citação
    if not sources:
        return {
            "ok": False,
            "error": "sem_fonte",
            "answer": "",
            "sources": [],
            "message": "OpenRAG não citou fontes — Véu não responde sem citação.",
            "raw_ok": result.get("ok"),
        }
    if not answer:
        return {
            "ok": False,
            "error": "sem_resposta",
            "answer": "",
            "sources": sources,
        }
    return {
        "ok": True,
        "answer": answer,
        "sources": sources,
        "chat_id": result.get("chat_id"),
        "provider": "openrag",
    }

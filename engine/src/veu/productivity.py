"""Produtividade — painel completo a partir de live.json + ações + decisões + saúde."""

from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from veu import actions as veu_actions
from veu.bridges import control_live

NOISE_SOURCES = frozenset({"ecc", "agent"})


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts < 1e12:
            ts *= 1000
        return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours_between(start: Any, end: Any) -> float:
    a = _parse_dt(start)
    b = _parse_dt(end)
    if not a or not b:
        return 0.0
    secs = (b - a).total_seconds()
    if secs <= 0 or secs > 12 * 3600:
        return 0.0
    return round(secs / 3600.0, 2)


def _decisions_recent(limit: int = 120) -> list[dict[str, Any]]:
    path = _root() / "decisions.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows


def _company_slug(name: str) -> str:
    return (name or "—").strip() or "—"


def snapshot() -> dict[str, Any]:
    raw = control_live.load_raw() or {}
    side = control_live.sideboard(limit_inbox=40, limit_meetings=50, limit_agenda=50)
    board = veu_actions.board(limit=160)
    decisions = _decisions_recent(120)

    # mental (opcional)
    mental: dict[str, Any] = {}
    try:
        from veu import mental_health as veu_mh

        mental = veu_mh.board()
    except Exception:  # noqa: BLE001
        mental = {}

    meetings = list(raw.get("meetings") or []) if raw else list(side.get("meetings") or [])
    agenda = list(raw.get("agenda") or []) if raw else list(side.get("agenda") or [])
    tasks = list(raw.get("tasks") or []) if raw else []
    projects = list(raw.get("projects") or []) if raw else list(side.get("projects") or [])
    inbox = list(raw.get("inbox") or []) if raw else list(side.get("inbox") or [])

    meeting_hours = 0.0
    hours_by_company: Counter[str] = Counter()
    agenda_items: list[dict[str, Any]] = []
    for a in agenda:
        if a.get("cancelled"):
            continue
        h = _hours_between(a.get("start"), a.get("end"))
        if h <= 0:
            h = 0.75
        meeting_hours += h
        co = _company_slug(str(a.get("company") or a.get("empresa") or "—"))
        hours_by_company[co] += h
        agenda_items.append(
            {
                "id": a.get("id"),
                "title": a.get("title") or "",
                "start": a.get("start"),
                "end": a.get("end"),
                "hours": h,
                "company": co,
                "location": a.get("location") or "",
                "response": a.get("response") or "",
            }
        )

    meetings_view: list[dict[str, Any]] = []
    for mt in meetings:
        co = _company_slug(str(mt.get("empresa") or mt.get("company") or "—"))
        if co not in hours_by_company:
            hours_by_company[co] += 0.5
            meeting_hours += 0.5
        meetings_view.append(
            {
                "id": mt.get("id"),
                "title": mt.get("title") or "",
                "when": mt.get("when") or "",
                "company": co,
                "behavior": mt.get("behavior") or "",
                "bullets": (mt.get("bullets") or [])[:5],
                "tags": mt.get("tags") or [],
                "source": mt.get("source") or "",
            }
        )

    task_status: Counter[str] = Counter()
    tasks_by_company: Counter[str] = Counter()
    done_tasks = 0
    open_tasks = 0
    blocked_tasks = 0
    tasks_open_list: list[dict[str, Any]] = []
    for t in tasks:
        st = str(t.get("status") or "todo").lower()
        task_status[st] += 1
        co = _company_slug(str(t.get("company") or t.get("projectId") or "—"))
        tasks_by_company[co] += 1
        if st in {"done", "completed", "closed"}:
            done_tasks += 1
        elif st in {"todo", "doing", "blocked", "deferred"}:
            open_tasks += 1
            if st == "blocked":
                blocked_tasks += 1
            tasks_open_list.append(
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "status": st,
                    "company": co,
                    "owner": t.get("owner") or "",
                    "due": t.get("due"),
                }
            )

    # por empresa — ficha consolidada
    company_bag: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "name": "",
            "hours": 0.0,
            "tasks_open": 0,
            "tasks_blocked": 0,
            "meetings": 0,
            "messages": 0,
            "projects": 0,
            "insights": 0,
        }
    )
    for co, h in hours_by_company.items():
        company_bag[co]["name"] = co
        company_bag[co]["hours"] = round(h, 2)
    for co, n in tasks_by_company.items():
        company_bag[co]["name"] = co
        company_bag[co]["tasks_open"] = n
    for t in tasks_open_list:
        if t.get("status") == "blocked":
            company_bag[str(t.get("company"))]["tasks_blocked"] += 1
    for mt in meetings_view:
        company_bag[str(mt.get("company"))]["name"] = mt.get("company")
        company_bag[str(mt.get("company"))]["meetings"] += 1
    for m in inbox:
        co = _company_slug(str(m.get("company") or "—"))
        company_bag[co]["name"] = co
        company_bag[co]["messages"] += 1

    projects_view = []
    for p in projects[:24]:
        co = _company_slug(str(p.get("company") or ""))
        if co != "—":
            company_bag[co]["projects"] += 1
        projects_view.append(
            {
                "id": p.get("id"),
                "name": p.get("name") or p.get("id"),
                "summary": (p.get("summary") or "")[:200],
                "company": co if co != "—" else "",
            }
        )

    study: list[dict[str, Any]] = []
    for ins in side.get("insights") or []:
        co = str(ins.get("company") or "")
        if co:
            company_bag[_company_slug(co)]["insights"] += 1
        study.append(
            {
                "id": ins.get("id"),
                "title": ins.get("title"),
                "body": (ins.get("body") or "")[:280],
                "company": co,
                "kind": "insight",
            }
        )

    # ações úteis (sem ECC)
    useful_actions = [
        a
        for a in (board.get("actions") or [])
        if a.get("source") not in NOISE_SOURCES
        and a.get("status") in {"open", "updated", "in_progress"}
    ]
    for act in useful_actions:
        if act.get("source") in {"study", "meeting"}:
            study.append(
                {
                    "id": act.get("id"),
                    "title": act.get("title"),
                    "body": (act.get("help") or "")[:280],
                    "company": act.get("company") or "",
                    "kind": "action",
                }
            )

    by_channel: Counter[str] = Counter()
    unread = 0
    needs_approval = 0
    for m in inbox:
        ch = str(m.get("channel") or m.get("source") or "outro").lower()
        by_channel[ch] += 1
        if m.get("unread"):
            unread += 1
        if m.get("needsApproval"):
            needs_approval += 1

    actions_counts = board.get("counts") or {}
    useful_open = len(useful_actions)
    noise_open = sum(
        1
        for a in (board.get("actions") or [])
        if a.get("source") in NOISE_SOURCES
        and a.get("status") in {"open", "updated", "in_progress"}
    )

    decided_done = sum(
        1
        for d in decisions
        if str(d.get("status") or d.get("outcome") or "").lower()
        in {"done", "approved", "completed"}
        or d.get("approved") is True
    )

    companies_ranked = sorted(
        company_bag.values(),
        key=lambda c: (c["hours"], c["tasks_open"], c["meetings"], c["messages"]),
        reverse=True,
    )
    companies_ranked = [c for c in companies_ranked if c["name"] and c["name"] != "—"][:16]

    # foco do dia — heurística
    focus: list[str] = []
    if needs_approval:
        focus.append(f"{needs_approval} mensagem(ns) pedem aprovação")
    if blocked_tasks:
        focus.append(f"{blocked_tasks} tarefa(s) bloqueada(s)")
    if useful_open:
        focus.append(f"{useful_open} ação(ões) do modo autônomo abertas")
    if unread >= 20:
        focus.append(f"inbox pesada · {unread} não lidas")
    if meeting_hours >= 4:
        focus.append(f"{meeting_hours:.1f}h em reuniões — proteja foco")
    mh_alerts = len(mental.get("open_alerts") or [])
    if mh_alerts:
        focus.append(f"{mh_alerts} alerta(s) de saúde mental")
    if not focus:
        focus.append("Dia sob controle — avance 1 tarefa e 1 resposta.")

    completion = 0.0
    denom = done_tasks + open_tasks
    if denom:
        completion = round(100.0 * done_tasks / denom, 1)

    charts = {
        "hours_by_company": [
            {"label": k, "value": round(v, 2)} for k, v in hours_by_company.most_common(12)
        ],
        "tasks_by_status": [{"label": k, "value": v} for k, v in task_status.most_common(8)],
        "tasks_by_company": [
            {"label": k, "value": v} for k, v in tasks_by_company.most_common(10)
        ],
        "inbox_by_channel": [{"label": k, "value": v} for k, v in by_channel.most_common(8)],
        "actions_pipeline": [
            {"label": "úteis", "value": useful_open},
            {"label": "feitas", "value": int(actions_counts.get("done") or 0)},
            {"label": "ruído arquivado", "value": noise_open},
        ],
        "messages_by_company": [
            {"label": c["name"], "value": c["messages"]}
            for c in sorted(companies_ranked, key=lambda x: x["messages"], reverse=True)[:8]
            if c["messages"]
        ],
    }

    indicators = {
        "meeting_hours": round(meeting_hours, 2),
        "meetings": len(meetings_view),
        "agenda_open": len(agenda_items),
        "tasks_open": open_tasks,
        "tasks_done": done_tasks,
        "tasks_blocked": blocked_tasks,
        "completion_pct": completion,
        "projects": len(projects),
        "companies": len(companies_ranked),
        "inbox": len(inbox),
        "unread": unread,
        "needs_approval": needs_approval,
        "actions_open": useful_open,
        "actions_done": int(actions_counts.get("done") or 0),
        "decisions_recent": len(decisions),
        "decisions_done": decided_done,
        "study_queue": len(study),
        "mental_alerts": mh_alerts,
    }

    return {
        "ok": True,
        "available": bool(side.get("available") or raw),
        "updatedAt": side.get("updatedAt") or raw.get("updatedAt"),
        "indicators": indicators,
        "charts": charts,
        "focus": focus,
        "companies": companies_ranked,
        "projects": projects_view,
        "study": study[:30],
        "meetings": meetings_view[:20],
        "agenda": agenda_items[:20],
        "tasks_open": tasks_open_list[:30],
        "actions": useful_actions[:80],
        "inbox_sample": [
            {
                "id": m.get("id"),
                "channel": m.get("channel"),
                "company": m.get("company") or "",
                "sender": m.get("sender") or "",
                "subject": m.get("subject") or "",
                "needsApproval": bool(m.get("needsApproval")),
                "unread": bool(m.get("unread")),
            }
            for m in (side.get("inbox") or [])[:12]
        ],
        "mental": {
            "averages_7d": mental.get("averages_7d"),
            "open_alerts": (mental.get("open_alerts") or [])[:5],
            "areas": mental.get("areas") or [],
        },
        "productivity_live": side.get("productivity") or {},
        "health": side.get("health") or {},
        "counsel": (side.get("productivity") or {}).get("counsel_headline")
        or (side.get("productivity") or {}).get("focus")
        or "",
        "ts": time.time(),
        "note": (
            "Painel vivo do Control/GrokBot + ações do modo autônomo (sem ruído ECC) "
            "+ sinais de saúde mental."
        ),
    }

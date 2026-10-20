"""Lê o live.json do Control kiosk — o que o Grok Bot já consolidou.

Não relê Outlook/Teams/Gmail/Plaud. Só transforma o snapshot que os
agentes cloud já escrevem em /var/www/control-kiosk/live.json.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_PATHS = (
    "/var/www/control-kiosk/live.json",
    "/root/control-kiosk-webroot-20260926003253/live.json",
)


def _paths() -> list[Path]:
    env = os.environ.get("VEU_CONTROL_LIVE_PATH", "").strip()
    out: list[Path] = []
    if env:
        out.append(Path(env))
    out.extend(Path(p) for p in DEFAULT_PATHS)
    return out


def load_raw() -> dict[str, Any] | None:
    for path in _paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data["_path"] = str(path)
            data["_mtime"] = path.stat().st_mtime
            return data
    return None


def _ch_norm(ch: str | None) -> str:
    c = (ch or "").strip().lower()
    if c in {"teams", "microsoft teams"}:
        return "teams"
    if c in {"outlook", "email", "gmail", "mail"}:
        return "mail" if c != "outlook" else "outlook"
    return c or "outro"


def sideboard(limit_inbox: int = 12, limit_meetings: int = 8, limit_agenda: int = 10) -> dict[str, Any]:
    """Painel direito do hub Grok Bot — zero gasto extra."""
    raw = load_raw()
    if not raw:
        return {
            "ok": False,
            "available": False,
            "error": "live.json do Control não encontrado no host",
            "hint": "Defina VEU_CONTROL_LIVE_PATH ou publique em /var/www/control-kiosk/live.json",
        }

    inbox = list(raw.get("inbox") or [])
    meetings = list(raw.get("meetings") or [])
    agenda = list(raw.get("agenda") or [])
    tasks = list(raw.get("tasks") or [])
    projects = list(raw.get("projects") or [])
    agents = list(raw.get("agents") or [])
    needs_login = list(raw.get("needs_login") or [])
    counsel = raw.get("counsel") if isinstance(raw.get("counsel"), dict) else {}
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}

    # Canais (outlook/teams/gmail…) — o Grok Bot já leu
    by_channel: dict[str, int] = {}
    unread = 0
    needs_approval = 0
    for m in inbox:
        ch = _ch_norm(str(m.get("channel") or m.get("source") or ""))
        by_channel[ch] = by_channel.get(ch, 0) + 1
        if m.get("unread"):
            unread += 1
        if m.get("needsApproval"):
            needs_approval += 1

    task_by_status: dict[str, int] = {}
    for t in tasks:
        st = str(t.get("status") or "todo")
        task_by_status[st] = task_by_status.get(st, 0) + 1

    agenda_open = [a for a in agenda if not a.get("cancelled")]
    agenda_cancel = [a for a in agenda if a.get("cancelled")]

    # Inbox útil (prioriza needsApproval / unread / recent)
    def _inbox_score(m: dict[str, Any]) -> tuple:
        return (
            0 if m.get("needsApproval") else 1,
            0 if m.get("unread") else 1,
            str(m.get("at") or ""),
        )

    inbox_sorted = sorted(inbox, key=_inbox_score)
    inbox_view = [
        {
            "id": m.get("id"),
            "at": m.get("at"),
            "channel": _ch_norm(str(m.get("channel") or m.get("source") or "")),
            "company": m.get("company") or "",
            "sender": m.get("sender") or "",
            "subject": m.get("subject") or m.get("preview") or "",
            "preview": (m.get("bodyPreview") or m.get("preview") or "")[:220],
            "unread": bool(m.get("unread")),
            "needsApproval": bool(m.get("needsApproval")),
            "why": (m.get("whyImportant") or "")[:160],
            "action": m.get("suggestedAction") or "",
        }
        for m in inbox_sorted[:limit_inbox]
    ]

    meetings_view = [
        {
            "id": mt.get("id"),
            "empresa": mt.get("empresa") or "",
            "title": mt.get("title") or "",
            "when": mt.get("when") or "",
            "tags": mt.get("tags") or [],
            "bullets": (mt.get("bullets") or [])[:5],
            "source": mt.get("source") or "",
            "behavior": _meeting_behavior(mt),
        }
        for mt in meetings[:limit_meetings]
    ]

    agenda_view = [
        {
            "id": a.get("id"),
            "title": a.get("title") or "",
            "start": a.get("start") or "",
            "end": a.get("end") or "",
            "company": a.get("company") or "",
            "source": a.get("source") or "",
            "status": a.get("status") or "",
            "cancelled": bool(a.get("cancelled")),
            "location": a.get("location") or "",
            "response": a.get("response") or "",
        }
        for a in agenda[:limit_agenda]
    ]

    tasks_view = [
        {
            "id": t.get("id"),
            "title": t.get("title") or "",
            "owner": t.get("owner") or "",
            "status": t.get("status") or "",
            "due": t.get("due") or "",
            "company": t.get("company") or t.get("projectId") or "",
        }
        for t in tasks
        if str(t.get("status") or "") in {"doing", "blocked", "todo"}
    ][:10]

    agents_view = [
        {
            "id": a.get("id") or a.get("name"),
            "name": a.get("name") or "",
            "label": a.get("name") or "",
            "title": a.get("title") or "",
            "hint": (a.get("title") or a.get("area") or "")[:80],
            "area": a.get("area") or "",
            "isGroup": bool(a.get("isGroup")),
        }
        for a in agents
        if not a.get("isGroup")
    ]

    insights = []
    for i in (counsel.get("insights") or [])[:5]:
        if isinstance(i, dict):
            insights.append(
                {
                    "id": i.get("id"),
                    "title": i.get("title") or "",
                    "body": i.get("body") or "",
                    "company": i.get("company") or "",
                }
            )

    health = {
        "fleet": raw.get("fleetHealth") or "unknown",
        "updatedAt": raw.get("updatedAt"),
        "source_note": (raw.get("source") or "")[:280],
        "needs_login": needs_login[:6],
        "needs_login_count": len(needs_login),
        "channels": by_channel,
        "unread": unread,
        "needs_approval": needs_approval,
        "inbox_total": len(inbox),
        "agenda_open": len(agenda_open),
        "agenda_cancelled": len(agenda_cancel),
        "tasks": task_by_status,
        "projects": len(projects),
        "meetings": len(meetings),
        "last_agendas": meta.get("lastAgendasAt"),
        "last_teams": meta.get("lastTeamsMsgsAt") or meta.get("lastTeamsMsgsWake"),
        "hatkg": meta.get("hatkg"),
    }

    productivity = {
        "doing": task_by_status.get("doing", 0),
        "blocked": task_by_status.get("blocked", 0),
        "todo": task_by_status.get("todo", 0),
        "deferred": task_by_status.get("deferred", 0),
        "outbound": len(raw.get("outbound") or []),
        "done_signals": len(raw.get("doneSignals") or []),
        "counsel_headline": counsel.get("headline") or "",
        "focus": insights[0]["title"] if insights else "",
    }

    return {
        "ok": True,
        "available": True,
        "policy": "reuse-live-json",
        "path": raw.get("_path"),
        "mtime": raw.get("_mtime"),
        "updatedAt": raw.get("updatedAt"),
        "health": health,
        "productivity": productivity,
        "insights": insights,
        "agenda": agenda_view,
        "inbox": inbox_view,
        "meetings": meetings_view,
        "tasks": tasks_view,
        "projects": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "summary": (p.get("summary") or "")[:200],
            }
            for p in projects[:6]
        ],
        "agents": agents_view,
        "ts": time.time(),
    }


def _meeting_behavior(mt: dict[str, Any]) -> str:
    """Heurística barata a partir dos bullets já gravados — sem LLM."""
    bullets = [str(b).lower() for b in (mt.get("bullets") or [])]
    blob = " ".join(bullets)
    tags = [str(t).lower() for t in (mt.get("tags") or [])]
    signals: list[str] = []
    if any(x in blob for x in ("adiad", "pendente", "travou", "bloque")):
        signals.append("decisões adiadas")
    if any(x in blob for x in ("sem ação", "acompanhar", "sem dono")):
        signals.append("ownership frouxo")
    if any(x in blob for x in ("overload", "muita", "pressa", "urgente")):
        signals.append("carga alta")
    if "integracoes" in tags or "integra" in blob:
        signals.append("foco integração")
    if not signals and bullets:
        signals.append("ata objetiva")
    return " · ".join(signals[:3]) if signals else "sem sinal claro"


# projectId / nome → empresa canônica (live.json nem sempre traz company)
_PROJECT_COMPANY: dict[str, str] = {
    "vale-integration": "Vale",
    "projeto-seguro": "Vale",
    "projeto-5": "CPQD",
    "dados-financas": "AlliedIT",
    "alliedit-projetos": "AlliedIT",
    "foxprime-sistema": "CH8",
}

_COMPANY_GLYPH: dict[str, str] = {
    "Vale": "V",
    "CPQD": "C",
    "AlliedIT": "A",
    "Allied": "A",
    "HatKG": "H",
    "CH8": "8",
    "CH8ai": "8",
}

_COMPANY_HUE: dict[str, str] = {
    "Vale": "#E8C27A",
    "CPQD": "#7FE7D4",
    "AlliedIT": "#9EC9B0",
    "Allied": "#9EC9B0",
    "HatKG": "#D4A27F",
    "CH8": "#F0D7A2",
    "CH8ai": "#F0D7A2",
}


def _canon_company(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    low = s.lower()
    if "vale" in low or "neovale" in low:
        return "Vale"
    if "cpqd" in low:
        return "CPQD"
    if "allied" in low:
        return "AlliedIT"
    if "hatkg" in low or "hat kg" in low:
        return "HatKG"
    if "ch8" in low or "fox prime" in low or "foxprime" in low:
        return "CH8"
    if "genesis" in low:
        return "CH8"
    # ignora ruído tipo "Projeto" / "Proj."
    if low in {"projeto", "proj.", "job"}:
        return None
    return s.split("/")[0].split("·")[0].strip() or None


def _company_of_project(p: dict[str, Any]) -> str:
    pid = str(p.get("id") or "")
    if pid in _PROJECT_COMPANY:
        return _PROJECT_COMPANY[pid]
    c = _canon_company(p.get("company"))
    if c:
        return c
    return _canon_company(p.get("name")) or "Outros"


def _slim_msg(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.get("id"),
        "at": m.get("at"),
        "channel": _ch_norm(str(m.get("channel") or m.get("source") or "")),
        "company": _canon_company(m.get("company")) or m.get("company") or "",
        "sender": m.get("sender") or "",
        "subject": m.get("subject") or m.get("preview") or "",
        "preview": (m.get("bodyPreview") or m.get("preview") or "")[:220],
        "unread": bool(m.get("unread")),
        "needsApproval": bool(m.get("needsApproval")),
        "why": (m.get("whyImportant") or "")[:160],
        "projectId": m.get("projectId") or "",
    }


def _slim_task(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": t.get("id"),
        "title": t.get("title") or "",
        "owner": t.get("owner") or "",
        "status": t.get("status") or "",
        "due": t.get("due") or "",
        "priority": t.get("priority") or "",
        "company": _canon_company(t.get("company")) or t.get("company") or "",
        "projectId": t.get("projectId") or "",
        "note": (t.get("note") or "")[:200],
    }


def _slim_meeting(mt: dict[str, Any]) -> dict[str, Any]:
    bullets = list(mt.get("bullets") or [])
    return {
        "id": mt.get("id"),
        "empresa": _canon_company(mt.get("empresa")) or mt.get("empresa") or "",
        "title": mt.get("title") or "",
        "when": mt.get("when") or "",
        "tags": mt.get("tags") or [],
        "bullets": bullets[:12],
        "source": mt.get("source") or "",
        "behavior": _meeting_behavior(mt),
        "noteId": mt.get("noteId") or "",
        "handoff": mt.get("handoff") or "",
        "summary": "\n".join(f"· {b}" for b in bullets[:12]) if bullets else "",
    }


def _slim_agenda(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": a.get("id"),
        "title": a.get("title") or "",
        "start": a.get("start") or "",
        "end": a.get("end") or "",
        "company": _canon_company(a.get("company")) or a.get("company") or "",
        "source": a.get("source") or "",
        "cancelled": bool(a.get("cancelled")),
        "status": a.get("status") or "",
        "location": a.get("location") or "",
    }


def companies_tree() -> dict[str, Any]:
    """Empresa → projetos → tarefas / mensagens / reuniões / agenda.

    Tudo do live.json — sem gastar auth em Outlook/Teams de novo.
    """
    raw = load_raw()
    if not raw:
        return {
            "ok": False,
            "available": False,
            "error": "live.json do Control não encontrado",
            "companies": [],
        }

    projects = list(raw.get("projects") or [])
    tasks = list(raw.get("tasks") or [])
    inbox = list(raw.get("inbox") or [])
    meetings = list(raw.get("meetings") or [])
    agenda = list(raw.get("agenda") or [])

    # index projects by id
    proj_by_id: dict[str, dict[str, Any]] = {}
    for p in projects:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        company = _company_of_project(p)
        proj_by_id[pid] = {
            "id": pid,
            "name": p.get("name") or pid,
            "summary": (p.get("summary") or "")[:280],
            "status": p.get("status") or "",
            "company": company,
            "glyph": (p.get("name") or pid)[:1].upper(),
            "hue": _COMPANY_HUE.get(company, "#A8B4C0"),
            "counts": {"tasks": 0, "messages": 0, "meetings": 0, "agenda": 0},
            "tasks": [],
            "messages": [],
            "meetings": [],
            "agenda": [],
        }

    companies: dict[str, dict[str, Any]] = {}

    def ensure_company(name: str) -> dict[str, Any]:
        if name not in companies:
            companies[name] = {
                "id": name.lower().replace(" ", "-"),
                "name": name,
                "glyph": _COMPANY_GLYPH.get(name, name[:1].upper()),
                "hue": _COMPANY_HUE.get(name, "#A8B4C0"),
                "counts": {
                    "projects": 0,
                    "tasks": 0,
                    "messages": 0,
                    "meetings": 0,
                    "agenda": 0,
                    "unread": 0,
                    "doing": 0,
                    "blocked": 0,
                },
                "projects": [],
                "loose": {"tasks": [], "messages": [], "meetings": [], "agenda": []},
            }
        return companies[name]

    for p in proj_by_id.values():
        co = ensure_company(str(p["company"]))
        co["projects"].append(p)
        co["counts"]["projects"] += 1

    def attach(
        *,
        company: str | None,
        project_id: str | None,
        bucket: str,
        item: dict[str, Any],
        unread: bool = False,
        status: str = "",
    ) -> None:
        co_name = company or "Outros"
        co = ensure_company(co_name)
        co["counts"][bucket if bucket != "messages" else "messages"] = (
            co["counts"].get("messages" if bucket == "messages" else bucket, 0) + 1
        )
        if unread:
            co["counts"]["unread"] += 1
        if status == "doing":
            co["counts"]["doing"] += 1
        if status == "blocked":
            co["counts"]["blocked"] += 1

        pid = project_id or ""
        if pid and pid in proj_by_id and proj_by_id[pid]["company"] == co_name:
            proj_by_id[pid][bucket].append(item)
            key = "messages" if bucket == "messages" else bucket
            proj_by_id[pid]["counts"][key] = proj_by_id[pid]["counts"].get(key, 0) + 1
            return
        # tenta casar por nome da empresa no project map
        if pid and pid in proj_by_id:
            # projeto de outra empresa — ainda assim anexa no projeto
            proj_by_id[pid][bucket].append(item)
            key = "messages" if bucket == "messages" else bucket
            proj_by_id[pid]["counts"][key] = proj_by_id[pid]["counts"].get(key, 0) + 1
            return
        co["loose"][bucket].append(item)

    for t in tasks:
        pid = str(t.get("projectId") or "")
        company = _canon_company(t.get("company"))
        if not company and pid in proj_by_id:
            company = str(proj_by_id[pid]["company"])
        if not company and pid in _PROJECT_COMPANY:
            company = _PROJECT_COMPANY[pid]
        attach(
            company=company,
            project_id=pid or None,
            bucket="tasks",
            item=_slim_task(t),
            status=str(t.get("status") or ""),
        )

    for m in inbox:
        pid = str(m.get("projectId") or "")
        company = _canon_company(m.get("company"))
        # projectId no inbox às vezes é nome de empresa
        if not company and pid:
            company = _canon_company(pid)
            if company:
                pid = ""
        attach(
            company=company,
            project_id=pid or None,
            bucket="messages",
            item=_slim_msg(m),
            unread=bool(m.get("unread")),
        )

    for mt in meetings:
        company = _canon_company(mt.get("empresa"))
        # casa reunião a um projeto da mesma empresa pelo título
        pid = None
        title_l = str(mt.get("title") or "").lower()
        if company:
            for p in proj_by_id.values():
                if p["company"] != company:
                    continue
                name_l = str(p["name"]).lower()
                if any(tok in title_l for tok in name_l.split() if len(tok) > 4):
                    pid = p["id"]
                    break
                if "projeto 5" in title_l and p["id"] == "projeto-5":
                    pid = p["id"]
                    break
                if "seguro" in title_l and p["id"] == "projeto-seguro":
                    pid = p["id"]
                    break
                if "neovale" in title_l or "integra" in title_l:
                    if p["id"] == "vale-integration":
                        pid = p["id"]
                        break
        attach(
            company=company,
            project_id=pid,
            bucket="meetings",
            item=_slim_meeting(mt),
        )

    for a in agenda:
        company = _canon_company(a.get("company"))
        attach(
            company=company,
            project_id=None,
            bucket="agenda",
            item=_slim_agenda(a),
        )

    # ordena e limita listas pesadas
    out_companies: list[dict[str, Any]] = []
    for name in sorted(companies.keys(), key=lambda n: (n == "Outros", n.lower())):
        co = companies[name]
        for p in co["projects"]:
            p["tasks"] = p["tasks"][:40]
            p["messages"] = p["messages"][:40]
            p["meetings"] = p["meetings"][:20]
            p["agenda"] = p["agenda"][:20]
        co["projects"] = sorted(co["projects"], key=lambda x: str(x.get("name") or ""))
        for bucket in ("tasks", "messages", "meetings", "agenda"):
            co["loose"][bucket] = co["loose"][bucket][:40]
        out_companies.append(co)

    return {
        "ok": True,
        "available": True,
        "policy": "reuse-live-json",
        "updatedAt": raw.get("updatedAt"),
        "path": raw.get("_path"),
        "companies": out_companies,
        "counts": {
            "companies": len(out_companies),
            "projects": len(proj_by_id),
            "tasks": len(tasks),
            "messages": len(inbox),
            "meetings": len(meetings),
        },
        "ts": time.time(),
    }


def company_detail(company_id: str) -> dict[str, Any]:
    tree = companies_tree()
    if not tree.get("ok"):
        return tree
    needle = company_id.strip().lower()
    for co in tree.get("companies") or []:
        if str(co.get("id") or "").lower() == needle or str(co.get("name") or "").lower() == needle:
            return {"ok": True, "available": True, "company": co, "updatedAt": tree.get("updatedAt")}
    return {"ok": False, "available": True, "error": f"empresa não encontrada: {company_id}"}


_SERVER_HUE = {
    "contabo": "#E8C27A",
    "hetzner": "#7FE7D4",
    "raspberrypi": "#9EC9B0",
    "raspberry": "#9EC9B0",
}

_SERVER_GLYPH = {
    "contabo": "C",
    "hetzner": "H",
    "raspberrypi": "π",
    "raspberry": "π",
}

# host SSH sugerido quando ainda não há cadastro na frota
_SERVER_SSH_HINT = {
    "contabo": {"host": "169.58.19.232", "port": 22, "username": "root"},
    "hetzner": {"host": "", "port": 22, "username": "root"},
    "raspberrypi": {"host": "", "port": 22, "username": "pi"},
}


def servers_inventory() -> dict[str, Any]:
    """Servidores do live.json (o que cada um tem) — sem SSH novo."""
    raw = load_raw()
    if not raw:
        return {"ok": False, "available": False, "servers": [], "error": "live.json ausente"}

    out = []
    for s in raw.get("servers") or []:
        sid = str(s.get("id") or s.get("hostname") or "srv")
        apps = [
            {
                "id": a.get("id"),
                "name": a.get("name") or a.get("id"),
                "status": a.get("status") or "",
                "cpu": a.get("cpu"),
                "ram": a.get("ram"),
                "domain": a.get("domain") or "",
            }
            for a in (s.get("apps") or [])
        ]
        hint = _SERVER_SSH_HINT.get(sid.lower(), {"host": "", "port": 22, "username": "root"})
        out.append(
            {
                "id": sid,
                "hostname": s.get("hostname") or sid,
                "provider": s.get("provider") or "",
                "os": s.get("os") or "",
                "reverseProxy": s.get("reverseProxy") or "",
                "domains": s.get("domains") or [],
                "role": s.get("role") or "",
                "apps": apps,
                "apps_up": sum(1 for a in apps if str(a.get("status") or "").lower() in {"up", "ok", "running"}),
                "apps_total": len(apps),
                "glyph": _SERVER_GLYPH.get(sid.lower(), (s.get("hostname") or sid)[:1].upper()),
                "hue": _SERVER_HUE.get(sid.lower(), "#A8B4C0"),
                "ssh_hint": hint,
                "source": "live.json",
            }
        )
    return {
        "ok": True,
        "available": True,
        "updatedAt": raw.get("updatedAt"),
        "servers": out,
        "fleetNotes": (raw.get("fleetNotes") or [])[:8],
        "fleetHealth": raw.get("fleetHealth"),
        "ts": time.time(),
    }

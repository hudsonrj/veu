"""Ponte Véu ↔ Grok Bot — handoff, inbox do dia a dia, decisões e callbacks.

Outbound: POST VEU_GROKBOT_WEBHOOK_URL
Inbound:  POST /bridge/grokbot/inbound

Persistência em $VEU_DATA_ROOT/grokbot-*.jsonl para o SO não esquecer
mensagens importantes após restart.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

# Agentes ECC que costumam administrar pedidos no Grok Bot
DAY_AGENTS: list[dict[str, str]] = [
    {"id": "chief-of-staff", "label": "chefe de gabinete", "hint": "triagem e prioridade"},
    {"id": "planner", "label": "planejador", "hint": "plano e próximos passos"},
    {"id": "doc-updater", "label": "docs", "hint": "notas e base"},
    {"id": "architect", "label": "arquiteto", "hint": "desenho técnico"},
]

# Capacidades que vivem no Grok Bot (cloud) — o Véu pede via handoff, não reimplementa.
REMOTE_CAPABILITIES: list[dict[str, str]] = [
    {
        "id": "plaud",
        "label": "Plaud",
        "hint": "transcrições e resumos de reuniões",
        "ask": (
            "Use o Plaud que você já tem: liste as reuniões recentes "
            "(últimos 7 dias) com nome + data e, para as 3 mais relevantes, "
            "traga o resumo/notas. Devolva no callback com result.summary "
            "e artifacts (ids/links Plaud). Não peça login — a conta já é sua."
        ),
    },
    {
        "id": "plaud-today",
        "label": "Plaud · hoje",
        "hint": "o que foi gravado hoje",
        "ask": (
            "No Plaud (já conectado em você): o que foi gravado hoje? "
            "Liste cada reunião e um resumo curto. Callback com kind=completed."
        ),
    },
    {
        "id": "empresa-pastas",
        "label": "empresas",
        "hint": "pastas Empresa → projetos → assuntos",
        "ask": (
            "Traga o mapa de pastas Empresa → projetos → assuntos que você "
            "já organiza no cloud (ou no Plaud/Notion ligado a você). "
            "Não invente estrutura nova — espelhe o que já existe. "
            "Callback com result.summary e artifacts."
        ),
    },
    {
        "id": "day-brief",
        "label": "briefing",
        "hint": "status do dia no cloud",
        "ask": (
            "Briefing do dia: o que importa agora no seu lado (jobs, Plaud, "
            "aprovacões pendentes). Resumo curto no callback."
        ),
    },
    {
        "id": "productivity",
        "label": "produtividade",
        "hint": "saúde + comportamento nas reuniões",
        "ask": (
            "Consolide produtividade e saúde a partir do Plaud e da sua agenda: "
            "(1) reuniões recentes com tom/comportamento (interrupções, "
            "decisões adiadas, overload, clareza); "
            "(2) sinais de saúde operacional (carga, atrasos, energia); "
            "(3) agenda do dia e foco recomendado. "
            "Callback kind=completed com result={summary, productivity, "
            "health, meetings:[{title,date,behavior,actions}], agenda, "
            "focus}. source=plaud. Não invente reuniões — use o Plaud."
        ),
    },
]


def _data_root() -> Path:
    env = os.environ.get("VEU_DATA_ROOT")
    root = Path(env) if env else Path.home() / ".veu" / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _load_jsonl(path: Path, limit: int = 120) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _classify_inbound(payload: dict[str, Any], kind: str) -> str:
    """Prioridade para inbox do dia a dia."""
    if kind in {"health", "ping", "heartbeat"}:
        return "noise"
    state = str(payload.get("state") or "").lower()
    if kind in {"needs_approval", "approval"} or state in {"waiting", "needs_approval"}:
        return "decision"
    if kind == "failed" or state == "failed":
        return "important"
    if kind in {"completed", "decision"} or state == "completed":
        return "important"
    if payload.get("jev") or payload.get("decisions"):
        return "decision"
    if kind in {"update", "progress"}:
        return "update"
    return "update"


def _title_from(payload: dict[str, Any], kind: str) -> str:
    if payload.get("title"):
        return str(payload["title"])[:120]
    msg = str(payload.get("message") or "").strip()
    if msg:
        return msg.split("\n")[0][:120]
    result = payload.get("result")
    if isinstance(result, dict) and result.get("summary"):
        return str(result["summary"]).split("\n")[0][:120]
    return {
        "needs_approval": "precisa da sua OK",
        "completed": "job concluído",
        "failed": "job falhou",
        "update": "atualização do Grok Bot",
        "decision": "decisão",
    }.get(kind, "mensagem do Grok Bot")


class GrokBotBridge:
    """Fila + webhook + inbox persistente do teammate cloud."""

    def __init__(self) -> None:
        self.webhook_url = os.environ.get("VEU_GROKBOT_WEBHOOK_URL", "").strip()
        self.webhook_secret = os.environ.get("VEU_GROKBOT_WEBHOOK_SECRET", "").strip()
        if not self.webhook_secret:
            self.webhook_secret = os.environ.get("VEU_GROKBOT_SEND_KEY", "").strip()
        self.xai_key = os.environ.get("XAI_API_KEY", "").strip()
        self.api_base = os.environ.get("VEU_GROKBOT_API_BASE", "").rstrip("/")
        self._out_path = _data_root() / "grokbot-outbound.jsonl"
        self._in_path = _data_root() / "grokbot-inbound.jsonl"
        self._side_path = _data_root() / "grokbot-sideboard.json"
        self._queue: list[dict[str, Any]] = _load_jsonl(self._out_path)
        self._inbound: list[dict[str, Any]] = _load_jsonl(self._in_path)
        self._sideboard: dict[str, Any] = _load_json_file(self._side_path)
        self._last_health: dict[str, Any] | None = None
        # recupera último health da fila inbound
        for ev in reversed(self._inbound):
            if ev.get("kind") in {"health", "ping", "heartbeat"} or (
                (ev.get("payload") or {}).get("kind") in {"health", "ping", "heartbeat"}
            ):
                self._last_health = {
                    "ok": True,
                    "ts": ev.get("ts") or time.time(),
                    "payload": ev.get("payload") or {},
                }
                break

    def status(self) -> str:
        if self.webhook_url:
            if any(j.get("state") == "dispatched" for j in self._queue) or (
                self._last_health and self._last_health.get("ok")
            ):
                return "live"
            return "ready"
        if self.api_base or self.xai_key:
            return "ready"
        return "planned"

    def _day_agents(self) -> list[dict[str, str]]:
        """Prefere agentes reais do live.json (Control/Grok Bot); fallback ECC."""
        try:
            from veu.bridges import control_live

            board = control_live.sideboard(limit_inbox=1, limit_meetings=1, limit_agenda=1)
            agents = board.get("agents") or []
            if agents:
                return [
                    {
                        "id": str(a.get("name") or a.get("id")),
                        "label": str(a.get("name") or a.get("id")),
                        "hint": str(a.get("hint") or a.get("title") or "")[:80],
                    }
                    for a in agents
                    if a.get("name")
                ][:12]
        except Exception:  # noqa: BLE001
            pass
        return DAY_AGENTS

    def pulse(self) -> dict[str, Any]:
        inbox = self.inbox(limit=8)
        return {
            "id": "grokbot",
            "name": "Grok Bot",
            "role": "cloud-always-on-teammate",
            "routine": "Handoff do Véu",
            "status": self.status(),
            "queue_depth": len(self._queue),
            "inbound_depth": len(self._inbound),
            "inbox_open": sum(1 for i in inbox if i.get("needs_action")),
            "webhook_configured": bool(self.webhook_url),
            "secret_configured": bool(self.webhook_secret),
            "xai_llm_tier": bool(self.xai_key),
            "last_health": self._last_health,
            "modes": ["handoff", "inbound", "ask", "inbox", "approve", "mirror", "health", "live"],
            "callback": "http://169.58.19.232:8821/bridge/grokbot/inbound",
            "day_agents": self._day_agents(),
            "remote_capabilities": REMOTE_CAPABILITIES,
            "policy": "reuse-not-rebuild",
            "control_live": _control_live_present(),
        }

    def sideboard(self) -> dict[str, Any]:
        """Painel direito: live.json do Control + cache de callbacks."""
        try:
            from veu.bridges import control_live

            live = control_live.sideboard()
        except Exception as exc:  # noqa: BLE001
            live = {"ok": False, "available": False, "error": str(exc)}

        cached = self._sideboard if isinstance(self._sideboard, dict) else {}
        if live.get("available"):
            live["callback_cache"] = {
                "summary": cached.get("summary"),
                "updated_at": cached.get("updated_at"),
            }
            return live
        if cached:
            return {
                "ok": True,
                "available": True,
                "policy": "callback-cache",
                "health": cached.get("health") or {},
                "productivity": cached.get("productivity") or {},
                "insights": cached.get("insights") or [],
                "agenda": cached.get("agenda") or [],
                "inbox": cached.get("inbox") or [],
                "meetings": cached.get("meetings") or [],
                "tasks": cached.get("tasks") or [],
                "projects": cached.get("projects") or [],
                "agents": cached.get("agents") or self._day_agents(),
                "updatedAt": cached.get("updated_at"),
                "source": "grokbot-callback-cache",
            }
        return live

    def _merge_sideboard(self, payload: dict[str, Any]) -> None:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        merged = dict(self._sideboard) if isinstance(self._sideboard, dict) else {}
        merged["updated_at"] = time.time()
        merged["summary"] = (
            result.get("summary")
            or payload.get("message")
            or merged.get("summary")
        )
        for key in (
            "health",
            "productivity",
            "insights",
            "agenda",
            "inbox",
            "meetings",
            "tasks",
            "projects",
            "focus",
        ):
            if key in result:
                merged[key] = result[key]
        if payload.get("source"):
            merged["source"] = payload.get("source")
        self._sideboard = merged
        _write_json_file(self._side_path, merged)

    def _auth_headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "User-Agent": "veu-kernel/0.3"}
        if self.webhook_secret:
            h["Authorization"] = f"Bearer {self.webhook_secret}"
            h["X-Webhook-Key"] = self.webhook_secret
            h["X-API-Key"] = self.webhook_secret
        return h

    def handoff(
        self,
        *,
        intent: str,
        breath: str = "semi",
        formation: dict[str, Any] | None = None,
        priority: str = "normal",
        job_id: str | None = None,
        agent: str | None = None,
        via: str = "os",
    ) -> dict[str, Any]:
        """Despacha job para a routine Handoff do Véu."""
        jid = job_id or f"gb-{uuid.uuid4().hex[:12]}"
        if breath not in {"guided", "semi", "free"}:
            breath = "semi"

        agent_id = (agent or "").strip() or None
        intent_text = intent.strip()
        if agent_id and not intent_text.lower().startswith("agente "):
            # deixa claro no Grok Bot quem administra o pedido
            intent_text = f"[agente:{agent_id}] {intent_text}"

        formation_slim = _slim_formation(formation)
        if agent_id:
            formation_slim["agent"] = agent_id
            formation_slim["via"] = via or "os"
            agents = list(formation_slim.get("agents") or [])
            if not any(isinstance(a, dict) and a.get("id") == agent_id for a in agents):
                meta = next((a for a in DAY_AGENTS if a["id"] == agent_id), None)
                agents.insert(
                    0,
                    {
                        "id": agent_id,
                        "title": (meta or {}).get("label") or agent_id,
                        "role": "administer",
                    },
                )
            formation_slim["agents"] = agents[:8]

        job = {
            "id": jid,
            "job_id": jid,
            "ts": time.time(),
            "intent": intent_text,
            "breath": breath or "semi",
            "priority": priority,
            "formation": formation_slim,
            "state": "queued",
            "source": via or "os",
            "target": "grokbot",
            "agent": agent_id,
            "routine": "Handoff do Véu",
        }

        payload = {
            "intent": job["intent"],
            "breath": job["breath"],
            "job_id": jid,
            "formation": job["formation"],
            "via": via or "os",
            "agent": agent_id,
        }

        delivered = False
        remote: dict[str, Any] | None = None
        endpoint = self.webhook_url or (
            f"{self.api_base}/handoff" if self.api_base else ""
        )
        if endpoint:
            try:
                with httpx.Client(timeout=20.0) as client:
                    r = client.post(
                        endpoint,
                        json=payload,
                        headers=self._auth_headers(),
                    )
                    remote = {
                        "http_status": r.status_code,
                        "body": _safe_json(r),
                    }
                    delivered = 200 <= r.status_code < 300
                    job["state"] = "dispatched" if delivered else "queued_local"
            except Exception as exc:  # noqa: BLE001
                remote = {"error": str(exc)}
                job["state"] = "queued_local"
        else:
            job["state"] = "queued_local"
            job["hint"] = (
                "Defina VEU_GROKBOT_WEBHOOK_URL e VEU_GROKBOT_WEBHOOK_SECRET "
                "(painel Routines → Handoff do Véu)."
            )

        self._queue.append(job)
        if len(self._queue) > 200:
            self._queue = self._queue[-100:]
        _append_jsonl(self._out_path, job)

        return {
            "ok": True,
            "bridge": "grokbot",
            "mode": "handoff",
            "delivered": delivered,
            "job": job,
            "payload": payload,
            "remote": remote,
            "message": (
                "Enviei pro Grok Bot — ele devolve no SO quando terminar ou precisar de OK."
                if delivered
                else "Handoff na fila local. Falta URL/chave da routine no .env."
            ),
        }

    def ask(
        self,
        *,
        intent: str,
        breath: str = "semi",
        agent: str | None = None,
        via: str = "os",
        priority: str = "normal",
    ) -> dict[str, Any]:
        """Pedido do SO (ou de um agente) → Grok Bot administra na nuvem."""
        text = (intent or "").strip()
        if not text:
            return {"ok": False, "error": "diga o que o Grok Bot deve fazer"}
        return self.handoff(
            intent=text,
            breath=breath,
            agent=agent,
            via=via,
            priority=priority,
            formation={"via": via, "agent": agent, "kind": "day"},
        )

    def approve(self, job_id: str, *, note: str = "") -> dict[str, Any]:
        """Humano aprovou no SO — manda o Grok Bot seguir."""
        jid = (job_id or "").strip()
        if not jid:
            return {"ok": False, "error": "job_id obrigatório"}
        original = None
        for job in self._queue:
            if job.get("id") == jid or job.get("job_id") == jid:
                original = job
                break
        intent = (
            f"aprovado no Véu — continue o job {jid}"
            + (f": {note.strip()}" if note.strip() else "")
        )
        if original and original.get("intent"):
            intent = f"{intent} · contexto: {original['intent'][:240]}"
        result = self.handoff(
            intent=intent,
            breath=(original or {}).get("breath") or "semi",
            agent=(original or {}).get("agent"),
            via="approve",
            priority="high",
            formation={"approved_job": jid, "note": note},
        )
        if original:
            original["state"] = "approved"
            original["approved_at"] = time.time()
        return {**result, "mode": "approve", "approved_job": jid}

    def inbound(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Callback da routine → Véu (inbox do dia a dia)."""
        kind = str(payload.get("kind") or payload.get("type") or "update")
        if kind in {"health", "ping", "heartbeat"}:
            self._last_health = {
                "ok": True,
                "ts": time.time(),
                "payload": {
                    k: payload.get(k) for k in ("message", "state", "from") if k in payload
                },
            }
            event = {
                "id": f"in-{uuid.uuid4().hex[:12]}",
                "ts": time.time(),
                "payload": payload,
                "kind": kind,
                "priority": "noise",
            }
            self._inbound.append(event)
            _append_jsonl(self._in_path, event)
            return {
                "ok": True,
                "bridge": "grokbot",
                "mode": "health",
                "message": "pong",
                "status": self.status(),
            }

        priority = _classify_inbound(payload, kind)
        event = {
            "id": f"in-{uuid.uuid4().hex[:12]}",
            "ts": time.time(),
            "payload": payload,
            "kind": kind,
            "priority": priority,
            "title": _title_from(payload, kind),
            "needs_action": priority == "decision",
        }
        self._inbound.append(event)
        if len(self._inbound) > 200:
            self._inbound = self._inbound[-100:]
        _append_jsonl(self._in_path, event)

        job_id = payload.get("job_id") or payload.get("id")
        if job_id:
            for job in self._queue:
                if job.get("id") == job_id or job.get("job_id") == job_id:
                    job["state"] = payload.get("state") or kind or "completed"
                    job["result"] = payload.get("result") or payload.get("message")
                    break

        # Consolida painel direito quando o cloud devolve produtividade/Plaud
        if _looks_like_sideboard(payload):
            self._merge_sideboard(payload)

        return {
            "ok": True,
            "bridge": "grokbot",
            "mode": "inbound",
            "event": event,
            "inbox_item": self._to_inbox_item(event),
            "message": "Recebi o retorno do Grok Bot no SO.",
        }

    def _to_inbox_item(self, ev: dict[str, Any]) -> dict[str, Any]:
        p = ev.get("payload") or {}
        jev = p.get("jev") or {}
        decisions = jev.get("decisions") if isinstance(jev, dict) else None
        if not decisions:
            decisions = p.get("decisions")
        return {
            "id": ev.get("id"),
            "ts": ev.get("ts"),
            "kind": ev.get("kind") or p.get("kind") or "update",
            "priority": ev.get("priority") or "update",
            "title": ev.get("title") or _title_from(p, str(ev.get("kind") or "update")),
            "message": str(p.get("message") or "")[:800],
            "job_id": p.get("job_id") or p.get("id"),
            "state": p.get("state"),
            "needs_action": bool(ev.get("needs_action")),
            "agent": (p.get("agent") or (p.get("formation") or {}).get("agent")),
            "decisions": decisions or [],
            "result": p.get("result"),
        }

    def inbox(self, *, limit: int = 30, include_noise: bool = False) -> list[dict[str, Any]]:
        """Mensagens importantes / decisões para o dia a dia no SO."""
        items: list[dict[str, Any]] = []
        for ev in reversed(self._inbound):
            pri = ev.get("priority") or _classify_inbound(
                ev.get("payload") or {}, str(ev.get("kind") or "update")
            )
            if pri == "noise" and not include_noise:
                continue
            item = self._to_inbox_item({**ev, "priority": pri})
            items.append(item)
            if len(items) >= limit:
                break
        # decisões e importantes primeiro
        rank = {"decision": 0, "important": 1, "update": 2, "noise": 3}
        items.sort(key=lambda i: (rank.get(str(i.get("priority")), 9), -(i.get("ts") or 0)))
        return items

    def queue_board(self, *, limit: int = 40) -> dict[str, Any]:
        """Fila completa: executando · enfileirado · concluído · falhou."""
        active_states = {
            "queued",
            "dispatched",
            "queued_local",
            "running",
            "approved",
            "waiting",
        }
        done_states = {"completed", "done", "approved_done"}
        fail_states = {"failed", "error", "rejected", "cancelled"}

        def slim(j: dict[str, Any]) -> dict[str, Any]:
            return {
                "job_id": j.get("job_id") or j.get("id"),
                "intent": j.get("intent") or j.get("title") or "",
                "state": j.get("state") or "unknown",
                "agent": j.get("agent") or (j.get("formation") or {}).get("agent"),
                "breath": j.get("breath"),
                "via": j.get("via") or (j.get("formation") or {}).get("via"),
                "ts": j.get("ts"),
                "source": "grokbot",
                "message": _message_from_result(j)[:240] if j.get("result") else "",
            }

        running: list[dict[str, Any]] = []
        queued: list[dict[str, Any]] = []
        done: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for j in reversed(self._queue[-limit:]):
            state = str(j.get("state") or "")
            row = slim(j)
            if state in {"running", "dispatched", "approved", "waiting"}:
                running.append(row)
            elif state in {"queued", "queued_local"}:
                queued.append(row)
            elif state in fail_states:
                failed.append(row)
            elif state in done_states or state == "completed":
                done.append(row)
            elif state in active_states:
                queued.append(row)
            else:
                done.append(row)
        return {
            "ok": True,
            "running": running[:20],
            "queued": queued[:20],
            "done": done[:20],
            "failed": failed[:12],
            "counts": {
                "running": len(running),
                "queued": len(queued),
                "done": len(done),
                "failed": len(failed),
                "total": len(self._queue),
            },
        }

    def day_insights(self) -> list[dict[str, str]]:
        """Insights curtos sobre a agenda do dia (a partir da inbox/fila)."""
        inbox = self.inbox(limit=20)
        board = self.queue_board(limit=30)
        insights: list[dict[str, str]] = []
        n_dec = sum(1 for i in inbox if i.get("priority") == "decision")
        n_imp = sum(1 for i in inbox if i.get("priority") == "important")
        n_run = board["counts"]["running"]
        n_q = board["counts"]["queued"]
        if n_dec:
            insights.append(
                {
                    "tone": "action",
                    "text": f"{n_dec} item(ns) pedem sua OK — abra a fila e aprove ou rejeite.",
                }
            )
        if n_run:
            insights.append(
                {
                    "tone": "live",
                    "text": f"{n_run} job(s) em execução agora no Grok Bot.",
                }
            )
        if n_q:
            insights.append(
                {
                    "tone": "queue",
                    "text": f"{n_q} na fila — o próximo sobe quando o atual concluir.",
                }
            )
        if n_imp and not n_dec:
            insights.append(
                {
                    "tone": "focus",
                    "text": f"{n_imp} update(s) importantes sem decisão pendente — vale um olhar.",
                }
            )
        if not insights:
            insights.append(
                {
                    "tone": "calm",
                    "text": "Agenda limpa por agora. Peça algo ao Grok Bot ou abra um arquivo no Studio.",
                }
            )
        # título do próximo job
        nxt = (board["running"] or board["queued"] or [None])[0]
        if nxt and nxt.get("intent"):
            insights.append(
                {
                    "tone": "next",
                    "text": f"Próximo foco: {str(nxt['intent'])[:120]}",
                }
            )
        return insights[:6]

    def brief(self) -> dict[str, Any]:
        """Resumo do dia — o que o SO mostra ao abrir Grok Bot / Agenda."""
        inbox = self.inbox(limit=20)
        decisions = [i for i in inbox if i.get("priority") == "decision"]
        important = [i for i in inbox if i.get("priority") == "important"]
        board = self.queue_board(limit=30)
        running = board["running"][:8]
        return {
            "ok": True,
            "status": self.status(),
            "webhook_configured": bool(self.webhook_url),
            "decisions": decisions[:8],
            "important": important[:8],
            "inbox": inbox[:12],
            "running": running,
            "queued": board["queued"][:8],
            "queue": board,
            "insights": self.day_insights(),
            "agents": self._day_agents(),
            "remote_capabilities": REMOTE_CAPABILITIES,
            "sideboard": self.sideboard(),
            "last_health": self._last_health,
            "counts": {
                "decisions": len(decisions),
                "important": len(important),
                "inbox": len(inbox),
                "running": board["counts"]["running"],
                "queued": board["counts"]["queued"],
                "failed": board["counts"]["failed"],
            },
            "tip": (
                "Plaud, pastas e o resto já vivem no Grok Bot — peça aqui; ele devolve na inbox. "
                "Não reinventamos cliente Plaud no Véu."
                if self.webhook_url
                else "Configure VEU_GROKBOT_WEBHOOK_URL no .env para handoff ao vivo."
            ),
        }

    def health_check(self) -> dict[str, Any]:
        return {
            "ok": True,
            "bridge": "grokbot",
            "mode": "health",
            "webhook_configured": bool(self.webhook_url),
            "secret_configured": bool(self.webhook_secret),
            "queue_depth": len(self._queue),
            "inbound_depth": len(self._inbound),
            "last_health": self._last_health,
            "callback": "http://169.58.19.232:8821/bridge/grokbot/inbound",
            "ts": time.time(),
        }

    def wait_for_job(
        self,
        job_id: str,
        *,
        timeout_s: float = 90.0,
        poll_s: float = 1.5,
    ) -> dict[str, Any] | None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            for job in self._queue:
                if job.get("job_id") == job_id or job.get("id") == job_id:
                    state = job.get("state")
                    if state in {"completed", "waiting", "failed", "approved"}:
                        return {
                            "job_id": job_id,
                            "state": state,
                            "result": job.get("result"),
                            "message": _message_from_result(job),
                        }
            for ev in reversed(self._inbound):
                p = ev.get("payload") or {}
                if (p.get("job_id") or p.get("id")) == job_id:
                    return {
                        "job_id": job_id,
                        "state": p.get("state") or ev.get("kind") or "completed",
                        "result": p.get("result"),
                        "message": p.get("message") or "",
                        "kind": p.get("kind") or ev.get("kind"),
                    }
            time.sleep(poll_s)
        return None

    def recent(self, limit: int = 20) -> dict[str, Any]:
        return {
            "outbound": list(reversed(self._queue[-limit:])),
            "inbound": list(reversed(self._inbound[-limit:])),
            "last_health": self._last_health,
            "inbox": self.inbox(limit=limit),
        }


def _control_live_present() -> bool:
    try:
        from veu.bridges.control_live import _paths

        return any(p.is_file() for p in _paths())
    except Exception:  # noqa: BLE001
        return False


def _looks_like_sideboard(payload: dict[str, Any]) -> bool:
    src = str(payload.get("source") or "").lower()
    if src in {"plaud", "control", "live", "productivity"}:
        return True
    result = payload.get("result")
    if not isinstance(result, dict):
        return False
    return any(
        k in result
        for k in ("productivity", "health", "meetings", "agenda", "inbox", "focus")
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _message_from_result(job: dict[str, Any]) -> str:
    result = job.get("result")
    if isinstance(result, dict):
        return str(result.get("summary") or result.get("message") or "")
    if isinstance(result, str):
        return result
    return ""


def _slim_formation(formation: dict[str, Any] | None) -> dict[str, Any]:
    if not formation:
        return {}
    keep = {
        "intent",
        "breath",
        "kind",
        "title",
        "connectors",
        "agents",
        "skills",
        "jev",
        "status",
        "via",
        "agent",
        "approved_job",
        "note",
    }
    out = {k: formation[k] for k in keep if k in formation}
    steps = formation.get("steps") or []
    if steps:
        out["steps"] = [
            {"id": s.get("id"), "label": s.get("label")} for s in steps[:12] if isinstance(s, dict)
        ]
    return out


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return (r.text or "")[:500]

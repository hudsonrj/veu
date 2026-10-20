from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from veu.bridges import BridgeBus
from veu.connectors import NotionAdapter, OpenRAGAdapter, default_registry
from veu.ecc import EccCatalog
from veu.harness import Harness
from veu.jev import JevRouter
from veu.llm import SYSTEM_OS, HybridLLM
from veu.memory import Memory
from veu.urls import extract_url, wants_open_url
from veu import host_actions

# Words that must never appear in user-facing chat replies.
_INTERNAL = re.compile(
    r"\b(h[ií]brid[oa]|forma[cç][aã]o|barramento|nervos?|weave|kernel|"
    r"respira[cç][aã]o|connector|adapter|system\s*one|ecc)\b",
    re.I,
)


def _ecc_root() -> Path | None:
    env = os.environ.get("VEU_ECC_ROOT")
    if env and Path(env).is_dir():
        return Path(env)
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "vendor" / "ecc",
        Path("/home/ubuntu/veu/vendor/ecc"),
        Path("/root/veu/vendor/ecc"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _sanitize_reply(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    # Drop sentences that are pure internal jargon leakage
    parts = re.split(r"(?<=[.!?])\s+", t)
    kept = [p for p in parts if not _INTERNAL.search(p)]
    out = " ".join(kept).strip() if kept else t
    out = _INTERNAL.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ·,-")
    return out or t


def _status_for_route(route: str) -> str:
    return {
        "chat": "…",
        "openrag": "consultando a base…",
        "notion": "olhando o Notion…",
        "grokbot": "enviando pra nuvem…",
        "comm": "preparando mensagens…",
        "browser": "navegando…",
        "files": "olhando arquivos…",
        "system": "no sistema…",
        "mcp": "chamando ferramentas…",
        "host": "na máquina local…",
        "system": "no PC…",
        "comm": "abrindo mensagens…",
    }.get(route, "…")


def _waited_message(waited: dict[str, Any]) -> str:
    msg = waited.get("message") or ""
    result = waited.get("result")
    if not msg and isinstance(result, dict):
        msg = str(result.get("summary") or result.get("message") or "")
    elif not msg and isinstance(result, str):
        msg = result
    return _sanitize_reply(str(msg))


@dataclass
class Runtime:
    """Kernel do Véu — SO administrado por IA."""

    adapters: dict[str, Any] = field(default_factory=dict)
    connectors: Any = field(default_factory=default_registry)
    ecc: EccCatalog = field(default_factory=lambda: EccCatalog(_ecc_root()))
    memory: Memory = field(default_factory=Memory)
    notion: NotionAdapter = field(default_factory=NotionAdapter)
    openrag: OpenRAGAdapter = field(default_factory=OpenRAGAdapter)
    bridges: BridgeBus = field(default_factory=BridgeBus)
    llm: HybridLLM = field(default_factory=HybridLLM)
    jev: JevRouter = field(default_factory=JevRouter)
    harness: Harness = field(default_factory=Harness)
    studio: Any = field(default=None)

    def __post_init__(self) -> None:
        if self.studio is None:
            from veu.studio import StudioEngine

            self.studio = StudioEngine(self)
        self.refresh_connector_status()
        self.adapters.setdefault("memory", self.memory)
        self.adapters.setdefault("notion", self.notion)
        self.adapters.setdefault("openrag", self.openrag)
        self.adapters.setdefault("bridges", self.bridges)
        self.adapters.setdefault("llm", self.llm)
        self.adapters.setdefault("jev", self.jev)
        self.adapters.setdefault("harness", self.harness)
        self.adapters.setdefault("studio", self.studio)

    def refresh_connector_status(self) -> None:
        """Reaplica status live/ready a partir do .env e adapters (sempre fresco)."""
        from veu.connectors.hydrate import hydrate_connectors
        from veu.mcp import bus as mcp_bus

        hydrate_connectors(
            self.connectors,
            bridges=self.bridges,
            jev=self.jev,
            notion=self.notion,
            openrag=self.openrag,
        )
        mcp_bus.sync_registry(self.connectors)

    def pulse(self) -> dict[str, Any]:
        self.refresh_connector_status()
        return {
            "product": "véu",
            "layer": "kernel",
            "mode": "ai-administered-os",
            "host": "windows|linux",
            "repo": "/home/ubuntu/veu",
            "connectors": len(self.connectors.all()),
            "ecc_agents": len(self.ecc.agents),
            "ecc_skills": len(self.ecc.skills),
            "ecc_root": str(_ecc_root() or ""),
            "memory": self.memory.pulse(),
            "notion": self.notion.status(),
            "openrag": self.openrag.pulse(),
            "bridges": self.bridges.pulse(),
            "llm": self.llm.pulse(),
            "jev": self.jev.pulse(),
            "harness": self.harness.pulse(),
            "adapters": sorted(self.adapters),
            "status": "alive",
        }

    def mission(self) -> dict[str, Any]:
        """Painel de missão: projetos ao vivo a partir do harness + memória."""
        self.refresh_connector_status()
        hp = self.harness.pulse()
        recent_raw = list(hp.get("recent") or [])
        # Dedup por id — fica o estado mais recente
        by_id: dict[str, dict[str, Any]] = {}
        for row in recent_raw:
            rid = str(row.get("id") or "")
            if not rid:
                continue
            prev = by_id.get(rid)
            if prev is None or float(row.get("ts") or 0) >= float(prev.get("ts") or 0):
                by_id[rid] = row
        projects = sorted(
            by_id.values(),
            key=lambda r: float(r.get("ts") or 0),
            reverse=True,
        )[:12]
        agents = [
            {
                "id": a.id,
                "title": a.title,
                "role": a.role,
                "triggers": list(a.triggers)[:6],
            }
            for a in list(self.ecc.agents.values())[:24]
        ]
        live_nerves = [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "kind": getattr(c.kind, "value", str(c.kind)),
            }
            for c in self.connectors.all()
            if c.status in {"live", "ready"}
        ]
        return {
            "status": "alive",
            "harness": {
                "active": hp.get("active"),
                "session": hp.get("session"),
            },
            "projects": [
                {
                    "id": p.get("id"),
                    "intent": p.get("intent"),
                    "route": p.get("route"),
                    "kind": p.get("kind"),
                    "state": p.get("state") or p.get("reason") or "unknown",
                    "breath": p.get("breath"),
                    "tools": p.get("tools") or [],
                    "risk": p.get("risk_ceiling"),
                    "ts": p.get("ts"),
                    "ended": p.get("ended"),
                }
                for p in projects
            ],
            "agents": agents,
            "nerves": live_nerves,
            "jev": self.jev.pulse(),
            "bridges": self.bridges.pulse(),
            "memory": self.memory.pulse(),
            "llm": self.llm.pulse(),
            "actions": [
                {
                    "id": "pulse-nerves",
                    "label": "auditar nervos",
                    "intent": "faça um pulso completo dos nervos live e me diga o que está no ar",
                    "agent": "chief-of-staff",
                },
                {
                    "id": "rag-scan",
                    "label": "varrer OpenRAG",
                    "intent": "o que há de mais relevante na base OpenRAG agora? resuma em 5 bullets",
                    "agent": "doc-updater",
                },
                {
                    "id": "open-control",
                    "label": "abrir control",
                    "intent": "acesse https://control.ch8ai.com.br",
                    "agent": "planner",
                },
                {
                    "id": "grok-handoff",
                    "label": "handoff Grok",
                    "intent": "mande pro grokbot: monitore o Véu e me avise se o kernel cair",
                    "agent": "chief-of-staff",
                },
                {
                    "id": "grok-day-brief",
                    "label": "briefing Grok",
                    "intent": "mande pro grokbot via chefe de gabinete: resuma o que importa hoje e o que precisa da minha OK",
                    "agent": "chief-of-staff",
                },
                {
                    "id": "grok-local-prep",
                    "label": "prep máquina",
                    "intent": "abra o gmail e o notion no host e peça ao grokbot um checklist do dia",
                    "agent": "planner",
                },
                {
                    "id": "build-connector",
                    "label": "construir conector",
                    "intent": "planeje passo a passo como ligar um novo conector MCP ao Véu",
                    "agent": "architect",
                },
                {
                    "id": "free-run",
                    "label": "missão livre",
                    "intent": "em autonomia livre, proponha a próxima melhoria de alto impacto para o Véu OS e execute o primeiro passo seguro",
                    "agent": "planner",
                },
            ],
            "flight": self.flight_board(),
        }

    def flight_board(self) -> dict[str, Any]:
        from veu.flight import readiness

        return readiness(self)

    def weave(self, intent: str, breath: str = "guided") -> dict[str, Any]:
        matched = self.connectors.match(intent)
        agents = self.ecc.match_agents(intent)
        skills = self.ecc.match_skills(intent)

        jev_decision = self.jev.classify(intent)
        kind = self._resolve_kind(intent, breath, matched, jev_decision)
        route = self._resolve_route(intent, kind, matched, jev_decision)
        # Chamar Arquiteto / skill ECC → fica no chat do SO (não "no PC")
        lower_i = intent.lower()
        if any(
            k in lower_i
            for k in (
                "ative o agente",
                "ativar o agente",
                "use a skill",
                "usar a skill",
                "skill ecc",
                "agente ecc",
            )
        ):
            kind = "task"
            route = "chat"
            jev_decision = {
                **jev_decision,
                "kind": "task",
                "route": "chat",
                "agentic_flag": True,
                "source": "ecc-activate",
            }
        bridge_route = self.bridges.route_intent(intent, breath)

        # User-facing titles — no "Formação … / híbrido"
        title_map = {
            "greeting": "",
            "question": "resposta",
            "comm": "mensagens",
            "workspace": "workspace",
            "openrag": "base documental",
            "browser": "navegação",
            "files": "arquivos",
            "mcp": "conexões",
            "system": "sistema",
            "host": "máquina local",
            "grokbot": "Grok Bot",
            "openclaw": "OpenClaw",
            "hermes": "aprendizado",
            "task": "tarefa",
            "hybrid": "tarefa",
        }

        if kind in {"greeting", "question"}:
            steps: list[dict[str, str]] = []
            status = ""
        else:
            steps = list(self._plan_steps(intent, breath, kind, matched, agents, skills))
            status = {
                "guided": "quando quiser, confirmo e sigo",
                "semi": "avanço e só peço o delicado",
                "free": "seguindo com autonomia",
                "autonomous": "varri o SO e trouxe propostas pra você escolher",
            }.get(breath, "")

        # Modo autônomo: varredura → quadro de ações (usuário escolhe)
        auto_board = None
        if breath == "autonomous":
            try:
                from veu import autonomous as veu_auto

                auto_board = veu_auto.scan(runtime=self)
            except Exception as e:  # noqa: BLE001
                auto_board = {"ok": False, "error": str(e)[:160]}

        reply = self._reply(intent, breath, kind, matched, agents, jev_decision)
        if breath == "autonomous" and isinstance(auto_board, dict) and auto_board.get("ok"):
            n = int(auto_board.get("upserted") or 0)
            open_n = int(((auto_board.get("board") or {}).get("counts") or {}).get("open") or 0)
            reply = (
                f"Modo autônomo: percorri apps e agentes e preparei {n} ações "
                f"({open_n} abertas no quadro). Abra Produtividade → Ações, "
                f"escolha o que fazer e marque como feito. {reply}"
            ).strip()

        formation = {
            "intent": intent,
            "breath": breath,
            "kind": kind,
            "route": route,
            "title": title_map.get(kind, ""),
            "reply": reply,
            "connectors": [
                {"id": c.id, "name": c.name, "surface": c.surface, "status": c.status}
                for c, _ in matched
            ],
            "agents": [{"id": a.id, "title": a.title, "role": a.role} for a in agents],
            "skills": [{"id": s.id, "title": s.title} for s in skills],
            "bridge": bridge_route,
            "jev": jev_decision,
            "agentic": bool(jev_decision.get("agentic_flag")),
            "agentic_score": float(jev_decision.get("agentic") or 0.0),
            "autonomous": auto_board,
            "harness": None,
            "steps": steps,
            "execution": None,
            "status": status,
        }
        self.memory.append(
            "weave",
            {
                "intent": intent,
                "breath": breath,
                "kind": kind,
                "route": route,
                "jev": jev_decision,
            },
            sink="sessions",
        )
        return formation

    def _resolve_kind(
        self,
        intent: str,
        breath: str,
        matched: list,
        jev_decision: dict[str, Any],
    ) -> str:
        # Explicit bridges win when user names them
        bridge_route = self.bridges.route_intent(intent, breath)
        if bridge_route and bridge_route["bridge"] in {"grokbot", "openclaw", "hermes"}:
            return bridge_route["bridge"]

        # PC local — abrir apps / e-mail / terminal (não deixa o Jev virar "mcp")
        if host_actions.wants_host(intent):
            return "host"

        kind = str(jev_decision.get("kind") or "task")
        conf = float(jev_decision.get("confidence") or 0.0)

        # Map Jev kinds onto runtime kinds
        if kind == "greeting":
            return "greeting"
        if kind == "openrag":
            return "openrag"
        if kind == "question":
            return "question"
        if kind in {
            "comm",
            "workspace",
            "browser",
            "files",
            "system",
            "grokbot",
            "openclaw",
            "hermes",
            "task",
        }:
            if conf >= 0.45 or jev_decision.get("source") == "jev":
                # Se o match de conector aponta OpenRAG, prioriza
                if matched and matched[0][0].id == "openrag":
                    return "openrag"
                if matched and matched[0][0].id == "notion":
                    return "workspace"
                return kind if kind != "task" else self._legacy_kind(intent, matched)

        return self._legacy_kind(intent, matched)

    def _resolve_route(
        self,
        intent: str,
        kind: str,
        matched: list,
        jev_decision: dict[str, Any],
    ) -> str:
        """Destino do chat central (Jev route → execução)."""
        route = str(jev_decision.get("route") or "")
        conf = float(jev_decision.get("route_confidence") or 0.0)
        if route and conf >= 0.45:
            # Alinha kind explícito
            if kind == "grokbot":
                return "grokbot"
            if kind == "openrag":
                return "openrag"
            if kind == "browser":
                return "browser"
            if kind == "greeting":
                return "chat"
            return route
        # Fallbacks
        if kind in {"greeting"}:
            return "chat"
        if kind == "grokbot":
            return "grokbot"
        if kind == "openrag":
            return "openrag"
        if kind == "browser":
            return "browser"
        if kind == "host":
            return "host"
        if kind == "workspace" or (matched and matched[0][0].id == "notion"):
            return "notion"
        if matched and matched[0][0].id == "openrag":
            return "openrag"
        if kind == "question" and self.openrag.live:
            return "openrag"
        if kind in {"comm", "browser", "files", "system", "mcp", "host"}:
            return kind
        return "chat"

    def _legacy_kind(self, intent: str, matched: list) -> str:
        lower = intent.lower()
        if matched and matched[0][0].id == "openrag":
            return "openrag"
        if host_actions.wants_host(intent):
            return "host"
        if matched and matched[0][0].kind.value in {"comm", "mail"}:
            return "comm"
        if matched and matched[0][0].id in {"notion", "google"}:
            return "workspace"
        if any(k in lower for k in ("openrag", "ragpro", "na base", "documentos da base")):
            return "openrag"
        if wants_open_url(intent) or self._url_from_context(intent):
            return "browser"
        if any(k in lower for k in ("site", "página", "pagina", "browser", "web", "link")):
            return "browser"
        if any(k in lower for k in ("arquivo", "pasta", "documento")):
            return "files"
        if "mcp" in lower:
            return "mcp"
        if any(k in lower for k in ("sistema", "terminal", "shell", "administr")):
            return "system"
        return "task"

    def _url_from_context(self, intent: str) -> str | None:
        """URL no pedido atual ou na memória recente (ex.: 'acesse esse site')."""
        direct = extract_url(intent)
        if direct:
            return direct
        lower = intent.lower()
        if not any(
            k in lower
            for k in (
                "esse site",
                "este site",
                "aquele site",
                "esse link",
                "este link",
                "a url",
                "o site",
                "acesse",
                "acessar",
                "abra",
                "abrir",
            )
        ):
            return None
        for ev in reversed(self.memory.recent(limit=30)):
            for key in ("intent", "message", "text"):
                cand = ev.get(key)
                if isinstance(cand, str):
                    found = extract_url(cand)
                    if found:
                        return found
            exe = ev.get("execution") or {}
            if isinstance(exe, dict):
                u = exe.get("url") or (exe.get("action") or {}).get("url")
                if isinstance(u, str) and u.startswith("http"):
                    return u
        return None

    def stream_weave(self, intent: str, breath: str = "guided") -> Iterator[dict[str, Any]]:
        """Chat central: Jev decide → executa no destino → espera → responde."""
        yield {"type": "status", "text": "…"}
        self._last_llm_handoff = None
        plan = self.weave(intent, breath)
        kind = plan.get("kind")
        route = plan.get("route") or "chat"

        # Qualquer handoff residual: descarta URL e responde no SO
        self._last_llm_handoff = None
        if plan.get("execution") and isinstance(plan["execution"], dict):
            act = plan["execution"].get("action") or {}
            url = plan["execution"].get("url") or act.get("url") or ""
            if isinstance(url, str) and any(
                h in url for h in ("chatgpt.com", "claude.ai", "grok.com", "accounts.x.ai")
            ):
                plan["execution"] = {
                    "ok": True,
                    "status": "stay_in_veu",
                    "message": plan.get("reply") or "Fico no Véu — sem abrir outra aba.",
                }

        # Força kind alinhado à rota para o executor
        plan["kind"] = self._kind_for_route(route, kind)

        agentic = self.harness.is_agentic(
            intent=intent,
            kind=plan["kind"],
            route=route,
            jev=plan.get("jev") or {},
        )
        plan["agentic"] = agentic
        plan["agentic_score"] = float((plan.get("jev") or {}).get("agentic") or 0.0)

        # Telemetria ao vivo — o desktop desenha a construção
        yield {"type": "plan", "formation": plan}
        steps = list(plan.get("steps") or [])
        for i, step in enumerate(steps):
            yield {
                "type": "step",
                "index": i,
                "step": step,
                "state": "pending",
            }

        if plan["kind"] != "greeting":
            # Ações agênticas → harness automático
            if agentic:
                channel = self.bridges.openclaw.detect_channel(intent)
                session = self.harness.activate(
                    intent=intent,
                    route=route,
                    kind=plan["kind"],
                    breath=breath,
                    channel=channel,
                )
                plan["harness"] = {
                    "id": session["id"],
                    "tools": session["tools"],
                    "risk_ceiling": session["risk_ceiling"],
                    "route": session["route"],
                }
                yield {
                    "type": "status",
                    "text": f"ferramentas ativas · {len(session['tools'])}",
                }
                yield {
                    "type": "harness",
                    "active": True,
                    "session": plan["harness"],
                }
                self.memory.append(
                    "harness.activate",
                    plan["harness"],
                    sink="decisions",
                )

            for i, step in enumerate(steps):
                yield {
                    "type": "step",
                    "index": i,
                    "step": step,
                    "state": "running",
                }

            yield {
                "type": "status",
                "text": _status_for_route(route),
            }
            if self._should_auto_run(plan["kind"], breath, intent) or route in {
                "openrag",
                "notion",
                "grokbot",
                "browser",
                "host",
                "comm",
                "system",
                "files",
                "mcp",
            } or agentic or wants_open_url(intent) or host_actions.wants_host(intent) or "mcpServers" in intent:
                execution = self._execute_route(intent, plan, route)
                plan["execution"] = execution

                # Grok Bot: espera callback antes de responder
                if route == "grokbot" and execution.get("delivered"):
                    job_id = (execution.get("job") or {}).get("job_id")
                    yield {"type": "status", "text": "aguardando a nuvem…"}
                    waited = None
                    if job_id:
                        waited = self.bridges.grokbot.wait_for_job(
                            job_id, timeout_s=90.0, poll_s=1.5
                        )
                    plan["awaited"] = waited
                    if waited:
                        msg = _waited_message(waited)
                        if waited.get("state") == "waiting" or waited.get("kind") == "needs_approval":
                            plan["reply"] = msg or (
                                "Preciso da sua aprovação pra seguir. Pode confirmar?"
                            )
                        elif msg:
                            plan["reply"] = self._reply_with_result(
                                intent, "grokbot", plan["reply"], msg
                            )
                        else:
                            plan["reply"] = "Pronto — a nuvem terminou o que pedi."
                    else:
                        plan["reply"] = (
                            "Mandei pra nuvem e ainda estou esperando. "
                            "Quando voltar, te conto aqui."
                        )
                else:
                    msg = _sanitize_reply(str(execution.get("message") or ""))
                    if msg:
                        # MCP / host / ações: resposta direta (não concatena plano genérico)
                        if (
                            execution.get("action")
                            or execution.get("actions")
                            or execution.get("ok")
                            or execution.get("status")
                            in {"mcp", "host", "need_json", "need_token", "need_url"}
                        ):
                            plan["reply"] = msg
                        else:
                            plan["reply"] = self._reply_with_result(
                                intent, plan["kind"], plan["reply"], msg
                            )
                    actions = execution.get("actions")
                    if not isinstance(actions, list) or not actions:
                        primary = execution.get("action")
                        actions = [primary] if isinstance(primary, dict) else []
                    for action in actions:
                        if not isinstance(action, dict) or not action.get("type"):
                            continue
                        yield {
                            "type": "action",
                            "action": action.get("type"),
                            "url": action.get("url"),
                            "app": action.get("app"),
                            "payload": action,
                        }

            for i, step in enumerate(steps):
                yield {
                    "type": "step",
                    "index": i,
                    "step": step,
                    "state": "done",
                }

            if agentic:
                self.harness.deactivate(reason="done")
                yield {"type": "harness", "active": False}

        self.memory.append(
            "chat",
            {
                "intent": intent,
                "breath": breath,
                "kind": plan.get("kind"),
                "route": route,
                "agentic": agentic,
                "harness": plan.get("harness"),
                "reply": plan["reply"],
                "execution": plan.get("execution"),
                "awaited": plan.get("awaited"),
                "jev": plan.get("jev"),
            },
            sink="audit",
        )
        yield {"type": "reply", "text": plan["reply"]}
        yield {"type": "done", "formation": plan}

    def _kind_for_route(self, route: str, kind: str) -> str:
        mapping = {
            "chat": kind if kind in {"greeting", "question", "task"} else "task",
            "openrag": "openrag",
            "notion": "workspace",
            "grokbot": "grokbot",
            "comm": "comm",
            "browser": "browser",
            "files": "files",
            "system": "system",
            "mcp": "mcp",
        }
        return mapping.get(route, kind)

    def _execute_route(
        self, intent: str, plan: dict[str, Any], route: str
    ) -> dict[str, Any]:
        if route == "openrag":
            plan["kind"] = "openrag"
            return self._execute(intent, plan)
        if route == "notion":
            plan["kind"] = "workspace"
            return self._execute(intent, plan)
        if route == "grokbot":
            plan["kind"] = "grokbot"
            # chat central age e espera — guided vira semi na ponte
            if plan.get("breath") == "guided":
                plan["breath"] = "semi"
            return self._execute(intent, plan)
        if route == "browser":
            plan["kind"] = "browser"
            return self._execute(intent, plan)
        return self._execute(intent, plan)

    def _should_auto_run(self, kind: str, breath: str, intent: str) -> bool:
        t = intent.lower()
        high = any(
            k in t
            for k in (
                "apagar",
                "deletar",
                "delete",
                "pagar",
                "transferir",
                "publicar",
                "enviar para todos",
                "formatar",
            )
        )
        if high and breath == "guided":
            return False
        if kind in {
            "grokbot",
            "openclaw",
            "hermes",
            "workspace",
            "openrag",
            "comm",
            "task",
            "browser",
            "files",
            "system",
            "mcp",
            "host",
            "question",
        }:
            return True
        return False

    def _reply_with_result(
        self, intent: str, kind: str, base_reply: str, result_msg: str
    ) -> str:
        prompt = (
            f"Mensagem do usuário: {intent.strip()}\n"
            f"Resultado interno (pode usar, sem jargão): {result_msg}\n"
            f"Rascunho: {base_reply}\n"
            "Responda ao usuário em 1–3 frases, só o útil."
        )
        from veu import voice_mode as veu_voice

        llm = self.llm.complete(
            prompt,
            system=veu_voice.compose_system(SYSTEM_OS),
            purpose="chat",
            allow_handoff=False,
            fallback_local=True,
        )
        self._last_llm_handoff = None
        if llm.ok and llm.text and not getattr(llm, "handoff_url", None):
            return _sanitize_reply(llm.text)
        return _sanitize_reply(f"{base_reply} {result_msg}".strip())

    def _execute(self, intent: str, plan: dict[str, Any]) -> dict[str, Any]:
        kind = plan.get("kind")
        breath = plan.get("breath", "guided")
        route = plan.get("route") or ""

        # MCP / Hugging Face — tools de verdade (antes de browser genérico)
        lower_intent = intent.lower()
        if (
            kind == "mcp"
            or route == "mcp"
            or "mcpServers" in intent
            or ("{" in intent and "mcp" in lower_intent)
            or "huggingface" in lower_intent
            or "hugging face" in lower_intent
            or "hf.co" in lower_intent
            or (
                any(k in lower_intent for k in ("modelo", "modelos", "dataset", "whisper", "qwen"))
                and any(k in lower_intent for k in ("pesquis", "busc", "procur", "hub", "hf"))
            )
        ):
            from veu.mcp import bus as mcp_bus

            result = mcp_bus.chat_plan_or_run(intent)
            self.memory.append("mcp.action", result, sink="decisions")
            self.refresh_connector_status()
            if result.get("mcp") or result.get("status") in {"mcp", "need_json", "need_token"}:
                return result
            if result.get("message") and result.get("ok") is not None:
                return result

        # ECC activate (Arquiteto / skills) — NÃO vira ação de PC
        ecc_fast = self._ecc_activate_reply(intent)
        if ecc_fast:
            return {
                "ok": True,
                "status": "ecc",
                "message": ecc_fast,
                "actions": [],
            }

        # Máquina local — apps, e-mail, mensagens, presets (antes de URL genérica)
        # system genérico (ex.: "Code Architect") NÃO força host — só se pediu PC
        hostish = (
            kind in {"host", "comm", "files"}
            or route in {"host", "comm", "files"}
            or host_actions.wants_host(intent)
        )
        if hostish:
            # URL explícita ainda ganha (acesse https://…)
            url_early = self._url_from_context(intent)
            if not (url_early and wants_open_url(intent)):
                result = host_actions.plan_host_actions(intent, breath=breath)
                self.memory.append("host.action", result, sink="decisions")
                if result.get("actions") or result.get("ok") is False:
                    return result

        # Abrir site/URL — sempre tenta, mesmo se o kind veio errado
        url = self._url_from_context(intent)
        if kind == "browser" or route == "browser" or (url and wants_open_url(intent)):
            if not url:
                return {
                    "ok": False,
                    "status": "need_url",
                    "message": "Qual site? Manda o endereço (ex.: control.ch8ai.com.br).",
                }
            host = re.sub(r"^https?://", "", url).split("/")[0]
            result = {
                "ok": True,
                "status": "live",
                "url": url,
                "action": {"type": "open_url", "url": url},
                "message": f"Abrindo {host} numa nova aba.\n{url}",
            }
            self.memory.append("browser.open", result)
            return result

        if kind == "grokbot":
            result = self.bridges.grokbot.handoff(
                intent=intent,
                breath=breath,
                formation=plan,
            )
            self.memory.append("bridge.grokbot.handoff", result, sink="decisions")
            return result

        if kind == "openclaw":
            result = self.bridges.openclaw.plan_dispatch(intent, breath)
            self.memory.append("bridge.openclaw.dispatch", result)
            return result

        if kind == "hermes":
            self.bridges.hermes.observe(intent, kind=kind, ok=True)
            proposal = self.bridges.hermes.maybe_propose(min_repeats=1)
            result = {
                "ok": True,
                "bridge": "hermes",
                "proposal": proposal,
                "pulse": self.bridges.hermes.pulse(),
                "message": (
                    "Anotei o padrão. Posso transformar isso em um procedimento reutilizável."
                    if proposal
                    else "Anotei. Quando repetir, monto um procedimento."
                ),
            }
            self.memory.append("bridge.hermes.observe", result)
            return result

        ids = {c["id"] for c in plan.get("connectors", [])}
        lower = intent.lower()
        wants_notion = "notion" in lower or kind == "workspace"
        wants_openrag = kind == "openrag" or any(
            k in lower for k in ("openrag", "ragpro", "na base", "base documental")
        )

        if wants_notion and not wants_openrag:
            result = self.notion.execute(intent)
            self.memory.append("notion.execute", result)
            self.bridges.hermes.observe(
                intent, kind="workspace", ok=bool(result.get("ok", True))
            )
            if result.get("ok"):
                titles = [r.get("title") for r in result.get("results") or [] if r.get("title")]
                if titles:
                    result["message"] = "No Notion achei: " + "; ".join(titles[:5])
                elif not result.get("message"):
                    result["message"] = "Busquei no Notion e não achei páginas com isso."
            return result

        if wants_openrag or ("openrag" in ids and not wants_notion):
            result = self.openrag.execute(intent)
            self.memory.append("openrag.execute", result)
            if result.get("ok") and result.get("answer"):
                result["message"] = str(result["answer"])
            return result

        if "notion" in ids or kind == "workspace":
            result = self.notion.execute(intent)
            self.memory.append("notion.execute", result)
            self.bridges.hermes.observe(
                intent, kind="workspace", ok=bool(result.get("ok", True))
            )
            return result

        self.bridges.hermes.observe(intent, kind=kind or "task", ok=True)
        return {
            "ok": True,
            "status": "planned",
            "message": "",
            "results": [],
        }

    def _plan_steps(
        self,
        intent: str,
        breath: str,
        kind: str,
        matched: list,
        agents: list,
        skills: list,
    ) -> Iterator[dict[str, str]]:
        yield {"id": "classify", "label": "Entender o pedido", "actor": "véu"}
        if matched:
            names = ", ".join(c.name for c, _ in matched[:3])
            yield {
                "id": "nerves",
                "label": f"Preparar: {names}",
                "actor": "véu",
            }
        if agents:
            yield {
                "id": "agents",
                "label": "Chamar · " + ", ".join(a.title for a in agents[:3]),
                "actor": "véu",
            }
        if skills:
            yield {
                "id": "skills",
                "label": "Usar · " + ", ".join(s.title for s in skills[:3]),
                "actor": "véu",
            }
        if kind == "grokbot":
            yield {
                "id": "bridge",
                "label": "Enviar ao Grok Bot (cloud)",
                "actor": "grokbot",
            }
        elif kind == "openclaw":
            yield {
                "id": "bridge",
                "label": "Preparar canal OpenClaw",
                "actor": "openclaw",
            }
        elif kind == "hermes":
            yield {
                "id": "bridge",
                "label": "Aprendendo com o padrão",
                "actor": "hermes",
            }
        elif kind in {"host", "comm"}:
            yield {
                "id": "host",
                "label": "Ação na máquina local",
                "actor": "host",
            }
        elif kind == "system":
            yield {
                "id": "compose",
                "label": "Montar a ação no SO",
                "actor": "véu",
            }
        elif kind == "openrag":
            yield {
                "id": "openrag",
                "label": "Consultar base documental",
                "actor": "openrag",
            }
        elif kind == "workspace":
            yield {
                "id": "workspace",
                "label": "Abrir workspace",
                "actor": "notion" if self.notion.live else "véu",
            }
        else:
            yield {
                "id": "compose",
                "label": "Montar a ação",
                "actor": "véu",
            }
        # Configurar MCP/host/browser não espera confirmação — executa
        auto_kinds = {"mcp", "host", "browser", "openrag", "notion", "workspace"}
        if (
            breath == "guided"
            and not self._wants_plan(intent)
            and kind not in auto_kinds
            and "hf_" not in intent
            and "mcpServers" not in intent
        ):
            yield {
                "id": "await",
                "label": "Aguardando sua confirmação",
                "actor": "véu",
            }
        else:
            yield {
                "id": "execute",
                "label": "Entregar plano" if self._wants_plan(intent) else "Executar",
                "actor": "véu",
            }

    def _ecc_skill_route_tools(self, skill_id: str) -> tuple[str, list[str]]:
        """Mapeia skill ECC → rota + tools do harness Véu (o que roda de verdade no SO)."""
        sid = skill_id.lower()
        # padrões Claude Code → musculatura Véu equivalente
        if any(k in sid for k in ("harness", "autonomous", "agent-loop", "continuous")):
            return (
                "system",
                [
                    "memory.read",
                    "memory.write",
                    "mcp.list",
                    "mcp.call",
                    "host.app.open",
                    "host.shell",
                    "grokbot.handoff",
                ],
            )
        if any(k in sid for k in ("browser", "qa", "web")):
            return "browser", ["browser.navigate", "browser.read", "browser.click", "memory.write"]
        if any(k in sid for k in ("connector", "api", "mcp", "oauth", "webhook")):
            return "mcp", ["mcp.list", "mcp.call", "memory.write"]
        if any(k in sid for k in ("notion", "doc", "wiki", "content")):
            return "notion", ["notion.search", "notion.read", "memory.write"]
        if any(k in sid for k in ("comm", "slack", "mail", "inbox", "channel")):
            return "comm", ["channel.read", "channel.draft", "memory.write"]
        if any(k in sid for k in ("file", "fs", "disk")):
            return "files", ["host.fs.list", "host.fs.read", "memory.write"]
        return "chat", ["memory.read", "memory.write", "ecc.match"]

    def _ecc_activate_reply(self, intent: str) -> str | None:
        """Ativar skill/agente ECC no SO: liga harness + memória — sem ChatGPT."""
        import re

        lower = intent.lower()
        wants = any(
            k in lower
            for k in (
                "use a skill",
                "usar a skill",
                "use a skill ecc",
                "ative o agente",
                "ativar o agente",
                "ative o agente ecc",
                "skill ecc",
                "agente ecc",
                "rodar skill",
                "acionar",
            )
        )
        if not wants and "ecc" not in lower:
            return None

        sid = None
        m = re.search(
            r"(?:skill|agente)\s+ecc\s+([a-z0-9][\w.-]*)",
            intent,
            flags=re.I,
        )
        if m:
            sid = m.group(1).lower()
        if not sid:
            m = re.search(r"\b([a-z][a-z0-9]+(?:-[a-z0-9]+)+)\b", lower)
            if m:
                sid = m.group(1)

        skill = self.ecc.skills.get(sid) if sid else None
        agent = self.ecc.agents.get(sid) if sid else None
        if not skill and not agent:
            skills = self.ecc.match_skills(intent, limit=1)
            agents = self.ecc.match_agents(intent, limit=1)
            skill = skills[0] if skills else None
            agent = agents[0] if agents else None

        breath = "semi"
        if skill:
            route, extra = self._ecc_skill_route_tools(skill.id)
            session = self.harness.activate(
                intent=intent,
                route=route,
                kind="task",
                breath=breath,
                extra_tools=extra + [f"ecc.skill.{skill.id}"],
            )
            self.memory.append(
                "ecc.skill.active",
                {
                    "id": skill.id,
                    "title": skill.title,
                    "route": route,
                    "harness": session.get("id"),
                    "tools": session.get("tools"),
                },
                sink="decisions",
            )
            tools_txt = " · ".join((session.get("tools") or [])[:10])
            cans = skill.can_do or []
            cans_txt = "\n".join(f"· {c}" for c in cans[:5]) or "· musculatura das formações"
            return (
                f"✓ Skill ECC «{skill.title}» ligada no SO.\n"
                f"Harness {session.get('id')} · rota `{route}` · respiração {breath}\n"
                f"Tools vivas: {tools_txt}\n\n"
                f"{(skill.description or '').strip()[:280]}\n\n"
                f"Cobre:\n{cans_txt}\n\n"
                "Isso já está ativo no Véu (não é abrir ChatGPT). "
                "Manda a tarefa concreta agora — ex.: “triage meu e-mail e Notion” "
                "ou “monitore isso todo dia” — que eu executo com esse harness."
            )
        if agent:
            # Arquiteto / code / planner → chat no SO (não host/system)
            route = "chat"
            if "chief" in agent.id or "inbox" in (agent.role or "").lower():
                route = "comm"
            if "doc" in agent.id:
                route = "notion"
            session = self.harness.activate(
                intent=intent,
                route=route,
                kind="task",
                breath=breath,
                extra_tools=[f"ecc.agent.{agent.id}"],
            )
            self.memory.append(
                "ecc.agent.active",
                {
                    "id": agent.id,
                    "title": agent.title,
                    "route": route,
                    "harness": session.get("id"),
                    "tools": session.get("tools"),
                },
                sink="decisions",
            )
            tools_txt = " · ".join((session.get("tools") or [])[:10])
            cans = agent.can_do or []
            cans_txt = "\n".join(f"· {c}" for c in cans[:5]) or "· especialista ECC"
            return (
                f"✓ Agente ECC «{agent.title}» no posto no SO.\n"
                f"Harness {session.get('id')} · rota `{route}`\n"
                f"Tools vivas: {tools_txt}\n\n"
                f"{(agent.role or agent.description or '').strip()}\n\n"
                f"Pode:\n{cans_txt}\n\n"
                "Manda a tarefa — ele assume daqui, dentro do Véu."
            )
        if wants:
            return (
                f"ECC no SO: {len(self.ecc.agents)} agentes · {len(self.ecc.skills)} skills. "
                "Abra ECC e clique «usar», ou diga o id "
                "(ex.: “use a skill ECC autonomous-agent-harness”)."
            )
        return None

    def _wants_plan(self, intent: str) -> bool:
        lower = intent.lower()
        return any(
            k in lower
            for k in (
                "planeje",
                "planejar",
                "passo a passo",
                "passo-a-passo",
                "como ligar",
                "como conectar",
                "como fazer",
                "checklist",
                "roteiro",
            )
        )

    def _deterministic_plan(self, intent: str, kind: str) -> str | None:
        """Plano útil sem LLM — evita o loop 'me diga o próximo passo'."""
        lower = intent.lower()
        if "mcp" in lower or kind == "mcp":
            # se já trouxe token/JSON, não enche linguiça — o execute liga
            if "hf_" in intent or "mcpServers" in intent or "{" in intent:
                return None
            return (
                "Pra ligar um MCP: diga o nome + token (ex. Hugging Face e hf_…) "
                "ou cole o JSON em Ajustes → MCP / no chat. Eu configuro sozinho."
            )
        if self._wants_plan(intent):
            return (
                "Vamos por passos:\n"
                "1. Deixar claro o objetivo e o que já existe no Véu.\n"
                "2. Listar o que falta (credencial, adapter, UI, teste).\n"
                "3. Implementar o mínimo que funciona.\n"
                "4. Validar no chat / Mission Control.\n"
                "5. Só então automatizar.\n"
                f"Sobre o seu pedido (“{intent.strip()[:120]}”): me diga o alvo "
                "exato (app/serviço) que eu avanço no passo 2 agora."
            )
        return None

    def _reply(
        self,
        intent: str,
        breath: str,
        kind: str,
        matched: list,
        agents: list,
        jev_decision: dict[str, Any] | None = None,
    ) -> str:
        # Caminhos rápidos — sem esperar modelo
        if kind == "greeting":
            return "Oi. Em que posso te ajudar?"

        lower = intent.lower()
        if any(
            k in lower
            for k in (
                "consegue fazer",
                "pode fazer",
                "o que você",
                "o que voce",
                "o que consegue",
                "pra que serve",
                "para que serve",
            )
        ):
            return (
                "Posso te ajudar no dia a dia: mensagens, e-mail, Notion, "
                "navegação, arquivos do PC e tarefas longas na nuvem. "
                "É só dizer o que precisa."
            )
        if kind == "grokbot":
            return "Posso mandar isso pro teammate na nuvem pra rodar enquanto você faz outra coisa."

        # PC local — resposta imediata (não espera OpenAI/Ollama)
        if kind == "host" or host_actions.wants_host(intent):
            preview = host_actions.plan_host_actions(intent, breath=breath)
            if preview.get("message"):
                return str(preview["message"])

        # MCP — resposta imediata (JSON/token/list); LLM morto não pode travar
        if (
            kind == "mcp"
            or "mcp" in lower
            or "mcpServers" in intent
            or "hf_" in intent
            or "huggingface" in lower
            or "hugginface" in lower
        ):
            from veu.mcp import bus as mcp_bus

            preview = mcp_bus.chat_plan_or_run(intent)
            if preview.get("message"):
                return str(preview["message"])

        # ECC agente/skill — responde no SO, sem ChatGPT / aba
        ecc_msg = self._ecc_activate_reply(intent)
        if ecc_msg:
            return ecc_msg

        # Plano pedido → já entrega (LLM só polui/atrasa se a key estiver morta)
        planned = self._deterministic_plan(intent, kind)
        if planned and self._wants_plan(intent):
            # Ainda tenta LLM pra enriquecer; se falhar, fica o plano sólido
            context_bits = []
            if agents:
                context_bits.append(
                    "especialistas: " + ", ".join(a.title for a in agents[:2])
                )
            prompt = (
                f"Mensagem do usuário: {intent.strip()}\n"
                f"Contexto: kind={kind}; {'; '.join(context_bits) or 'nenhum'}.\n"
                "Responda em português com um plano numerado (5–8 passos), "
                "prático, sem jargão interno. Sem pedir 'me diga o próximo passo'."
            )
            from veu import voice_mode as veu_voice

            llm = self.llm.complete(
                prompt,
                system=veu_voice.compose_system(SYSTEM_OS),
                purpose="chat",
                allow_handoff=False,
                fallback_local=True,
            )
            self._last_llm_handoff = None
            if llm.ok and llm.text and "próximo passo que eu faço" not in llm.text.lower():
                return _sanitize_reply(llm.text)
            return planned

        context_bits = []
        if matched:
            context_bits.append(
                "ferramentas relevantes: " + ", ".join(c.name for c, _ in matched[:3])
            )
        if agents:
            context_bits.append(
                "especialistas: " + ", ".join(a.title for a in agents[:2])
            )
        mode_hint = {
            "guided": "peça confirmação antes de ações delicadas",
            "semi": "avance e só peça o delicado",
            "free": "pode executar com autonomia",
            "autonomous": "propostas prontas; o usuário escolhe",
        }.get(breath, "")

        from veu import voice_mode as veu_voice

        voice = veu_voice.get()
        voice_hint = (
            "Fale como o próprio usuário (Clone ativo) — 1ª pessoa, jeito dele."
            if voice == "clone"
            else ""
        )

        prompt = (
            f"Mensagem do usuário: {intent.strip()}\n"
            f"Contexto interno (NÃO repetir jargão): kind={kind}; "
            f"{'; '.join(context_bits) or 'nenhum'}; {mode_hint}. {voice_hint}\n"
            "Responda só ao usuário, útil e direto. Se for plano, use passos numerados. "
            "Nunca diga apenas 'me diga o próximo passo'."
        )
        llm = self.llm.complete(
            prompt,
            system=veu_voice.compose_system(SYSTEM_OS),
            purpose="chat",
            allow_handoff=False,
            fallback_local=True,
        )
        # Sem handoff de URL — conversa fica no SO
        self._last_llm_handoff = None
        if llm.ok and llm.text and not getattr(llm, "handoff_url", None):
            text = _sanitize_reply(llm.text)
            # Nunca ecoar texto de handoff de assinatura
            if text and "abro o chat da assinatura" not in text.lower():
                if "próximo passo que eu faço" not in text.lower():
                    return text

        if planned:
            return planned
        if matched:
            names = ", ".join(c.name for c, _ in matched[:2])
            return f"Beleza — cuido disso com {names}. Quer que eu comece agora?"
        if kind == "question":
            return "Me conta o que você precisa e eu te respondo direto."
        return (
            "Entendi o pedido, mas o modelo de chat falhou agora "
            "(chave OpenAI inválida / Ollama lento). "
            "Reformule em uma ação concreta — ou atualize a OPENAI_API_KEY em Ajustes → assinaturas."
        )

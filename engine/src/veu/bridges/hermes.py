"""Padrões Hermes (Nous) no Véu — learning loop + fila local + skills.

Hermes cria skills a partir da experiência. No Véu: após formações
repetidas, propor skill ECC sanitizada (padrão hermes-imports).

Também expõe fila de jobs locais (Studio / Chat) para a Agenda do SO.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


def _data_root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _queue_path() -> Path:
    return _data_root() / "hermes_queue.jsonl"


def _load_queue() -> list[dict[str, Any]]:
    path = _queue_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows


def _append_queue(job: dict[str, Any]) -> None:
    path = _queue_path()
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _pref_path() -> Path:
    return _data_root() / "hermes_preferred_agent.json"


# Agentes Hermes — quem assume o learning loop / distill / memória
HERMES_AGENTS: list[dict[str, str]] = [
    {
        "id": "hermes-operator",
        "label": "operador",
        "hint": "learning loop padrão · observa e enfileira",
    },
    {
        "id": "skill-distiller",
        "label": "distilador",
        "hint": "transforma padrões repetidos em skill ECC",
    },
    {
        "id": "memory-curator",
        "label": "curador",
        "hint": "organiza memória e vault do operador",
    },
    {
        "id": "architect",
        "label": "arquiteto",
        "hint": "desenho técnico · trade-offs (ECC)",
    },
    {
        "id": "planner",
        "label": "planejador",
        "hint": "quebra pedidos em passos (ECC)",
    },
    {
        "id": "chief-of-staff",
        "label": "chefe de gabinete",
        "hint": "triagem e priorização do dia (ECC)",
    },
    {
        "id": "code-reviewer",
        "label": "revisor",
        "hint": "qualidade e riscos de código (ECC)",
    },
]


class HermesBridge:
    """Observa formações, propõe skills e mantém fila local visível no SO."""

    def __init__(self) -> None:
        self.home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
        self.api_url = (
            os.environ.get("HERMES_API_URL")
            or os.environ.get("VEU_HERMES_API")
            or ""
        ).rstrip("/")
        self._seen: list[str] = []
        self._proposals: list[dict[str, Any]] = []
        self._queue: list[dict[str, Any]] = _load_queue()
        self._preferred_agent = self._load_preferred()

    def _load_preferred(self) -> str:
        path = _pref_path()
        if not path.exists():
            return "hermes-operator"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            aid = str(data.get("agent") or "hermes-operator")
            if any(a["id"] == aid for a in HERMES_AGENTS):
                return aid
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        return "hermes-operator"

    def set_preferred_agent(self, agent_id: str) -> dict[str, Any]:
        aid = (agent_id or "").strip() or "hermes-operator"
        meta = next((a for a in HERMES_AGENTS if a["id"] == aid), None)
        if not meta:
            return {"ok": False, "error": f"agente desconhecido: {aid}"}
        self._preferred_agent = aid
        try:
            _pref_path().write_text(
                json.dumps({"agent": aid, "ts": time.time()}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
        return {"ok": True, "agent": meta, "preferred": aid}

    def preferred_agent(self) -> dict[str, str]:
        return next(
            (a for a in HERMES_AGENTS if a["id"] == self._preferred_agent),
            HERMES_AGENTS[0],
        )

    def status(self) -> str:
        if self.api_url:
            return "live"
        if os.path.isdir(self.home):
            return "ready"
        return "planned"

    def pulse(self) -> dict[str, Any]:
        board = self.queue_board(limit=20)
        pref = self.preferred_agent()
        return {
            "id": "hermes",
            "name": "Hermes",
            "role": "self-improving-operator-loop",
            "status": self.status(),
            "home": self.home if os.path.isdir(self.home) else None,
            "api_url": self.api_url or None,
            "observations": len(self._seen),
            "proposals": len(self._proposals),
            "queue_depth": len(self._queue),
            "running": board["counts"]["running"],
            "queued": board["counts"]["queued"],
            "patterns": ["learning-loop", "skill-distill", "memory-vault", "local-jobs"],
            "ecc_skills": ["hermes-imports"],
            "modes": ["observe", "propose", "enqueue", "run"],
            "agents": HERMES_AGENTS,
            "preferred_agent": pref,
        }

    def observe(self, intent: str, *, kind: str = "hybrid", ok: bool = True) -> None:
        if not ok:
            return
        key = _normalize(intent)
        if key:
            self._seen.append(key)
            if len(self._seen) > 500:
                self._seen = self._seen[-250:]

    def maybe_propose(self, *, min_repeats: int = 3) -> dict[str, Any] | None:
        counts = Counter(self._seen)
        for pattern, n in counts.most_common(5):
            if n < min_repeats:
                continue
            if any(p.get("pattern") == pattern for p in self._proposals):
                continue
            proposal = {
                "id": f"hp-{uuid.uuid4().hex[:10]}",
                "ts": time.time(),
                "pattern": pattern,
                "repeats": n,
                "suggested_skill": {
                    "name": _slug(pattern)[:48] or "veu-formation",
                    "description": (
                        f"Skill ECC proposta a partir de {n} formações Hermes-style: "
                        f"“{pattern}”."
                    ),
                    "origin": "hermes-loop→veu",
                    "sanitize": True,
                },
                "message": (
                    "Hermes loop: padrão repetido — candidato a skill ECC "
                    "(use hermes-imports para publicar sanitizado)."
                ),
            }
            self._proposals.append(proposal)
            return proposal
        return None

    def recent_proposals(self, limit: int = 10) -> list[dict[str, Any]]:
        return list(reversed(self._proposals[-limit:]))

    def enqueue(
        self,
        *,
        intent: str,
        kind: str = "task",
        payload: dict[str, Any] | None = None,
        source: str = "os",
        agent: str | None = None,
    ) -> dict[str, Any]:
        """Enfileira job local Hermes — aparece na Agenda / Fila do SO."""
        aid = (agent or self._preferred_agent or "hermes-operator").strip()
        meta = next((a for a in HERMES_AGENTS if a["id"] == aid), None)
        if not meta:
            aid = self._preferred_agent
            meta = self.preferred_agent()
        job_id = f"hm-{uuid.uuid4().hex[:10]}"
        job: dict[str, Any] = {
            "id": job_id,
            "job_id": job_id,
            "ts": time.time(),
            "intent": (intent or "")[:500],
            "kind": kind,
            "state": "queued",
            "source": "hermes",
            "via": source,
            "agent": aid,
            "agent_label": meta.get("label") if meta else aid,
            "payload": payload or {},
        }
        # Se API local ligada, marca como dispatched; senão processa no loop local
        if self.api_url:
            job["state"] = "dispatched"
            job["message"] = f"enviado ao Hermes API ({self.api_url}) · agente {meta.get('label', aid)}"
        else:
            job["state"] = "running"
            job["message"] = f"Hermes local · {meta.get('label', aid)}"
        self._queue.append(job)
        if len(self._queue) > 200:
            self._queue = self._queue[-100:]
        _append_queue(job)
        self.observe(intent, kind=kind, ok=True)
        return {"ok": True, "job": job, "status": self.status(), "agent": meta}

    def complete(self, job_id: str, *, result: dict[str, Any] | None = None) -> dict[str, Any]:
        for job in self._queue:
            if job.get("job_id") == job_id or job.get("id") == job_id:
                job["state"] = "completed"
                job["result"] = result or {}
                job["message"] = str((result or {}).get("message") or "concluído")
                _append_queue({**job, "ts": time.time(), "event": "complete"})
                return {"ok": True, "job": job}
        return {"ok": False, "error": "job não encontrado"}

    def queue_board(self, *, limit: int = 40) -> dict[str, Any]:
        running: list[dict[str, Any]] = []
        queued: list[dict[str, Any]] = []
        done: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        def slim(j: dict[str, Any]) -> dict[str, Any]:
            return {
                "job_id": j.get("job_id") or j.get("id"),
                "intent": j.get("intent") or "",
                "state": j.get("state") or "unknown",
                "agent": j.get("agent") or "hermes-operator",
                "agent_label": j.get("agent_label")
                or next(
                    (
                        a["label"]
                        for a in HERMES_AGENTS
                        if a["id"] == (j.get("agent") or "")
                    ),
                    "operador",
                ),
                "ts": j.get("ts"),
                "source": "hermes",
                "kind": j.get("kind"),
                "message": str(j.get("message") or "")[:240],
            }

        for j in reversed(self._queue[-limit:]):
            state = str(j.get("state") or "")
            row = slim(j)
            if state in {"running", "dispatched"}:
                running.append(row)
            elif state in {"queued", "queued_local"}:
                queued.append(row)
            elif state in {"failed", "error"}:
                failed.append(row)
            else:
                done.append(row)
        return {
            "ok": True,
            "running": running[:16],
            "queued": queued[:16],
            "done": done[:16],
            "failed": failed[:8],
            "proposals": self.recent_proposals(6),
            "counts": {
                "running": len(running),
                "queued": len(queued),
                "done": len(done),
                "failed": len(failed),
                "proposals": len(self._proposals),
                "total": len(self._queue),
            },
            "status": self.status(),
            "agents": HERMES_AGENTS,
            "preferred_agent": self.preferred_agent(),
        }

    def ask(
        self,
        intent: str,
        *,
        source: str = "os",
        agent: str | None = None,
    ) -> dict[str, Any]:
        """Pedido explícito ao Hermes — observa + enfileira + tenta propor skill."""
        if agent:
            self.set_preferred_agent(agent)
        enq = self.enqueue(intent=intent, kind="ask", source=source, agent=agent)
        proposal = self.maybe_propose(min_repeats=1)
        pref = self.preferred_agent()
        return {
            "ok": True,
            "message": (
                proposal["message"]
                if proposal
                else f"Hermes · {pref['label']} recebeu o pedido — na fila."
            ),
            "job": enq.get("job"),
            "agent": pref,
            "proposal": proposal,
            "pulse": self.pulse(),
        }


def _normalize(intent: str) -> str:
    t = re.sub(r"\s+", " ", intent.strip().lower())
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\b[0-9a-f]{8,}\b", "", t)
    return t.strip()[:120]


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "pattern"

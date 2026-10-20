"""Ciclo de vida real dos jobs — queued → running → done|failed|cancelled + dedup."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from veu.bus import bus
from veu.redact import redact_obj, redact_text

TERMINAL = {"done", "failed", "cancelled"}
DEDUP_WINDOW_SEC = 10 * 60
DEFAULT_TIMEOUT_SEC = 180
MAX_RETRIES = 2
ACTIVE_RETENTION_DAYS = 7


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "jobs.json"


def _hist_path() -> Path:
    return _root() / "jobs_history.jsonl"


def _reports_dir() -> Path:
    d = _root() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _report_path(job_id: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", job_id)[:80]
    return _reports_dir() / f"{safe}.json"


def _norm_intent(intent: str) -> str:
    t = re.sub(r"\s+", " ", (intent or "").strip().lower())
    t = re.sub(r"[^\w\s\-à-ú]", "", t)
    return t[:200]


def _fp(intent: str, route: str) -> str:
    raw = f"{_norm_intent(intent)}|{route or 'chat'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._load()
        self._executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None
        self._worker_started = False
        self._paused = False

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = bool(paused)

    def is_paused(self) -> bool:
        with self._lock:
            return bool(self._paused)

    def _executor_paused(self) -> bool:
        """Pausa local ou da central de controle."""
        if self._paused:
            return True
        try:
            from veu.control import control

            return control.is_paused()
        except Exception:  # noqa: BLE001
            return False

    def _load(self) -> None:
        path = _path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data.get("jobs") or []:
                if row.get("id"):
                    self._jobs[str(row["id"])] = row
        except (OSError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        path = _path()
        tmp = path.with_suffix(".tmp")
        payload = {"jobs": list(self._jobs.values()), "version": 1}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def set_executor(self, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self._executor = fn

    def ensure_worker(self) -> None:
        if self._worker_started:
            return
        self._worker_started = True
        t = threading.Thread(target=self._loop, name="veu-jobs", daemon=True)
        t.start()

    def _loop(self) -> None:
        while True:
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.2)

    def _tick(self) -> None:
        now = time.time()
        with self._lock:
            # timeout running
            for job in list(self._jobs.values()):
                if job.get("state") != "running":
                    continue
                started = float(job.get("started") or job.get("created") or now)
                raw_timeout = job.get("timeout_sec")
                timeout = float(DEFAULT_TIMEOUT_SEC if raw_timeout is None else raw_timeout)
                if now - started > timeout:
                    self._fail_locked(job, "timeout", retry=True)

            # pick next queued — parado se executor pausado (parar tudo)
            if self._executor_paused():
                return
            queued = [
                j
                for j in self._jobs.values()
                if j.get("state") == "queued"
            ]
            queued.sort(key=lambda j: float(j.get("created") or 0))
            if not queued or self._executor is None:
                return
            # one at a time
            if any(j.get("state") == "running" for j in self._jobs.values()):
                return
            job = queued[0]
            job["state"] = "running"
            job["started"] = now
            job["attempts"] = int(job.get("attempts") or 0) + 1
            job["progress"] = {"phase": "start", "percent": 0, "message": "iniciando"}
            self._save()
            bus.publish_sync("job", {"id": job["id"], "state": "running"}, full=self._public(job))
            self._emit_progress_locked(job, phase="start", percent=0, message="iniciando")

        # run outside lock
        try:
            result = self._executor(dict(job)) if self._executor else {"summary": "sem executor"}
            with self._lock:
                cur = self._jobs.get(job["id"])
                if not cur or cur.get("state") != "running":
                    return
                cur["state"] = "done"
                cur["ended"] = time.time()
                cur["result"] = {
                    "summary": str((result or {}).get("summary") or "")[:2000],
                    "artifacts": list((result or {}).get("artifacts") or [])[:20],
                    "next_action": (result or {}).get("next_action"),
                }
                cur["error"] = None
                cur["progress"] = {"phase": "done", "percent": 100, "message": "concluído"}
                report = self._build_report_locked(cur, result or {})
                cur["report"] = report
                self._persist_report(report)
                self._save()
                bus.publish_sync("job", {"id": cur["id"], "state": "done"}, full=self._public(cur))
                bus.publish_sync("job.report", {"job_id": cur["id"]}, full=report)
                try:
                    from veu import logbook

                    logbook.emit(
                        level="info",
                        source="agente",
                        message=f"job {cur['id']} concluído",
                        job_id=cur["id"],
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                cur = self._jobs.get(job["id"])
                if cur and cur.get("state") == "running":
                    self._fail_locked(cur, str(exc)[:400], retry=True)

    def _fail_locked(self, job: dict[str, Any], error: str, *, retry: bool) -> None:
        attempts = int(job.get("attempts") or 0)
        if retry and attempts <= MAX_RETRIES:
            job["state"] = "queued"
            job["error"] = error
            job["started"] = None
            # backoff embutido via created bump leve
            job["created"] = time.time() + min(30, 2 ** attempts)
            self._save()
            bus.publish_sync(
                "job",
                {"id": job["id"], "state": "queued", "retry": attempts},
                full=self._public(job),
            )
            return
        job["state"] = "failed"
        job["ended"] = time.time()
        job["error"] = error
        job["progress"] = {"phase": "failed", "percent": 100, "message": error[:200]}
        report = self._build_report_locked(job, {})
        job["report"] = report
        self._persist_report(report)
        self._save()
        bus.publish_sync("job", {"id": job["id"], "state": "failed"}, full=self._public(job))
        bus.publish_sync("job.report", {"job_id": job["id"]}, full=report)

    def _emit_progress_locked(
        self,
        job: dict[str, Any],
        *,
        phase: str,
        percent: float | None = None,
        message: str = "",
    ) -> None:
        payload = {
            "job_id": job.get("id"),
            "phase": phase,
            "percent": percent,
            "message": redact_text(message)[:500],
        }
        job["progress"] = {
            "phase": phase,
            "percent": percent,
            "message": payload["message"],
        }
        bus.publish_sync("job.progress", payload, full=payload)
        try:
            from veu import logbook

            logbook.emit(
                level="info",
                source="agente",
                message=f"{phase}: {payload['message'] or phase}",
                job_id=str(job.get("id") or ""),
            )
        except Exception:  # noqa: BLE001
            pass

    def emit_progress(
        self,
        job_id: str,
        *,
        phase: str,
        percent: float | None = None,
        message: str = "",
    ) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            self._emit_progress_locked(job, phase=phase, percent=percent, message=message)
            self._save()
            return dict(job.get("progress") or {})

    def _artifact_rows(self, artifacts: list[Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for a in artifacts[:20]:
            if isinstance(a, dict):
                name = str(a.get("name") or a.get("title") or a.get("kind") or "artefato")[:200]
                raw = json.dumps(a, sort_keys=True, default=str)
            else:
                name = str(a)[:200]
                raw = name
            rows.append(
                {
                    "nome": redact_text(name),
                    "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                }
            )
        return rows

    def _build_report_locked(self, job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        started = float(job.get("started") or job.get("created") or time.time())
        ended = float(job.get("ended") or time.time())
        artifacts = list((result.get("artifacts") if result else None) or (job.get("result") or {}).get("artifacts") or [])
        tools = list((job.get("meta") or {}).get("tools") or [])
        summary = ""
        if job.get("result") and job["result"].get("summary"):
            summary = str(job["result"]["summary"])
        elif result.get("summary"):
            summary = str(result["summary"])
        elif job.get("error"):
            summary = str(job["error"])
        cost = (job.get("meta") or {}).get("cost_usd")
        if cost is None and result.get("cost_usd") is not None:
            cost = result.get("cost_usd")
        next_steps = []
        na = (job.get("result") or {}).get("next_action") or result.get("next_action")
        if na:
            next_steps.append(str(na)[:500])
        report = {
            "job_id": job.get("id"),
            "intent": redact_text(str(job.get("intent") or "")),
            "agente": str((job.get("meta") or {}).get("agent") or job.get("route") or "chat"),
            "modo": str(job.get("breath") or "guided"),
            "ferramentas": [redact_text(str(t)) for t in tools][:40],
            "duracao_sec": round(max(0.0, ended - started), 3),
            "custo_estimado": float(cost) if cost is not None else 0.0,
            "resultado": redact_text(summary)[:4000],
            "artefatos": self._artifact_rows(artifacts),
            "proximos_passos": [redact_text(s) for s in next_steps][:10],
            "state": job.get("state"),
            "error": redact_text(str(job.get("error") or "")) or None,
            "ts": time.time(),
        }
        return redact_obj(report)

    def _persist_report(self, report: dict[str, Any]) -> None:
        jid = str(report.get("job_id") or "")
        if not jid:
            return
        path = _report_path(jid)
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    def get_report(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.get("report"):
                return dict(job["report"])
        path = _report_path(job_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return None

    @staticmethod
    def report_to_md(report: dict[str, Any]) -> str:
        arts = report.get("artefatos") or []
        art_lines = "\n".join(
            f"- `{a.get('nome')}` · `{a.get('sha256')}`" for a in arts
        ) or "- (nenhum)"
        tools = report.get("ferramentas") or []
        tool_line = ", ".join(str(t) for t in tools) if tools else "(nenhuma)"
        steps = report.get("proximos_passos") or []
        step_lines = "\n".join(f"- {s}" for s in steps) or "- (nenhum)"
        return (
            f"# Relatório · {report.get('job_id')}\n\n"
            f"- **intent:** {report.get('intent')}\n"
            f"- **agente:** {report.get('agente')}\n"
            f"- **modo:** {report.get('modo')}\n"
            f"- **ferramentas:** {tool_line}\n"
            f"- **duração:** {report.get('duracao_sec')}s\n"
            f"- **custo estimado:** ${report.get('custo_estimado')}\n"
            f"- **estado:** {report.get('state')}\n\n"
            f"## Resultado\n\n{report.get('resultado') or '—'}\n\n"
            f"## Artefatos\n\n{art_lines}\n\n"
            f"## Próximos passos\n\n{step_lines}\n"
        )

    def _public(self, job: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": job.get("id"),
            "intent": job.get("intent"),
            "route": job.get("route"),
            "state": job.get("state"),
            "breath": job.get("breath"),
            "created": job.get("created"),
            "started": job.get("started"),
            "ended": job.get("ended"),
            "attempts": job.get("attempts") or 0,
            "result": job.get("result"),
            "error": job.get("error"),
            "risk": job.get("risk"),
            "fingerprint": job.get("fingerprint"),
            "progress": job.get("progress"),
            "has_report": bool(job.get("report")),
        }

    def enqueue(
        self,
        *,
        intent: str,
        route: str = "chat",
        breath: str = "guided",
        risk: str = "medium",
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._executor_paused():
            return {
                "ok": False,
                "error": "executor pausado — use /control/resume",
                "paused": True,
                "state": "paused",
            }
        self.ensure_worker()
        fp = _fp(intent, route)
        now = time.time()
        with self._lock:
            # dedup
            for job in self._jobs.values():
                if job.get("fingerprint") != fp:
                    continue
                if job.get("state") in TERMINAL:
                    continue
                created = float(job.get("created") or 0)
                if now - created <= DEDUP_WINDOW_SEC:
                    return {**self._public(job), "deduped": True}

            jid = f"job-{uuid.uuid4().hex[:10]}"
            job = {
                "id": jid,
                "intent": intent.strip()[:500],
                "route": route,
                "breath": breath,
                "risk": risk,
                "state": "queued",
                "created": now,
                "started": None,
                "ended": None,
                "attempts": 0,
                "timeout_sec": timeout_sec,
                "result": None,
                "error": None,
                "fingerprint": fp,
                "meta": meta or {},
            }
            self._jobs[jid] = job
            self._gc_locked()
            self._save()
            bus.publish_sync("job", {"id": jid, "state": "queued"}, full=self._public(job))
            return self._public(job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {"ok": False, "error": "job não encontrado"}
            if job.get("state") in TERMINAL:
                return {"ok": True, "job": self._public(job), "note": "já terminal"}
            job["state"] = "cancelled"
            job["ended"] = time.time()
            job["progress"] = {"phase": "cancelled", "percent": 100, "message": "cancelado"}
            if not job.get("report"):
                report = self._build_report_locked(job, {})
                job["report"] = report
                self._persist_report(report)
                bus.publish_sync("job.report", {"job_id": job_id}, full=report)
            self._save()
            bus.publish_sync("job", {"id": job_id, "state": "cancelled"}, full=self._public(job))
            return {"ok": True, "job": self._public(job)}

    def cancel_all_active(self) -> int:
        """Cancela todos os jobs não terminais. Devolve quantos cancelou."""
        with self._lock:
            ids = [
                jid
                for jid, j in self._jobs.items()
                if j.get("state") not in TERMINAL
            ]
        n = 0
        for jid in ids:
            out = self.cancel(jid)
            if out.get("ok") and out.get("note") != "já terminal":
                n += 1
        return n

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._public(job) if job else None

    def list_active(self, *, limit: int = 40) -> list[dict[str, Any]]:
        with self._lock:
            rows = [self._public(j) for j in self._jobs.values()]
        rows.sort(key=lambda j: float(j.get("created") or 0), reverse=True)
        return rows[:limit]

    def board(self, *, limit: int = 40) -> dict[str, Any]:
        rows = self.list_active(limit=limit)
        counts: dict[str, int] = defaultdict_count(rows)
        return {
            "ok": True,
            "jobs": rows,
            "counts": counts,
        }

    def _gc_locked(self) -> None:
        cutoff = time.time() - ACTIVE_RETENTION_DAYS * 86400
        drop: list[str] = []
        for jid, job in self._jobs.items():
            if job.get("state") not in TERMINAL:
                continue
            ended = float(job.get("ended") or job.get("created") or 0)
            if ended < cutoff:
                drop.append(jid)
                try:
                    with _hist_path().open("a", encoding="utf-8") as f:
                        f.write(json.dumps(job, ensure_ascii=False) + "\n")
                except OSError:
                    pass
        for jid in drop:
            self._jobs.pop(jid, None)


def defaultdict_count(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        s = str(r.get("state") or "unknown")
        out[s] = out.get(s, 0) + 1
    return out


store = JobStore()

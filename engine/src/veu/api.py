"""API do kernel — chat + execução em tempo real (SSE)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

# Secrets locais (TYPESAFE_API_KEY, OPENAI_API_KEY…) — nunca versionar .env
for _env in (
    Path("/root/veu/engine/.env"),
    Path(__file__).resolve().parents[2] / ".env",
):
    if _env.is_file():
        load_dotenv(_env, override=False)

import asyncio
import time as _time

from veu.runtime import Runtime
from veu import subscriptions as subs
from veu import fleet
from veu import auth as veu_auth
from veu import jobs as veu_jobs
from veu import credentials as veu_creds
from veu import usage as veu_usage
from veu import billing as veu_billing
from veu import receipt_scan as veu_receipts
from veu import provider_costs as veu_provider_costs
from veu import billing_alerts as veu_billing_alerts
from veu import projects as veu_projects
from veu import import_chatgpt as veu_import_chatgpt
from veu import import_claude as veu_import_claude
from veu import import_cursor as veu_import_cursor
from veu import voice as veu_voice
from veu import approvals as veu_approvals
from veu import briefing as veu_briefing
from veu import inbox as veu_inbox
from veu import routines as veu_routines
from veu.bus import bus as veu_bus
from veu import logbook as veu_logbook
from veu.flight import readiness
from veu.mcp import bus as mcp_bus

app = FastAPI(title="Véu Kernel", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(veu_auth.allowed_origins()),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _veu_startup_publishers() -> None:
    from veu import stream_publishers

    def _side() -> Any:
        try:
            return rt.bridges.grokbot.sideboard()
        except Exception:  # noqa: BLE001
            return None

    stream_publishers.start(
        pulse_fn=lambda: rt.pulse(),
        mission_fn=lambda: mission(),
        sideboard_fn=_side,
    )


@app.on_event("shutdown")
async def _veu_shutdown_publishers() -> None:
    from veu import stream_publishers

    stream_publishers.stop()


class _AuthGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        return await veu_auth.auth_middleware(request, call_next)


app.add_middleware(_AuthGate)

rt = Runtime()


def _job_executor(job: dict[str, Any]) -> dict[str, Any]:
    """Executa intenção via weave curto (sem stream HTTP)."""
    intent = str(job.get("intent") or "")
    breath = str(job.get("breath") or "guided")
    jid = str(job.get("id") or "")
    reply_bits: list[str] = []
    artifacts: list[Any] = []
    tools_seen: list[str] = []
    veu_jobs.store.emit_progress(jid, phase="route", percent=5, message=f"roteando · {intent[:80]}")
    veu_logbook.emit(level="info", source="agente", message=f"route · {intent[:120]}", job_id=jid)
    try:
        for event in rt.stream_weave(intent, breath=breath):  # type: ignore[attr-defined]
            et = event.get("type")
            if et == "plan" and event.get("formation"):
                form = event["formation"]
                route = str(form.get("route") or "chat")
                veu_jobs.store.emit_progress(
                    jid, phase="plan", percent=20, message=f"plano · {route}"
                )
                veu_logbook.emit(
                    level="info",
                    source="agente",
                    message=f"jev.route · {route}",
                    job_id=jid,
                )
                risk = (form.get("harness") or {}).get("risk_ceiling") or breath
                veu_logbook.emit(
                    level="info",
                    source="agente",
                    message=f"policy.risk · {risk}",
                    job_id=jid,
                )
                for t in list((form.get("harness") or {}).get("tools") or [])[:20]:
                    tools_seen.append(str(t))
                    veu_logbook.emit(
                        level="info",
                        source="agente",
                        message=f"tool · {t}",
                        job_id=jid,
                    )
            if et == "harness" and event.get("session"):
                sess = event["session"]
                veu_jobs.store.emit_progress(
                    jid,
                    phase="harness",
                    percent=40,
                    message=f"harness · {len(sess.get('tools') or [])} tools",
                )
            if et == "step":
                idx = int(event.get("index") or 0)
                veu_jobs.store.emit_progress(
                    jid,
                    phase="step",
                    percent=min(90, 45 + idx * 8),
                    message=str((event.get("step") or {}).get("label") or f"passo {idx}"),
                )
            if et == "reply" and event.get("text"):
                reply_bits.append(str(event["text"]))
            if et == "done" and event.get("formation"):
                form = event["formation"]
                if form.get("reply"):
                    reply_bits.append(str(form["reply"]))
                artifacts.append({"kind": "formation", "title": form.get("title")})
            if et == "action":
                artifacts.append(event)
                kind = str(event.get("kind") or event.get("type") or "action")
                if kind.startswith("host.") or "host" in kind:
                    veu_logbook.emit(
                        level="info",
                        source="host",
                        message=f"host.* · {kind}",
                        job_id=jid,
                    )
                elif "memory" in kind:
                    veu_logbook.emit(
                        level="info",
                        source="agente",
                        message=f"memory.write · {kind}",
                        job_id=jid,
                    )
                else:
                    veu_logbook.emit(
                        level="info",
                        source="conector",
                        message=f"tool · {kind}",
                        job_id=jid,
                    )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(str(exc)[:400]) from exc
    veu_jobs.store.emit_progress(jid, phase="finalize", percent=95, message="fechando relatório")
    if tools_seen:
        with veu_jobs.store._lock:
            cur = veu_jobs.store._jobs.get(jid)
            if cur:
                meta = dict(cur.get("meta") or {})
                meta["tools"] = tools_seen[:40]
                cur["meta"] = meta
    summary = "\n".join(reply_bits).strip() or f"job {job.get('id')} concluído"
    return {"summary": summary[:2000], "artifacts": artifacts[:12], "next_action": None}


veu_jobs.store.set_executor(_job_executor)
veu_jobs.store.ensure_worker()
veu_routines.ensure_worker()


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    breath: Literal["guided", "semi", "free", "autonomous"] = "guided"


class JobIn(BaseModel):
    intent: str = Field(min_length=1, max_length=2000)
    route: str = "chat"
    breath: Literal["guided", "semi", "free", "autonomous"] = "guided"
    risk: str | None = None


class ApprovalDecideIn(BaseModel):
    approve: bool
    note: str = ""


class LifeAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = 8


class InboxDraftIn(BaseModel):
    item_id: str = ""
    channel: str = "outlook"
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=4000)
    to: str = ""


class RoutineIn(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1, max_length=120)
    cron: str = Field(min_length=5, max_length=40)
    intent: str = Field(min_length=1, max_length=500)
    breath: Literal["guided", "semi", "free", "autonomous"] = "guided"
    enabled: bool = True


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class SubscriptionIn(BaseModel):
    """Conexão por API key (legado / modo api_key)."""

    provider: Literal["openai", "claude", "xai"]
    api_key: str = Field(min_length=12)
    model: str | None = None


class SubscriptionLinkIn(BaseModel):
    provider: Literal["openai", "claude", "xai"]


class BillingSubIn(BaseModel):
    servico: str = Field(min_length=1, max_length=120)
    plano: str = ""
    valor: float = 0
    moeda: Literal["BRL", "USD", "EUR"] = "BRL"
    ciclo: Literal["mensal", "anual"] = "mensal"
    proxima_renovacao: str | None = None
    pago_por: str = "eu"
    reembolsavel: bool = False
    meio_de_pagamento: str = ""
    link_de_gestao: str = ""
    status: Literal["ativa", "pausada", "cancelada", "em_decisao"] = "ativa"
    notas: str = ""
    categoria: str | None = None


class BillingSubPatch(BaseModel):
    servico: str | None = None
    plano: str | None = None
    valor: float | None = None
    moeda: Literal["BRL", "USD", "EUR"] | None = None
    ciclo: Literal["mensal", "anual"] | None = None
    proxima_renovacao: str | None = None
    pago_por: str | None = None
    reembolsavel: bool | None = None
    meio_de_pagamento: str | None = None
    link_de_gestao: str | None = None
    status: Literal["ativa", "pausada", "cancelada", "em_decisao"] | None = None
    notas: str | None = None
    categoria: str | None = None


class SuggestionDecideIn(BaseModel):
    action: Literal["approve", "ignore"]


class ProviderSampleIn(BaseModel):
    provider: Literal["openai", "anthropic", "claude", "xai", "grok"]
    payload: dict[str, Any]


class ProjectIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    empresa: str | None = None
    fonte: str = "manual"
    caminho_ou_url: str | None = None
    resumo: str = ""
    tags: list[str] = Field(default_factory=list)


class ProjectPatch(BaseModel):
    empresa: str | None = None
    tags: list[str] | None = None
    resumo: str | None = None
    nome: str | None = None


class ProjectAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class AllowedFolderIn(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    fonte: Literal["claude-code", "cursor"]


class CursorSyncIn(BaseModel):
    workspaces: list[str] = Field(default_factory=list)
    chat_db_path: str | None = None


@app.get("/pulse")
def pulse() -> dict[str, Any]:
    from veu.redact import redact_obj

    return redact_obj(rt.pulse())


@app.get("/health")
@app.get("/healthz")
def health() -> dict[str, Any]:
    """Liveness — processo no ar (Caddy / systemd / probes). Público."""
    return {"status": "ok", "product": "véu", "layer": "kernel"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    """Flight readiness — go / no-go com checklist crítico. Público."""
    return readiness(rt)


@app.get("/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    """Estado da sessão — público (não vaza dados sensíveis)."""
    session = veu_auth.read_session(request)
    return {
        "ok": True,
        "configured": veu_auth.auth_configured(),
        "authenticated": session is not None,
        "subject": (session or {}).get("subject") if session else None,
        "methods": {
            "password": bool(veu_auth._password()),  # noqa: SLF001
            "google": veu_auth.google_oauth_configured(),
        },
        "google_client_id": veu_auth.google_client_id() or None,
    }


@app.post("/auth/login")
def auth_login(body: LoginIn, request: Request) -> JSONResponse:
    """Login por senha (fallback) — cookie HttpOnly + Secure + SameSite=Strict."""
    if not veu_auth._password():  # noqa: SLF001
        return JSONResponse(
            {"ok": False, "error": "password_disabled", "detail": "use Google"},
            status_code=400,
        )
    if not veu_auth.login_rate_ok(request):
        return JSONResponse(
            {"ok": False, "error": "rate_limited"},
            status_code=429,
        )
    if not veu_auth.check_password(body.password):
        return JSONResponse(
            {"ok": False, "error": "invalid_credentials"},
            status_code=401,
        )
    token = veu_auth.mint_session_token()
    resp = JSONResponse({"ok": True, "authenticated": True})
    veu_auth.set_session_cookie(resp, token)
    return resp


@app.get("/auth/google")
def auth_google_start():
    """Login Google — só openid/email/profile (identidade)."""
    if not veu_auth.google_oauth_configured():
        return JSONResponse(
            {"ok": False, "error": "google_not_configured"},
            status_code=503,
        )
    return veu_auth.google_start_redirect()


@app.get("/auth/google/workspace")
def auth_google_workspace_start():
    """Conector Workspace — Drive/Docs/Sheets/Calendar/Gmail (autorização incremental)."""
    if not veu_auth.google_oauth_configured():
        return JSONResponse(
            {"ok": False, "error": "google_not_configured"},
            status_code=503,
        )
    return veu_auth.google_workspace_start_redirect()


@app.get("/auth/google/callback")
def auth_google_callback(code: str | None = None, state: str | None = None):
    """Callback OAuth — cookie de sessão; Workspace só se state=gw."""
    return veu_auth.google_callback_response(code, state)


@app.get("/workspace")
@app.get("/workspace/status")
def workspace_status() -> dict[str, Any]:
    from veu import google_workspace as gw

    return gw.status()


@app.get("/workspace/drive")
def workspace_drive(q: str = "", kind: str = "", limit: int = 25) -> dict[str, Any]:
    from veu import google_workspace as gw

    try:
        return gw.list_drive(query=q, kind=kind, limit=limit)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200], "files": []}


@app.get("/workspace/calendar")
def workspace_calendar(limit: int = 20) -> dict[str, Any]:
    from veu import google_workspace as gw

    try:
        return gw.list_calendar(limit=limit)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200], "events": []}


@app.get("/workspace/gmail")
def workspace_gmail(limit: int = 15) -> dict[str, Any]:
    from veu import google_workspace as gw

    try:
        return gw.list_gmail(limit=limit)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200], "messages": []}


@app.post("/workspace/disconnect")
def workspace_disconnect() -> dict[str, Any]:
    from veu import google_workspace as gw

    return gw.disconnect()


@app.post("/auth/logout")
def auth_logout(request: Request) -> JSONResponse:
    session = veu_auth.read_session(request)
    veu_auth.revoke_session(session)
    resp = JSONResponse({"ok": True, "authenticated": False})
    veu_auth.clear_session_cookie(resp)
    return resp


@app.get("/connectors")
def connectors() -> dict[str, Any]:
    rt.refresh_connector_status()
    return rt.connectors.as_dict()


@app.get("/harness")
def harness_pulse() -> dict[str, Any]:
    """Estado do harness agêntico (tools ativas / últimas sessões)."""
    return rt.harness.pulse()


@app.get("/mission")
def mission() -> dict[str, Any]:
    """Mission Control — projetos, agentes, ações autônomas, Jev/harness."""
    snap = rt.mission()
    # injeta jobs reais (ciclo de vida) ao lado dos projects do harness
    board = veu_jobs.store.board(limit=24)
    snap["jobs"] = board.get("jobs") or []
    snap["job_counts"] = board.get("counts") or {}
    return snap


@app.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """SSE com deltas — mission/pulse/sideboard/job/credentials/approval."""

    async def gen():
        sid, q = veu_bus.subscribe()
        # snapshot inicial
        try:
            try:
                side = rt.bridges.grokbot.sideboard()
            except Exception:  # noqa: BLE001
                side = None
            snap = {
                "mission": True,
                "pulse": rt.pulse(),
                "jobs": veu_jobs.store.board(limit=12),
                "sideboard": bool(side),
            }
            yield f"event: hello\ndata: {json.dumps(snap, default=str)}\n\n"
            if side is not None:
                yield (
                    "event: sideboard\ndata: "
                    + json.dumps(
                        {"type": "sideboard", "patch": {"refreshed": True}, "full": None},
                        default=str,
                    )
                    + "\n\n"
                )
        except Exception:  # noqa: BLE001
            yield "event: hello\ndata: {}\n\n"
        last_beat = _time.time()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=5.0)
                    et = msg.get("type") or "message"
                    payload = {
                        "type": et,
                        "patch": msg.get("patch") or {},
                        "full": msg.get("full"),
                        "ts": msg.get("ts"),
                    }
                    yield f"event: {et}\ndata: {json.dumps(payload, default=str, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    pass
                now = _time.time()
                if now - last_beat >= 15:
                    yield ": heartbeat\n\n"
                    last_beat = now
        finally:
            veu_bus.unsubscribe(sid)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/stream/log")
async def stream_log(
    request: Request,
    level: str | None = None,
    source: str | None = None,
    job_id: str | None = None,
) -> StreamingResponse:
    """SSE do registro estruturado — Last-Event-ID, filtros, heartbeat 15s."""

    last_event_id = request.headers.get("last-event-id") or request.query_params.get(
        "last_event_id"
    )

    async def gen():
        sid, q = veu_logbook.book.subscribe()
        try:
            for ev in veu_logbook.book.since(
                last_event_id, level=level, source=source, job_id=job_id
            ):
                yield (
                    f"id: {ev['id']}\nevent: log\ndata: "
                    + json.dumps(ev, ensure_ascii=False, default=str)
                    + "\n\n"
                )
            last_beat = _time.time()
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=5.0)
                    if not veu_logbook.book.matches_filters(
                        ev, level=level, source=source, job_id=job_id
                    ):
                        continue
                    yield (
                        f"id: {ev['id']}\nevent: log\ndata: "
                        + json.dumps(ev, ensure_ascii=False, default=str)
                        + "\n\n"
                    )
                except asyncio.TimeoutError:
                    pass
                now = _time.time()
                if now - last_beat >= 15:
                    yield ": heartbeat\n\n"
                    last_beat = now
        finally:
            veu_logbook.book.unsubscribe(sid)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/jobs")
def jobs_list(limit: int = 40) -> dict[str, Any]:
    return veu_jobs.store.board(limit=limit)


@app.post("/jobs")
def jobs_create(body: JobIn) -> dict[str, Any]:
    risk = body.risk or veu_approvals.classify_risk(intent=body.intent)
    # fila de aprovação quando a respiração exige
    gate = veu_approvals.enqueue(
        intent=body.intent,
        breath=body.breath,
        route=body.route,
        tools=[],
        context={"source": "api.jobs"},
    )
    if gate.get("needs_approval"):
        return {"ok": True, "queued_for_approval": True, **gate}
    job = veu_jobs.store.enqueue(
        intent=body.intent,
        route=body.route,
        breath=body.breath,
        risk=risk,
    )
    return {"ok": True, "job": job}


@app.get("/jobs/{job_id}/report")
def jobs_report(job_id: str, format: str = "json") -> Any:
    report = veu_jobs.store.get_report(job_id)
    if not report:
        return JSONResponse({"ok": False, "error": "relatório não encontrado"}, status_code=404)
    fmt = (format or "json").lower()
    if fmt in {"md", "markdown", "text"}:
        return PlainTextResponse(
            veu_jobs.JobStore.report_to_md(report),
            media_type="text/markdown; charset=utf-8",
        )
    return {"ok": True, "report": report}


@app.get("/jobs/{job_id}")
def jobs_get(job_id: str) -> dict[str, Any]:
    job = veu_jobs.store.get(job_id)
    if not job:
        return {"ok": False, "error": "não encontrado"}
    return {"ok": True, "job": job}


@app.post("/jobs/{job_id}/cancel")
def jobs_cancel(job_id: str) -> dict[str, Any]:
    return veu_jobs.store.cancel(job_id)


@app.get("/credentials")
def credentials_board() -> dict[str, Any]:
    return veu_creds.refresh_from_live()


@app.post("/credentials/{account_id}/relogin-ok")
def credentials_relogin_ok(account_id: str) -> dict[str, Any]:
    return veu_creds.mark_relogin_ok(account_id)


@app.get("/usage")
def usage_get(period: str = "today") -> dict[str, Any]:
    return veu_usage.summarize(period)


# --- Billing (assinaturas de serviços) — distinto de /subscriptions (login LLM) ---


@app.get("/billing/subscriptions")
def billing_list(status: str | None = None) -> dict[str, Any]:
    return {"ok": True, "subscriptions": veu_billing.list_subscriptions(status=status)}


@app.post("/billing/subscriptions")
def billing_create(body: BillingSubIn) -> dict[str, Any]:
    try:
        row = veu_billing.create_subscription(body.model_dump())
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "subscription": row}


@app.get("/billing/subscriptions/{sub_id}")
def billing_get(sub_id: str) -> dict[str, Any]:
    row = veu_billing.get_subscription(sub_id)
    if not row:
        return JSONResponse({"ok": False, "error": "não encontrado"}, status_code=404)
    return {"ok": True, "subscription": row}


@app.patch("/billing/subscriptions/{sub_id}")
def billing_patch(sub_id: str, body: BillingSubPatch) -> dict[str, Any]:
    try:
        row = veu_billing.update_subscription(
            sub_id, {k: v for k, v in body.model_dump().items() if v is not None}
        )
    except KeyError:
        return JSONResponse({"ok": False, "error": "não encontrado"}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "subscription": row}


@app.delete("/billing/subscriptions/{sub_id}")
def billing_delete(sub_id: str) -> dict[str, Any]:
    ok = veu_billing.delete_subscription(sub_id)
    if not ok:
        return JSONResponse({"ok": False, "error": "não encontrado"}, status_code=404)
    return {"ok": True}


@app.post("/billing/subscriptions/{sub_id}/decision")
def billing_decision(sub_id: str, action: Literal["pausar", "cancelar"] = "pausar") -> dict[str, Any]:
    try:
        return veu_billing.mark_decision(sub_id, action)
    except KeyError:
        return JSONResponse({"ok": False, "error": "não encontrado"}, status_code=404)


@app.get("/billing/dashboard")
def billing_dashboard() -> dict[str, Any]:
    return veu_billing.dashboard()


@app.get("/billing/export.csv")
def billing_export_csv() -> PlainTextResponse:
    return PlainTextResponse(veu_billing.export_csv(), media_type="text/csv")


@app.post("/billing/receipts/scan")
def billing_receipts_scan(limit: int = 40) -> dict[str, Any]:
    """Opt-in: varre e-mail conectado por recibos. Não guarda corpo."""
    return veu_receipts.scan_connected_email(limit=limit)


@app.post("/billing/receipts/ingest")
def billing_receipts_ingest(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Ingestão de metadados já lidos (testes / host)."""
    messages = list(body.get("messages") or [])
    return veu_receipts.ingest_receipts(messages)


@app.get("/billing/suggestions")
def billing_suggestions(status: str | None = "pending") -> dict[str, Any]:
    return {
        "ok": True,
        "suggestions": veu_receipts.list_suggestions(status=status),
        "alerts": veu_receipts.list_alerts(open_only=True),
    }


@app.post("/billing/suggestions/{suggestion_id}/decide")
def billing_suggestion_decide(suggestion_id: str, body: SuggestionDecideIn) -> dict[str, Any]:
    return veu_receipts.decide_suggestion(suggestion_id, body.action)


@app.get("/billing/provider-costs/status")
def billing_provider_status() -> dict[str, Any]:
    return {"ok": True, "providers": veu_provider_costs.provider_status()}


@app.post("/billing/provider-costs/collect")
def billing_provider_collect() -> dict[str, Any]:
    return veu_provider_costs.collect_all()


@app.post("/billing/provider-costs/sample")
def billing_provider_sample(body: ProviderSampleIn) -> dict[str, Any]:
    return veu_provider_costs.ingest_provider_sample(body.provider, body.payload)


@app.get("/billing/provider-costs/reconcile")
def billing_provider_reconcile(days: int = 30) -> dict[str, Any]:
    return veu_provider_costs.reconcile(days=days)


@app.post("/billing/alerts/evaluate")
def billing_alerts_evaluate() -> dict[str, Any]:
    return veu_billing_alerts.evaluate_alerts()


# --- Projetos (inventário multi-IA) ---


@app.get("/projects")
def projects_list(
    fonte: str | None = None,
    empresa: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    return {
        "ok": True,
        "projects": veu_projects.list_projects(fonte=fonte, empresa=empresa, q=q, limit=limit),
        "sync": veu_projects.sync_status(),
    }


@app.post("/projects")
def projects_create(body: ProjectIn) -> dict[str, Any]:
    try:
        row = veu_projects.create_project(body.model_dump())
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "project": row}


@app.post("/projects/folders/allow")
def projects_allow_folder(body: AllowedFolderIn) -> dict[str, Any]:
    return veu_projects.allow_folder(body.path, body.fonte)


@app.post("/projects/folders/deny")
def projects_deny_folder(body: AllowedFolderIn) -> dict[str, Any]:
    return veu_projects.deny_folder(body.path)


@app.get("/projects/folders")
def projects_list_folders(fonte: str | None = None) -> dict[str, Any]:
    return {"ok": True, "folders": veu_projects.list_allowed_folders(fonte)}


@app.post("/projects/sync/claude-code")
def projects_sync_claude_code(root: str | None = None) -> dict[str, Any]:
    return veu_import_claude.collect_claude_code(root=root)


@app.post("/projects/sync/cursor")
def projects_sync_cursor(body: CursorSyncIn | None = None) -> dict[str, Any]:
    body = body or CursorSyncIn()
    return veu_import_cursor.collect_cursor(
        workspace_roots=body.workspaces or None,
        chat_db_path=body.chat_db_path,
    )


@app.post("/import/chatgpt")
async def import_chatgpt(
    file: UploadFile = File(...),
    confirm: bool = Form(False),
) -> dict[str, Any]:
    raw = await file.read()
    return veu_import_chatgpt.import_zip(raw, confirm=confirm)


@app.post("/import/claude")
async def import_claude(
    file: UploadFile = File(...),
    confirm: bool = Form(False),
) -> dict[str, Any]:
    raw = await file.read()
    return veu_import_claude.import_zip(raw, confirm=confirm)


@app.get("/projects/{project_id}")
def projects_get(project_id: str) -> dict[str, Any]:
    row = veu_projects.get_project(project_id)
    if not row:
        return JSONResponse({"ok": False, "error": "não encontrado"}, status_code=404)
    return {"ok": True, "project": row}


@app.patch("/projects/{project_id}")
def projects_patch(project_id: str, body: ProjectPatch) -> dict[str, Any]:
    try:
        row = veu_projects.patch_project(
            project_id, {k: v for k, v in body.model_dump().items() if v is not None}
        )
    except KeyError:
        return JSONResponse({"ok": False, "error": "não encontrado"}, status_code=404)
    return {"ok": True, "project": row}


@app.post("/projects/{project_id}/ask")
def projects_ask(project_id: str, body: ProjectAskIn) -> dict[str, Any]:
    return veu_projects.ask_about_project(project_id, body.question)


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    result = veu_voice.transcribe(raw, filename=file.filename or "audio.webm")
    return result


@app.post("/voice/ask")
async def voice_ask(
    file: UploadFile = File(...),
    breath: Literal["guided", "semi", "free", "autonomous"] = Form("guided"),
) -> dict[str, Any]:
    """Transcreve e enfileira a intenção (mesmo fluxo do chat/jobs)."""
    raw = await file.read()
    tr = veu_voice.transcribe(raw, filename=file.filename or "audio.webm")
    if not tr.get("ok") or not tr.get("text"):
        return {"ok": False, "stage": "transcribe", **tr}
    text = str(tr["text"]).strip()
    gate = veu_approvals.enqueue(intent=text, breath=breath, route="chat")
    if gate.get("needs_approval"):
        return {"ok": True, "text": text, "queued_for_approval": True, **gate}
    job = veu_jobs.store.enqueue(intent=text, route="chat", breath=breath)
    return {"ok": True, "text": text, "job": job, "stage": "queued"}


@app.get("/approvals")
def approvals_board() -> dict[str, Any]:
    return veu_approvals.board()


@app.post("/approvals/{approval_id}/decide")
def approvals_decide(approval_id: str, body: ApprovalDecideIn) -> dict[str, Any]:
    return veu_approvals.decide(approval_id, approve=body.approve, note=body.note)


@app.post("/life/ask")
def life_ask(body: LifeAskIn) -> dict[str, Any]:
    """Pergunte à minha vida — OpenRAG com citação obrigatória."""
    return veu_briefing.ask_life(body.question, limit=body.limit)


@app.get("/briefing")
def briefing_get(kind: str = "morning") -> dict[str, Any]:
    latest = veu_briefing.latest(kind if kind in {"morning", "evening"} else None)
    if latest:
        return {"ok": True, "cached": True, **latest}
    return veu_briefing.build(kind)


@app.post("/briefing/build")
def briefing_build(kind: str = "morning") -> dict[str, Any]:
    return veu_briefing.build(kind)


@app.get("/briefing/schedule")
def briefing_schedule_get() -> dict[str, Any]:
    return veu_briefing.get_schedule()


@app.post("/briefing/schedule")
def briefing_schedule_set(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    return veu_briefing.set_schedule(
        enabled=body.get("enabled") if "enabled" in body else None,
        morning_hour=body.get("morning_hour"),
        evening_hour=body.get("evening_hour"),
        tz=body.get("tz"),
    )


@app.post("/briefing/schedule/tick")
def briefing_schedule_tick() -> dict[str, Any]:
    return veu_briefing.tick_schedule()


@app.get("/inbox")
def inbox_unified(channel: str | None = None, limit: int = 40) -> dict[str, Any]:
    """Fila unificada WhatsApp/Teams/Outlook/Gmail/Slack a partir do live.json."""
    return veu_inbox.unified(channel=channel, limit=limit)


@app.post("/inbox/drafts")
def inbox_draft_create(body: InboxDraftIn) -> dict[str, Any]:
    return veu_inbox.create_draft(
        item_id=body.item_id,
        channel=body.channel,
        subject=body.subject,
        body=body.body,
        to=body.to,
    )


@app.post("/inbox/drafts/{draft_id}/decide")
def inbox_draft_decide(draft_id: str, body: ApprovalDecideIn) -> dict[str, Any]:
    return veu_inbox.decide_draft(draft_id, approve=body.approve)


class PushSubIn(BaseModel):
    endpoint: str = Field(min_length=8)
    keys: dict[str, str]
    ua: str = ""


class HfKeyIn(BaseModel):
    token: str = Field(min_length=10)
    model: str | None = None


@app.get("/push/vapid-public")
def push_vapid_public() -> dict[str, Any]:
    from veu import push as veu_push

    return {"ok": True, "publicKey": veu_push.public_key()}


@app.post("/push/subscribe")
def push_subscribe(body: PushSubIn) -> dict[str, Any]:
    from veu import push as veu_push

    return veu_push.subscribe(
        {"endpoint": body.endpoint, "keys": body.keys, "ua": body.ua}
    )


@app.post("/push/unsubscribe")
def push_unsubscribe(body: PushSubIn) -> dict[str, Any]:
    from veu import push as veu_push

    return veu_push.unsubscribe(body.endpoint)


@app.post("/push/test")
def push_test() -> dict[str, Any]:
    from veu import push as veu_push

    return veu_push.notify("Véu", "Push ligado — notificações ativas", url="/", tag="test")


@app.post("/llm/keys/huggingface")
def llm_hf_key(body: HfKeyIn) -> dict[str, Any]:
    """Grava HF_TOKEN no .env e liga o provedor no chat."""
    import re as _re

    from veu.subscriptions import resolve_env_file, upsert_env

    raw = body.token.strip()
    m = _re.search(r"(hf_[A-Za-z0-9]{20,})", raw)
    token = m.group(1) if m else raw
    if not token.startswith("hf_") or len(token) < 20:
        return {"ok": False, "error": "token Hugging Face inválido (começa com hf_)"}
    updates = {
        "HF_TOKEN": token,
        "HUGGINGFACE_HUB_TOKEN": token,
    }
    if body.model and body.model.strip():
        updates["VEU_HF_MODEL"] = body.model.strip()
    upsert_env(resolve_env_file(), updates)
    import os as _os

    for k, v in updates.items():
        _os.environ[k] = v
    rt.llm.reload()
    return {
        "ok": True,
        "provider": "huggingface",
        "model": rt.llm.hf_model,
        "llm": rt.llm.pulse(),
    }


@app.get("/decisions")
def decisions_diary(limit: int = 50) -> dict[str, Any]:
    """Diário de decisões — memória + aprovações."""
    rows = list(reversed(rt.memory.recent(sink="decisions", limit=limit)))
    # também approvals log
    apr = veu_approvals.board()
    for item in apr.get("recent") or []:
        rows.append(
            {
                "id": item.get("id"),
                "ts": item.get("decided_at") or item.get("created"),
                "kind": "approval",
                "intent": item.get("intent"),
                "risk": item.get("risk"),
                "status": item.get("status"),
                "why": f"respiração {item.get('breath')} · risco {item.get('risk')}",
                "outcome": item.get("status"),
            }
        )
    # normaliza
    out = []
    for r in rows:
        out.append(
            {
                "id": r.get("id"),
                "ts": r.get("ts"),
                "kind": r.get("kind") or "decision",
                "title": r.get("intent") or r.get("title") or r.get("kind") or "decisão",
                "why": r.get("why") or r.get("note") or "",
                "outcome": r.get("outcome") or r.get("status") or r.get("approved"),
                "raw": {k: v for k, v in r.items() if k not in {"raw"}},
            }
        )
    def _ts_key(x: dict[str, Any]) -> float:
        ts = x.get("ts")
        if isinstance(ts, (int, float)):
            return float(ts if ts > 1e12 else ts)
        if isinstance(ts, str) and ts:
            try:
                from datetime import datetime

                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0
        return 0.0

    out.sort(key=_ts_key, reverse=True)
    return {"ok": True, "decisions": out[:limit], "count": len(out[:limit]), "pulse": rt.memory.pulse()}


class ActionDecideIn(BaseModel):
    status: Literal["open", "done", "dismissed", "updated", "in_progress"] = "done"
    note: str = ""


@app.get("/autonomous")
@app.get("/autonomous/board")
def autonomous_board(status: str | None = None, limit: int = 80) -> dict[str, Any]:
    from veu import actions as veu_actions

    return veu_actions.board(status=status, limit=limit)


@app.post("/autonomous/scan")
def autonomous_scan() -> dict[str, Any]:
    """Percorre apps/agentes/live.json e prepara ações para o usuário escolher."""
    from veu import autonomous as veu_auto

    return veu_auto.scan(runtime=rt)


@app.post("/autonomous/clean-noise")
def autonomous_clean_noise() -> dict[str, Any]:
    """Descarta propostas ECC/agent em massa."""
    from veu import actions as veu_actions

    return veu_actions.dismiss_noise()


@app.post("/autonomous/actions/{action_id}/decide")
def autonomous_decide(action_id: str, body: ActionDecideIn) -> dict[str, Any]:
    """Marca ação como feita / atualizada / descartada / em progresso (e pode despachar ajuda)."""
    from veu import autonomous as veu_auto

    return veu_auto.act(
        action_id,
        status=body.status,
        note=body.note,
        runtime=rt,
    )


@app.get("/productivity")
def productivity_snapshot() -> dict[str, Any]:
    """Indicadores, gráficos e filas (reuniões, empresas, tarefas, estudos)."""
    from veu import productivity as veu_prod

    return veu_prod.snapshot()


class CloneChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CloneTeachIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    kind: str = "sample"


class CloneCorrectIn(BaseModel):
    clone_said: str = ""
    better: str = Field(min_length=1, max_length=2000)


@app.get("/clone")
@app.get("/clone/status")
def clone_status() -> dict[str, Any]:
    from veu import clone as veu_clone

    return veu_clone.status()


@app.get("/clone/history")
def clone_history(limit: int = 40) -> dict[str, Any]:
    from veu import clone as veu_clone

    return veu_clone.history(limit=limit)


@app.post("/clone/harvest")
def clone_harvest() -> dict[str, Any]:
    from veu import clone as veu_clone

    return veu_clone.harvest(memory=rt.memory)


@app.post("/clone/chat")
def clone_chat(body: CloneChatIn) -> dict[str, Any]:
    from veu import clone as veu_clone

    return veu_clone.chat(body.message, llm=rt.llm)


@app.post("/clone/teach")
def clone_teach(body: CloneTeachIn) -> dict[str, Any]:
    from veu import clone as veu_clone

    return veu_clone.teach(text=body.text, kind=body.kind)


@app.post("/clone/correct")
def clone_correct(body: CloneCorrectIn) -> dict[str, Any]:
    from veu import clone as veu_clone

    return veu_clone.correct(clone_said=body.clone_said, better=body.better)


class ReaAnalyzeIn(BaseModel):
    target: str = Field(min_length=1, max_length=2000)
    kind: str = "url"  # url | path
    observation_ms: int = Field(default=1500, ge=200, le=15_000)
    fetch_source_maps: bool = True


class ReaPublishIn(BaseModel):
    repo: str | None = None
    owner: str | None = None
    description: str | None = None
    private: bool = True


@app.get("/rea")
@app.get("/rea/status")
def rea_status() -> dict[str, Any]:
    """REA (morluto/rea) — CLI + CDP Lite disponíveis?"""
    from veu import rea as veu_rea

    return veu_rea.status()


@app.get("/rea/jobs")
def rea_jobs(limit: int = 20) -> dict[str, Any]:
    from veu import rea as veu_rea

    return veu_rea.list_jobs(limit=limit)


@app.get("/rea/jobs/{job_id}")
def rea_job(job_id: str) -> dict[str, Any]:
    from veu import rea as veu_rea

    return veu_rea.get_job(job_id)


@app.post("/rea/analyze")
def rea_analyze(body: ReaAnalyzeIn) -> dict[str, Any]:
    """Reverse: site (URL via Chrome Lite) ou app JS/Electron (path)."""
    from veu import rea as veu_rea

    return veu_rea.analyze(
        target=body.target,
        kind=body.kind,
        observation_ms=body.observation_ms,
        fetch_source_maps=body.fetch_source_maps,
    )


@app.post("/rea/jobs/{job_id}/publish")
def rea_publish(job_id: str, body: ReaPublishIn | None = None) -> dict[str, Any]:
    """Publica evidência REA num repositório GitHub novo."""
    from veu import rea as veu_rea

    body = body or ReaPublishIn()
    return veu_rea.publish(
        job_id,
        repo=body.repo,
        owner=body.owner,
        description=body.description,
        private=body.private,
    )


@app.post("/rea/mcp/register")
def rea_mcp_register() -> dict[str, Any]:
    """Cadastra REA como MCP stdio no barramento do Véu."""
    from veu import rea as veu_rea

    cfg = veu_rea.mcp_config()
    # formato Cursor/Claude: mcpServers.<id>
    payload = {
        "mcpServers": {
            str(cfg["id"]): {
                "command": cfg["command"],
                "args": cfg.get("args") or [],
                "env": cfg.get("env") or {},
            }
        }
    }
    try:
        result = mcp_bus.import_json(payload, probe_now=False, confirm=True, subject="veu-rea")
        return {"ok": True, "id": cfg.get("id"), "imported": result, "config": cfg}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:400], "config": cfg}


class Esp32EnrollIn(BaseModel):
    label: str = "placa amarela"
    model: str = "ESP32-2432S028R"


class Esp32EventIn(BaseModel):
    type: str = Field(min_length=1, max_length=64)
    payload: str = ""
    device: str = "esp32-cyd"


@app.get("/device/esp32/board")
def esp32_board() -> dict[str, Any]:
    """Ficha da placa amarela CYD (TFT 2.8 / 61115)."""
    from veu import esp32_device as veu_esp

    return veu_esp.board_info()


@app.get("/device/esp32/devices")
def esp32_devices() -> dict[str, Any]:
    from veu import esp32_device as veu_esp

    return veu_esp.list_devices()


@app.post("/device/esp32/enroll")
def esp32_enroll(body: Esp32EnrollIn | None = None) -> dict[str, Any]:
    """Gera token pra gravar no portal WiFi da placa."""
    from veu import esp32_device as veu_esp

    body = body or Esp32EnrollIn()
    return veu_esp.enroll(label=body.label, model=body.model)


@app.get("/device/esp32/state")
def esp32_state(request: Request) -> dict[str, Any]:
    """Snapshot compacto pro TFT (Bearer = token da placa)."""
    from veu import esp32_device as veu_esp

    device = getattr(request.state, "veu_device", None)
    return veu_esp.compact_state(rt, device=device)


@app.post("/device/esp32/event")
def esp32_event(request: Request, body: Esp32EventIn) -> dict[str, Any]:
    """Eventos da placa: captura, fôlego, ping."""
    from veu import esp32_device as veu_esp

    device = getattr(request.state, "veu_device", None)
    return veu_esp.handle_event(
        rt, device=device, typ=body.type, payload=body.payload
    )


@app.get("/device/esp32/events")
def esp32_events(limit: int = 30) -> dict[str, Any]:
    from veu import esp32_device as veu_esp

    return veu_esp.recent_events(limit=limit)


class MentalCheckinIn(BaseModel):
    mood: int = Field(ge=1, le=5)
    energy: int = Field(ge=1, le=5)
    focus: int = Field(ge=1, le=5)
    note: str = ""
    tags: list[str] = Field(default_factory=list)


class MentalTriggerIn(BaseModel):
    kind: str = "gatilho"
    title: str = Field(min_length=1, max_length=160)
    body: str = ""
    intensity: int = Field(default=3, ge=1, le=5)


@app.get("/mental")
@app.get("/mental/board")
def mental_board() -> dict[str, Any]:
    from veu import mental_health as veu_mh

    return veu_mh.board()


@app.post("/mental/checkin")
def mental_checkin(body: MentalCheckinIn) -> dict[str, Any]:
    from veu import mental_health as veu_mh

    return veu_mh.checkin(
        mood=body.mood,
        energy=body.energy,
        focus=body.focus,
        note=body.note,
        tags=body.tags,
    )


@app.post("/mental/trigger")
def mental_trigger(body: MentalTriggerIn) -> dict[str, Any]:
    from veu import mental_health as veu_mh

    return veu_mh.log_trigger(
        kind=body.kind,
        title=body.title,
        body=body.body,
        intensity=body.intensity,
    )


@app.post("/mental/scan")
def mental_scan() -> dict[str, Any]:
    from veu import mental_health as veu_mh

    return veu_mh.scan_context()


@app.post("/mental/alerts/{alert_id}/ack")
def mental_ack(alert_id: str) -> dict[str, Any]:
    from veu import mental_health as veu_mh

    return veu_mh.ack_alert(alert_id)


@app.get("/routines")
def routines_list() -> dict[str, Any]:
    return veu_routines.list_routines()


@app.post("/routines")
def routines_upsert(body: RoutineIn) -> dict[str, Any]:
    return veu_routines.upsert(
        routine_id=body.id,
        title=body.title,
        cron=body.cron,
        intent=body.intent,
        breath=body.breath,
        enabled=body.enabled,
    )


@app.delete("/routines/{routine_id}")
def routines_delete(routine_id: str) -> dict[str, Any]:
    return veu_routines.delete(routine_id)


@app.post("/routines/tick")
def routines_tick() -> dict[str, Any]:
    """Disparo manual do avaliador de rotinas (debug)."""
    fired = veu_routines.tick()
    return {"ok": True, "fired": fired, "count": len(fired)}


@app.get("/agents")
def agents() -> dict[str, Any]:
    """Catálogo ECC de agentes disponíveis para acionamento direto."""
    items = [
        {
            "id": a.id,
            "title": a.title,
            "role": a.role,
            "triggers": list(a.triggers)[:8],
            "description": getattr(a, "description", "") or "",
            "can_do": list(getattr(a, "can_do", []) or [])[:8],
            "tools": list(getattr(a, "tools", []) or [])[:12],
        }
        for a in rt.ecc.agents.values()
    ]
    return {"agents": items, "count": len(items)}


@app.get("/skills")
def skills() -> dict[str, Any]:
    """Skills ECC — musculatura acionável."""
    items = [
        {
            "id": s.id,
            "title": s.title,
            "triggers": list(s.triggers)[:8],
            "description": getattr(s, "description", "") or "",
            "can_do": list(getattr(s, "can_do", []) or [])[:8],
            "origin": getattr(s, "origin", "") or "",
        }
        for s in sorted(rt.ecc.skills.values(), key=lambda x: x.title.lower())
    ]
    return {"skills": items, "count": len(items)}


@app.get("/ecc")
def ecc_catalog() -> dict[str, Any]:
    """Catálogo completo ECC — agentes, skills e o que dá pra fazer."""
    return rt.ecc.catalog()


@app.get("/subscriptions")
def subscriptions_get() -> dict[str, Any]:
    """Espaços OpenAI · Claude · Grok — API key e/ou assinatura de conta."""
    return {**subs.status_snapshot(), "llm": rt.llm.pulse()}


class LlmChatIn(BaseModel):
    message: str = Field(min_length=1)
    provider: Literal[
        "openai", "deepseek", "claude", "xai", "ollama", "openrouter", "huggingface"
    ] | None = None
    force: bool = False
    system: str | None = None
    # Conversa nos ícones ChatGPT/Claude/Grok: fica no Véu (sem abrir aba).
    stay_in_veu: bool = True
    fallback_local: bool = True


@app.get("/llm/decide")
def llm_decide() -> dict[str, Any]:
    """Quem assume o chat agora + superfície de cada assinatura."""
    rt.llm.reload()
    decision = rt.llm.decide("chat")
    surfaces = [
        {
            "id": "chatgpt",
            "provider": "openai",
            "label": "ChatGPT",
            "url": "https://chatgpt.com/",
            "kind": "chat",
        },
        {
            "id": "codex",
            "provider": "openai",
            "label": "Codex",
            "url": "https://chatgpt.com/codex",
            "kind": "work",
        },
        {
            "id": "claude",
            "provider": "claude",
            "label": "Claude",
            "url": "https://claude.ai/new",
            "kind": "chat",
        },
        {
            "id": "claude-work",
            "provider": "claude",
            "label": "Claude Work",
            "url": "https://claude.ai/projects",
            "kind": "work",
        },
        {
            "id": "grok",
            "provider": "xai",
            "label": "Grok",
            "url": "https://grok.com/",
            "kind": "chat",
        },
    ]
    snap = subs.status_snapshot()
    by_id = {s["id"]: s for s in snap.get("subscriptions") or []}
    for s in surfaces:
        slot = by_id.get(s["provider"]) or {}
        modes = slot.get("modes") or {}
        sub = modes.get("subscription") or {}
        ak = modes.get("api_key") or {}
        s["status"] = slot.get("status") or "ready"
        s["api_key"] = bool(ak.get("configured"))
        s["subscription"] = sub.get("status") == "linked"
        s["can_chat_in_veu"] = bool(ak.get("configured"))
        s["can_open_subscription"] = bool(sub.get("status") in {"linked", "pending"} or s["provider"] == "openai")
    return {"decision": decision, "surfaces": surfaces, "llm": rt.llm.pulse()}


class SubscriptionComposeIn(BaseModel):
    provider: Literal["openai", "claude", "xai", "chatgpt", "codex", "grok"]
    message: str = Field(min_length=1)
    surface: str | None = None


@app.post("/llm/subscription-compose")
def llm_subscription_compose(body: SubscriptionComposeIn) -> dict[str, Any]:
    """Usa assinatura (ChatGPT Plus / Claude Pro / Grok) via Host — sem API key."""
    try:
        return subs.compose_subscription(
            body.provider,
            body.message.strip(),
            surface=body.surface,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.get("/openrag/pulse")
def openrag_pulse() -> dict[str, Any]:
    return rt.openrag.pulse()


class OpenRagAskIn(BaseModel):
    message: str = Field(min_length=1)
    limit: int = 8


@app.post("/openrag/ask")
def openrag_ask(body: OpenRagAskIn) -> dict[str, Any]:
    result = rt.openrag.ask(body.message.strip(), limit=body.limit)
    rt.memory.append("openrag.ask", {"q": body.message[:200], "ok": result.get("ok")}, sink="audit")
    return result


@app.get("/notion/pulse")
def notion_pulse() -> dict[str, Any]:
    return {
        "id": "notion",
        "status": rt.notion.status(),
        "live": rt.notion.live,
    }


class NotionSearchIn(BaseModel):
    query: str = Field(min_length=1)
    page_size: int = 10


@app.post("/notion/search")
def notion_search(body: NotionSearchIn) -> dict[str, Any]:
    result = rt.notion.search(body.query.strip(), page_size=body.page_size)
    rt.memory.append("notion.search", {"q": body.query[:120], "ok": result.get("ok")}, sink="audit")
    return result


@app.post("/llm/chat")
def llm_chat(body: LlmChatIn) -> dict[str, Any]:
    """Conversa no Véu. Por padrão não abre aba externa (stay_in_veu=True)."""
    from veu.llm import SYSTEM_OS

    rt.llm.reload()
    prefer = body.provider
    stay = body.stay_in_veu
    result = rt.llm.complete(
        body.message.strip(),
        system=body.system or SYSTEM_OS,
        purpose="chat",
        prefer=prefer if not body.force else None,
        force=prefer if body.force else None,
        allow_handoff=not stay,
        fallback_local=stay and body.fallback_local,
    )
    out: dict[str, Any] = {
        "ok": result.ok,
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "error": result.error,
        "decided": rt.llm.decide("chat"),
        "stay_in_veu": stay,
    }
    # Só devolve URL se o cliente pediu handoff explícito
    if not stay and result.handoff_url:
        out["action"] = {"type": "open_url", "url": result.handoff_url}
        out["handoff_url"] = result.handoff_url
        out["ok"] = True
    return out


class PlaygroundIn(BaseModel):
    """Playground unificado — OpenAI / Claude / Grok / Ollama / Hugging Face."""

    surface: Literal["openai", "claude", "xai", "ollama", "huggingface"] = "openai"
    prompt: str = Field(default="", min_length=0)
    system: str | None = None
    model: str | None = None
    # Hugging Face MCP
    tool: str | None = None
    arguments: dict[str, Any] | None = None


@app.get("/llm/playground")
def llm_playground_meta() -> dict[str, Any]:
    """O que o playground pode usar agora (keys, models, tools HF)."""
    rt.llm.reload()
    pulse = rt.llm.pulse()
    mcp_servers = mcp_bus.list_public()
    hf = next((s for s in mcp_servers if s.get("id") == "huggingface"), None)
    surfaces = [
        {
            "id": "openai",
            "label": "OpenAI",
            "kind": "llm",
            "ready": bool(pulse.get("openai_api_key")),
            "model": pulse.get("openai_model"),
            "hint": "API key em Ajustes → assinaturas",
        },
        {
            "id": "claude",
            "label": "Claude",
            "kind": "llm",
            "ready": bool(pulse.get("claude_api_key")),
            "model": pulse.get("claude_model"),
            "hint": "API key Anthropic em Ajustes → assinaturas",
        },
        {
            "id": "xai",
            "label": "Grok",
            "kind": "llm",
            "ready": bool(pulse.get("xai_api_key")),
            "model": pulse.get("xai_model"),
            "hint": "API key Grok em Ajustes → assinaturas",
        },
        {
            "id": "ollama",
            "label": "Ollama",
            "kind": "llm",
            "ready": bool(pulse.get("ollama")),
            "model": pulse.get("ollama_model"),
            "models": pulse.get("ollama_models") or [],
            "hint": "local no servidor",
        },
        {
            "id": "huggingface",
            "label": "Hugging Face",
            "kind": "mcp",
            "ready": bool(hf and hf.get("status") == "live"),
            "tools": [
                {"name": t.get("name"), "description": t.get("description")}
                for t in (hf.get("tools") or [])
            ]
            if hf
            else [],
            "hint": "MCP live — busque modelos / whoami / detalhes",
        },
    ]
    return {"surfaces": surfaces, "llm": pulse, "mcp_count": len(mcp_servers)}


@app.post("/llm/playground")
def llm_playground_run(body: PlaygroundIn) -> dict[str, Any]:
    """Roda um prompt ou tool no playground — sempre dentro do Véu."""
    from veu.llm import SYSTEM_OS

    surface = body.surface
    if surface == "huggingface":
        tool = (body.tool or "hf_whoami").strip()
        args = dict(body.arguments or {})
        if tool == "hub_repo_search" and body.prompt.strip() and "query" not in args:
            args["query"] = body.prompt.strip()
            args.setdefault("limit", 5)
            args.setdefault("repo_types", ["model"])
        if tool == "hub_repo_details" and body.prompt.strip() and "repo_ids" not in args:
            rid = body.prompt.strip().split()[0]
            args["repo_ids"] = [rid]
        call = mcp_bus.call_tool("huggingface", tool, args)
        text = ""
        result = call.get("result")
        if isinstance(result, dict):
            for c in result.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "text":
                    text += str(c.get("text") or "")
        if not text:
            text = call.get("error") or str(result or "")[:3000]
        return {
            "ok": bool(call.get("ok")),
            "surface": "huggingface",
            "kind": "mcp",
            "tool": tool,
            "text": text[:8000],
            "error": call.get("error"),
            "model": "mcp:huggingface",
        }

    prompt = body.prompt.strip()
    if not prompt:
        return {"ok": False, "error": "digite um prompt", "text": "", "surface": surface}

    # modelo opcional só para este request
    rt.llm.reload()
    prev_model = None
    env_map = {
        "openai": ("VEU_OPENAI_MODEL", "openai_model"),
        "claude": ("VEU_CLAUDE_MODEL", "claude_model"),
        "xai": ("VEU_XAI_MODEL", "xai_model"),
        "ollama": ("VEU_OLLAMA_MODEL", "ollama_model"),
    }
    if body.model and surface in env_map:
        attr = env_map[surface][1]
        prev_model = getattr(rt.llm, attr, None)
        setattr(rt.llm, attr, body.model.strip())

    try:
        result = rt.llm.complete(
            prompt,
            system=body.system if body.system is not None else SYSTEM_OS,
            purpose="chat",
            force=surface,  # type: ignore[arg-type]
            allow_handoff=False,
            # se a key falhar, cascata (Ollama/outros) — Playground nunca morre mudo
            fallback_local=True,
        )
    finally:
        if prev_model is not None and surface in env_map:
            setattr(rt.llm, env_map[surface][1], prev_model)

    return {
        "ok": bool(result.ok and (result.text or "").strip()),
        "surface": surface,
        "kind": "llm",
        "provider": result.provider,
        "model": result.model,
        "text": result.text or result.error or "",
        "error": result.error,
    }


@app.post("/subscriptions")
def subscriptions_connect(body: SubscriptionIn) -> dict[str, Any]:
    """Conecta via API key — grava no .env e recarrega o LLM."""
    result = subs.connect_api_key(body.provider, body.api_key, body.model)
    rt.llm.reload()
    rt.refresh_connector_status()
    return result


@app.post("/subscriptions/link")
def subscriptions_link(body: SubscriptionLinkIn) -> dict[str, Any]:
    """Inicia ligação por assinatura de conta (ChatGPT / Claude.ai / Grok)."""
    result = subs.begin_subscription_link(body.provider)
    rt.llm.reload()
    rt.refresh_connector_status()
    return result


@app.post("/subscriptions/confirm")
def subscriptions_confirm(body: SubscriptionLinkIn) -> dict[str, Any]:
    """Confirma que a conta/assinatura está logada no browser."""
    result = subs.confirm_subscription(body.provider)
    rt.llm.reload()
    rt.refresh_connector_status()
    return result


@app.delete("/subscriptions/{provider}")
def subscriptions_disconnect(
    provider: str, path: Literal["api_key", "subscription", "both"] = "both"
) -> dict[str, Any]:
    """Remove API key, assinatura, ou ambos."""
    result = subs.disconnect(provider, path=path)
    rt.llm.reload()
    rt.refresh_connector_status()
    return result


class ServerIn(BaseModel):
    """Cadastro de servidor do Hudson — host que ele informa; senha vai pro .env."""

    id: str | None = None
    name: str = ""
    host: str = Field(min_length=1)
    port: int = 22
    username: str = "root"
    password: str | None = None
    notes: str | None = None
    clear_secret: bool = False


@app.get("/mcp")
def mcp_list() -> dict[str, Any]:
    """Servidores MCP cadastrados (import JSON automático)."""
    items = mcp_bus.list_public()
    return {
        "servers": items,
        "count": len(items),
        "note": "Cole JSON Cursor/Claude em POST /mcp/import ou no chat.",
    }


class McpImportIn(BaseModel):
    """JSON MCP cru — objeto, string, ou {mcpServers:{...}}."""

    config: Any = None
    payload: Any = None
    probe: bool = False
    confirm: bool = False


@app.post("/mcp/import")
def mcp_import(body: McpImportIn, request: Request) -> dict[str, Any]:
    """Prévia (padrão) ou importação confirmada — sem rodar no import."""
    raw = body.config if body.config is not None else body.payload
    if raw is None:
        return {"ok": False, "error": "envie config ou payload"}
    session = getattr(request.state, "veu_session", None) or {}
    subject = str(session.get("subject") or "user")
    try:
        result = mcp_bus.import_json(
            raw,
            probe_now=False,  # primeiro probe só após approve, em guiado
            confirm=body.confirm,
            subject=subject,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}
    if body.confirm:
        rt.refresh_connector_status()
    return result


@app.post("/mcp/{server_id}/approve")
def mcp_approve(server_id: str) -> dict[str, Any]:
    """Marca MCP como verificado; probe inicial roda em modo guiado."""
    result = mcp_bus.approve_server(server_id)
    if result.get("ok"):
        # probe sob guiado
        breath = getattr(rt.harness, "breath", None) or "guided"
        if breath != "free":
            probe = mcp_bus.probe(server_id)
            result["probe"] = probe
        rt.refresh_connector_status()
    return result


@app.post("/mcp/{server_id}/probe")
def mcp_probe(server_id: str) -> dict[str, Any]:
    result = mcp_bus.probe(server_id)
    rt.refresh_connector_status()
    return result


@app.delete("/mcp/{server_id}")
def mcp_delete(server_id: str) -> dict[str, Any]:
    result = mcp_bus.delete(server_id)
    rt.refresh_connector_status()
    return result


@app.post("/mcp/{server_id}/call")
def mcp_call(server_id: str, body: dict[str, Any]) -> dict[str, Any]:
    tool = str(body.get("tool") or body.get("name") or "").strip()
    if not tool:
        return {"ok": False, "error": "tool obrigatório"}
    args = body.get("arguments") if isinstance(body.get("arguments"), dict) else {}
    return mcp_bus.call_tool(server_id, tool, args)


@app.get("/servers")
def servers_list(reveal: bool = False) -> dict[str, Any]:
    """Servidores cadastrados — host/user mascarados por padrão; ?reveal=1 só com sessão."""
    from veu.targets import targets as veu_targets

    items = fleet.list_servers(reveal=reveal)
    for s in items:
        sid = str(s.get("id") or "")
        s["mark"] = veu_targets.get_mark("server", sid)
    return {
        "servers": items,
        "count": len(items),
        "revealed": bool(reveal),
        "note": "Host/IP/user mascarados por padrão. Segredo nunca em claro.",
    }


@app.get("/servers/board")
def servers_board(reveal: bool = False) -> dict[str, Any]:
    """Ícones: inventário live.json (apps/domínios) + frota SSH cadastrada."""
    return fleet.board(reveal=reveal)


class DestructiveConfirmIn(BaseModel):
    confirm_name: str | None = None
    advanced: bool | None = None


@app.post("/servers/{server_id}/ssh")
def servers_ssh(
    server_id: str,
    reveal: bool = False,
    body: DestructiveConfirmIn | None = Body(None),
) -> dict[str, Any]:
    """Devolve comando SSH (+ probe se senha cadastrada). UI abre terminal no host."""
    from veu.targets import targets as veu_targets

    confirm = (body.confirm_name if body else None) or None
    gate = veu_targets.authorize_destructive(
        kind="server",
        target_id=server_id,
        action="ssh_write",
        confirm_name=confirm,
        who="user",
    )
    if not gate.get("allowed"):
        return gate
    return fleet.ssh_launch(server_id, reveal=reveal)


@app.post("/servers")
def servers_upsert(body: ServerIn) -> dict[str, Any]:
    """Cria/atualiza cadastro. Senha nova grava no .env; vazia mantém a atual."""
    try:
        row = fleet.upsert_server(
            server_id=body.id,
            name=body.name,
            host=body.host,
            port=body.port,
            username=body.username,
            password=body.password,
            notes=body.notes,
            clear_secret=body.clear_secret,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "server": row}


@app.delete("/servers/{server_id}")
def servers_delete(
    server_id: str,
    confirm_name: str | None = None,
) -> dict[str, Any]:
    """Remove cadastro e limpa VEU_SRV_*_PASSWORD do .env."""
    from veu.targets import targets as veu_targets

    gate = veu_targets.authorize_destructive(
        kind="server",
        target_id=server_id,
        action="delete",
        confirm_name=confirm_name,
        who="user",
    )
    if not gate.get("allowed"):
        return gate
    ok = fleet.delete_server(server_id)
    if not ok:
        return {"ok": False, "error": "servidor não encontrado"}
    return {"ok": True}


@app.post("/servers/{server_id}/test")
def servers_test(server_id: str) -> dict[str, Any]:
    """Testa SSH só neste host cadastrado."""
    try:
        return fleet.test_connection(server_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@app.get("/servers/{server_id}/sites")
def servers_sites(server_id: str) -> dict[str, Any]:
    """Lista sites/serviços neste host cadastrado."""
    try:
        return fleet.sites(server_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@app.get("/servers/{server_id}/maintenance")
def servers_maintenance(server_id: str) -> dict[str, Any]:
    """Status de manutenção (leitura) deste host cadastrado."""
    try:
        return fleet.maintenance(server_id)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# ── Ruflo spine + ruOS fleet / vault ─────────────────────────────────────────


@app.get("/ruflo")
@app.get("/ruflo/status")
def ruflo_status() -> dict[str, Any]:
    """Espinha Ruflo — plugins, swarm, Claude control, arquitetura."""
    from veu.ruflo_spine import spine as ruflo_spine

    try:
        rp = rt.pulse()
    except Exception:  # noqa: BLE001
        rp = {}
    return ruflo_spine.snapshot(runtime_pulse=rp)


@app.get("/ruflo/plugins")
def ruflo_plugins() -> dict[str, Any]:
    from veu.ruflo_spine import spine as ruflo_spine

    plugs = ruflo_spine.plugins()
    return {"ok": True, "plugins": plugs, "enabled": sum(1 for p in plugs if p.get("enabled"))}


@app.post("/ruflo/plugins/{plugin_id}")
def ruflo_plugin_toggle(plugin_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    from veu.ruflo_spine import spine as ruflo_spine

    enabled = True if body is None else bool((body or {}).get("enabled", True))
    return ruflo_spine.set_plugin(plugin_id, enabled)


@app.post("/ruflo/control")
def ruflo_control(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruflo_spine import spine as ruflo_spine

    return ruflo_spine.set_control(
        level=body.get("level"),  # type: ignore[arg-type]
        approval=body.get("approval"),  # type: ignore[arg-type]
        active=body.get("active"),
    )


@app.post("/ruflo/swarm/init")
def ruflo_swarm_init(body: dict[str, Any] | None = None) -> dict[str, Any]:
    from veu.ruflo_spine import spine as ruflo_spine

    topo = str((body or {}).get("topology") or "hierarchical")
    return ruflo_spine.swarm_init(topo)  # type: ignore[arg-type]


@app.post("/ruflo/swarm/stop")
def ruflo_swarm_stop() -> dict[str, Any]:
    from veu.ruflo_spine import spine as ruflo_spine

    return ruflo_spine.swarm_stop()


@app.post("/ruflo/missions")
def ruflo_mission_create(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruflo_spine import spine as ruflo_spine

    return ruflo_spine.mission_create(
        str(body.get("goal") or ""),
        confirm=bool(body.get("confirm")),
    )


@app.post("/ruflo/theme")
def ruflo_theme(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruflo_spine import spine as ruflo_spine

    # aceita theme | id | palette (UI Orbital)
    name = str(body.get("theme") or body.get("id") or body.get("palette") or "orbital")
    palette = body.get("palette")
    return ruflo_spine.set_theme(name, palette if isinstance(palette, str) else None)


@app.get("/ruos")
@app.get("/ruos/desktops")
def ruos_desktops(q: str = "") -> dict[str, Any]:
    """Frota Véu — cloud, Lite, Mac/Linux, RustDesk."""
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.board(query=q)


@app.post("/ruos/desktops/{desktop_id}/start")
def ruos_start(desktop_id: str) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.start(desktop_id)


@app.post("/ruos/desktops/{desktop_id}/stop")
def ruos_stop(desktop_id: str) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.stop(desktop_id)


@app.post("/ruos/desktops/{desktop_id}/reconnect")
def ruos_reconnect(desktop_id: str) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.reconnect(desktop_id)


@app.post("/ruos/provision")
def ruos_provision(body: dict[str, Any] | None = None) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    profile = str((body or {}).get("profile") or "desktop")
    return fleet_ruos.provision_cloud(profile)  # type: ignore[arg-type]


@app.post("/ruos/rustdesk")
def ruos_rustdesk(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.add_rustdesk(str(body.get("id") or ""), str(body.get("label") or ""))


@app.post("/ruos/enroll")
def ruos_enroll(body: dict[str, Any]) -> dict[str, Any]:
    """Gera comando one-shot (linux/mac) — token 15 min."""
    from veu.ruos_fleet import fleet_ruos

    platform = str(body.get("platform") or "linux")
    if platform not in {"linux", "mac"}:
        return {"ok": False, "error": "platform must be linux|mac"}
    return fleet_ruos.generate_enroll(platform)  # type: ignore[arg-type]


@app.post("/ruos/enroll/claim")
def ruos_enroll_claim(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.claim_enroll(
        str(body.get("token") or ""),
        host_name=str(body.get("host_name") or ""),
        rustdesk_id=str(body.get("rustdesk_id") or ""),
    )


@app.get("/ruos/enroll.sh")
def ruos_enroll_sh() -> Any:
    from fastapi.responses import PlainTextResponse
    from veu.ruos_fleet import fleet_ruos

    return PlainTextResponse(fleet_ruos.enroll_script(), media_type="text/x-shellscript")


@app.get("/ruos/snapshots")
def ruos_snapshots(desktop_id: str | None = None) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.snapshots(desktop_id)


@app.post("/ruos/snapshots")
def ruos_take_snapshot(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.take_snapshot(
        str(body.get("desktop_id") or ""),
        str(body.get("label") or ""),
        as_template=bool(body.get("template")),
    )


@app.post("/ruos/snapshots/{snap_id}/duplicate")
def ruos_dup_snapshot(snap_id: str) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.duplicate_snapshot(snap_id)


@app.get("/browser/probe")
def browser_probe(url: str = "") -> dict[str, Any]:
    """11.2 — cabeçalhos XFO/CSP + SSRF; decide iframe vs Host vs proxy SO."""
    from veu import browser_probe as bp
    from veu import browser_view as bv

    out = bp.probe(url)
    # Preferir janela do SO (proxy) quando o site só bloqueia frame-ancestors.
    if out.get("ok") and out.get("iframe_ok") is False and out.get("mode") != "blocked":
        hint = bv.probe_hint(str(out.get("url") or url))
        if hint.get("view") == "proxy":
            out["mode"] = "proxy"
            out["iframe_ok"] = True
            out["view"] = "proxy"
            out["view_path"] = hint.get("view_path")
            out["reason"] = hint.get("reason") or out.get("reason")
            out["hint"] = "conteúdo na janela do Browser do SO"
        elif hint.get("view") == "host":
            out["mode"] = "host"
            out["view"] = "host"
            out["hint"] = hint.get("reason")
    return out


@app.get("/browser/view")
def browser_view(request: Request, url: str = ""):
    """Abre URL na janela do Browser do SO (proxy que remove frame-ancestors)."""
    from veu import browser_view as bv

    origin = str(request.base_url).rstrip("/")
    prefix = f"{origin}/browser/view?url="
    return bv.fetch_view(url, proxy_prefix=prefix)


@app.get("/browser/lite/status")
def browser_lite_status() -> dict[str, Any]:
    """Chrome Lite (CDP) disponível? — padrão ruOS Lite."""
    from veu import browser_lite as bl

    return bl.list_sessions()


@app.post("/browser/lite/sessions")
def browser_lite_start(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inicia sessão Lite: Chrome real streamado na janela do SO."""
    from veu import browser_lite as bl

    body = body or {}
    url = str(body.get("url") or "https://web.whatsapp.com/").strip()
    sid = str(body.get("id") or "") or None
    return bl.start_session(url, sid=sid)


@app.get("/browser/lite/sessions")
def browser_lite_list() -> dict[str, Any]:
    from veu import browser_lite as bl

    return bl.list_sessions()


@app.delete("/browser/lite/sessions/{sid}")
def browser_lite_stop(sid: str) -> dict[str, Any]:
    from veu import browser_lite as bl

    return bl.stop_session(sid)


@app.get("/browser/lite/{sid}/frame.jpg")
def browser_lite_frame(sid: str):
    """Último frame JPEG da sessão Lite (polling)."""
    from fastapi.responses import Response
    from veu import browser_lite as bl

    sess = bl.get_session(sid)
    if not sess:
        return JSONResponse({"ok": False, "error": "sessão não encontrada"}, status_code=404)
    if sess.error:
        return JSONResponse({"ok": False, "error": sess.error}, status_code=502)
    if not sess.frame_jpeg:
        # placeholder 1x1 até o primeiro frame
        import base64

        tiny = base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
            "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
            "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
            "AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEB"
            "AQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAGfAP/E"
            "ABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAI"
            "AQMBAT8Bf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8Bf//Z"
        )
        return Response(content=tiny, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    return Response(
        content=sess.frame_jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Veu-Lite-Ts": str(int(sess.frame_ts * 1000)),
        },
    )


@app.post("/browser/lite/{sid}/input")
def browser_lite_input(sid: str, body: dict[str, Any]) -> dict[str, Any]:
    from veu import browser_lite as bl

    sess = bl.get_session(sid)
    if not sess:
        return {"ok": False, "error": "sessão não encontrada"}
    sess.enqueue_input(body or {})
    return {"ok": True}


@app.get("/os/workspaces")
def os_workspaces_list() -> dict[str, Any]:
    from veu import os_workspaces as osw

    return osw.list_workspaces()


@app.get("/os/workspaces/{ws_id}")
def os_workspaces_get(ws_id: str) -> dict[str, Any]:
    from veu import os_workspaces as osw

    return osw.get_workspace(ws_id)


@app.post("/os/workspaces")
def os_workspaces_save(body: dict[str, Any]) -> dict[str, Any]:
    from veu import os_workspaces as osw

    return osw.save_workspace(
        name=str(body.get("name") or ""),
        windows=list(body.get("windows") or []),
        company=str(body.get("company") or "") or None,
        browser_tabs=list(body.get("browser_tabs") or []) or None,
        ws_id=str(body.get("id") or "") or None,
    )


@app.post("/os/workspaces/{ws_id}/activate")
def os_workspaces_activate(ws_id: str) -> dict[str, Any]:
    from veu import os_workspaces as osw

    return osw.activate(ws_id)


@app.delete("/os/workspaces/{ws_id}")
def os_workspaces_delete(ws_id: str) -> dict[str, Any]:
    from veu import os_workspaces as osw

    return osw.delete_workspace(ws_id)


@app.post("/ruos/lite/resume")
def ruos_lite_resume() -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.resume_lite()


@app.post("/ruos/lite/ai")
def ruos_lite_ai(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_fleet import fleet_ruos

    return fleet_ruos.lite_set_ai(bool(body.get("enabled")))


@app.get("/ruos/keys")
def ruos_keys() -> dict[str, Any]:
    """Vault write-only — Keys / LLM routing / MCP / Slack / Tailscale."""
    from veu.ruos_vault import vault

    return vault.status()


@app.post("/ruos/keys/model")
def ruos_keys_model(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_vault import vault

    return vault.put_model_key(str(body.get("slot") or ""), str(body.get("value") or ""))


@app.delete("/ruos/keys/model/{slot}")
def ruos_keys_model_del(slot: str) -> dict[str, Any]:
    from veu.ruos_vault import vault

    return vault.delete_model_key(slot)


@app.post("/ruos/keys/routing")
def ruos_keys_routing(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_vault import vault

    return vault.set_routing(
        str(body.get("mode") or "shared"),  # type: ignore[arg-type]
        provider=str(body.get("provider") or "cognitum"),
        custom_base=str(body.get("custom_base") or ""),
    )


@app.post("/ruos/keys/custom")
def ruos_keys_custom(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_vault import vault

    return vault.put_custom(str(body.get("name") or ""), str(body.get("value") or ""))


@app.post("/ruos/keys/website")
def ruos_keys_website(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_vault import vault

    return vault.put_website(
        str(body.get("site") or ""),
        str(body.get("username") or ""),
        str(body.get("password") or ""),
        include_subdomains=bool(body.get("include_subdomains")),
    )


@app.post("/ruos/keys/mcp")
def ruos_keys_mcp(body: dict[str, Any] | None = None) -> dict[str, Any]:
    from veu.ruos_vault import vault

    b = body or {}
    days = b.get("days")
    return vault.create_mcp_token(
        label=str(b.get("label") or ""),
        scope=str(b.get("scope") or "full"),  # type: ignore[arg-type]
        days=int(days) if days is not None else 30,
    )


@app.delete("/ruos/keys/mcp/{token_id}")
def ruos_keys_mcp_del(token_id: str) -> dict[str, Any]:
    from veu.ruos_vault import vault

    return vault.revoke_mcp_token(token_id)


@app.post("/ruos/keys/slack")
def ruos_keys_slack(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_vault import vault

    return vault.set_slack(body.get("webhook"), enabled=body.get("enabled"))


@app.post("/ruos/keys/tailscale")
def ruos_keys_tailscale(body: dict[str, Any]) -> dict[str, Any]:
    from veu.ruos_vault import vault

    if body.get("disconnect"):
        return vault.set_tailscale(disconnect=True)
    return vault.set_tailscale(str(body.get("auth_key") or ""))


@app.get("/memory")
def memory(limit: int = 40) -> dict[str, Any]:
    return {
        "pulse": rt.memory.pulse(),
        "recent": rt.memory.recent(limit=limit),
    }


@app.post("/weave")
def weave(body: ChatIn) -> dict[str, Any]:
    return rt.weave(body.message, breath=body.breath)


@app.get("/bridge")
def bridge_pulse() -> dict[str, Any]:
    """Status das pontes OpenClaw · Hermes · Grok Bot."""
    return rt.bridges.pulse()


class GrokHandoffIn(BaseModel):
    intent: str = Field(min_length=1)
    breath: Literal["guided", "semi", "free", "autonomous"] = "guided"
    priority: str = "normal"
    formation: dict[str, Any] | None = None
    agent: str | None = None
    via: str = "os"


class GrokAskIn(BaseModel):
    """Pedido do SO ou de um agente → Grok Bot administra na nuvem."""

    intent: str = Field(min_length=1)
    breath: Literal["guided", "semi", "free", "autonomous"] = "semi"
    agent: str | None = None
    via: Literal["os", "agent", "chat"] = "os"
    priority: str = "normal"


class GrokApproveIn(BaseModel):
    job_id: str = Field(min_length=1)
    note: str = ""


@app.post("/bridge/grokbot/handoff")
def grokbot_handoff(body: GrokHandoffIn) -> dict[str, Any]:
    """Véu → Grok Bot: enfileira / despacha job always-on."""
    result = rt.bridges.grokbot.handoff(
        intent=body.intent,
        breath=body.breath,
        formation=body.formation,
        priority=body.priority,
        agent=body.agent,
        via=body.via,
    )
    rt.memory.append("bridge.grokbot.handoff", result, sink="decisions")
    return result


@app.post("/bridge/grokbot/ask")
def grokbot_ask(body: GrokAskIn) -> dict[str, Any]:
    """Pedir ao Grok Bot pelo SO — opcionalmente via agente ECC."""
    result = rt.bridges.grokbot.ask(
        intent=body.intent,
        breath=body.breath,
        agent=body.agent,
        via=body.via,
        priority=body.priority,
    )
    rt.memory.append("bridge.grokbot.ask", result, sink="decisions")
    return result


@app.post("/bridge/grokbot/approve")
def grokbot_approve(body: GrokApproveIn) -> dict[str, Any]:
    """Aprovar decisão pendente do Grok Bot no SO."""
    result = rt.bridges.grokbot.approve(body.job_id, note=body.note)
    rt.memory.append("bridge.grokbot.approve", result, sink="decisions")
    return result


@app.get("/bridge/grokbot/inbox")
def grokbot_inbox(limit: int = 30) -> dict[str, Any]:
    """Inbox do dia a dia — decisões, importantes, updates."""
    items = rt.bridges.grokbot.inbox(limit=limit)
    return {"ok": True, "inbox": items, "count": len(items)}


@app.get("/bridge/grokbot/brief")
def grokbot_brief() -> dict[str, Any]:
    """Resumo do dia: decisões, jobs em curso, agentes."""
    return rt.bridges.grokbot.brief()


@app.get("/bridge/grokbot/sideboard")
def grokbot_sideboard() -> dict[str, Any]:
    """Painel direito: live.json do Control (Outlook/Teams/agenda/reuniões) sem reler."""
    return rt.bridges.grokbot.sideboard()


@app.get("/bridge/control/live")
def control_live_board() -> dict[str, Any]:
    """Snapshot útil do Control kiosk live.json — reuse, não rebuild."""
    from veu.bridges import control_live

    return control_live.sideboard()


@app.get("/bridge/control/companies")
def control_companies() -> dict[str, Any]:
    """Pastas Empresa → projetos → tarefas/msgs/reuniões (live.json)."""
    from veu.bridges import control_live

    return control_live.companies_tree()


@app.get("/bridge/control/companies/{company_id}")
def control_company(company_id: str) -> dict[str, Any]:
    from veu.bridges import control_live

    return control_live.company_detail(company_id)


@app.get("/bridge/control/meetings/{meeting_id}")
def control_meeting(meeting_id: str) -> dict[str, Any]:
    """Detalhe de reunião no live.json; se raso, sugere ask ao Grok Bot."""
    from veu.bridges import control_live

    tree = control_live.companies_tree()
    if not tree.get("ok"):
        return tree
    found = None
    company_name = None
    project_id = None
    for co in tree.get("companies") or []:
        for mt in (co.get("loose") or {}).get("meetings") or []:
            if str(mt.get("id")) == meeting_id:
                found, company_name = mt, co.get("name")
                break
        if found:
            break
        for p in co.get("projects") or []:
            for mt in p.get("meetings") or []:
                if str(mt.get("id")) == meeting_id:
                    found, company_name, project_id = mt, co.get("name"), p.get("id")
                    break
            if found:
                break
        if found:
            break
    if not found:
        # busca bruta no raw
        raw = control_live.load_raw() or {}
        for mt in raw.get("meetings") or []:
            if str(mt.get("id")) == meeting_id:
                found = control_live._slim_meeting(mt)
                company_name = control_live._canon_company(mt.get("empresa"))
                break
    if not found:
        ask = (
            f"No Plaud/Control: traga o resumo completo da reunião id={meeting_id} "
            "(notas, bullets, ações, comportamento). Callback com result.summary e meetings."
        )
        return {
            "ok": False,
            "available": True,
            "error": "reunião não está no live.json",
            "needs_grok": True,
            "ask": ask,
        }
    bullets = found.get("bullets") or []
    summary = str(found.get("summary") or "")
    shallow = len(bullets) < 2 and len(summary) < 40
    ask = (
        f"Aprofunde a reunião «{found.get('title')}» ({found.get('when')}) "
        f"da empresa {company_name or ''}: resumo completo, decisões, ações e "
        "sinais de comportamento/sobrecarga. Use Plaud se tiver. "
        "Callback result.summary + meetings."
    )
    return {
        "ok": True,
        "meeting": found,
        "company": company_name,
        "projectId": project_id,
        "shallow": shallow,
        "needs_grok": shallow,
        # sempre oferecee ask — se já tem bullets, o bot aprofunda; se não, preenche
        "ask": ask,
    }


@app.post("/bridge/grokbot/inbound")
def grokbot_inbound(payload: dict[str, Any]) -> dict[str, Any]:
    """Grok Bot → Véu: callback de conclusão / aprovação / espelho."""
    result = rt.bridges.grokbot.inbound(payload)
    sink = "decisions" if (result.get("event") or {}).get("priority") == "decision" else "audit"
    rt.memory.append("bridge.grokbot.inbound", result, sink=sink)
    return result


@app.get("/bridge/grokbot/queue")
def grokbot_queue(limit: int = 20) -> dict[str, Any]:
    recent = rt.bridges.grokbot.recent(limit=limit)
    board = rt.bridges.grokbot.queue_board(limit=limit)
    return {**recent, **board}


def _agenda_collect(range_key: str = "day") -> dict[str, Any]:
    """Monta agenda dia/semana/mês a partir de Grok Bot + Hermes + Studio + harness."""
    import time as _time
    from datetime import datetime, timedelta, timezone

    now = _time.time()
    # ranges em segundos
    spans = {"day": 86_400, "week": 7 * 86_400, "month": 31 * 86_400}
    span = spans.get(range_key, spans["day"])
    start = now - span
    end = now + (span if range_key != "day" else 86_400)  # inclui futuro próximo

    def in_range(ts: float | None) -> bool:
        if not ts:
            return range_key == "day"  # sem ts: só mostra no dia como vivo
        return start <= float(ts) <= end

    brief = rt.bridges.grokbot.brief()
    board = rt.bridges.grokbot.queue_board(limit=80)
    hermes = rt.bridges.hermes.queue_board(limit=40)
    harness = rt.harness.pulse()

    items: list[dict[str, Any]] = []

    def push(
        *,
        title: str,
        kind: str,
        source: str,
        ts: float | None = None,
        state: str = "",
        agent: str = "",
        message: str = "",
        job_id: str = "",
        priority: str = "",
    ) -> None:
        if not in_range(ts):
            return
        items.append(
            {
                "id": job_id or f"{source}-{len(items)}",
                "title": (title or "")[:200],
                "kind": kind,
                "source": source,
                "ts": ts or now,
                "state": state,
                "agent": agent,
                "message": (message or "")[:400],
                "priority": priority,
                "job_id": job_id or None,
            }
        )

    for j in (board.get("running") or []) + (board.get("queued") or []) + (
        board.get("done") or []
    ):
        push(
            title=str(j.get("intent") or j.get("job_id") or "job"),
            kind="job",
            source="grokbot",
            ts=j.get("ts"),
            state=str(j.get("state") or ""),
            agent=str(j.get("agent") or ""),
            message=str(j.get("message") or ""),
            job_id=str(j.get("job_id") or ""),
        )

    for j in (hermes.get("running") or []) + (hermes.get("queued") or []) + (
        hermes.get("done") or []
    ):
        push(
            title=str(j.get("intent") or j.get("job_id") or "hermes"),
            kind="job",
            source="hermes",
            ts=j.get("ts"),
            state=str(j.get("state") or ""),
            agent=str(j.get("agent_label") or j.get("agent") or "hermes"),
            message=str(j.get("message") or ""),
            job_id=str(j.get("job_id") or ""),
        )

    try:
        from veu.studio import store as studio_store

        for j in studio_store.list_jobs(40):
            push(
                title=f"studio · {j.get('action')} · {j.get('filename') or ''}",
                kind="studio",
                source="studio",
                ts=j.get("ts"),
                state=str(j.get("status") or ""),
                agent=str((j.get("decision") or {}).get("executor") or ""),
                message=str(((j.get("result") or {}).get("message") or ""))[:240],
                job_id=str(j.get("id") or ""),
            )
    except Exception:  # noqa: BLE001
        pass

    for ev in rt.bridges.grokbot.inbox(limit=40):
        push(
            title=str(ev.get("title") or ev.get("kind") or "inbox"),
            kind="inbox",
            source="grokbot",
            ts=ev.get("ts"),
            state=str(ev.get("state") or ev.get("priority") or ""),
            agent=str(ev.get("agent") or ""),
            message=str(ev.get("message") or ""),
            job_id=str(ev.get("job_id") or ev.get("id") or ""),
            priority=str(ev.get("priority") or ""),
        )

    if harness.get("active") and harness.get("session"):
        s = harness["session"]
        push(
            title=str(s.get("intent") or s.get("skill") or "harness"),
            kind="harness",
            source="harness",
            ts=s.get("ts") or s.get("started") or now,
            state="running",
            agent=str(s.get("agent") or "ecc"),
            message=str(s.get("reason") or ""),
            job_id=str(s.get("id") or s.get("session_id") or ""),
        )

    # Calendário real (ICS + Host Google/Outlook)
    cal_tip: str | None = None
    try:
        from veu import calendar_feed

        cal = calendar_feed.collect(range_key, limit=40)
        for ev in cal.get("items") or []:
            push(
                title=str(ev.get("title") or "evento"),
                kind="calendar",
                source=str(ev.get("source") or "calendar"),
                ts=ev.get("ts"),
                state=str(ev.get("state") or "scheduled"),
                agent=str(ev.get("agent") or "calendar"),
                message=str(ev.get("message") or ""),
                job_id=str(ev.get("id") or ""),
                priority="calendar",
            )
        cal_tip = cal.get("tip")
    except Exception:  # noqa: BLE001
        cal_tip = None

    items.sort(key=lambda x: float(x.get("ts") or 0), reverse=True)

    # Agrupa por dia (para semana/mês)
    by_day: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        day = datetime.fromtimestamp(float(it["ts"]), tz=timezone.utc).strftime("%Y-%m-%d")
        by_day.setdefault(day, []).append(it)

    # Insights por range
    insights = list(brief.get("insights") or [])
    n_cal = sum(1 for i in items if i.get("kind") == "calendar")
    if n_cal:
        insights = [
            {
                "tone": "calendar",
                "text": f"Calendário · {n_cal} evento(s) (Google/Outlook/ICS).",
            },
            *insights[:4],
        ]
    if range_key == "week":
        insights = [
            {
                "tone": "week",
                "text": f"Semana · {len(items)} itens (fila + calendário).",
            },
            *insights[:4],
        ]
    elif range_key == "month":
        insights = [
            {
                "tone": "month",
                "text": f"Mês · {len(items)} registros · {len(by_day)} dias com atividade.",
            },
            *insights[:4],
        ]
    if not insights:
        insights = [
            {
                "tone": "calm",
                "text": "Sem eventos neste período. Puxe Google/Outlook no Host ou peça briefing ao Grok Bot.",
            }
        ]

    # Blocos do dia (manhã / tarde / noite) só no range day
    slots: list[dict[str, Any]] = []
    if range_key == "day":
        local = datetime.now().astimezone()
        for label, h0, h1 in (
            ("manhã", 6, 12),
            ("tarde", 12, 18),
            ("noite", 18, 24),
        ):
            bucket = [
                it
                for it in items
                if h0
                <= datetime.fromtimestamp(float(it["ts"])).astimezone().hour
                < h1
            ]
            slots.append({"id": label, "label": label, "items": bucket[:12]})

    # Pedir briefing ao Grok Bot se webhook live e range pediu e inbox vazia
    tip = brief.get("tip")
    if cal_tip and (not items or n_cal == 0):
        tip = cal_tip
    if not items and rt.bridges.grokbot.status() in {"ready", "live"}:
        tip = (
            f"Nada neste período ainda. Em Grok Bot peça: "
            f"“resuma minha agenda da { {'day': 'hoje', 'week': 'semana', 'month': 'mês'}[range_key] }”."
        )

    tz_name = datetime.now().astimezone().tzname() or "local"
    return {
        "ok": True,
        "range": range_key,
        "label": {"day": "hoje", "week": "esta semana", "month": "este mês"}.get(
            range_key, range_key
        ),
        "now": now,
        "tz": tz_name,
        "from_ts": start,
        "to_ts": end,
        "items": items[:80],
        "by_day": [
            {"day": d, "count": len(v), "items": v[:16]}
            for d, v in sorted(by_day.items(), reverse=True)
        ][:31],
        "slots": slots,
        "insights": insights[:8],
        "decisions": [
            i
            for i in (brief.get("decisions") or [])
            if in_range(i.get("ts"))
        ][:12],
        "running": [i for i in items if i.get("state") in {"running", "dispatched", "queued"}][
            :16
        ],
        "counts": {
            "items": len(items),
            "days": len(by_day),
            "decisions": len(brief.get("decisions") or []),
            "running": len(board.get("running") or []),
            "queued": len(board.get("queued") or []),
        },
        "bridges": {
            "grokbot": rt.bridges.grokbot.status(),
            "hermes": rt.bridges.hermes.status(),
        },
        "tip": tip,
        "brief_status": brief.get("status"),
    }


class VoiceModeIn(BaseModel):
    voice: Literal["llm", "clone"] = "llm"


@app.get("/os/voice")
def os_voice_get() -> dict[str, Any]:
    """Quem redige no SO: LLM ou Clone — preferência ativa no sistema."""
    from veu import voice_mode as veu_voice

    return veu_voice.status()


@app.post("/os/voice")
def os_voice_set(body: VoiceModeIn) -> dict[str, Any]:
    from veu import voice_mode as veu_voice

    return veu_voice.set_voice(body.voice)


@app.get("/os/day")
def os_day() -> dict[str, Any]:
    """Agenda do dia — alias de /os/agenda?range=day."""
    return _agenda_collect("day")


@app.get("/os/agenda")
def os_agenda(range: str = "day") -> dict[str, Any]:
    """Agenda Dia / Semana / Mês — eventos reais do SO + Grok Bot."""
    key = (range or "day").strip().lower()
    if key not in {"day", "week", "month"}:
        key = "day"
    return _agenda_collect(key)


@app.get("/os/calendar")
def os_calendar(range: str = "day") -> dict[str, Any]:
    """Só calendário (ICS + cache Host Google/Outlook)."""
    from veu import calendar_feed

    key = (range or "day").strip().lower()
    if key not in {"day", "week", "month"}:
        key = "day"
    return calendar_feed.collect(key)


@app.post("/os/calendar/ingest")
def os_calendar_ingest(body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Recebe eventos scrapados do Host (Google Calendar / Outlook)."""
    from veu import calendar_feed

    source = str(body.get("source") or body.get("app") or "calendar")
    items = body.get("items") or []
    if isinstance(items, str):
        items = [items]
    if not isinstance(items, list):
        return {"ok": False, "error": "items deve ser lista"}
    return calendar_feed.ingest_host_events(
        source=source,
        items=[str(x) for x in items],
        url=body.get("url"),
    )


@app.get("/os/queue")
def os_queue(limit: int = 40) -> dict[str, Any]:
    """Fila unificada: veu_jobs + Grok Bot + Hermes + Studio + harness."""
    board = rt.bridges.grokbot.queue_board(limit=limit)
    hermes_board = rt.bridges.hermes.queue_board(limit=limit)
    harness = rt.harness.pulse()
    studio_running: list[dict[str, Any]] = []
    studio_done: list[dict[str, Any]] = []
    try:
        from veu.studio import store as studio_store

        for j in studio_store.list_jobs(limit):
            row = {
                "job_id": j.get("id"),
                "intent": f"studio · {j.get('action')} · {j.get('filename') or ''}",
                "state": j.get("status") or "done",
                "agent": (j.get("decision") or {}).get("executor"),
                "ts": j.get("ts"),
                "source": "studio",
                "message": ((j.get("result") or {}).get("message") or "")[:240],
            }
            if row["state"] == "running":
                studio_running.append(row)
            else:
                studio_done.append(row)
    except Exception:  # noqa: BLE001
        pass

    # JobStore Véu — estados variados (queued/running/done/failed/cancelled)
    veu_running: list[dict[str, Any]] = []
    veu_queued: list[dict[str, Any]] = []
    veu_done: list[dict[str, Any]] = []
    veu_failed: list[dict[str, Any]] = []
    try:
        jb = veu_jobs.store.board(limit=limit)
        for j in jb.get("jobs") or []:
            row = {
                "job_id": j.get("id"),
                "intent": j.get("intent"),
                "state": j.get("state"),
                "agent": j.get("route") or "veu",
                "ts": j.get("created") or j.get("started"),
                "source": "veu_jobs",
                "message": ((j.get("progress") or {}).get("message") or j.get("error") or "")[
                    :240
                ],
                "breath": j.get("breath"),
                "risk": j.get("risk"),
            }
            st = str(j.get("state") or "")
            if st == "running":
                veu_running.append(row)
            elif st == "queued":
                veu_queued.append(row)
            elif st in {"done", "cancelled"}:
                veu_done.append(row)
            elif st == "failed":
                veu_failed.append(row)
    except Exception:  # noqa: BLE001
        pass

    active = None
    if harness.get("active") and harness.get("session"):
        s = harness["session"]
        active = {
            "job_id": s.get("id") or s.get("session_id"),
            "intent": s.get("intent") or s.get("skill") or "harness",
            "state": "running",
            "agent": s.get("agent") or "ecc",
            "ts": s.get("ts") or s.get("started"),
            "source": "harness",
            "message": s.get("reason") or "",
        }

    running = (
        veu_running
        + list(board.get("running") or [])
        + list(hermes_board.get("running") or [])
        + studio_running
    )
    queued = (
        veu_queued
        + list(board.get("queued") or [])
        + list(hermes_board.get("queued") or [])
    )
    if active:
        running = [active] + running

    return {
        "ok": True,
        "running": running[:24],
        "queued": queued[:24],
        "done": veu_done[:12]
        + (board.get("done") or [])[:12]
        + (hermes_board.get("done") or [])[:8]
        + studio_done[:8],
        "failed": veu_failed + (board.get("failed") or []) + (hermes_board.get("failed") or []),
        "insights": rt.bridges.grokbot.day_insights(),
        "decisions": rt.bridges.grokbot.inbox(limit=12),
        "hermes": hermes_board,
        "proposals": hermes_board.get("proposals") or [],
        "veu_jobs": veu_jobs.store.board(limit=min(limit, 24)),
        "counts": {
            **(board.get("counts") or {}),
            "running": len(running),
            "queued": len(queued),
            "hermes": (hermes_board.get("counts") or {}).get("total", 0),
            "studio": len(studio_running) + len(studio_done),
            "harness_active": bool(active),
            "veu_jobs": len(veu_running) + len(veu_queued),
        },
        "bridges": {
            "grokbot": rt.bridges.grokbot.status(),
            "hermes": rt.bridges.hermes.status(),
        },
        "tip": (rt.bridges.grokbot.brief() or {}).get("tip"),
    }


@app.get("/bridge/hermes/pulse")
def hermes_pulse() -> dict[str, Any]:
    return rt.bridges.hermes.pulse()


@app.get("/bridge/hermes/queue")
def hermes_queue(limit: int = 30) -> dict[str, Any]:
    return rt.bridges.hermes.queue_board(limit=limit)


class HermesAskIn(BaseModel):
    intent: str = Field(min_length=1)
    source: str = "os"
    agent: str | None = None


@app.post("/bridge/hermes/ask")
def hermes_ask(body: HermesAskIn) -> dict[str, Any]:
    result = rt.bridges.hermes.ask(
        body.intent, source=body.source, agent=body.agent
    )
    rt.memory.append("bridge.hermes.ask", result, sink="decisions")
    return result


class HermesPreferIn(BaseModel):
    agent: str = Field(min_length=1)


@app.post("/bridge/hermes/prefer")
def hermes_prefer(body: HermesPreferIn) -> dict[str, Any]:
    """Define o agente Hermes preferido para a fila / próximos pedidos."""
    result = rt.bridges.hermes.set_preferred_agent(body.agent)
    if result.get("ok"):
        rt.memory.append("bridge.hermes.prefer", result, sink="decisions")
    return result


class StudioRunIn(BaseModel):
    action: str
    asset_id: str | None = None
    path: str | None = None
    text: str | None = None
    filename: str | None = None
    prompt: str | None = None
    force_executor: Literal["local", "hermes", "grokbot"] | None = None


@app.get("/studio/pulse")
def studio_pulse() -> dict[str, Any]:
    return rt.studio.pulse()


@app.get("/studio/actions")
def studio_actions(path: str | None = None, filename: str | None = None, kind: str | None = None) -> dict[str, Any]:
    """Menu de ações disponíveis para um arquivo (duplo-clique)."""
    from veu.studio import store as studio_store
    from veu.studio.engine import actions_for

    name = filename or (path.split("/")[-1] if path else "") or "file"
    k = kind or studio_store.classify(name, "")
    return {"ok": True, "kind": k, "path": path, "filename": name, "actions": actions_for(k)}


@app.get("/studio/assets")
def studio_assets(limit: int = 40) -> dict[str, Any]:
    from veu.studio import store as studio_store
    from veu.integrity import verify as integrity_verify

    items = studio_store.list_assets(limit)
    for a in items:
        a["actions"] = rt.studio.menu_for_asset(a)
        path = a.get("path")
        if path:
            v = integrity_verify(str(path))
            a["selo"] = v.get("selo") or v.get("status") or "ausente"
            a["integrity"] = v.get("status")
            if v.get("sha256"):
                a["sha256"] = v["sha256"]
    return {"ok": True, "assets": items}


@app.get("/studio/jobs")
def studio_jobs(limit: int = 30) -> dict[str, Any]:
    from veu.studio import store as studio_store

    return {"ok": True, "jobs": studio_store.list_jobs(limit)}


@app.post("/studio/upload")
async def studio_upload(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    data = await file.read()
    meta = rt.studio.ingest_bytes(
        filename=file.filename or "upload.bin",
        data=data,
        content_type=file.content_type or "",
    )
    return {"ok": True, "asset": meta}


@app.post("/studio/from-text")
async def studio_from_text(
    filename: str = Form(...),
    text: str = Form(...),
    path: str | None = Form(None),
) -> dict[str, Any]:
    """Ingere texto lido do host nativo (duplo-clique → Arquivos)."""
    meta = rt.studio.ingest_bytes(
        filename=filename,
        data=(text or "").encode("utf-8"),
        content_type="text/plain",
    )
    if path:
        meta["source_path"] = path
    return {"ok": True, "asset": meta}


@app.post("/studio/run")
def studio_run(body: StudioRunIn) -> dict[str, Any]:
    job = rt.studio.run(
        action=body.action,
        asset_id=body.asset_id,
        path=body.path,
        text=body.text,
        filename=body.filename,
        prompt=body.prompt,
        force_executor=body.force_executor,
    )
    return {"ok": True, "job": job}


@app.get("/bridge/grokbot/health")
def grokbot_health_get() -> dict[str, Any]:
    """Ping de saúde — routine agendada (dias úteis) ou curl manual."""
    return rt.bridges.grokbot.health_check()


@app.post("/bridge/grokbot/health")
def grokbot_health_post(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = payload or {}
    if body.get("kind") in {"health", "ping", "heartbeat"} or body.get("type") in {
        "health",
        "ping",
    }:
        return rt.bridges.grokbot.inbound({**body, "kind": "health"})
    return rt.bridges.grokbot.health_check()


@app.post("/chat")
async def chat(body: ChatIn) -> StreamingResponse:
    def gen():
        for event in rt.stream_weave(body.message, breath=body.breath):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── Fase C · controle e integridade (9.8 / 9.1 / 9.2 / 9.9) ──────────────


class ControlGrantIn(BaseModel):
    kind: Literal["connector", "app"] = "app"
    id: str | None = Field(default=None, max_length=80)
    subject_id: str | None = Field(default=None, max_length=80)
    read: bool = False
    write: bool = False
    delete: bool = False
    ttl: Literal["session", "7d", "30d", "forever"] = "session"


class ControlResumeIn(BaseModel):
    breath: Literal["guided", "semi", "free", "autonomous"] | None = None


class TargetMarkIn(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    id: str | None = Field(default=None, max_length=120)
    target_id: str | None = Field(default=None, max_length=120)
    mark: Literal["seguro", "protegido"]
    name: str = ""


class TargetAuthIn(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    id: str | None = Field(default=None, max_length=120)
    target_id: str | None = Field(default=None, max_length=120)
    action: str = Field(min_length=1, max_length=60)
    confirm_name: str | None = None
    breath: str = "guided"


class DataDeleteIn(BaseModel):
    source: str = Field(min_length=1, max_length=80)
    confirm: str = Field(min_length=1, max_length=120)


@app.get("/control")
def control_status() -> dict[str, Any]:
    from veu.control import control

    return control.status()


@app.post("/control/stop-all")
def control_stop_all() -> dict[str, Any]:
    from veu.control import control

    return control.stop_all(who="user")


@app.post("/control/resume")
def control_resume(body: ControlResumeIn | None = None) -> dict[str, Any]:
    from veu.control import control

    return control.resume(who="user", breath=(body.breath if body else None))


@app.get("/control/permissions")
def control_permissions() -> dict[str, Any]:
    from veu.control import control

    return control.list_permission_matrix()


@app.post("/control/permissions")
def control_grant(body: ControlGrantIn) -> dict[str, Any]:
    from veu.control import control

    sid = (body.id or body.subject_id or "").strip()
    if not sid:
        return {"ok": False, "error": "id obrigatório"}
    return control.grant(
        kind=body.kind,
        subject_id=sid,
        read=body.read,
        write=body.write,
        delete=body.delete,
        ttl=body.ttl,
        who="user",
    )


@app.get("/control/audit")
def control_audit(
    who: str | None = None,
    what: str | None = None,
    target: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    from veu.control import control

    rows = control.audit_rows(who=who, what=what, target=target, limit=limit)
    return {"ok": True, "events": rows, "count": len(rows)}


@app.get("/control/audit.csv")
def control_audit_csv(
    who: str | None = None,
    what: str | None = None,
    target: str | None = None,
    limit: int = 2000,
) -> StreamingResponse:
    from veu.control import control

    csv_text = control.audit_csv(who=who, what=what, target=target, limit=limit)

    def gen():
        yield csv_text

    return StreamingResponse(
        gen(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="veu-audit.csv"'},
    )


@app.get("/targets")
def targets_list(
    kind: str | None = None,
    destructive: bool = False,
    advanced: bool | None = None,
) -> dict[str, Any]:
    from veu.targets import targets as veu_targets

    if advanced is not None:
        veu_targets.set_advanced(bool(advanced), who="user")
    rows = veu_targets.list_targets(kind=kind, destructive=destructive)
    return {
        "ok": True,
        "targets": rows,
        "advanced": veu_targets.is_advanced(),
    }


@app.post("/targets/mark")
def targets_mark(body: TargetMarkIn) -> dict[str, Any]:
    from veu.targets import targets as veu_targets

    tid = (body.id or body.target_id or "").strip()
    if not tid:
        return {"ok": False, "error": "id obrigatório"}
    return veu_targets.set_mark(
        kind=body.kind,
        target_id=tid,
        mark=body.mark,
        name=body.name,
        who="user",
    )


@app.post("/targets/advanced")
def targets_advanced(on: bool = True) -> dict[str, Any]:
    from veu.targets import targets as veu_targets

    return veu_targets.set_advanced(on, who="user")


@app.post("/targets/authorize")
def targets_authorize(body: TargetAuthIn) -> dict[str, Any]:
    from veu.targets import targets as veu_targets

    tid = (body.id or body.target_id or "").strip()
    if not tid:
        return {"ok": False, "error": "id obrigatório"}
    return veu_targets.authorize_destructive(
        kind=body.kind,
        target_id=tid,
        action=body.action,
        confirm_name=body.confirm_name,
        who="user",
        breath=body.breath,
    )


@app.get("/integrity/verify")
def integrity_verify_get(path: str) -> dict[str, Any]:
    from veu.integrity import verify

    return verify(path)


@app.get("/data")
def data_inventory() -> dict[str, Any]:
    from veu.sovereignty import inventory

    return inventory()


@app.post("/data/export")
def data_export() -> dict[str, Any]:
    from veu.sovereignty import export_all

    return export_all()


@app.get("/data/delete/preview")
def data_delete_preview(source: str) -> dict[str, Any]:
    from veu.sovereignty import preview_delete

    return preview_delete(source)


@app.post("/data/delete")
def data_delete(body: DataDeleteIn) -> dict[str, Any]:
    from veu.sovereignty import delete_by_source

    return delete_by_source(source=body.source, confirm=body.confirm, who="user")


@app.post("/connectors/selftest")
def connectors_selftest(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """9.3 — self-test de um ou todos os conectores."""
    from veu.connectors import selftest as veu_selftest

    payload = body or {}
    ids = payload.get("ids")
    if isinstance(ids, list) and ids:
        return veu_selftest.audit_nerves([str(i) for i in ids])
    cid = str(payload.get("id") or "").strip()
    if cid:
        return {"ok": True, "result": veu_selftest.run_one(cid)}
    return veu_selftest.audit_nerves()


@app.post("/connectors/audit-nerves")
def connectors_audit_nerves() -> dict[str, Any]:
    """9.3 — auditar nervos (todos) + alerta WhatsApp live→parado."""
    from veu.connectors import selftest as veu_selftest

    return veu_selftest.audit_nerves()


@app.get("/connectors/selftest")
def connectors_selftest_last() -> dict[str, Any]:
    from veu.connectors import selftest as veu_selftest

    return veu_selftest.last_report()


class UpdateCheckIn(BaseModel):
    enabled: bool = False
    manifest: dict[str, Any] | None = None
    manifest_url: str | None = None


@app.post("/updates/check")
def updates_check(body: UpdateCheckIn) -> dict[str, Any]:
    """9.6 — checagem opt-in; manifesto ed25519 obrigatório se enabled."""
    from veu import updates as veu_updates

    return veu_updates.check_update(
        enabled=body.enabled,
        manifest=body.manifest,
        manifest_url=body.manifest_url,
    )


@app.get("/updates/previous")
def updates_previous() -> dict[str, Any]:
    from veu import updates as veu_updates

    prev = veu_updates.previous_version()
    return {"ok": True, "previous": prev}


class CaptureIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    company: str = ""
    kind: str | None = None
    title: str | None = None
    due: str | None = None
    confirm: bool = False


@app.post("/capture/preview")
def capture_preview(body: CaptureIn) -> dict[str, Any]:
    """11.4 — classifica nota/tarefa/lembrete (prévia)."""
    from veu import capture as veu_capture

    return veu_capture.preview(body.text, company=body.company)


@app.post("/capture")
def capture_save(body: CaptureIn) -> dict[str, Any]:
    from veu import capture as veu_capture

    if not body.confirm:
        return veu_capture.preview(body.text, company=body.company)
    return veu_capture.confirm(
        body.text,
        kind=body.kind,
        company=body.company,
        title=body.title,
        due=body.due,
    )


# Rotas do roteiro (controle, billing, integrity, togo, projects, about)
from veu.roteiro_routes import register as _register_roteiro_routes

_register_roteiro_routes(app)

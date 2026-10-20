"""Sessão single-user — cookie HttpOnly + CSRF por Origin/Referer + rate limit.

Fecha o plano de controle público (P0 do review veuajustes).
Rotas públicas: /health, /ready, /auth/*.
Inbound GrokBot pode autenticar por webhook secret (sem cookie).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

COOKIE_NAME = "veu_session"
CSRF_HEADER = "X-Veu-CSRF"  # opcional; Origin/Referer já bastam (ASCII only)
SESSION_TTL_SEC = 60 * 60 * 24 * 14  # 14 dias
LOGIN_WINDOW_SEC = 60
LOGIN_MAX = 8
ACTION_WINDOW_SEC = 60
ACTION_MAX = 120

PUBLIC_EXACT = {
    "/health",
    "/healthz",
    "/ready",
    "/auth/login",
    "/auth/status",
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_PREFIXES = (
    "/auth/",
)

# Machine-to-machine: cookie OU secret de webhook (vigia + handoff do GrokBot)
WEBHOOK_PATHS = {
    "/pulse",
    "/bridge/grokbot/inbound",
    "/bridge/grokbot/health",
    "/bridge/grokbot/queue",
    "/bridge/grokbot/sideboard",
    "/bridge/grokbot/inbox",
    "/bridge/grokbot/brief",
}

# Prefixos M2M além dos paths exatos (ex.: /bridge/grokbot/health?…)
WEBHOOK_PREFIXES = (
    "/bridge/grokbot/inbound",
    "/bridge/grokbot/health",
)

# ESP32 / placa amarela — Bearer = token de dispositivo (não cookie)
DEVICE_PREFIXES = (
    "/device/esp32/state",
    "/device/esp32/event",
)


def _password() -> str:
    return (os.environ.get("VEU_AUTH_PASSWORD") or "").strip()


def google_client_id() -> str:
    return (os.environ.get("VEU_GOOGLE_CLIENT_ID") or "").strip()


def google_client_secret() -> str:
    return (os.environ.get("VEU_GOOGLE_CLIENT_SECRET") or "").strip()


def google_oauth_configured() -> bool:
    return bool(google_client_id() and google_client_secret())


def allowed_google_emails() -> set[str]:
    """Lista de e-mails autorizados (vírgula). Preferir VEU_ALLOWED_EMAILS; fallback legado."""
    raw = (
        os.environ.get("VEU_ALLOWED_EMAILS")
        or os.environ.get("VEU_AUTH_GOOGLE_EMAILS")
        or ""
    ).strip().lower()
    if not raw:
        return set()
    return {p.strip() for p in raw.split(",") if p.strip()}


# Sessões invalidadas no logout (nonce → exp)
_revoked_sessions: dict[str, float] = {}


def revoke_session(session: dict[str, Any] | None) -> None:
    if not session:
        return
    nonce = str(session.get("nonce") or "")
    exp = float(session.get("exp") or 0)
    if nonce:
        _revoked_sessions[nonce] = exp
    # GC leve
    now = time.time()
    dead = [k for k, e in _revoked_sessions.items() if e < now]
    for k in dead:
        _revoked_sessions.pop(k, None)


def _audit_auth(kind: str, payload: dict[str, Any]) -> None:
    try:
        from veu import memory as mem_mod

        mem_mod.MemoryStore().append(kind, payload, sink="audit")
    except Exception:  # noqa: BLE001
        pass


def public_base_url() -> str:
    return (os.environ.get("VEU_PUBLIC_URL") or "https://veu.ch8ai.com.br").rstrip("/")


def google_redirect_uri() -> str:
    override = (os.environ.get("VEU_GOOGLE_REDIRECT_URI") or "").strip()
    if override:
        return override
    return f"{public_base_url()}/auth/google/callback"


def _signing_secret() -> bytes:
    raw = (os.environ.get("VEU_AUTH_SECRET") or "").strip()
    if raw:
        return raw.encode("utf-8")
    seed = _password() or google_client_secret() or "veu-dev"
    return hashlib.sha256(f"veu-session::{seed}".encode("utf-8")).digest()


def auth_configured() -> bool:
    return bool(_password() or google_oauth_configured())


def allowed_origins() -> set[str]:
    extra = (os.environ.get("VEU_AUTH_ORIGINS") or "").strip()
    origins = {
        "https://veu.ch8ai.com.br",
        "http://127.0.0.1:8820",
        "http://localhost:8820",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    }
    for part in extra.split(","):
        p = part.strip().rstrip("/")
        if p:
            origins.add(p)
    return origins


def _b64(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    import base64

    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def mint_session_token(*, subject: str = "hudson") -> str:
    exp = int(time.time()) + SESSION_TTL_SEC
    nonce = secrets.token_hex(8)
    body = f"{subject}|{exp}|{nonce}".encode("utf-8")
    sig = hmac.new(_signing_secret(), body, hashlib.sha256).digest()
    return f"{_b64(body)}.{_b64(sig)}"


def verify_session_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    try:
        body_b64, sig_b64 = token.split(".", 1)
        body = _b64d(body_b64)
        sig = _b64d(sig_b64)
    except Exception:  # noqa: BLE001
        return None
    expect = hmac.new(_signing_secret(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        text = body.decode("utf-8")
        subject, exp_s, nonce = text.split("|", 2)
        exp = int(exp_s)
    except Exception:  # noqa: BLE001
        return None
    if exp < int(time.time()):
        return None
    if nonce in _revoked_sessions:
        return None
    return {"subject": subject, "exp": exp, "nonce": nonce}


def set_session_cookie(response: Response, token: str) -> None:
    secure = (os.environ.get("VEU_AUTH_COOKIE_SECURE") or "1").strip() != "0"
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=SESSION_TTL_SEC,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def read_session(request: Request) -> dict[str, Any] | None:
    return verify_session_token(request.cookies.get(COOKIE_NAME))


def check_password(candidate: str) -> bool:
    expected = _password()
    if not expected:
        return False
    return hmac.compare_digest(candidate.strip(), expected)


def webhook_secret_ok(request: Request) -> bool:
    """Aceita secret do GrokBot em header ou query (só as WEBHOOK_PATHS)."""
    expected = (
        os.environ.get("VEU_GROKBOT_WEBHOOK_SECRET")
        or os.environ.get("VEU_GROKBOT_SEND_KEY")
        or os.environ.get("VEU_BRIDGE_TOKEN")
        or ""
    ).strip()
    if not expected:
        return False
    auth = (request.headers.get("Authorization") or "").strip()
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    got = (
        request.headers.get("X-VEU-Webhook-Secret")
        or request.headers.get("X-Veu-Webhook-Secret")
        or request.headers.get("X-Webhook-Secret")
        or request.headers.get("X-GrokBot-Secret")
        or request.headers.get("X-Veu-Bridge-Token")
        or bearer
        or (request.query_params.get("secret") or "").strip()
        or (request.query_params.get("token") or "").strip()
        or ""
    ).strip()
    if not got:
        return False
    return hmac.compare_digest(got, expected)


def is_webhook_path(path: str) -> bool:
    if path in WEBHOOK_PATHS:
        return True
    return any(path == p or path.startswith(p + "/") for p in WEBHOOK_PREFIXES)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def request_origin(request: Request) -> str | None:
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin:
        return origin
    referer = (request.headers.get("referer") or "").strip()
    if not referer:
        return None
    try:
        parsed = urlparse(referer)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    except Exception:  # noqa: BLE001
        return None


def csrf_ok(request: Request) -> bool:
    """Mutations: Origin/Referer deve bater com allowlist (ou same-host)."""
    origin = request_origin(request)
    if not origin:
        # Sem Origin/Referer (curl/scripts): exige header CSRF + sessão já validada
        return bool(
            (request.headers.get("x-veu-csrf") or request.headers.get("x-véu-csrf") or "").strip()
        )
    if origin in allowed_origins():
        return True
    # Same-host fallback (IP direto / preview)
    host = (request.headers.get("host") or "").split(":")[0].lower()
    try:
        ohost = urlparse(origin).hostname or ""
    except Exception:  # noqa: BLE001
        ohost = ""
    return bool(host and ohost and host == ohost.lower())


# --- rate limit em memória (single-process uvicorn) ---
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if fwd:
        return fwd
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def rate_ok(request: Request, bucket: str, *, window: int, limit: int) -> bool:
    key = f"{bucket}:{_client_ip(request)}"
    now = time.time()
    q = _hits[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def login_rate_ok(request: Request) -> bool:
    return rate_ok(request, "login", window=LOGIN_WINDOW_SEC, limit=LOGIN_MAX)


def action_rate_ok(request: Request) -> bool:
    return rate_ok(request, "action", window=ACTION_WINDOW_SEC, limit=ACTION_MAX)


def mask_host(host: str | None) -> str:
    h = (host or "").strip()
    if not h:
        return ""
    # IPv4
    parts = h.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return f"{parts[0]}.***.***.{parts[3]}"
    # hostname
    if len(h) <= 4:
        return "••••"
    return f"{h[:2]}…{h[-2:]}"


def mask_username(user: str | None) -> str:
    u = (user or "").strip()
    if not u:
        return ""
    if len(u) <= 2:
        return "•" * len(u)
    return f"{u[0]}…{u[-1]}"


async def auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    path = request.url.path

    if is_public_path(path):
        return await call_next(request)

    # Sem senha configurada: fail-closed no plano de controle
    if not auth_configured() and path not in PUBLIC_EXACT:
        return JSONResponse(
            {
                "ok": False,
                "error": "auth_not_configured",
                "detail": "Defina VEU_AUTH_PASSWORD ou VEU_GOOGLE_CLIENT_ID/SECRET no .env.",
            },
            status_code=503,
        )

    if is_webhook_path(path) and webhook_secret_ok(request):
        # M2M: marca sessão sintética pra handlers que leem request.state
        request.state.veu_session = {"sub": "grokbot-bridge", "via": "webhook"}
        return await call_next(request)

    # Placa ESP32: Authorization Bearer = token enroll / VEU_ESP32_TOKEN
    if any(path == p or path.startswith(p) for p in DEVICE_PREFIXES):
        auth = (request.headers.get("authorization") or "").strip()
        bearer = ""
        if auth.lower().startswith("bearer "):
            bearer = auth[7:].strip()
        if not bearer:
            bearer = (request.headers.get("x-veu-device-token") or "").strip()
        try:
            from veu import esp32_device as veu_esp

            device = veu_esp.verify_token(bearer)
        except Exception:  # noqa: BLE001
            device = None
        if device:
            request.state.veu_session = {
                "sub": f"esp32:{device.get('id')}",
                "via": "device",
            }
            request.state.veu_device = device
            return await call_next(request)

    session = read_session(request)
    if session is None:
        return JSONResponse(
            {
                "ok": False,
                "error": "unauthorized",
                "detail": "login necessário",
                "bridge_hint": (
                    "GrokBot: mande X-VEU-Webhook-Secret ou Authorization: Bearer "
                    "<VEU_GROKBOT_WEBHOOK_SECRET> em /pulse, /bridge/grokbot/health "
                    "e /bridge/grokbot/inbound"
                ),
            },
            status_code=401,
        )

    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        if not csrf_ok(request):
            return JSONResponse(
                {"ok": False, "error": "csrf", "detail": "Origin/Referer inválido"},
                status_code=403,
            )
        if not action_rate_ok(request):
            return JSONResponse(
                {"ok": False, "error": "rate_limited", "detail": "muitas ações"},
                status_code=429,
            )

    request.state.veu_session = session
    return await call_next(request)


def require_session(request: Request) -> dict[str, Any]:
    """Dependency opcional para rotas que precisam do subject."""
    session = getattr(request.state, "veu_session", None) or read_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="login necessário")
    return session


LOGIN_SCOPES = "openid email profile"
WORKSPACE_SCOPES = (
    "openid email profile "
    "https://www.googleapis.com/auth/drive.readonly "
    "https://www.googleapis.com/auth/documents.readonly "
    "https://www.googleapis.com/auth/spreadsheets.readonly "
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/gmail.readonly"
)


class GoogleAuthError(Exception):
    """Erro tipado do login Google — status HTTP + código curto."""

    def __init__(self, message: str, *, status: int = 401, code: str = "auth") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def mint_oauth_state(*, kind: str = "g", nonce: str | None = None) -> str:
    """State anti-CSRF para o redirect Google (assinado, TTL curto).

    kind: `g` = login Véu · `gw` = conectar Google Workspace (API).
    """
    k = (kind or "g").strip() or "g"
    if k not in {"g", "gw"}:
        k = "g"
    exp = int(time.time()) + 600
    n = nonce or secrets.token_hex(12)
    body = f"{k}|{exp}|{n}".encode("utf-8")
    sig = hmac.new(_signing_secret(), body, hashlib.sha256).digest()
    return f"{_b64(body)}.{_b64(sig)}"


def parse_oauth_state(state: str | None) -> dict[str, str] | None:
    """Devolve {kind, nonce} se válido, senão None."""
    if not state or "." not in state:
        return None
    try:
        body_b64, sig_b64 = state.split(".", 1)
        body = _b64d(body_b64)
        sig = _b64d(sig_b64)
    except Exception:  # noqa: BLE001
        return None
    expect = hmac.new(_signing_secret(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        kind, exp_s, nonce = body.decode("utf-8").split("|", 2)
        if kind not in {"g", "gw"}:
            return None
        if int(exp_s) < int(time.time()):
            return None
        return {"kind": kind, "nonce": nonce}
    except Exception:  # noqa: BLE001
        return None


def verify_oauth_state(state: str | None) -> bool:
    return parse_oauth_state(state) is not None


def google_authorize_url(
    state: str,
    *,
    workspace: bool = False,
    nonce: str | None = None,
) -> str:
    """Login: só identidade. Workspace: escopos Drive/Docs/Sheets/Calendar/Gmail."""
    params = {
        "client_id": google_client_id(),
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": WORKSPACE_SCOPES if workspace else LOGIN_SCOPES,
        "include_granted_scopes": "true",
        "prompt": "select_account" if not workspace else "consent select_account",
        "state": state,
    }
    if workspace:
        params["access_type"] = "offline"
    if nonce:
        params["nonce"] = nonce
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def verify_google_id_token(
    id_token: str,
    *,
    expected_nonce: str | None = None,
) -> dict[str, Any]:
    """Valida id_token via tokeninfo: assinatura/iss/aud/exp (e nonce se houver)."""
    import httpx

    if not id_token or not str(id_token).strip():
        raise GoogleAuthError("id_token ausente", status=401, code="id_token")
    with httpx.Client(timeout=15.0) as client:
        res = client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
        )
    if res.status_code >= 400:
        raise GoogleAuthError("id_token inválido", status=401, code="id_token")
    claims = res.json()
    aud = str(claims.get("aud") or "")
    if aud != google_client_id():
        raise GoogleAuthError("id_token aud inválido", status=401, code="aud")
    iss = str(claims.get("iss") or "")
    if iss not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleAuthError("id_token iss inválido", status=401, code="iss")
    try:
        exp = int(claims.get("exp") or 0)
    except (TypeError, ValueError):
        exp = 0
    if exp < int(time.time()):
        raise GoogleAuthError("id_token expirado", status=401, code="exp")
    if expected_nonce:
        got = str(claims.get("nonce") or "")
        if got and got != expected_nonce:
            raise GoogleAuthError("id_token nonce inválido", status=401, code="nonce")
    return claims


def exchange_google_code(
    code: str,
    *,
    persist_workspace: bool = False,
    expected_nonce: str | None = None,
) -> dict[str, Any]:
    """Troca code por perfil; Workspace só quando persist_workspace=True."""
    import httpx

    if not google_oauth_configured():
        raise GoogleAuthError("Google OAuth não configurado", status=503, code="config")
    with httpx.Client(timeout=20.0) as client:
        token_res = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": google_client_id(),
                "client_secret": google_client_secret(),
                "redirect_uri": google_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        if token_res.status_code >= 400:
            raise GoogleAuthError(
                f"token Google: HTTP {token_res.status_code}",
                status=401,
                code="token",
            )
        tokens = token_res.json()
        id_token = str(tokens.get("id_token") or "")
        claims = verify_google_id_token(id_token, expected_nonce=expected_nonce)
        access = tokens.get("access_token")
        if not access:
            raise GoogleAuthError("token Google sem access_token", status=401, code="token")

    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise GoogleAuthError("Google não devolveu e-mail", status=401, code="email")
    verified = str(claims.get("email_verified") or "").lower() in {"true", "1"}
    if not verified:
        _audit_auth("auth.google.denied", {"email": email, "reason": "email_unverified"})
        raise GoogleAuthError("e-mail não verificado", status=403, code="unverified")

    allow = allowed_google_emails()
    if not allow:
        _audit_auth("auth.google.denied", {"email": email, "reason": "allowlist_empty"})
        raise GoogleAuthError("lista de e-mails vazia", status=403, code="allowlist")
    if email not in allow:
        _audit_auth("auth.google.denied", {"email": email, "reason": "not_allowed"})
        raise GoogleAuthError(f"e-mail não autorizado: {email}", status=403, code="forbidden")

    if persist_workspace:
        _persist_workspace_tokens(tokens, email=email)

    return {
        "email": email,
        "sub": str(claims.get("sub") or ""),
        "name": str(claims.get("name") or email),
        "picture": str(claims.get("picture") or ""),
        "workspace": bool(persist_workspace),
        "has_refresh": bool(tokens.get("refresh_token"))
        or bool((os.environ.get("GOOGLE_REFRESH_TOKEN") or "").strip()),
    }


def _persist_workspace_tokens(tokens: dict[str, Any], *, email: str) -> None:
    """Grava access/refresh no .env do kernel (Workspace API)."""
    from veu.subscriptions import resolve_env_file, upsert_env

    access = str(tokens.get("access_token") or "").strip()
    refresh = str(tokens.get("refresh_token") or "").strip()
    expires_in = int(tokens.get("expires_in") or 3600)
    updates = {
        "GOOGLE_ACCESS_TOKEN": access,
        "GOOGLE_TOKEN_EXPIRES": str(int(time.time()) + max(60, expires_in - 60)),
        "GOOGLE_WORKSPACE_EMAIL": email,
        "GOOGLE_WORKSPACE_SCOPES": "drive,docs,sheets,calendar,gmail",
    }
    if refresh:
        updates["GOOGLE_REFRESH_TOKEN"] = refresh
    path = resolve_env_file()
    upsert_env(path, updates)
    for k, v in updates.items():
        os.environ[k] = v


def google_start_redirect() -> RedirectResponse:
    """Login Google — só openid/email/profile."""
    nonce = secrets.token_hex(12)
    state = mint_oauth_state(kind="g", nonce=nonce)
    return RedirectResponse(
        url=google_authorize_url(state, workspace=False, nonce=nonce),
        status_code=302,
    )


def google_workspace_start_redirect() -> RedirectResponse:
    """Conector Workspace — escopos Drive/Docs/Sheets/Calendar/Gmail (incremental)."""
    nonce = secrets.token_hex(12)
    state = mint_oauth_state(kind="gw", nonce=nonce)
    return RedirectResponse(
        url=google_authorize_url(state, workspace=True, nonce=nonce),
        status_code=302,
    )


def google_callback_response(code: str | None, state: str | None) -> Response:
    parsed = parse_oauth_state(state)
    if not parsed:
        return JSONResponse(
            {"ok": False, "error": "state", "detail": "state inválido"},
            status_code=401,
        )
    kind = parsed["kind"]
    nonce = parsed["nonce"]
    if not code:
        return JSONResponse(
            {"ok": False, "error": "code", "detail": "code ausente"},
            status_code=401,
        )
    try:
        profile = exchange_google_code(
            code,
            persist_workspace=(kind == "gw"),
            expected_nonce=nonce,
        )
    except GoogleAuthError as e:
        return JSONResponse(
            {"ok": False, "error": e.code, "detail": str(e)[:120]},
            status_code=e.status,
        )
    # Gira o id da sessão após login
    token = mint_session_token(subject=profile["email"])
    dest = f"{public_base_url()}/?auth=ok"
    if kind == "gw":
        dest += "&workspace=1"
    resp = RedirectResponse(url=dest, status_code=302)
    set_session_cookie(resp, token)
    return resp

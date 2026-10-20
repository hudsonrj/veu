"""Google Workspace — Drive · Docs · Sheets · Calendar · Gmail via OAuth do Véu."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

MIME = {
    "docs": "application/vnd.google-apps.document",
    "sheets": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
    "folder": "application/vnd.google-apps.folder",
}


def configured() -> bool:
    return bool(
        (os.environ.get("GOOGLE_ACCESS_TOKEN") or "").strip()
        or (os.environ.get("GOOGLE_REFRESH_TOKEN") or "").strip()
    )


def email() -> str:
    return (os.environ.get("GOOGLE_WORKSPACE_EMAIL") or "").strip().lower()


def status() -> dict[str, Any]:
    live = configured()
    return {
        "ok": True,
        "connected": live,
        "email": email() or None,
        "scopes": (os.environ.get("GOOGLE_WORKSPACE_SCOPES") or "").split(",")
        if live
        else [],
        "has_refresh": bool((os.environ.get("GOOGLE_REFRESH_TOKEN") or "").strip()),
        "connect_url": "/auth/google",
        "surfaces": ["drive", "docs", "sheets", "calendar", "gmail"],
        "note": (
            f"live · {email()}"
            if live
            else "Entre com Google — o login já autoriza Drive/Docs/Sheets/Calendar/Gmail."
        ),
    }


def _client_ids() -> tuple[str, str]:
    cid = (os.environ.get("VEU_GOOGLE_CLIENT_ID") or "").strip()
    secret = (os.environ.get("VEU_GOOGLE_CLIENT_SECRET") or "").strip()
    return cid, secret


def refresh_access_token() -> str:
    """Renova access token com refresh_token; devolve access atualizado."""
    refresh = (os.environ.get("GOOGLE_REFRESH_TOKEN") or "").strip()
    access = (os.environ.get("GOOGLE_ACCESS_TOKEN") or "").strip()
    exp = int(os.environ.get("GOOGLE_TOKEN_EXPIRES") or "0")
    if access and exp > int(time.time()) + 30:
        return access
    if not refresh:
        if access:
            return access
        raise RuntimeError("Workspace não conectado — entre de novo com Google (/auth/google)")

    cid, secret = _client_ids()
    if not cid or not secret:
        raise RuntimeError("VEU_GOOGLE_CLIENT_ID/SECRET ausentes")

    with httpx.Client(timeout=20.0) as client:
        r = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"refresh Google falhou · HTTP {r.status_code}")
        data = r.json()
    new_access = str(data.get("access_token") or "").strip()
    if not new_access:
        raise RuntimeError("refresh sem access_token")
    expires_in = int(data.get("expires_in") or 3600)
    from veu.subscriptions import resolve_env_file, upsert_env

    updates = {
        "GOOGLE_ACCESS_TOKEN": new_access,
        "GOOGLE_TOKEN_EXPIRES": str(int(time.time()) + max(60, expires_in - 60)),
    }
    upsert_env(resolve_env_file(), updates)
    os.environ.update(updates)
    return new_access


def _get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = refresh_access_token()
    url = path if path.startswith("http") else f"https://www.googleapis.com{path}"
    with httpx.Client(timeout=30.0) as client:
        r = client.get(
            url,
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code == 401:
            # força refresh e tenta 1x
            os.environ["GOOGLE_TOKEN_EXPIRES"] = "0"
            token = refresh_access_token()
            r = client.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code >= 400:
            raise RuntimeError(_friendly_http(r.status_code, r.text[:240]))
        return r.json() if r.content else {}


def _friendly_http(code: int, body: str) -> str:
    low = (body or "").lower()
    if code == 403 and ("access_not_configured" in low or "has not been used" in low):
        return (
            "API Google não habilitada no Cloud Console "
            "(ative Drive/Calendar/Gmail/Docs/Sheets na mesma conta do OAuth)"
        )
    if code == 403:
        return "sem permissão — reconecte o Workspace com os escopos novos"
    if code == 401:
        return "token expirado — reconecte o Workspace"
    return f"Google HTTP {code}"


def list_drive(*, query: str = "", kind: str = "", limit: int = 25) -> dict[str, Any]:
    q_parts: list[str] = ["trashed=false"]
    if kind == "docs":
        q_parts.append(f"mimeType='{MIME['docs']}'")
    elif kind == "sheets":
        q_parts.append(f"mimeType='{MIME['sheets']}'")
    elif kind == "slides":
        q_parts.append(f"mimeType='{MIME['slides']}'")
    elif kind == "folder":
        q_parts.append(f"mimeType='{MIME['folder']}'")
    if query.strip():
        safe = query.strip().replace("\\", "\\\\").replace("'", "\\'")
        q_parts.append(f"name contains '{safe}'")
    data = _get(
        "/drive/v3/files",
        params={
            "pageSize": min(50, max(1, limit)),
            "q": " and ".join(q_parts),
            "fields": "files(id,name,mimeType,modifiedTime,webViewLink,owners,iconLink,size)",
            "orderBy": "modifiedTime desc",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        },
    )
    files = []
    for f in data.get("files") or []:
        mime = str(f.get("mimeType") or "")
        surface = "file"
        if mime == MIME["docs"]:
            surface = "docs"
        elif mime == MIME["sheets"]:
            surface = "sheets"
        elif mime == MIME["slides"]:
            surface = "slides"
        elif mime == MIME["folder"]:
            surface = "folder"
        files.append(
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "mime": mime,
                "surface": surface,
                "modified": f.get("modifiedTime"),
                "url": f.get("webViewLink"),
                "owner": ((f.get("owners") or [{}])[0] or {}).get("emailAddress"),
            }
        )
    return {"ok": True, "count": len(files), "files": files, "email": email()}


def list_calendar(*, limit: int = 20) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data = _get(
        "/calendar/v3/calendars/primary/events",
        params={
            "maxResults": min(40, max(1, limit)),
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": now,
        },
    )
    events = []
    for ev in data.get("items") or []:
        start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date")
        end = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date")
        events.append(
            {
                "id": ev.get("id"),
                "title": ev.get("summary") or "(sem título)",
                "start": start,
                "end": end,
                "location": ev.get("location") or "",
                "url": ev.get("htmlLink"),
                "status": ev.get("status"),
            }
        )
    return {"ok": True, "count": len(events), "events": events, "email": email()}


def list_gmail(*, limit: int = 15) -> dict[str, Any]:
    data = _get(
        "/gmail/v1/users/me/messages",
        params={"maxResults": min(30, max(1, limit)), "q": "in:inbox"},
    )
    out = []
    for msg in (data.get("messages") or [])[:limit]:
        mid = msg.get("id")
        if not mid:
            continue
        detail = _get(
            f"/gmail/v1/users/me/messages/{mid}",
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
        )
        headers = {
            h.get("name"): h.get("value")
            for h in ((detail.get("payload") or {}).get("headers") or [])
        }
        out.append(
            {
                "id": mid,
                "thread": detail.get("threadId"),
                "from": headers.get("From") or "",
                "subject": headers.get("Subject") or "(sem assunto)",
                "date": headers.get("Date") or "",
                "snippet": (detail.get("snippet") or "")[:180],
            }
        )
    return {"ok": True, "count": len(out), "messages": out, "email": email()}


def disconnect() -> dict[str, Any]:
    from veu.subscriptions import resolve_env_file, upsert_env

    keys = [
        "GOOGLE_ACCESS_TOKEN",
        "GOOGLE_REFRESH_TOKEN",
        "GOOGLE_TOKEN_EXPIRES",
        "GOOGLE_WORKSPACE_EMAIL",
        "GOOGLE_WORKSPACE_SCOPES",
    ]
    upsert_env(resolve_env_file(), {k: "" for k in keys})
    for k in keys:
        os.environ.pop(k, None)
    return {"ok": True, "connected": False}

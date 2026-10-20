"""Probe de URL para o Browser do Véu — X-Frame-Options / CSP frame-ancestors + SSRF."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

# Sites que sabemos que recusam iframe (mensagem "recusou a conexão").
KNOWN_FRAME_BLOCKED = (
    "google.com",
    "www.google.com",
    "mail.google.com",
    "calendar.google.com",
    "drive.google.com",
    "accounts.google.com",
    "docs.google.com",
    "chatgpt.com",
    "chat.openai.com",
    "claude.ai",
    "grok.com",
    "grok.x.ai",
    "x.ai",
    "github.com",
    "login.microsoftonline.com",
    "outlook.live.com",
    "outlook.office.com",
    "notion.so",
    "www.notion.so",
    "slack.com",
    "app.slack.com",
    "uol.com.br",
    "www.uol.com.br",
)

# Costumam permitir iframe / webview embutido
KNOWN_FRAME_OK = (
    "wikipedia.org",
    "www.wikipedia.org",
    "en.wikipedia.org",
    "pt.wikipedia.org",
    "duckduckgo.com",
)

# Bloqueiam frame-ancestors — Browser usa /browser/view (proxy SO)
KNOWN_FRAME_PROXY = (
    "vscode.dev",
    "github.dev",
    "uol.com.br",
    "www.uol.com.br",
)


def _host_matches(host: str, pattern: str) -> bool:
    h = host.lower().rstrip(".")
    p = pattern.lower().rstrip(".")
    return h == p or h.endswith("." + p)


def is_private_url(url: str) -> tuple[bool, str]:
    try:
        u = urlparse(url)
    except Exception:  # noqa: BLE001
        return True, "url inválida"
    if u.scheme not in {"http", "https"}:
        return True, "só http/https"
    host = (u.hostname or "").lower()
    if not host:
        return True, "sem host"
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True, "localhost"
    if host.endswith(".local") or host.endswith(".internal"):
        return True, "host interno"
    if host == "metadata.google.internal" or host == "169.254.169.254":
        return True, "metadata"
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return True, f"IP privado ({ip})"
    except Exception:  # noqa: BLE001
        # DNS falhou — ainda deixa o probe tentar; SSRF de IP fica no resolve
        pass
    return False, ""


def _csp_blocks_framing(csp: str) -> bool:
    if not csp:
        return False
    # frame-ancestors 'none' | 'self' | sem * / https:
    m = re.search(r"frame-ancestors\s+([^;]+)", csp, re.I)
    if not m:
        return False
    val = m.group(1).strip().lower()
    if "'none'" in val:
        return True
    if "*" in val or "https:" in val or "http:" in val:
        return False
    # só 'self' ou origens específicas → bloqueia nosso embed cross-origin
    return True


def probe(url: str) -> dict[str, Any]:
    """Devolve se a URL pode ir em iframe do Véu e qual fallback usar."""
    raw = (url or "").strip()
    if not raw:
        return {"ok": False, "error": "url vazia", "iframe_ok": False}

    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw

    blocked, why = is_private_url(raw)
    if blocked:
        return {
            "ok": False,
            "error": f"URL recusada (SSRF): {why}",
            "url": raw,
            "iframe_ok": False,
            "mode": "blocked",
        }

    host = (urlparse(raw).hostname or "").lower()

    for p in KNOWN_FRAME_OK:
        if _host_matches(host, p):
            return {
                "ok": True,
                "url": raw,
                "host": host,
                "iframe_ok": True,
                "mode": "iframe",
                "reason": "site costuma permitir embed",
                "known": True,
            }

    for p in KNOWN_FRAME_PROXY:
        if _host_matches(host, p):
            return {
                "ok": True,
                "url": raw,
                "host": host,
                "iframe_ok": True,
                "mode": "proxy",
                "view": "proxy",
                "reason": "abre na janela do Browser do SO (proxy Véu)",
                "hint": "conteúdo na janela do SO — sem iframe direto",
                "view_path": f"/browser/view?url={raw}",
                "known": True,
            }

    for p in KNOWN_FRAME_BLOCKED:
        if _host_matches(host, p):
            return {
                "ok": True,
                "url": raw,
                "host": host,
                "iframe_ok": False,
                "mode": "host",
                "reason": "site impede iframe (X-Frame-Options / CSP)",
                "hint": "abra via Host do Véu — a extensão controla a aba no Chrome",
                "known": True,
            }

    # Probe de cabeçalhos
    headers: dict[str, str] = {}
    status = 0
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=6.0,
            headers={"User-Agent": "VeuBrowserProbe/1.0"},
        ) as client:
            try:
                r = client.head(raw)
            except Exception:  # noqa: BLE001
                r = client.get(raw)
            status = r.status_code
            headers = {k.lower(): v for k, v in r.headers.items()}
    except Exception as e:  # noqa: BLE001
        # Rede falhou no kernel — assume host (melhor UX que iframe morto)
        return {
            "ok": True,
            "url": raw,
            "host": host,
            "iframe_ok": False,
            "mode": "host",
            "reason": f"probe falhou: {e}",
            "hint": "abra via Host; iframe pode falhar",
        }

    xfo = (headers.get("x-frame-options") or "").lower()
    csp = headers.get("content-security-policy") or headers.get(
        "content-security-policy-report-only"
    ) or ""

    iframe_ok = True
    reason = "sem restrição de frame nos cabeçalhos"
    if "deny" in xfo or "sameorigin" in xfo:
        iframe_ok = False
        reason = f"X-Frame-Options: {xfo}"
    elif _csp_blocks_framing(csp):
        iframe_ok = False
        reason = "CSP frame-ancestors bloqueia embed"

    return {
        "ok": True,
        "url": raw,
        "host": host,
        "status": status,
        "iframe_ok": iframe_ok,
        "mode": "iframe" if iframe_ok else "host",
        "reason": reason,
        "x_frame_options": headers.get("x-frame-options"),
        "hint": (
            None
            if iframe_ok
            else "abra via Host do Véu — a extensão controla a aba no Chrome"
        ),
    }

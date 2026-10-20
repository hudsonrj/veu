"""Proxy de leitura — abre sites com frame-ancestors na janela do Browser do SO.

Remove X-Frame-Options / CSP frame-ancestors e reescreve navegação para
permanecer em /browser/view. Não substitui neko/Kasm; cookies do usuário
no Chrome da máquina não passam — sites de login ficam no Host.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from fastapi import Response
from fastapi.responses import HTMLResponse

from veu.browser_probe import is_private_url

_UA = (
    "Mozilla/5.0 (compatible; VeuOSBrowser/1.0; +https://veu.ch8ai.com.br)"
)
_MAX_BYTES = 2_500_000

# Login / SPA autenticada — proxy do servidor não vê a sessão do usuário.
HOST_ONLY_HOSTS = (
    "accounts.google.com",
    "mail.google.com",
    "chatgpt.com",
    "chat.openai.com",
    "claude.ai",
    "grok.com",
    "login.microsoftonline.com",
    "outlook.live.com",
    "outlook.office.com",
    "slack.com",
    "app.slack.com",
    "web.whatsapp.com",
    "notion.so",
    "www.notion.so",
)


def _host_matches(host: str, pattern: str) -> bool:
    h = host.lower().rstrip(".")
    p = pattern.lower().rstrip(".")
    return h == p or h.endswith("." + p)


def is_host_only(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(_host_matches(host, p) for p in HOST_ONLY_HOSTS)


def normalize_public_url(raw: str) -> tuple[str | None, str | None]:
    u = (raw or "").strip()
    if not u:
        return None, "url vazia"
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u
    blocked, why = is_private_url(u)
    if blocked:
        return None, f"URL recusada (SSRF): {why}"
    return u, None


def view_url_for(target: str, origin: str = "") -> str:
    """Path same-origin para o iframe do Browser."""
    base = (origin or "").rstrip("/")
    path = f"/browser/view?url={quote(target, safe='')}"
    return f"{base}{path}" if base else path


def _strip_csp_frame_ancestors(csp: str) -> str:
    if not csp:
        return ""
    parts = []
    for dir_ in csp.split(";"):
        d = dir_.strip()
        if not d:
            continue
        if re.match(r"frame-ancestors\b", d, re.I):
            continue
        parts.append(d)
    return "; ".join(parts)


def _inject_shell(html: str, page_url: str, proxy_prefix: str) -> str:
    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}/"
    base_tag = f'<base href="{escape(origin, quote=True)}">'
    # Navegação e form GET ficam no proxy → conteúdo permanece na janela do SO.
    boot = f"""<script data-veu-proxy="1">(function(){{
  var P={proxy_prefix!r};
  function wrap(u){{
    try {{
      var x=new URL(u, document.baseURI);
      if(x.protocol!=="http:"&&x.protocol!=="https:") return null;
      return P+encodeURIComponent(x.href);
    }} catch(e) {{ return null; }}
  }}
  document.addEventListener("click",function(e){{
    var a=e.target&&e.target.closest?e.target.closest("a[href]"):null;
    if(!a) return;
    if(aTargetBlank(a)) return;
    var w=wrap(a.href); if(!w) return;
    e.preventDefault(); e.stopPropagation();
    location.href=w;
  }},true);
  function aTargetBlank(a){{
    var t=(a.getAttribute("target")||"").toLowerCase();
    return t==="_blank"||t==="_new";
  }}
  document.addEventListener("submit",function(e){{
    var f=e.target; if(!f||!f.action) return;
    var m=(f.method||"get").toLowerCase();
    if(m&&m!=="get") return;
    var w=wrap(f.action); if(!w) return;
    e.preventDefault();
    var fd=new FormData(f);
    var q=new URLSearchParams(fd).toString();
    location.href=w+(q?((w.indexOf("?")>=0)?"&":"?")+q:"");
  }},true);
}})();</script>"""

    # Remover meta CSP que reimpõe frame-ancestors
    html = re.sub(
        r"<meta[^>]+http-equiv=[\"']?Content-Security-Policy[\"']?[^>]*>",
        "",
        html,
        flags=re.I,
    )

    if re.search(r"<head\b", html, re.I):
        return re.sub(
            r"(<head[^>]*>)",
            r"\1" + base_tag + boot,
            html,
            count=1,
            flags=re.I,
        )
    return base_tag + boot + html


def fetch_view(url: str, proxy_prefix: str) -> Response:
    """Busca a URL e devolve resposta franqueável no iframe do Véu."""
    target, err = normalize_public_url(url)
    if err or not target:
        return HTMLResponse(
            f"<!doctype html><meta charset=utf-8><title>Véu</title>"
            f"<p>Não foi possível abrir: {escape(err or 'erro')}</p>",
            status_code=400,
        )

    if is_host_only(target):
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>Host</title>"
            "<body style='font:14px system-ui;background:#0a0c10;color:#ecf2f8;padding:2rem'>"
            "<p>Este site precisa da sessão no Chrome da máquina.</p>"
            "<p>Use <strong>Abrir via Host</strong> na janela do Browser.</p>"
            "</body>",
            status_code=200,
            headers={"X-Veu-View-Mode": "host-only"},
        )

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=12.0,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            },
        ) as client:
            r = client.get(target)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(
            f"<!doctype html><meta charset=utf-8><p>Falha ao carregar: "
            f"{escape(str(e))}</p>",
            status_code=502,
        )

    final = str(r.url)
    ct = (r.headers.get("content-type") or "text/html").split(";")[0].strip().lower()
    body = r.content[:_MAX_BYTES]

    out_headers: dict[str, str] = {
        "Cache-Control": "private, max-age=60",
        "X-Veu-View-Url": final,
        "X-Veu-View-Mode": "proxy",
        # Embutível só pelo próprio Véu (Browser do SO)
        "Content-Security-Policy": (
            "frame-ancestors 'self' https://veu.ch8ai.com.br"
        ),
        "X-Frame-Options": "SAMEORIGIN",
    }

    if "html" in ct or body[:200].lstrip().lower().startswith(
        (b"<!doctype", b"<html")
    ):
        try:
            text = body.decode(r.encoding or "utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = body.decode("utf-8", errors="replace")
        text = _inject_shell(text, final, proxy_prefix)
        return HTMLResponse(
            text,
            status_code=200,
            headers=out_headers,
        )

    # Assets raros via este path — devolve bytes sem XFO
    return Response(
        content=body,
        status_code=200,
        media_type=ct or "application/octet-stream",
        headers=out_headers,
    )


def probe_hint(url: str) -> dict[str, Any]:
    """Sugestão de modo para o Browser do SO."""
    target, err = normalize_public_url(url)
    if err or not target:
        return {"mode": "blocked", "iframe_ok": False, "error": err}
    if is_host_only(target):
        return {
            "mode": "host",
            "iframe_ok": False,
            "view": "host",
            "reason": "site de login — sessão só no Chrome do host",
        }
    return {
        "mode": "proxy",
        "iframe_ok": True,
        "view": "proxy",
        "reason": "abre na janela do Browser do SO (proxy Véu)",
        "view_path": view_url_for(target),
    }

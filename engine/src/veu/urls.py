"""Extração de URLs de pedidos do chat."""

from __future__ import annotations

import re

# http(s), www., ou domínio tipo control.ch8ai.com.br[/path]
_URL_RE = re.compile(
    r"(?P<url>"
    r"https?://[^\s<>\"'`]+|"
    r"www\.[^\s<>\"'`]+|"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?:/[^\s<>\"'`]*)?"
    r")",
    re.IGNORECASE,
)

_OPEN_VERBS = (
    "acesse",
    "acessar",
    "abra",
    "abre",
    "abrir",
    "abre o site",
    "abrir o site",
    "navegue",
    "navegar",
    "vai em",
    "vai pro",
    "vá para",
    "va para",
    "open ",
    "browse",
)


def extract_url(text: str) -> str | None:
    if not text:
        return None
    m = _URL_RE.search(text.strip())
    if not m:
        return None
    raw = m.group("url").rstrip(".,;:!?)】」'\"")
    if raw.lower().startswith("www."):
        return "https://" + raw
    if re.match(r"^https?://", raw, re.I):
        return raw
    # domínio nu
    if "." in raw and " " not in raw:
        return "https://" + raw
    return None


def wants_open_url(text: str) -> bool:
    t = (text or "").lower()
    if extract_url(text):
        if any(v in t for v in _OPEN_VERBS) or "http" in t or "www." in t:
            return True
        # "control.ch8ai.com.br" sozinho também
        if _URL_RE.fullmatch(text.strip().rstrip(".,;:!?)")):
            return True
    if any(v in t for v in _OPEN_VERBS) and any(
        k in t for k in ("site", "página", "pagina", "link", "url", "web")
    ):
        return True
    return False

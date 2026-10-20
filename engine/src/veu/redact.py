"""Redação de secrets em logs/pulse — nunca ecoar hf_/sk-/Bearer em claro."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS = [
    re.compile(r"\bhf_[A-Za-z0-9]{10,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\bsk-svcacct-[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\bcrsr_[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|cookie)\s*[:=]\s*['\"]?([^\s'\"]{8,})"),
    re.compile(r"(?i)(set-cookie)\s*[:=]\s*([^\s;]+)"),
]


def redact_text(text: str) -> str:
    out = text or ""
    for pat in _PATTERNS:
        if pat.groups:
            out = pat.sub(lambda m: f"{m.group(1)}=***", out)
        else:
            out = pat.sub("***", out)
    return out


def redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            lk = str(k).lower()
            if any(s in lk for s in ("token", "secret", "password", "api_key", "authorization")):
                if isinstance(v, str) and v.strip():
                    out[k] = "***"
                else:
                    out[k] = redact_obj(v)
            else:
                out[k] = redact_obj(v)
        return out
    return value

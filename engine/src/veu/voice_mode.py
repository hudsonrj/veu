"""Quem redige no SO: LLM padrão ou Clone (personalidade do usuário)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal

Voice = Literal["llm", "clone"]


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "voice_mode.json"


def get() -> Voice:
    path = _path()
    if not path.exists():
        env = (os.environ.get("VEU_VOICE_MODE") or "llm").strip().lower()
        return "clone" if env == "clone" else "llm"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        v = str(data.get("voice") or "llm").lower()
        return "clone" if v == "clone" else "llm"
    except (OSError, json.JSONDecodeError):
        return "llm"


def set_voice(voice: str) -> dict[str, Any]:
    v: Voice = "clone" if str(voice).strip().lower() == "clone" else "llm"
    data = {"voice": v, "updated": time.time()}
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    os.environ["VEU_VOICE_MODE"] = v
    return status()


def status() -> dict[str, Any]:
    voice = get()
    clone_pct = 0
    clone_label = "esboço"
    try:
        from veu import clone as veu_clone

        st = veu_clone.status()
        clone_pct = int(st.get("percent") or 0)
        clone_label = str(st.get("label") or "esboço")
    except Exception:  # noqa: BLE001
        pass

    ready = voice == "llm" or clone_pct >= 15
    return {
        "ok": True,
        "voice": voice,
        "active": voice,
        "label": "Clone" if voice == "clone" else "LLM",
        "clone_percent": clone_pct,
        "clone_label": clone_label,
        "ready": ready,
        "note": (
            "Clone ativo — respostas no jeito do usuário."
            if voice == "clone"
            else "LLM ativo — respostas do modelo do Véu."
        )
        + (
            f" Clone ainda fraco ({clone_pct}%) — treine no app Clone."
            if voice == "clone" and clone_pct < 35
            else ""
        ),
        "options": [
            {
                "id": "llm",
                "label": "LLM",
                "blurb": "modelo do Véu (ChatGPT/DeepSeek/Ollama…)",
            },
            {
                "id": "clone",
                "label": "Clone",
                "blurb": f"sua personalidade · {clone_pct}% · {clone_label}",
            },
        ],
    }


def system_overlay() -> str:
    """Trecho extra pro system prompt quando Clone está ativo."""
    if get() != "clone":
        return ""
    try:
        from veu import clone as veu_clone

        return veu_clone.profile_for_prompt()
    except Exception:  # noqa: BLE001
        return (
            "Modo Clone ativo: responda na 1ª pessoa como o usuário falaria — "
            "tom, vocabulário e jeito dele. Sem meta-comentário de IA."
        )


def compose_system(base: str) -> str:
    extra = system_overlay()
    if not extra:
        return base
    return f"{base}\n\n---\nMODO CLONE (sistema):\n{extra}"

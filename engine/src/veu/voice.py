"""Voz — STT plugável (OpenAI Whisper por padrão) + descarte do áudio."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

# Whisper aceita estes; extensão precisa bater com o container real.
_MIME_BY_EXT = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
}


def provider_name() -> str:
    return (os.environ.get("VEU_STT_PROVIDER") or "openai").strip().lower()


def _friendly_stt_error(raw: str) -> str:
    low = (raw or "").lower()
    if "could not be decoded" in low or "format is not supported" in low:
        return "áudio inválido — segure o mic ~1s e fale de novo"
    if "incorrect api key" in low or "invalid_api_key" in low:
        return "OPENAI_API_KEY inválida pra voz"
    if "audio vazio" in low or "áudio vazio" in low:
        return "áudio vazio — segure e fale"
    clean = (raw or "").replace("\n", " ").strip()
    if clean.startswith("{") or "<html" in low:
        return "falha no Whisper — tente de novo"
    return clean[:160]


def transcribe(audio_bytes: bytes, *, filename: str = "audio.webm") -> dict[str, Any]:
    """Transcreve bytes de áudio. Não persiste o arquivo além da chamada."""
    if not audio_bytes or len(audio_bytes) < 600:
        return {
            "ok": False,
            "error": "áudio vazio ou curto demais — segure o mic ~1s",
            "text": "",
        }
    prov = provider_name()
    if prov in {"openai", "whisper"}:
        return _openai_whisper(audio_bytes, filename=filename)
    if prov in {"none", "echo", "stub"}:
        return {
            "ok": True,
            "text": "",
            "provider": "stub",
            "note": "STT stub — configure VEU_STT_PROVIDER=openai",
        }
    return {"ok": False, "error": f"provedor STT desconhecido: {prov}", "text": ""}


def _sniff_ext(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    """Devolve (filename_com_ext, content_type) a partir do container."""
    name = Path(filename or "veu.webm").name
    suffix = Path(name).suffix.lower()
    head = audio_bytes[:16]
    # EBML / WebM
    if head[:4] == b"\x1a\x45\xdf\xa3":
        suffix = ".webm"
    # Ogg
    elif head[:4] == b"OggS":
        suffix = ".ogg"
    # RIFF/WAVE
    elif head[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        suffix = ".wav"
    # ftyp (mp4/m4a)
    elif b"ftyp" in audio_bytes[:12]:
        suffix = ".m4a"
    # ID3 / mp3
    elif head[:3] == b"ID3" or head[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        suffix = ".mp3"
    if suffix not in _MIME_BY_EXT:
        suffix = ".webm"
    stem = Path(name).stem or "veu"
    return f"{stem}{suffix}", _MIME_BY_EXT[suffix]


def _openai_whisper(audio_bytes: bytes, *, filename: str) -> dict[str, Any]:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key or len(key) < 40:
        return {"ok": False, "error": "OPENAI_API_KEY ausente para STT", "text": ""}
    try:
        import httpx
    except ImportError:
        return {"ok": False, "error": "httpx necessário", "text": ""}

    safe_name, content_type = _sniff_ext(audio_bytes, filename)
    suffix = Path(safe_name).suffix or ".webm"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        model = os.environ.get("VEU_STT_MODEL") or "whisper-1"
        with open(tmp_path, "rb") as f:
            files = {"file": (safe_name, f, content_type)}
            data = {"model": model, "language": "pt", "response_format": "json"}
            with httpx.Client(timeout=60.0) as client:
                r = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files=files,
                    data=data,
                )
        if r.status_code >= 400:
            return {"ok": False, "error": _friendly_stt_error(r.text[:400]), "text": ""}
        payload = r.json() if r.content else {}
        text = str(payload.get("text") or "").strip()
        if not text:
            return {
                "ok": False,
                "error": "não entendi — fale de novo um pouco mais alto",
                "text": "",
            }
        return {"ok": True, "text": text, "provider": "openai", "model": model}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _friendly_stt_error(str(exc)[:300]), "text": ""}
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass

"""Hidrata status/notes dos nervos a partir do .env real (não catálogo estático)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .registry import Registry


def _has(*names: str) -> bool:
    return any(bool(os.environ.get(n, "").strip()) for n in names)


def hydrate_connectors(registry: Registry, *, bridges=None, jev=None, notion=None, openrag=None) -> None:
    """Atualiza status live/ready/planned conforme secrets e adapters."""

    def set_status(cid: str, status: str, note: str | None = None) -> None:
        c = registry.get(cid)
        if c is None:
            return
        c.status = status
        if note is not None:
            c.notes = note

    # Notion
    if notion is not None:
        live = notion.live
    else:
        live = _has("NOTION_TOKEN")
    set_status(
        "notion",
        "live" if live else "ready",
        "live · NOTION_TOKEN no .env" if live else "defina NOTION_TOKEN no .env do kernel",
    )

    # OpenRAG
    if openrag is not None:
        live = openrag.live
        base = getattr(openrag, "base_url", "") or ""
    else:
        live = _has("OPENRAG_API_KEY", "ORAG_API_KEY") and _has(
            "OPENRAG_URL", "OPENRAG_BASE_URL"
        )
        base = os.environ.get("OPENRAG_URL") or os.environ.get("OPENRAG_BASE_URL") or ""
    set_status(
        "openrag",
        "live" if live else "planned",
        f"live · {base}" if live else "defina OPENRAG_API_KEY + OPENRAG_URL no .env",
    )

    # Jev
    if jev is not None:
        st = jev.status()
    else:
        st = "live" if _has("TYPESAFE_API_KEY") else "planned"
    set_status(
        "jev",
        st,
        "live · TYPESAFE_API_KEY" if st == "live" else "defina TYPESAFE_API_KEY no .env",
    )

    # Bridges
    if bridges is not None:
        for cid, bridge in (
            ("openclaw", bridges.openclaw),
            ("hermes", bridges.hermes),
            ("grokbot", bridges.grokbot),
        ):
            st = bridge.status()
            pulse = bridge.pulse() if hasattr(bridge, "pulse") else {}
            # webhook no .env = nervo operacional (handoff pronto)
            if cid == "grokbot" and pulse.get("webhook_configured"):
                st = "live"
            set_status(cid, st, _bridge_note(cid, st, pulse))
    else:
        gb = "live" if _has("VEU_GROKBOT_WEBHOOK_URL") else "planned"
        oc = "ready" if _has("VEU_OPENCLAW_GATEWAY_URL") else "planned"
        hm = "ready" if _has("HERMES_HOME") else "planned"
        set_status("grokbot", gb, _bridge_note("grokbot", gb))
        set_status("openclaw", oc, _bridge_note("openclaw", oc))
        set_status("hermes", hm, _bridge_note("hermes", hm))

    # Assinaturas de modelos — API key e/ou conta (ChatGPT / Claude.ai / Grok)
    def _sub_live(key_env: str, sub_env: str) -> tuple[str, str]:
        key_ok = _has(key_env)
        sub = os.environ.get(sub_env, "").strip().lower() == "linked"
        if key_ok and sub:
            return "live", "live · API key + assinatura"
        if key_ok:
            return "live", f"live · {key_env}"
        if sub:
            return "live", "live · assinatura (conta no browser)"
        return "ready", "Ajustes → assinaturas · API key ou login da conta"

    st, note = _sub_live("OPENAI_API_KEY", "VEU_OPENAI_SUB_STATUS")
    set_status("openai", st, note)
    st, note = _sub_live("ANTHROPIC_API_KEY", "VEU_CLAUDE_SUB_STATUS")
    set_status("claude", st, note)
    st, note = _sub_live("XAI_API_KEY", "VEU_XAI_SUB_STATUS")
    set_status("xai", st, note)

    # Canais: token dedicado = live; senão, live.json do Control/GrokBot = ready/live
    live_channels = _channels_from_live()

    def _channel_status(
        cid: str,
        *,
        token_live: bool,
        token_note: str,
        planned_note: str,
        aliases: tuple[str, ...] | None = None,
    ) -> None:
        names = aliases or (cid,)
        count = sum(live_channels.get(a, 0) for a in names)
        if token_live:
            set_status(cid, "live", token_note)
        elif count > 0:
            set_status(
                cid,
                "live",
                f"live · GrokBot/Control · {count} msg no live.json",
            )
        else:
            # slack fica ready (superfície); demais planned sem sinal
            if cid == "slack":
                set_status(cid, "ready", planned_note)
            else:
                set_status(cid, "planned", planned_note)

    _channel_status(
        "slack",
        token_live=_has("SLACK_BOT_TOKEN", "SLACK_TOKEN"),
        token_note="live · SLACK_BOT_TOKEN",
        planned_note="MCP/API — defina SLACK_BOT_TOKEN no .env quando for usar",
    )
    # Workspace/Gmail = tokens gravados no login Google (escopos completos)
    gw_live = _has("GOOGLE_REFRESH_TOKEN") or (
        _has("GOOGLE_ACCESS_TOKEN") and _has("GOOGLE_WORKSPACE_EMAIL")
    )
    gw_email = (os.environ.get("GOOGLE_WORKSPACE_EMAIL") or "").strip()
    set_status(
        "google",
        "live" if gw_live else "ready",
        (
            f"live · Workspace · {gw_email or 'conectado'} · drive·docs·sheets·calendar"
            if gw_live
            else "pronto · entre com Google (o login já pede Drive/Docs/Sheets/Calendar/Gmail)"
        ),
    )
    if gw_live:
        set_status("gmail", "live", f"live · Gmail API · {gw_email or 'ok'}")
    else:
        _channel_status(
            "gmail",
            token_live=_has("GMAIL_TOKEN"),
            token_note="live · GMAIL_TOKEN",
            planned_note="entre com Google pra ligar Gmail API (ou use live.json via GrokBot)",
        )
    _channel_status(
        "google-chat",
        token_live=gw_live,
        token_note=f"live · mesma conta · {gw_email or 'ok'}",
        planned_note="Google Chat — login Google do Véu",
        aliases=("gchat", "google-chat", "chat"),
    )
    _channel_status(
        "outlook",
        token_live=_has("MS_GRAPH_TOKEN", "AZURE_CLIENT_ID"),
        token_note="live · Graph",
        planned_note="Outlook via GrokBot/Control (sem Graph local)",
        aliases=("outlook", "email"),
    )
    _channel_status(
        "teams",
        token_live=_has("MS_GRAPH_TOKEN", "AZURE_CLIENT_ID"),
        token_note="live · Graph",
        planned_note="Teams via GrokBot/Control (sem Graph local)",
        aliases=("teams", "team"),
    )
    wa_count = live_channels.get("whatsapp", 0)
    set_status(
        "whatsapp",
        "live",
        (
            "live · bridge + WP Web QR"
            if _has("WHATSAPP_TOKEN", "WA_BRIDGE_URL")
            else (
                f"live · WhatsApp Web · {wa_count} no live.json"
                if wa_count
                else "WhatsApp Web · QR · janela no dock"
            )
        ),
    )

    # Barramentos — prontos como superfície; live se houver endpoint
    set_status(
        "mcp-bus",
        "live" if _has("MCP_SERVER_URL", "VEU_MCP_URL") else "ready",
        "live · MCP_SERVER_URL" if _has("MCP_SERVER_URL", "VEU_MCP_URL") else "barramento MCP — aponte MCP_SERVER_URL no .env",
    )
    set_status(
        "api-bus",
        "ready",
        "HTTP/OAuth/webhooks — use conforme a formação",
    )
    set_status(
        "host-desktop",
        "live",
        "janela Máquina no dock · extensão Véu Host 0.3.6",
    )


def _channels_from_live() -> dict[str, int]:
    """Conta canais já ingeridos pelo Control/GrokBot (live.json)."""
    try:
        from veu.bridges import control_live

        raw = control_live.load_raw() or {}
    except Exception:  # noqa: BLE001
        return {}
    counts: dict[str, int] = {}
    for m in raw.get("inbox") or []:
        if not isinstance(m, dict):
            continue
        ch = str(m.get("channel") or m.get("source") or "other").lower()
        if "outlook" in ch or ch == "email":
            ch = "outlook"
        elif "team" in ch:
            ch = "teams"
        elif "gmail" in ch:
            ch = "gmail"
        elif "slack" in ch:
            ch = "slack"
        elif "whats" in ch or ch in {"wa", "wpp"}:
            ch = "whatsapp"
        elif "chat" in ch and "google" in ch:
            ch = "gchat"
        counts[ch] = counts.get(ch, 0) + 1
    # sinais extras no meta
    meta = raw.get("meta") or {}
    if meta.get("lastTeamsMsgsAt") and not counts.get("teams"):
        counts["teams"] = max(1, counts.get("teams", 0))
    return counts


def _bridge_note(cid: str, status: str, pulse: dict | None = None) -> str:
    pulse = pulse or {}
    if cid == "grokbot":
        return (
            "live · VEU_GROKBOT_WEBHOOK_URL"
            if status == "live" or pulse.get("webhook_configured")
            else "defina VEU_GROKBOT_WEBHOOK_URL / SECRET no .env"
        )
    if cid == "openclaw":
        return (
            "ready · gateway"
            if status in {"ready", "live"}
            else "defina VEU_OPENCLAW_GATEWAY_URL no .env"
        )
    if cid == "hermes":
        return (
            "ready · HERMES_HOME"
            if status in {"ready", "live"}
            else "defina HERMES_HOME ou ~/.hermes"
        )
    return status

"""Intenções do chat → ações na máquina local (extensão / Native Messaging).

O kernel só planeja; o desktop executa via `veu.host.*`.
"""

from __future__ import annotations

import re
from typing import Any

# app id → aliases em PT/EN
APP_ALIASES: dict[str, tuple[str, ...]] = {
    "gmail": ("gmail", "e-mail", "email", "correio", "inbox"),
    "calendar": ("agenda", "calendar", "calendário", "calendario"),
    "notion": ("notion",),
    "slack": ("slack",),
    "outlook": ("outlook",),
    "teams": ("teams", "microsoft teams"),
    "whatsapp": ("whatsapp", "zap", "wpp"),
    "grok": ("grok",),
    "chatgpt": ("chatgpt", "chat gpt"),
    "terminal": ("terminal", "console", "cmd", "powershell", "shell"),
    "explorer": ("arquivos", "explorer", "finder", "pasta", "files"),
}

OPEN_VERBS = (
    "abra",
    "abre",
    "abrir",
    "abre o",
    "abre a",
    "abre meu",
    "abre a minha",
    "abrir o",
    "abrir a",
    "abrir meu",
    "abrir minha",
    "abre pra mim",
    "abre aí",
    "abre ai",
    "open",
    "launch",
    "inicia",
    "iniciar",
    "mostra",
    "mostrar",
    "vai pro",
    "vai para",
    "abre no",
)

READ_VERBS = (
    "leia",
    "ler",
    "lê",
    "le ",
    "mostre",
    "mostra",
    "verifique",
    "checa",
    "checar",
    "olha",
    "olhe",
    "triage",
    "triagem",
    "resumo",
    "resuma",
    "o que tem",
    "tem mensagem",
    "novas mensagens",
    "não lidas",
    "nao lidas",
)

LIST_HINTS = (
    "programas abertos",
    "apps abertos",
    "abas abertas",
    "o que está aberto",
    "o que esta aberto",
    "o que tá aberto",
    "o que ta aberto",
    "janelas abertas",
    "lista as abas",
    "listar abas",
    "listar programas",
    "quais apps",
    "quais programas",
    "what's open",
    "list tabs",
    "open tabs",
)

SHELL_HINTS = (
    "rode",
    "executa",
    "executar",
    "no terminal",
    "no shell",
    "comando",
    "whoami",
    "pwd",
)

LABELS = {
    "gmail": "Gmail",
    "calendar": "Agenda",
    "notion": "Notion",
    "slack": "Slack",
    "outlook": "Outlook",
    "teams": "Teams",
    "whatsapp": "WhatsApp",
    "terminal": "terminal",
    "explorer": "arquivos",
    "grok": "Grok",
    "chatgpt": "ChatGPT",
}


def _has_open(intent: str) -> bool:
    t = f" {intent.lower()} "
    return any(f" {v} " in t or t.strip().startswith(v) for v in OPEN_VERBS) or any(
        v in intent.lower() for v in ("abra", "abrir", "abre ", "open ")
    )


def _has_read(intent: str) -> bool:
    t = intent.lower()
    return any(v in t for v in READ_VERBS)


def _has_list(intent: str) -> bool:
    t = intent.lower()
    return any(v in t for v in LIST_HINTS)


def detect_apps(intent: str) -> list[str]:
    lower = intent.lower()
    found: list[str] = []
    for app, aliases in APP_ALIASES.items():
        if any(a in lower for a in aliases):
            found.append(app)
    out: list[str] = []
    for a in found:
        if a not in out:
            out.append(a)
    return out


def wants_host(intent: str) -> bool:
    lower = intent.lower()
    if detect_apps(intent) and (_has_open(intent) or _has_read(intent)):
        return True
    if _has_list(intent):
        return True
    if _has_read(intent) and any(
        k in lower
        for k in (
            "mail",
            "email",
            "e-mail",
            "mensagem",
            "mensagens",
            "inbox",
            "whatsapp",
            "slack",
            "outlook",
            "teams",
            "gmail",
        )
    ):
        return True
    if any(k in lower for k in ("no pc", "no computador", "na máquina", "na maquina", "local")):
        return True
    if any(k in lower for k in SHELL_HINTS):
        return True
    if any(k in lower for k in ("terminal", "explorer", "arquivos locais")):
        return True
    return False


def parse_shell_command(intent: str) -> str | None:
    """Extrai comando curto allowlisted — senão None (desktop pede confirmação)."""
    lower = intent.lower().strip()
    for preset in ("whoami", "pwd", "date"):
        if re.search(rf"\b{preset}\b", lower):
            return preset
    m = re.search(
        r"(?:rode|executa(?:r)?|comando)\s*[: ]\s*[`\"]?([a-zA-Z0-9_./\s\-|]+)",
        intent,
        re.I,
    )
    if m:
        cmd = m.group(1).strip().strip("`\"'")
        if 0 < len(cmd) <= 120 and not re.search(r"[;&`$<>]", cmd):
            return cmd
    return None


def plan_host_actions(intent: str, *, breath: str = "semi") -> dict[str, Any]:
    """Monta lista de ações pro desktop + mensagem ao usuário."""
    apps = detect_apps(intent)
    actions: list[dict[str, Any]] = []
    bits: list[str] = []
    lower = intent.lower()

    openish = _has_open(intent) or _has_read(intent) or wants_host(intent)
    reading = _has_read(intent)

    # Inventário: abas do browser + processos no host
    if _has_list(intent):
        actions.append({"type": "list_tabs"})
        actions.append({"type": "run_preset", "preset": "apps-open"})
        bits.append("Vou listar abas do browser e programas no PC.")

    # Ler e-mail / mensagens → foca app (se aberto) e lê a superfície
    if reading:
        mailish = (
            any(a in apps for a in ("gmail", "outlook"))
            or "mail" in lower
            or "e-mail" in lower
            or "email" in lower
            or "inbox" in lower
            or "correio" in lower
        )
        msgish = (
            any(a in apps for a in ("whatsapp", "slack", "teams"))
            or "mensagem" in lower
            or "mensagens" in lower
            or "zap" in lower
        )
        if mailish:
            if "outlook" in apps and ("outlook" in lower or "gmail" not in apps):
                target = "outlook"
            else:
                target = "gmail"
            if target not in apps:
                apps = [target] + [a for a in apps if a != target]
            actions.append({"type": "focus_app", "app": target})
            actions.append({"type": "read_surface", "app": target})
            bits.append(f"Leio o que está aberto no {LABELS.get(target, target)}.")
        if msgish:
            cand = next((a for a in ("whatsapp", "slack", "teams") if a in apps), "whatsapp")
            if cand not in apps:
                apps = [cand] + apps
            actions.append({"type": "focus_app", "app": cand})
            actions.append({"type": "read_surface", "app": cand})
            bits.append(f"Leio mensagens no {LABELS.get(cand, cand)}.")

    if openish and not apps and "terminal" in lower:
        apps = ["terminal"]
    if openish and not apps and any(k in lower for k in ("arquivo", "pasta", "explorer")):
        apps = ["explorer"]

    # Abrir / focar apps ainda não cobertos pela leitura
    covered = {a.get("app") for a in actions if a.get("type") in {"focus_app", "read_surface"}}
    for app in apps:
        if app in covered and not _has_open(intent):
            continue
        if app in covered and _has_open(intent):
            # já tem focus; só reforça se pediu abrir explicitamente
            continue
        if app in ("terminal", "explorer"):
            actions.append({"type": "run_preset", "preset": app, "app": app})
        else:
            actions.append({"type": "focus_app", "app": app})
        bits.append(f"Abrindo {LABELS.get(app, app)} no seu PC.")

    shell = parse_shell_command(intent)
    if shell in {"whoami", "pwd", "date"}:
        actions.append({"type": "run_preset", "preset": shell})
        bits.append(f"Rodando preset `{shell}` no host.")
    elif shell:
        if breath == "guided":
            bits.append(
                f"Posso rodar `{shell}` no PC — confirme (modo guiado) ou mude pra semi/livre."
            )
        else:
            actions.append({"type": "shell", "command": shell})
            bits.append(f"Executando no PC: `{shell}`")

    # Dedup actions preserving order
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for a in actions:
        key = f"{a.get('type')}:{a.get('app') or a.get('preset') or a.get('command') or ''}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    actions = deduped

    if not actions and not bits:
        return {
            "ok": False,
            "status": "need_target",
            "message": (
                "No PC local posso abrir/ler Gmail, Outlook, Slack, WhatsApp, Teams, "
                "Notion, terminal e arquivos; listar o que está aberto; ou rodar "
                "whoami/date. Diga o que fazer."
            ),
            "actions": [],
        }

    primary = actions[0] if actions else None
    msg = " ".join(bits) if bits else "Ação no PC local."
    if actions:
        msg += " (precisa da extensão Véu Host · host · ok)"
    return {
        "ok": True,
        "status": "host",
        "message": msg,
        "action": primary,
        "actions": actions,
    }

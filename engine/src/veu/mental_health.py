"""Saúde mental — check-ins, gatilhos, sobrecarga, burnout (apoio, não diagnóstico)."""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

# Palavras-sinal (PT) — heurística de apoio; nunca rotula diagnóstico clínico.
_SIGNALS: dict[str, tuple[str, ...]] = {
    "depressao": (
        "sem energia",
        "não aguento",
        "vazio",
        "desânimo",
        "desanimo",
        "sem vontade",
        "triste",
        "choro",
        "inútil",
        "inutil",
        "sem sentido",
        "não vejo saída",
        "nao vejo saida",
    ),
    "ansiedade": (
        "ansioso",
        "ansiedade",
        "coração acelerado",
        "aperto no peito",
        "pânico",
        "panico",
        "preocupado demais",
        "não consigo parar de pensar",
        "nao consigo parar",
    ),
    "toc": (
        "chequei de novo",
        "preciso checar",
        "não consigo parar de verificar",
        "repetir",
        "ritual",
        "contaminação",
        "se eu não fizer",
        "obsess",
    ),
    "procrastinacao": (
        "depois eu faço",
        "deixa pra depois",
        "procrastin",
        "não começo",
        "nao comeco",
        "travado",
        "evitando",
        "adiar",
        "adiando",
    ),
    "burnout": (
        "burnout",
        "esgotado",
        "esgotamento",
        "não aguento mais trabalhar",
        "exaurido",
        "sobrecarregado",
        "sobrecarga",
        "no limite",
        "apagado",
    ),
    "sobrecarga": (
        "muita coisa",
        "não dá conta",
        "nao da conta",
        "lotado",
        "inbox explodiu",
        "sem tempo",
        "afogado",
        "overload",
    ),
}


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "mental_health.json"


def _default() -> dict[str, Any]:
    return {
        "version": 1,
        "updated": 0,
        "checkins": [],
        "triggers": [],
        "alerts": [],
        "notes": [],
        "prefs": {
            "quiet_hours": False,
            "max_open_actions_warn": 25,
            "crisis_resources": True,
        },
    }


def _load() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return _default()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default()
    base = _default()
    base.update({k: v for k, v in data.items() if k in base})
    return base


def _save(data: dict[str, Any]) -> None:
    data["updated"] = time.time()
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _scan_text(text: str) -> list[str]:
    low = (text or "").lower()
    hits: list[str] = []
    for kind, words in _SIGNALS.items():
        if any(w in low for w in words):
            hits.append(kind)
    return hits


def _push_alert(
    data: dict[str, Any],
    *,
    kind: str,
    level: str,
    title: str,
    body: str,
    source: str = "scan",
) -> dict[str, Any]:
    alert = {
        "id": f"mh-{int(time.time())}-{kind[:4]}",
        "ts": time.time(),
        "kind": kind,
        "level": level,  # info | watch | high
        "title": title[:160],
        "body": body[:400],
        "source": source,
        "acked": False,
    }
    alerts = list(data.get("alerts") or [])
    # dedup recente mesmo kind
    for a in alerts[:8]:
        if a.get("kind") == kind and a.get("acked") is False and (time.time() - float(a.get("ts") or 0)) < 3600:
            return a
    alerts.insert(0, alert)
    data["alerts"] = alerts[:60]
    return alert


def checkin(
    *,
    mood: int,
    energy: int,
    focus: int,
    note: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Check-in 1–5 (humor, energia, foco)."""
    mood = max(1, min(5, int(mood)))
    energy = max(1, min(5, int(energy)))
    focus = max(1, min(5, int(focus)))
    data = _load()
    row = {
        "ts": time.time(),
        "mood": mood,
        "energy": energy,
        "focus": focus,
        "note": (note or "")[:400],
        "tags": [str(t)[:40] for t in (tags or [])][:8],
    }
    checkins = list(data.get("checkins") or [])
    checkins.insert(0, row)
    data["checkins"] = checkins[:120]

    # alertas a partir do check-in
    if mood <= 2 and energy <= 2:
        _push_alert(
            data,
            kind="depressao",
            level="watch",
            title="Humor e energia baixos",
            body="Check-in indica dia pesado. Vale pausa, água, e um contato de confiança se piorar.",
            source="checkin",
        )
    if energy <= 2 and focus <= 2:
        _push_alert(
            data,
            kind="burnout",
            level="watch",
            title="Sinais de esgotamento",
            body="Energia e foco no chão. Proteja o resto do dia: menos decisões, mais recuperação.",
            source="checkin",
        )
    if focus <= 2 and mood >= 3:
        _push_alert(
            data,
            kind="procrastinacao",
            level="info",
            title="Foco baixo",
            body="Quebre a próxima tarefa em 10 minutos. Uma micro-ação conta.",
            source="checkin",
        )

    hits = _scan_text(note)
    for h in hits:
        _push_alert(
            data,
            kind=h,
            level="watch" if h in {"depressao", "burnout", "toc"} else "info",
            title=f"Nota tocou em {h}",
            body=note[:200] or "Sinal na nota do check-in.",
            source="checkin-note",
        )

    _save(data)
    return {"ok": True, "checkin": row, **board()}


def log_trigger(
    *,
    kind: str,
    title: str,
    body: str = "",
    intensity: int = 3,
) -> dict[str, Any]:
    kind = (kind or "gatilho").lower().strip()[:40]
    data = _load()
    row = {
        "ts": time.time(),
        "kind": kind,
        "title": (title or "gatilho")[:160],
        "body": (body or "")[:400],
        "intensity": max(1, min(5, int(intensity))),
    }
    triggers = list(data.get("triggers") or [])
    triggers.insert(0, row)
    data["triggers"] = triggers[:100]
    level = "high" if row["intensity"] >= 4 else "watch"
    _push_alert(
        data,
        kind=kind if kind in _SIGNALS else "gatilho",
        level=level,
        title=f"Gatilho · {row['title']}",
        body=row["body"] or "Registrado pelo usuário.",
        source="trigger",
    )
    _save(data)
    return {"ok": True, "trigger": row, **board()}


def ack_alert(alert_id: str) -> dict[str, Any]:
    data = _load()
    found = False
    for a in data.get("alerts") or []:
        if a.get("id") == alert_id:
            a["acked"] = True
            a["acked_at"] = time.time()
            found = True
            break
    if not found:
        return {"ok": False, "error": "alerta não encontrado"}
    _save(data)
    return {"ok": True, **board()}


def scan_context(*, actions_open: int | None = None, recent_texts: list[str] | None = None) -> dict[str, Any]:
    """Varre contexto do SO (ações abertas, textos recentes) e gera alertas."""
    data = _load()
    created: list[str] = []

    # sobrecarga por volume de ações
    try:
        if actions_open is None:
            from veu import actions as veu_actions

            actions_open = int((veu_actions.board().get("counts") or {}).get("open") or 0)
    except Exception:  # noqa: BLE001
        actions_open = actions_open or 0

    warn_at = int((data.get("prefs") or {}).get("max_open_actions_warn") or 25)
    if actions_open >= warn_at:
        a = _push_alert(
            data,
            kind="sobrecarga",
            level="high" if actions_open >= warn_at + 20 else "watch",
            title=f"Sobrecarga · {actions_open} ações abertas",
            body="Fila grande demais. Priorize 3 itens e arquive o resto por hoje.",
            source="actions",
        )
        created.append(a["id"])

    # produtividade / live
    try:
        from veu.bridges import control_live

        side = control_live.sideboard()
        health = side.get("health") or {}
        inbox = int(health.get("inbox_total") or 0)
        unread = int(health.get("unread") or 0)
        if unread >= 40 or inbox >= 200:
            a = _push_alert(
                data,
                kind="sobrecarga",
                level="watch",
                title=f"Inbox pesada · {unread} não lidas",
                body="Loteie: 15 min só triagem, sem responder tudo agora.",
                source="inbox",
            )
            created.append(a["id"])
        prod = side.get("productivity") or {}
        if int(prod.get("blocked") or 0) >= 5:
            a = _push_alert(
                data,
                kind="procrastinacao",
                level="info",
                title="Várias tarefas bloqueadas",
                body="Desbloqueie uma só: peça ajuda ou reduza o escopo.",
                source="tasks",
            )
            created.append(a["id"])
    except Exception:  # noqa: BLE001
        pass

    # textos recentes (opcional)
    for text in recent_texts or []:
        for h in _scan_text(text):
            a = _push_alert(
                data,
                kind=h,
                level="watch",
                title=f"Sinal em conversa · {h}",
                body=text[:180],
                source="text",
            )
            created.append(a["id"])

    # check-ins recentes em queda
    checkins = list(data.get("checkins") or [])[:5]
    if len(checkins) >= 3:
        moods = [int(c.get("mood") or 3) for c in checkins]
        if sum(moods) / len(moods) <= 2.2:
            a = _push_alert(
                data,
                kind="depressao",
                level="high",
                title="Humor baixo nos últimos check-ins",
                body="Padrão recente preocupa. Se estiver em crise, busque ajuda profissional / CVV 188.",
                source="trend",
            )
            created.append(a["id"])

    _save(data)
    return {"ok": True, "created": list(dict.fromkeys(created)), **board()}


def board() -> dict[str, Any]:
    data = _load()
    checkins = list(data.get("checkins") or [])
    alerts = list(data.get("alerts") or [])
    triggers = list(data.get("triggers") or [])

    open_alerts = [a for a in alerts if not a.get("acked")]
    by_kind = Counter(a.get("kind") for a in open_alerts)

    # médias 7 dias
    week = time.time() - 7 * 86400
    recent = [c for c in checkins if float(c.get("ts") or 0) >= week]
    avg = {
        "mood": round(sum(int(c.get("mood") or 0) for c in recent) / len(recent), 2) if recent else None,
        "energy": round(sum(int(c.get("energy") or 0) for c in recent) / len(recent), 2) if recent else None,
        "focus": round(sum(int(c.get("focus") or 0) for c in recent) / len(recent), 2) if recent else None,
        "n": len(recent),
    }

    trend = []
    for c in reversed(checkins[:14]):
        trend.append(
            {
                "ts": c.get("ts"),
                "mood": c.get("mood"),
                "energy": c.get("energy"),
                "focus": c.get("focus"),
            }
        )

    return {
        "ok": True,
        "disclaimer": (
            "Apoio e prevenção — não substitui terapia, psiquiatria ou emergência. "
            "No Brasil, CVV 188 (24h) se estiver em sofrimento intenso."
        ),
        "averages_7d": avg,
        "open_alerts": open_alerts[:20],
        "alerts_by_kind": dict(by_kind),
        "checkins": checkins[:20],
        "triggers": triggers[:20],
        "trend": trend,
        "areas": [
            {
                "id": "depressao",
                "label": "humor / depressão",
                "open": by_kind.get("depressao", 0),
                "hint": "energia, sentido, rede de apoio",
            },
            {
                "id": "toc",
                "label": "TOC / checagens",
                "open": by_kind.get("toc", 0),
                "hint": "rituais, dúvidas, exposição gradual com profissional",
            },
            {
                "id": "procrastinacao",
                "label": "procrastinação",
                "open": by_kind.get("procrastinacao", 0),
                "hint": "micro-passos, timer, uma tarefa só",
            },
            {
                "id": "burnout",
                "label": "burnout",
                "open": by_kind.get("burnout", 0),
                "hint": "limites, sono, menos decisão",
            },
            {
                "id": "sobrecarga",
                "label": "sobrecarga",
                "open": by_kind.get("sobrecarga", 0),
                "hint": "cortar fila, priorizar 3",
            },
            {
                "id": "ansiedade",
                "label": "ansiedade",
                "open": by_kind.get("ansiedade", 0),
                "hint": "respiração, corpo, reduzir cafeína/tela",
            },
        ],
        "updated": data.get("updated") or 0,
    }

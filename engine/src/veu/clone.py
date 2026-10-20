"""Clone — perfil de personalidade do usuário + treino + % de proximidade."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "clone.json"


def _default() -> dict[str, Any]:
    return {
        "version": 1,
        "updated": 0,
        "traits": {
            "tone": [],  # ex.: direto, caloroso, técnico
            "vocabulary": [],  # gírias / frases típicas
            "habits": [],  # jeito de decidir / trabalhar
            "values": [],  # o que importa
            "avoid": [],  # o que o clone NÃO deve fazer/falar
        },
        "samples": [],  # falas do usuário
        "corrections": [],  # feedback: clone errou → correção
        "chat": [],  # histórico da janela Clone
        "harvest": {"sessions": 0, "audit": 0, "last": 0},
        "scores": {},
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
    base.update({k: v for k, v in data.items() if k in base or k in {"version", "updated", "scores", "harvest"}})
    for k in ("traits", "samples", "corrections", "chat"):
        if k not in data:
            continue
        base[k] = data[k]
    return base


def _save(data: dict[str, Any]) -> None:
    data["updated"] = time.time()
    data["scores"] = _compute_scores(data)
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _uniq_add(bucket: list[str], items: list[str], *, cap: int = 40) -> list[str]:
    seen = {x.lower() for x in bucket}
    for it in items:
        s = str(it).strip()
        if not s or s.lower() in seen:
            continue
        bucket.append(s[:160])
        seen.add(s.lower())
    return bucket[-cap:]


def _extract_style(text: str) -> dict[str, list[str]]:
    """Heurística leve de tom / vocabulário a partir de uma fala."""
    t = (text or "").strip()
    low = t.lower()
    tone: list[str] = []
    vocab: list[str] = []
    habits: list[str] = []

    if any(x in low for x in ("por favor", "obrigad", "valeu", "agradeço")):
        tone.append("cortês")
    if any(x in low for x in ("direto", "objetivo", "sem enrolação", "vá ao ponto")):
        tone.append("direto")
    if any(x in low for x in ("cara", "mano", "tipo", "né", "pô", "véi")):
        tone.append("informal")
        vocab.extend(re.findall(r"\b(cara|mano|tipo|né|pô)\b", low))
    if any(x in low for x in ("preciso", "quero que", "faça", "resolva", "mande")):
        habits.append("pede ação concreta")
    if "!" in t:
        tone.append("enfático")
    if "?" in t and len(t) < 80:
        habits.append("faz perguntas curtas")
    if len(t) > 280:
        habits.append("explica com detalhe")
    elif 0 < len(t) < 60:
        habits.append("mensagens curtas")

    # frases marcantes (amostras)
    return {"tone": tone, "vocabulary": vocab, "habits": habits}


def _compute_scores(data: dict[str, Any]) -> dict[str, Any]:
    traits = data.get("traits") or {}
    samples = data.get("samples") or []
    corrections = data.get("corrections") or []
    chat = data.get("chat") or []
    harvest = data.get("harvest") or {}

    def clamp(n: float) -> int:
        return int(max(0, min(100, round(n))))

    # Dimensões (0–100)
    voice = clamp(len(samples) * 4 + len(traits.get("vocabulary") or []) * 5)
    tone = clamp(len(traits.get("tone") or []) * 12 + len(samples) * 2)
    behavior = clamp(
        len(traits.get("habits") or []) * 10
        + len(traits.get("values") or []) * 8
        + int(harvest.get("sessions") or 0) * 0.5
    )
    feedback = clamp(len(corrections) * 15 + sum(1 for c in chat if c.get("role") == "user") * 1.5)
    avoid = clamp(len(traits.get("avoid") or []) * 20)  # saber o que NÃO fazer também é clone

    # Colheita de interações do SO
    absorb = clamp(
        int(harvest.get("sessions") or 0) * 0.8
        + int(harvest.get("audit") or 0) * 0.15
        + len(samples) * 2
    )

    dims = {
        "voz": voice,
        "tom": tone,
        "comportamento": behavior,
        "feedback": feedback,
        "limites": avoid,
        "absorção": absorb,
    }
    overall = clamp(sum(dims.values()) / max(1, len(dims)))
    return {
        "overall": overall,
        "dimensions": dims,
        "label": _label(overall),
        "samples": len(samples),
        "corrections": len(corrections),
        "chat_turns": len(chat),
    }


def _label(pct: int) -> str:
    if pct < 15:
        return "esboço"
    if pct < 35:
        return "rascunho"
    if pct < 55:
        return "parecido"
    if pct < 75:
        return "quase clone"
    if pct < 90:
        return "clone forte"
    return "clone próximo"


def status() -> dict[str, Any]:
    data = _load()
    scores = data.get("scores") or _compute_scores(data)
    return {
        "ok": True,
        "percent": int(scores.get("overall") or 0),
        "label": scores.get("label") or "esboço",
        "dimensions": scores.get("dimensions") or {},
        "traits": data.get("traits") or {},
        "stats": {
            "samples": len(data.get("samples") or []),
            "corrections": len(data.get("corrections") or []),
            "chat_turns": len(data.get("chat") or []),
            "harvest": data.get("harvest") or {},
            "updated": data.get("updated") or 0,
        },
        "note": (
            "O Clone aprende com o que você fala aqui, com correções e com "
            "interações do SO. A % mede proximidade — não é identidade."
        ),
    }


def harvest(*, memory: Any | None = None) -> dict[str, Any]:
    """Absorve falas recentes do usuário em sessions/audit."""
    data = _load()
    added = 0
    sessions_n = 0
    audit_n = 0

    rows: list[dict[str, Any]] = []
    if memory is not None:
        try:
            rows.extend(memory.recent(sink="sessions", limit=80))
            sessions_n = len(rows)
            rows.extend(memory.recent(sink="audit", limit=40))
            audit_n = 40
        except Exception:  # noqa: BLE001
            pass
    else:
        # leitura direta
        for name, key in (("sessions.jsonl", "sessions"), ("audit.jsonl", "audit")):
            path = _root() / name
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()[-60:]
                for line in lines:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                if key == "sessions":
                    sessions_n = len(lines)
                else:
                    audit_n = len(lines)
            except OSError:
                continue

    for row in rows:
        intent = str(row.get("intent") or row.get("message") or "").strip()
        if len(intent) < 12:
            continue
        # ignora comandos de sistema
        if intent.startswith("[autônomo]") or intent.startswith("aprovado no Véu"):
            continue
        style = _extract_style(intent)
        for k, vals in style.items():
            data["traits"][k] = _uniq_add(list(data["traits"].get(k) or []), vals)
        # amostra
        samples = list(data.get("samples") or [])
        if not any(s.get("text") == intent[:400] for s in samples):
            samples.append({"ts": time.time(), "text": intent[:400], "src": "harvest"})
            data["samples"] = samples[-120:]
            added += 1

    data["harvest"] = {
        "sessions": int((data.get("harvest") or {}).get("sessions") or 0) + sessions_n,
        "audit": int((data.get("harvest") or {}).get("audit") or 0) + audit_n,
        "last": time.time(),
        "last_added": added,
    }
    _save(data)
    return {"ok": True, "added": added, **status()}


def teach(
    *,
    text: str,
    kind: str = "sample",
    trait_key: str | None = None,
) -> dict[str, Any]:
    """Ensina o clone: sample | tone | vocabulary | habits | values | avoid."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "texto vazio"}
    data = _load()
    kind = (kind or "sample").lower()
    if kind == "sample" or kind == "fala":
        samples = list(data.get("samples") or [])
        samples.append({"ts": time.time(), "text": text[:500], "src": "teach"})
        data["samples"] = samples[-120:]
        style = _extract_style(text)
        for k, vals in style.items():
            data["traits"][k] = _uniq_add(list(data["traits"].get(k) or []), vals)
    elif kind in {"tone", "vocabulary", "habits", "values", "avoid"}:
        data["traits"][kind] = _uniq_add(list(data["traits"].get(kind) or []), [text])
    elif trait_key and trait_key in {"tone", "vocabulary", "habits", "values", "avoid"}:
        data["traits"][trait_key] = _uniq_add(list(data["traits"].get(trait_key) or []), [text])
    else:
        return {"ok": False, "error": f"kind inválido: {kind}"}
    _save(data)
    return {"ok": True, **status()}


def correct(*, clone_said: str, better: str) -> dict[str, Any]:
    """Usuário corrige uma fala do clone — reforço forte."""
    better = (better or "").strip()
    if not better:
        return {"ok": False, "error": "diga como você falaria"}
    data = _load()
    corr = list(data.get("corrections") or [])
    corr.append(
        {
            "ts": time.time(),
            "clone": (clone_said or "")[:400],
            "better": better[:400],
        }
    )
    data["corrections"] = corr[-80:]
    samples = list(data.get("samples") or [])
    samples.append({"ts": time.time(), "text": better[:500], "src": "correction"})
    data["samples"] = samples[-120:]
    style = _extract_style(better)
    for k, vals in style.items():
        data["traits"][k] = _uniq_add(list(data["traits"].get(k) or []), vals)
    _save(data)
    return {"ok": True, **status()}


def _system_prompt(data: dict[str, Any]) -> str:
    traits = data.get("traits") or {}
    samples = data.get("samples") or []
    corrections = data.get("corrections") or []
    pct = int((data.get("scores") or {}).get("overall") or 0)

    bits = [
        "Você é o Clone do usuário no Véu — treine para falar e agir como ele.",
        f"Proximidade atual: {pct}%.",
        "Responda SEMPRE como se fosse o usuário (1ª pessoa), no jeito dele.",
        "Seja breve, natural, em português do Brasil, sem meta-comentário de IA.",
    ]
    if traits.get("tone"):
        bits.append("Tom: " + ", ".join(traits["tone"][-8:]))
    if traits.get("vocabulary"):
        bits.append("Vocabulário típico: " + ", ".join(traits["vocabulary"][-12:]))
    if traits.get("habits"):
        bits.append("Hábitos: " + ", ".join(traits["habits"][-8:]))
    if traits.get("values"):
        bits.append("Valores: " + ", ".join(traits["values"][-8:]))
    if traits.get("avoid"):
        bits.append("Evitar: " + ", ".join(traits["avoid"][-8:]))
    if samples:
        bits.append("Exemplos de fala do usuário:")
        for s in samples[-6:]:
            bits.append(f"- «{s.get('text')}»")
    if corrections:
        bits.append("Correções (prefira o 'melhor'):")
        for c in corrections[-4:]:
            bits.append(f"- em vez de «{c.get('clone')}» → «{c.get('better')}»")
    return "\n".join(bits)


def chat(message: str, *, llm: Any | None = None) -> dict[str, Any]:
    """Conversa de treino: usuário fala → clone responde no estilo → perfil cresce."""
    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "mensagem vazia"}

    data = _load()
    # toda fala do usuário treina
    samples = list(data.get("samples") or [])
    samples.append({"ts": time.time(), "text": message[:500], "src": "chat"})
    data["samples"] = samples[-120:]
    style = _extract_style(message)
    for k, vals in style.items():
        data["traits"][k] = _uniq_add(list(data["traits"].get(k) or []), vals)

    # comandos leves
    low = message.lower()
    if low.startswith("tom:"):
        data["traits"]["tone"] = _uniq_add(list(data["traits"]["tone"]), [message.split(":", 1)[1].strip()])
    elif low.startswith("evite:") or low.startswith("evitar:"):
        data["traits"]["avoid"] = _uniq_add(
            list(data["traits"]["avoid"]), [message.split(":", 1)[1].strip()]
        )
    elif low.startswith("valor:"):
        data["traits"]["values"] = _uniq_add(
            list(data["traits"]["values"]), [message.split(":", 1)[1].strip()]
        )

    reply = ""
    if llm is not None:
        try:
            from veu.llm import SYSTEM_OS  # noqa: F401

            prompt = (
                "O usuário disse (treino de clone):\n"
                f"{message}\n\n"
                "Responda como o próprio usuário responderia a si mesmo num espelho — "
                "mostrando o jeito dele. Se ele pediu para o clone praticar um assunto, "
                "fale sobre isso no estilo dele."
            )
            result = llm.complete(
                prompt,
                system=_system_prompt(data),
                purpose="clone",
                allow_handoff=False,
                fallback_local=True,
            )
            if result.ok and result.text:
                reply = str(result.text).strip()[:1200]
        except Exception as e:  # noqa: BLE001
            reply = ""
            err = str(e)[:120]
        else:
            err = None
    else:
        err = None

    if not reply:
        # fallback local sem LLM
        tones = ", ".join((data.get("traits") or {}).get("tone") or ["neutro"])
        reply = (
            f"Beleza — anotado no meu jeito ({tones}). "
            f"Continua me corrigindo quando eu sair do personagem."
        )

    chat_log = list(data.get("chat") or [])
    chat_log.append({"ts": time.time(), "role": "user", "text": message[:800]})
    chat_log.append({"ts": time.time(), "role": "clone", "text": reply[:800]})
    data["chat"] = chat_log[-80:]
    _save(data)

    out = {"ok": True, "reply": reply, **status(), "history": data["chat"][-20:]}
    if err:
        out["llm_note"] = err
    return out


def history(limit: int = 40) -> dict[str, Any]:
    data = _load()
    return {
        "ok": True,
        "chat": (data.get("chat") or [])[-limit:],
        **status(),
    }


def reset(*, keep_traits: bool = False) -> dict[str, Any]:
    data = _default() if not keep_traits else _load()
    if keep_traits:
        data["samples"] = []
        data["corrections"] = []
        data["chat"] = []
        data["harvest"] = {"sessions": 0, "audit": 0, "last": 0}
    else:
        data = _default()
    _save(data)
    return {"ok": True, **status()}


def profile_for_prompt() -> str:
    """Trecho curto para outros módulos (chat do SO) usarem o clone."""
    data = _load()
    scores = data.get("scores") or _compute_scores(data)
    if int(scores.get("overall") or 0) < 20:
        return ""
    return _system_prompt(data)[:1500]

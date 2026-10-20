"""Modo autônomo — percorre apps, agentes e live.json e prepara ações para o usuário."""

from __future__ import annotations

import time
from typing import Any

from veu import actions as veu_actions
from veu import approvals as veu_approvals
from veu.bridges import control_live


def scan(*, runtime: Any | None = None) -> dict[str, Any]:
    """Varre superfícies do SO e upserta propostas acionáveis."""
    started = time.time()
    created: list[str] = []
    sources: dict[str, int] = {}
    # limpa spam ECC/agent antes de montar o quadro útil
    cleaned = veu_actions.dismiss_noise(sources=("ecc", "agent"))

    def _add(**kwargs: Any) -> None:
        row = veu_actions.upsert(**kwargs)
        created.append(str(row.get("id")))
        src = str(kwargs.get("source") or "other")
        sources[src] = sources.get(src, 0) + 1

    # 1) Aprovações pendentes
    board = veu_approvals.board()
    for item in board.get("pending") or []:
        _add(
            source="approval",
            ref=str(item.get("id") or ""),
            title=f"Aprovar · {str(item.get('intent') or '')[:90]}",
            help_text=(
                f"Risco {item.get('risk')} · respiração {item.get('breath')}. "
                "Escolha aprovar ou rejeitar em Aprovações."
            ),
            suggested="approve",
            subject="aprovação",
            priority="high" if item.get("risk") == "high" else "normal",
            meta={"approval_id": item.get("id"), "app": "approvals"},
        )

    # 2) Live.json — inbox / tarefas / reuniões / agenda / insights
    side = control_live.sideboard(limit_inbox=20, limit_meetings=12, limit_agenda=15)
    if side.get("available"):
        for m in side.get("inbox") or []:
            if not (m.get("needsApproval") or m.get("unread")):
                continue
            act = str(m.get("action") or "").strip()
            help_bits = [
                f"De {m.get('sender') or 'remetente'} · {m.get('channel')}",
                str(m.get("preview") or "")[:200],
            ]
            if act:
                help_bits.append(f"Sugestão: {act}")
            if m.get("why"):
                help_bits.append(str(m.get("why")))
            _add(
                source="inbox",
                ref=str(m.get("id") or m.get("subject") or ""),
                title=f"Responder · {str(m.get('subject') or 'mensagem')[:100]}",
                help_text=" · ".join(x for x in help_bits if x)[:800],
                suggested="reply",
                company=str(m.get("company") or ""),
                subject=str(m.get("subject") or "")[:120],
                priority="high" if m.get("needsApproval") else "normal",
                meta={"app": "inbox", "channel": m.get("channel")},
            )

        for t in side.get("tasks") or []:
            st = str(t.get("status") or "todo")
            if st not in {"todo", "doing", "blocked"}:
                continue
            _add(
                source="task",
                ref=str(t.get("id") or t.get("title") or ""),
                title=f"Tarefa · {str(t.get('title') or '')[:100]}",
                help_text=(
                    f"Status {st}"
                    + (f" · dono {t.get('owner')}" if t.get("owner") else "")
                    + (f" · prazo {t.get('due')}" if t.get("due") else "")
                    + ". Marque como feita quando concluir ou peça ajuda ao chat."
                ),
                suggested="complete" if st != "blocked" else "unblock",
                company=str(t.get("company") or ""),
                subject=str(t.get("title") or "")[:120],
                priority="high" if st == "blocked" else "normal",
                meta={"app": "companies", "status": st},
            )

        for mt in side.get("meetings") or []:
            bullets = mt.get("bullets") or []
            shallow = len(bullets) < 2
            _add(
                source="meeting",
                ref=str(mt.get("id") or mt.get("title") or ""),
                title=f"Reunião · {str(mt.get('title') or '')[:100]}",
                help_text=(
                    (mt.get("behavior") or "revisar ata")
                    + (f" · {'; '.join(str(b) for b in bullets[:3])}" if bullets else "")
                    + (
                        ". Peça resumo profundo ao GrokBot se faltar detalhe."
                        if shallow
                        else ". Extrair ações e marcar o que já foi tratado."
                    )
                ),
                suggested="study" if shallow else "extract",
                company=str(mt.get("empresa") or ""),
                subject=str(mt.get("title") or "")[:120],
                meta={"app": "companies", "meeting_id": mt.get("id")},
            )

        for a in side.get("agenda") or []:
            if a.get("cancelled"):
                continue
            resp = str(a.get("response") or "").lower()
            if resp in {"accepted", "organizer", "aceito"}:
                continue
            _add(
                source="agenda",
                ref=str(a.get("id") or a.get("title") or ""),
                title=f"Agenda · {str(a.get('title') or '')[:100]}",
                help_text=(
                    f"{a.get('start') or '?'} · {a.get('company') or ''}. "
                    f"Resposta atual: {a.get('response') or 'pendente'}. "
                    "Confirme presença ou prepare pauta."
                ),
                suggested="rsvp",
                company=str(a.get("company") or ""),
                subject=str(a.get("title") or "")[:120],
                meta={"app": "agenda"},
            )

        for ins in side.get("insights") or []:
            _add(
                source="study",
                ref=str(ins.get("id") or ins.get("title") or ""),
                title=f"Estudar · {str(ins.get('title') or '')[:100]}",
                help_text=str(ins.get("body") or "assunto a tratar / estudar")[:800],
                suggested="study",
                company=str(ins.get("company") or ""),
                subject=str(ins.get("title") or "")[:120],
                meta={"app": "productivity"},
            )

    # 3) Conectores quebrados (não lista ECC — polui o quadro)
    if runtime is not None:
        try:
            runtime.refresh_connector_status()
            for c in runtime.connectors.all():
                st = getattr(c, "status", "") or ""
                if st in {"planned", "error"}:
                    _add(
                        source="connector",
                        ref=str(getattr(c, "id", "") or getattr(c, "name", "")),
                        title=f"Nervo · {getattr(c, 'name', c)}",
                        help_text=(
                            f"Status {st}. "
                            f"{getattr(c, 'note', '') or 'Conectar ou validar credencial.'}"
                        )[:800],
                        suggested="connect",
                        subject=str(getattr(c, "id", "")),
                        meta={"app": "credentials"},
                        priority="normal",
                    )
        except Exception:  # noqa: BLE001
            pass

    board_out = veu_actions.board(limit=100)
    # esconde ruído no payload do board
    useful = [
        a
        for a in (board_out.get("actions") or [])
        if a.get("source") not in {"ecc", "agent"}
        and a.get("status") in {"open", "updated", "in_progress"}
    ]
    board_out = {**board_out, "actions": useful, "counts": {**(board_out.get("counts") or {}), "open": len(useful)}}
    return {
        "ok": True,
        "scanned_at": time.time(),
        "elapsed_ms": int((time.time() - started) * 1000),
        "upserted": len(created),
        "sources": sources,
        "cleaned_noise": int(cleaned.get("dismissed") or 0),
        "board": board_out,
        "note": (
            "Modo autônomo: propostas úteis (inbox, tarefas, reuniões, agenda). "
            "Ruído de agentes ECC foi arquivado. Escolha e marque como feito."
        ),
    }


def act(action_id: str, *, status: str, note: str = "", runtime: Any | None = None) -> dict[str, Any]:
    """Marca ação e, se 'in_progress' com suggested known, dispara ajuda leve."""
    row = veu_actions.get(action_id)
    if not row:
        return {"ok": False, "error": "ação não encontrada"}

    result = veu_actions.set_status(action_id, status=status, note=note)
    if not result.get("ok"):
        return result

    dispatch: dict[str, Any] | None = None
    if status == "in_progress" and runtime is not None:
        suggested = str(row.get("suggested") or "")
        meta = row.get("meta") or {}
        # Aprovar via fila se for approval
        if suggested == "approve" and meta.get("approval_id"):
            dispatch = veu_approvals.decide(str(meta["approval_id"]), approve=True, note=note or "autônomo")
        elif suggested in {"study", "extract", "reply", "delegate"} and hasattr(runtime, "bridges"):
            intent = (
                f"[autônomo] Ajude com: {row.get('title')}. "
                f"Contexto: {row.get('help')}. "
                f"Empresa: {row.get('company') or '—'}. Assunto: {row.get('subject') or '—'}."
            )
            try:
                dispatch = runtime.bridges.grokbot.ask(
                    intent=intent,
                    breath="autonomous",
                    via="os",
                    agent=str(meta.get("agent") or "") or None,
                )
            except Exception as e:  # noqa: BLE001
                dispatch = {"ok": False, "error": str(e)[:200]}

    return {**result, "dispatch": dispatch}

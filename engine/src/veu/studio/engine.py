"""Studio — decide quem executa e roda análise / RAG / planilha / geração."""

from __future__ import annotations

import csv
import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from veu.studio import store


ACTIONS: dict[str, dict[str, Any]] = {
    "analyze": {
        "label": "Analisar / resumir",
        "kinds": ["text", "pdf", "doc", "image", "audio", "sheet", "binary"],
        "hint": "Extrai pontos-chave e insights",
    },
    "transcribe": {
        "label": "Transcrever áudio",
        "kinds": ["audio"],
        "hint": "Speech → texto (local / Hermes / Grok Bot)",
    },
    "vision": {
        "label": "Descrever imagem",
        "kinds": ["image"],
        "hint": "O que há na imagem",
    },
    "rag_ingest": {
        "label": "Inserir no OpenRAG",
        "kinds": ["text", "pdf", "doc", "sheet"],
        "hint": "Indexa na base documental",
    },
    "sheet_dw": {
        "label": "DW vivo · gráficos e indicadores",
        "kinds": ["sheet"],
        "hint": "Colunas, KPIs e insights na hora",
    },
    "generate_md": {
        "label": "Gerar documento (Markdown)",
        "kinds": ["text", "pdf", "doc", "sheet"],
        "hint": "Relatório / plano a partir do arquivo",
    },
    "generate_plan": {
        "label": "Planejamento · cronograma",
        "kinds": ["text", "pdf", "doc", "sheet"],
        "hint": "Plano, fases e entregas",
    },
    "delegate_hermes": {
        "label": "Delegar ao Hermes",
        "kinds": ["text", "pdf", "doc", "image", "audio", "sheet", "binary"],
        "hint": "Agente local com tools",
    },
    "delegate_grokbot": {
        "label": "Delegar ao Grok Bot",
        "kinds": ["text", "pdf", "doc", "image", "audio", "sheet", "binary"],
        "hint": "Job always-on na nuvem",
    },
}


def actions_for(kind: str) -> list[dict[str, Any]]:
    out = []
    for aid, meta in ACTIONS.items():
        if kind in meta["kinds"] or kind == "binary":
            if aid in {"transcribe", "vision", "sheet_dw"} and kind not in meta["kinds"]:
                continue
            out.append({"id": aid, **meta})
    return out


def decide_executor(
    *,
    action: str,
    kind: str,
    size: int,
    bridges: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """SO decide: local | hermes | grokbot."""
    bridges = bridges or {}
    hermes_ok = (bridges.get("hermes") or {}).get("status") in {"ready", "live"}
    grok_ok = (bridges.get("grokbot") or {}).get("status") in {"ready", "live"}

    if action == "delegate_hermes":
        return {"executor": "hermes", "reason": "pedido explícito Hermes"}
    if action == "delegate_grokbot":
        return {"executor": "grokbot", "reason": "pedido explícito Grok Bot"}

    # áudio grande / jobs longos → cloud
    if action == "transcribe" and (size > 2_000_000 or kind == "audio"):
        if grok_ok:
            return {"executor": "grokbot", "reason": "áudio/transcrição longa → Grok Bot"}
        if hermes_ok:
            return {"executor": "hermes", "reason": "Hermes local com tools de áudio"}
        return {"executor": "local", "reason": "sem ponte — fila local (stub)"}

    if action == "rag_ingest":
        return {"executor": "local", "reason": "OpenRAG no kernel"}

    if action in {"sheet_dw", "analyze", "generate_md", "generate_plan", "vision"}:
        if size > 5_000_000 and grok_ok:
            return {"executor": "grokbot", "reason": "arquivo grande → Grok Bot"}
        return {"executor": "local", "reason": "rápido no SO"}

    if hermes_ok and action.startswith("delegate"):
        return {"executor": "hermes", "reason": "Hermes disponível"}
    return {"executor": "local", "reason": "default SO"}


class StudioEngine:
    def __init__(self, runtime: Any = None) -> None:
        self.rt = runtime

    def pulse(self) -> dict[str, Any]:
        return {
            "id": "studio",
            "status": "live",
            "assets": len(store.list_assets(200)),
            "jobs": len(store.list_jobs(50)),
            "actions": list(ACTIONS.keys()),
        }

    def menu_for_asset(self, asset: dict[str, Any]) -> list[dict[str, Any]]:
        return actions_for(str(asset.get("kind") or "binary"))

    def menu_for_path(self, path: str, filename: str | None = None) -> list[dict[str, Any]]:
        name = filename or Path(path).name
        kind = store.classify(name, "")
        return actions_for(kind)

    def ingest_bytes(
        self,
        *,
        filename: str,
        data: bytes,
        content_type: str = "",
    ) -> dict[str, Any]:
        meta = store.save_upload(filename=filename, data=data, content_type=content_type)
        meta["actions"] = self.menu_for_asset(meta)
        return meta

    def run(
        self,
        *,
        action: str,
        asset_id: str | None = None,
        path: str | None = None,
        text: str | None = None,
        filename: str | None = None,
        prompt: str | None = None,
        force_executor: str | None = None,
    ) -> dict[str, Any]:
        asset = store.get_asset(asset_id) if asset_id else None
        kind = (asset or {}).get("kind") or store.classify(filename or path or "file", "")
        size = int((asset or {}).get("bytes") or (len(text.encode()) if text else 0))
        bridges = {}
        if self.rt is not None:
            bridges = (self.rt.bridges.pulse() if hasattr(self.rt, "bridges") else {}) or {}
            if hasattr(bridges, "get") is False:
                bridges = {}

        decision = decide_executor(action=action, kind=kind, size=size, bridges=bridges)
        if force_executor in {"local", "hermes", "grokbot"}:
            decision = {"executor": force_executor, "reason": "forçado pelo usuário"}

        job_id = f"job-{uuid.uuid4().hex[:10]}"
        job: dict[str, Any] = {
            "id": job_id,
            "ts": time.time(),
            "action": action,
            "asset_id": asset_id,
            "path": path,
            "filename": filename or (asset or {}).get("filename"),
            "kind": kind,
            "decision": decision,
            "status": "running",
            "prompt": (prompt or "")[:500],
        }

        executor = decision["executor"]
        if executor == "hermes":
            result = self._delegate_hermes(action, asset, text, prompt)
        elif executor == "grokbot":
            result = self._delegate_grokbot(action, asset, text, prompt)
        else:
            result = self._run_local(action, asset, text, prompt, kind)

        job["status"] = "done" if result.get("ok") else "error"
        job["result"] = result
        store.append_job(job)
        if self.rt is not None:
            self.rt.memory.append("studio.job", job, sink="decisions")
        return job

    def _read_asset_text(self, asset: dict[str, Any] | None, text: str | None) -> str:
        if text:
            return text
        if not asset:
            return ""
        path = Path(str(asset.get("path") or ""))
        if not path.is_file():
            return ""
        kind = asset.get("kind")
        if kind in {"text", "sheet", "doc"} or path.suffix.lower() in {
            ".txt",
            ".md",
            ".csv",
            ".tsv",
            ".json",
            ".html",
            ".yaml",
            ".yml",
        }:
            try:
                return path.read_text(encoding="utf-8", errors="replace")[:80_000]
            except OSError:
                return ""
        if kind == "pdf":
            try:
                raw = path.read_bytes()
                # extração tosca de strings PDF
                chunks = re.findall(rb"[\x20-\x7e]{5,}", raw)
                return "\n".join(c.decode("latin-1", errors="ignore") for c in chunks[:400])[:40_000]
            except OSError:
                return ""
        return f"[arquivo binário {path.name} · {asset.get('bytes')} bytes · kind={kind}]"

    def _run_local(
        self,
        action: str,
        asset: dict[str, Any] | None,
        text: str | None,
        prompt: str | None,
        kind: str,
    ) -> dict[str, Any]:
        body = self._read_asset_text(asset, text)
        name = (asset or {}).get("filename") or "arquivo"

        if action == "sheet_dw":
            return self._sheet_dw(body, name)
        if action == "rag_ingest":
            return self._rag_ingest(body, name)
        if action == "transcribe":
            return {
                "ok": True,
                "message": (
                    "Áudio recebido no Studio. Transcrição local ainda é stub — "
                    "ative Hermes/Grok Bot ou Whisper via HF/Ollama. "
                    f"Arquivo: {name}."
                ),
                "transcript": "",
            }
        if action == "vision":
            return self._llm_job(
                f"Descreva a imagem/arquivo «{name}» com base neste contexto:\n{body[:4000]}\n"
                f"Pedido: {prompt or 'descreva e destaque o que importa'}",
            )
        if action == "generate_plan":
            return self._generate_plan(body, name, prompt)
        if action == "generate_md":
            return self._generate_md(body, name, prompt)
        # analyze default
        return self._analyze(body, name, prompt)

    def _analyze(self, body: str, name: str, prompt: str | None) -> dict[str, Any]:
        if not body.strip():
            return {"ok": False, "message": "sem texto extraível deste arquivo"}
        ask = prompt or "Resuma, destaque riscos e próximos passos."
        return self._llm_job(
            f"Arquivo «{name}».\n\nConteúdo:\n{body[:12000]}\n\nTarefa: {ask}\n"
            "Responda em português, estruturado (resumo · pontos · ações)."
        )

    def _generate_md(self, body: str, name: str, prompt: str | None) -> dict[str, Any]:
        ask = prompt or "Gere um documento Markdown profissional."
        out = self._llm_job(
            f"Com base em «{name}» e no material abaixo, {ask}\n\n{body[:10000]}"
        )
        if out.get("ok") and out.get("text"):
            path = store.out_dir() / f"doc-{uuid.uuid4().hex[:8]}.md"
            path.write_text(str(out["text"]), encoding="utf-8")
            out["artifact"] = str(path)
            out["message"] = f"Documento gerado: {path.name}"
            try:
                from veu.integrity import seal_artifact

                seal = seal_artifact(path, job_id=str(out.get("job_id") or ""))
                out["integrity"] = seal.get("entry")
            except Exception:  # noqa: BLE001
                pass
        return out

    def _generate_plan(self, body: str, name: str, prompt: str | None) -> dict[str, Any]:
        ask = prompt or "Monte planejamento com fases, cronograma e entregas."
        out = self._llm_job(
            f"Material «{name}»:\n{body[:10000]}\n\n{ask}\n"
            "Formato: fases numeradas, prazos relativos, responsáveis, riscos."
        )
        if out.get("ok") and out.get("text"):
            path = store.out_dir() / f"plan-{uuid.uuid4().hex[:8]}.md"
            path.write_text(str(out["text"]), encoding="utf-8")
            out["artifact"] = str(path)
            out["message"] = f"Plano gerado: {path.name}"
            try:
                from veu.integrity import seal_artifact

                seal = seal_artifact(path, job_id=str(out.get("job_id") or ""))
                out["integrity"] = seal.get("entry")
            except Exception:  # noqa: BLE001
                pass
        return out

    def _sheet_dw(self, body: str, name: str) -> dict[str, Any]:
        if not body.strip():
            return {"ok": False, "message": "planilha vazia ou ilegível"}
        sample = body.strip()
        # detect delimiter
        delim = ";" if sample.count(";") > sample.count(",") else ","
        try:
            reader = csv.reader(io.StringIO(sample), delimiter=delim)
            rows = [r for r in reader if any(c.strip() for c in r)]
        except Exception as e:
            return {"ok": False, "message": f"CSV inválido: {e}"}
        if not rows:
            return {"ok": False, "message": "sem linhas"}
        header = rows[0]
        data = rows[1:]
        cols = len(header)
        numeric: dict[str, list[float]] = {h: [] for h in header}
        for r in data:
            for i, h in enumerate(header):
                if i >= len(r):
                    continue
                raw = r[i].replace(".", "").replace(",", ".") if False else r[i].replace(",", ".")
                try:
                    numeric[h].append(float(re.sub(r"[^\d.\-]", "", raw)))
                except ValueError:
                    pass
        kpis = []
        charts = []
        for h, vals in numeric.items():
            if len(vals) < 2:
                continue
            kpis.append(
                {
                    "column": h,
                    "count": len(vals),
                    "sum": round(sum(vals), 4),
                    "avg": round(sum(vals) / len(vals), 4),
                    "min": round(min(vals), 4),
                    "max": round(max(vals), 4),
                }
            )
            charts.append(
                {
                    "type": "bar",
                    "title": h,
                    "points": [{"i": i, "v": v} for i, v in enumerate(vals[:40])],
                }
            )
        insight = (
            f"Planilha «{name}»: {len(data)} linhas · {cols} colunas. "
            f"{len(kpis)} indicadores numéricos calculados na hora (DW vivo)."
        )
        # LLM opcional sobre KPIs
        llm_bit = ""
        if self.rt is not None and kpis:
            brief = json.dumps(kpis[:8], ensure_ascii=False)
            llm = self._llm_job(
                f"KPIs da planilha {name}:\n{brief}\nDê 4 insights e 3 indicadores a acompanhar."
            )
            if llm.get("ok"):
                llm_bit = llm.get("text") or ""
        artifact = {
            "rows": len(data),
            "columns": header,
            "kpis": kpis,
            "charts": charts[:6],
            "insight": insight,
            "narrative": llm_bit,
        }
        path = store.out_dir() / f"dw-{uuid.uuid4().hex[:8]}.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "message": insight,
            "dw": artifact,
            "artifact": str(path),
            "text": llm_bit or insight,
        }

    def _rag_ingest(self, body: str, name: str) -> dict[str, Any]:
        if self.rt is None or not getattr(self.rt, "openrag", None):
            return {"ok": False, "message": "OpenRAG indisponível"}
        orag = self.rt.openrag
        if not orag.live:
            return {
                "ok": False,
                "message": "OpenRAG sem chave — defina OPENRAG_API_KEY em Ajustes",
            }
        # pergunta de indexação via chat (API chat) — guarda também em memória Véu
        self.rt.memory.append(
            "studio.rag_ingest",
            {"filename": name, "chars": len(body), "preview": body[:400]},
            sink="decisions",
        )
        ask = orag.ask(
            f"Indexe mentalmente este documento «{name}» e confirme o tema em 2 frases:\n{body[:6000]}"
        )
        return {
            "ok": bool(ask.get("ok")),
            "message": ask.get("message")
            or ask.get("answer")
            or "Documento registrado na memória do SO + consultado no OpenRAG.",
            "answer": ask.get("answer"),
            "sources": ask.get("sources"),
        }

    def _llm_job(self, prompt: str) -> dict[str, Any]:
        if self.rt is None:
            return {"ok": False, "message": "kernel sem runtime", "text": ""}
        result = self.rt.llm.complete(
            prompt,
            purpose="chat",
            allow_handoff=False,
            fallback_local=True,
        )
        self.rt._last_llm_handoff = None
        text = (result.text or "").strip()
        if "abro o chat da assinatura" in text.lower():
            text = ""
        return {
            "ok": bool(result.ok and text),
            "text": text or result.error or "sem resposta do modelo",
            "message": text[:500] if text else (result.error or "falha"),
            "provider": result.provider,
            "model": result.model,
        }

    def _delegate_hermes(
        self,
        action: str,
        asset: dict[str, Any] | None,
        text: str | None,
        prompt: str | None,
    ) -> dict[str, Any]:
        if self.rt is None:
            return {"ok": False, "message": "sem runtime"}
        bridges = self.rt.bridges.pulse()
        hm = bridges.get("hermes") or {}
        payload = {
            "action": action,
            "file": (asset or {}).get("filename"),
            "prompt": prompt,
            "preview": (text or "")[:1000],
        }
        intent = (
            f"studio:{action} · {(asset or {}).get('filename') or 'arquivo'} · "
            f"{(prompt or 'processar')[:200]}"
        )
        enq = self.rt.bridges.hermes.enqueue(
            intent=intent,
            kind="studio",
            payload=payload,
            source="studio",
        )
        self.rt.memory.append(
            "studio.delegate.hermes",
            {**payload, "job": enq.get("job")},
            sink="decisions",
        )
        st = self.rt.bridges.hermes.status()
        return {
            "ok": True,
            "message": (
                f"Hermes ({st}) · job {enq.get('job', {}).get('job_id')} na fila. "
                "Aparece em Agenda · Fila. Com HERMES_API_URL o handoff vai ao API Server."
            ),
            "queued": payload,
            "hermes": enq,
        }

    def _delegate_grokbot(
        self,
        action: str,
        asset: dict[str, Any] | None,
        text: str | None,
        prompt: str | None,
    ) -> dict[str, Any]:
        if self.rt is None:
            return {"ok": False, "message": "sem runtime"}
        brief = (
            f"Studio Véu · ação `{action}` no arquivo "
            f"{(asset or {}).get('filename') or 'sem-nome'}.\n"
            f"Pedido: {prompt or 'analisar e devolver resultado'}\n"
            f"Preview:\n{(text or '')[:2000]}"
        )
        result = self.rt.bridges.grokbot.ask(brief, agent="chief-of-staff")
        return {
            "ok": bool(result.get("ok", True)),
            "message": result.get("message")
            or "Handoff ao Grok Bot — retorno chega no SO via inbound.",
            "grokbot": result,
        }

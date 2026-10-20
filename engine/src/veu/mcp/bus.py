"""API de alto nível: importar JSON → probe → tools → registry."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from veu.connectors.registry import Connector, ConnectorKind, Registry
from veu.mcp import store
from veu.mcp.client import McpError, open_client
from veu.mcp.parse import extract_json_from_text, parse_mcp_json
from veu.mcp.presets import detect_preset_config


def list_public() -> list[dict[str, Any]]:
    return store.list_servers()


def _compact_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for t in tools[:80]:
        out.append(
            {
                "name": t.get("name"),
                "description": (t.get("description") or "")[:240],
            }
        )
    return out


def probe_raw(row: dict[str, Any]) -> dict[str, Any]:
    env = store.resolve_env(row)
    headers = store.resolve_headers(row)
    client = open_client(row, env, headers)
    try:
        # Http + Stdio suportam context manager
        if hasattr(client, "__enter__"):
            client.__enter__()  # type: ignore[misc]
        info = client.initialize()
        tools = client.list_tools()
        return {
            "ok": True,
            "status": "live",
            "tools": _compact_tools(tools),
            "probe": {
                "ok": True,
                "server": (info or {}).get("serverInfo") if isinstance(info, dict) else None,
                "tool_count": len(tools),
            },
            "error": "",
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "error",
            "tools": [],
            "probe": {"ok": False},
            "error": str(e)[:400],
        }
    finally:
        try:
            if hasattr(client, "__exit__"):
                client.__exit__(None, None, None)  # type: ignore[misc]
            elif hasattr(client, "close"):
                client.close()  # type: ignore[misc]
        except Exception:
            pass


def probe(server_id: str) -> dict[str, Any]:
    row = store.get_raw(server_id)
    if not row:
        return {"ok": False, "error": "servidor MCP não encontrado"}
    result = probe_raw(row)
    pub = store.update_probe(
        server_id,
        ok=bool(result["ok"]),
        tools=result.get("tools") or [],
        error=result.get("error") or "",
        probe=result.get("probe"),
    )
    return {
        "ok": bool(result["ok"]),
        "server": pub,
        "tools": result.get("tools") or [],
        "error": result.get("error") or "",
    }


ALLOWED_MCP_COMMANDS = frozenset({"npx", "uvx", "node", "python", "python3"})
_SHELL_META = re.compile(r"[;&|`$<>\n\r]")


def _validate_command(cfg: dict[str, Any]) -> str | None:
    cmd = str(cfg.get("command") or "").strip()
    if not cmd:
        return None  # http/sse transport
    base = Path(cmd).name.lower()
    if base not in ALLOWED_MCP_COMMANDS:
        return f"comando fora da lista: {base}"
    joined = " ".join([cmd, *list(cfg.get("args") or [])])
    if _SHELL_META.search(joined):
        return "metacaracteres de shell bloqueados"
    return None


def preview_import(raw: Any) -> dict[str, Any]:
    """Prévia sem gravar — comando, args, chaves de env, URL."""
    import hashlib
    import json as _json

    servers = parse_mcp_json(raw)
    items = []
    errors: list[str] = []
    for cfg in servers:
        err = _validate_command(cfg)
        if err:
            errors.append(f"{cfg.get('id')}: {err}")
        env_keys = sorted((cfg.get("env") or {}).keys())
        # segredos só como referência — nunca valores
        items.append(
            {
                "id": cfg.get("id"),
                "name": cfg.get("name") or cfg.get("id"),
                "transport": cfg.get("transport") or "http",
                "url": cfg.get("url") or "",
                "command": cfg.get("command") or "",
                "args": list(cfg.get("args") or []),
                "env_keys": env_keys,
                "header_keys": sorted((cfg.get("headers") or {}).keys()),
                "ok": err is None,
                "error": err or "",
            }
        )
    blob = _json.dumps(servers, sort_keys=True, default=str)
    return {
        "ok": not errors,
        "preview": True,
        "items": items,
        "count": len(items),
        "errors": errors,
        "hash": hashlib.sha256(blob.encode()).hexdigest()[:24],
        "note": "Nada foi gravado. Confirme com confirm=true para importar.",
    }


def import_json(
    raw: Any,
    *,
    probe_now: bool = False,
    confirm: bool = False,
    subject: str = "user",
) -> dict[str, Any]:
    """Importa JSON MCP com revisão. Sem confirm → só prévia. Nada probe no import."""
    import hashlib
    import json as _json

    if not confirm:
        return preview_import(raw)

    servers = parse_mcp_json(raw)
    imported: list[dict[str, Any]] = []
    errors: list[str] = []
    for cfg in servers:
        err = _validate_command(cfg)
        if err:
            errors.append(f"{cfg.get('id')}: {err}")
            continue
        # Env com segredos: só nomes — valores já tratados em upsert via .env refs
        cfg = dict(cfg)
        # marca não verificado até aprovação explícita
        pub = store.upsert_normalized(cfg)
        # força status unverified (sem probe automático no import)
        data = store.load_raw()
        for i, s in enumerate(data.get("servers") or []):
            if s.get("id") == pub["id"]:
                s = dict(s)
                s["status"] = "unverified"
                s["verified"] = False
                s["updated_at"] = time.time()
                data["servers"][i] = s
                store.save_raw(data)
                pub = store.public_server(s)
                break
        # probe só se pedido E depois — mas default False no import revisado
        if probe_now:
            row = store.get_raw(pub["id"])
            if row:
                probe_info = probe_raw(row)
                store.update_probe(
                    pub["id"],
                    ok=bool(probe_info["ok"]),
                    tools=probe_info.get("tools") or [],
                    error=probe_info.get("error") or "",
                    probe=probe_info.get("probe"),
                )
                # mantém unverified até approve
                data = store.load_raw()
                for i, s in enumerate(data.get("servers") or []):
                    if s.get("id") == pub["id"]:
                        s = dict(s)
                        s["status"] = "unverified"
                        s["verified"] = False
                        data["servers"][i] = s
                        store.save_raw(data)
                        pub = store.public_server(s)
                        break
        imported.append(pub)

    blob = _json.dumps(servers, sort_keys=True, default=str)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    try:
        from veu.memory import Memory

        Memory().append(
            "mcp.import",
            {
                "subject": subject,
                "count": len(imported),
                "hash": digest[:32],
                "ids": [s.get("id") for s in imported],
            },
            sink="audit",
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": bool(imported) and not errors,
        "imported": imported,
        "count": len(imported),
        "live": 0,
        "errors": errors,
        "hash": digest[:24],
        "message": (
            f"Importados {len(imported)} MCP como não verificados"
            + (f" · recusados: {'; '.join(errors)}" if errors else "")
            + " — aprove e rode o probe em modo guiado"
        ),
    }


def approve_server(server_id: str) -> dict[str, Any]:
    data = store.load_raw()
    found = None
    for i, s in enumerate(data.get("servers") or []):
        if s.get("id") != server_id:
            continue
        s = dict(s)
        s["verified"] = True
        s["status"] = s.get("status") if s.get("status") == "live" else "ready"
        s["updated_at"] = time.time()
        data["servers"][i] = s
        store.save_raw(data)
        found = store.public_server(s)
        break
    if not found:
        return {"ok": False, "error": "não encontrado"}
    return {"ok": True, "server": found}


def delete(server_id: str) -> dict[str, Any]:
    ok = store.delete_server(server_id)
    return {"ok": ok, "error": "" if ok else "não encontrado"}


def call_tool(server_id: str, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    row = store.get_raw(server_id)
    if not row:
        return {"ok": False, "error": "servidor MCP não encontrado"}
    env = store.resolve_env(row)
    headers = store.resolve_headers(row)
    client = open_client(row, env, headers)
    try:
        if hasattr(client, "__enter__"):
            client.__enter__()  # type: ignore[misc]
        client.initialize()
        result = client.call_tool(tool, arguments or {})
        return {"ok": True, "result": result, "server": row["id"], "tool": tool}
    except McpError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}
    finally:
        if hasattr(client, "close"):
            try:
                client.close()  # type: ignore[misc]
            except Exception:
                pass


def sync_registry(registry: Registry) -> None:
    """Injeta cada MCP cadastrado como Connector no registry."""
    for s in store.list_servers():
        cid = f"mcp:{s['id']}"
        existing = registry.get(cid)
        status = s.get("status") or "ready"
        if status == "error":
            status = "ready"
        caps = [t.get("name") for t in (s.get("tools") or []) if t.get("name")]
        note = (
            f"{s.get('transport')} · {s.get('tool_count', 0)} tools"
            + (f" · {s.get('url')}" if s.get("url") else f" · {s.get('command')}")
        )
        if s.get("last_error"):
            note += f" · {s['last_error'][:80]}"
        conn = Connector(
            id=cid,
            name=f"MCP · {s.get('name') or s['id']}",
            kind=ConnectorKind.MCP,
            surface="mcp",
            status="live" if s.get("status") == "live" else "ready",
            capabilities=caps[:24] or ["tools"],
            notes=note,
        )
        registry._items[cid] = conn  # noqa: SLF001 — registry interno

    # mcp-bus agrega
    bus = registry.get("mcp-bus")
    n = len(store.list_servers())
    live = sum(1 for s in store.list_servers() if s.get("status") == "live")
    if bus:
        bus.status = "live" if live else ("ready" if n else bus.status)
        bus.notes = (
            f"{live}/{n} MCP live — cole JSON em Ajustes → MCP"
            if n
            else "cole JSON (Cursor/Claude) em Ajustes → MCP ou no chat"
        )


def try_import_from_chat(text: str) -> dict[str, Any] | None:
    """Se a mensagem trouxer JSON MCP, importa automaticamente."""
    raw = extract_json_from_text(text)
    if raw is None:
        return None
    lower = text.lower()
    # só auto-importa se parecer pedido de config OU o JSON for o corpo quase todo
    hints = (
        "mcp",
        "conector",
        "liga",
        "ligar",
        "configura",
        "configure",
        "importa",
        "adicionar",
        "mcpservers",
    )
    stripped = text.strip()
    mostly_json = stripped.startswith("{") and (
        "mcpServers" in stripped
        or "command" in stripped
        or '"url"' in stripped
        or "serverUrl" in stripped
    )
    if not (mostly_json or any(h in lower for h in hints)):
        return None
    return import_json(raw, probe_now=True)


def try_preset_from_chat(text: str) -> dict[str, Any] | None:
    """Hugging Face etc. — só nome + token, sem JSON."""
    cfg = detect_preset_config(text)
    if cfg is None:
        return None
    if cfg.get("_need_token"):
        return {
            "ok": False,
            "status": "need_token",
            "message": cfg.get("hint")
            or f"Pra ligar {cfg.get('name')}, manda o token na mensagem.",
            "actions": [],
        }
    # não ecoar token na mensagem
    result = import_json(
        {
            "mcpServers": {
                cfg["id"]: {
                    "url": cfg.get("url"),
                    "transport": cfg.get("transport"),
                    "headers": cfg.get("headers") or {},
                    "env": cfg.get("env") or {},
                    "command": cfg.get("command") or "",
                    "args": cfg.get("args") or [],
                    "notes": cfg.get("notes") or "",
                    "name": cfg.get("name"),
                }
            }
        },
        probe_now=True,
    )
    live = result.get("live") or 0
    name = cfg.get("name") or cfg["id"]
    tools_n = 0
    for s in result.get("imported") or []:
        tools_n = max(tools_n, int(s.get("tool_count") or 0))
    err = "; ".join(result.get("errors") or [])
    if live:
        msg = (
            f"Liguei o MCP {name} automaticamente"
            + (f" · {tools_n} tools" if tools_n else "")
            + ". Pode pedir, por exemplo: busque modelos Qwen no Hugging Face."
        )
    else:
        msg = (
            f"Cadastrei o MCP {name}, mas o probe falhou"
            + (f": {err}" if err else ".")
            + " Confira o token (hf_…) e tente de novo."
        )
    return {
        "ok": bool(live),
        "status": "mcp",
        "message": msg,
        "mcp": result,
        "actions": [],
    }


def _mcp_text_result(call: dict[str, Any]) -> str:
    if not call.get("ok"):
        return call.get("error") or "falha na tool MCP"
    result = call.get("result")
    if isinstance(result, dict):
        parts = []
        for c in result.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(str(c.get("text") or ""))
        if parts:
            return "\n".join(parts).strip()
        return str(result)[:2000]
    if isinstance(result, str):
        return result
    return str(result)[:2000]


def _extract_search_query(intent: str) -> str:
    """Tira ruído e deixa o termo de busca do hub."""
    import re

    t = intent.strip()
    for pat in (
        r"(?i)\b(no|do|da|em|pelo|pela)?\s*(hugging\s*face|huggingface|hf|hub)\b",
        r"(?i)\b(pesquise|pesquisa|busque|busca|procure|procura|ache|encontre|liste|lista)\b",
        r"(?i)\b(modelos?|datasets?|spaces?|reposit[oó]rios?|repos?)\b",
        r"(?i)\b(trending|em alta|populares?|de)\b",
        r"(?i)\b(mcp|tool|tools|ferramentas?)\b",
    ):
        t = re.sub(pat, " ", t)
    t = re.sub(r"\s+", " ", t).strip(" .,;:-")
    return t or intent.strip()[:80]


def try_run_huggingface(intent: str) -> dict[str, Any] | None:
    """Conversa natural → tool HF (já configurada)."""
    lower = intent.lower()
    hf_hints = (
        "huggingface",
        "hugging face",
        "hf.co",
        " no hf",
        "do hf",
        " no hub",
        "do hub",
        "modelo",
        "modelos",
        "dataset",
        "space",
        "spaces",
        "whisper",
        "qwen",
        "llama",
        "mistral",
        "asr",
        "tts",
        "diffusion",
    )
    if not any(h in lower for h in hf_hints):
        # ainda assim: "quem sou eu" só se MCP HF existir e frase bater
        if not any(k in lower for k in ("quem sou", "whoami", "minha conta hf", "conta no hf")):
            return None

    servers = {s["id"]: s for s in store.list_servers()}
    hf = servers.get("huggingface")
    if not hf:
        return None
    if hf.get("status") != "live":
        pr = probe("huggingface")
        if not pr.get("ok"):
            return {
                "ok": False,
                "status": "mcp",
                "message": (
                    "Hugging Face está cadastrado mas offline. "
                    "Diga “testa o mcp huggingface” ou confira o token em Ajustes → MCP."
                ),
                "actions": [],
            }

    # quem sou eu
    if any(
        k in lower
        for k in ("quem sou", "whoami", "minha conta", "autenticad", "logado no hf")
    ):
        call = call_tool("huggingface", "hf_whoami", {})
        text = _mcp_text_result(call)
        return {
            "ok": bool(call.get("ok")),
            "status": "mcp",
            "message": text[:3500],
            "mcp": {"call": call},
            "actions": [],
        }

    # detalhes de um repo owner/name
    import re

    m = re.search(r"\b([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*)\b", intent)
    if m and any(k in lower for k in ("detalhe", "detalhes", "info", "sobre o", "abre o repo")):
        repo_id = f"{m.group(1)}/{m.group(2)}"
        call = call_tool(
            "huggingface",
            "hub_repo_details",
            {"repo_ids": [repo_id]},
        )
        if not call.get("ok"):
            call = call_tool(
                "huggingface",
                "hub_repo_details",
                {"repo_id": repo_id},
            )
        text = _mcp_text_result(call)
        return {
            "ok": bool(call.get("ok")),
            "status": "mcp",
            "message": text[:3500],
            "mcp": {"call": call},
            "actions": [],
        }

    # busca / trending / listar modelos
    wants_search = any(
        k in lower
        for k in (
            "pesquis",
            "busc",
            "procur",
            "encontr",
            "trending",
            "em alta",
            "modelos",
            "modelo",
            "dataset",
            "space",
            "liste",
            "lista",
            "ache",
        )
    )
    if wants_search or any(h in lower for h in ("huggingface", "hugging face", "hf.co")):
        query = _extract_search_query(intent)
        if query.lower() in {"", "huggingface", "hugging face", "hf", "hub", "mcp"}:
            query = "trending"
        args: dict[str, Any] = {"query": query, "limit": 5}
        if "dataset" in lower:
            args["repo_types"] = ["dataset"]
        elif "space" in lower:
            args["repo_types"] = ["space"]
        else:
            args["repo_types"] = ["model"]
        call = call_tool("huggingface", "hub_repo_search", args)
        text = _mcp_text_result(call)
        if call.get("ok"):
            header = f"Hugging Face · busca “{query}”\n\n"
            return {
                "ok": True,
                "status": "mcp",
                "message": (header + text)[:3500],
                "mcp": {"call": call},
                "actions": [],
            }
        return {
            "ok": False,
            "status": "mcp",
            "message": f"Falhou a busca no Hugging Face: {text}",
            "mcp": {"call": call},
            "actions": [],
        }

    return None


def chat_plan_or_run(intent: str) -> dict[str, Any]:
    """Usado pelo runtime: preset/token, JSON, ou listar/chamar tools."""
    preset = try_preset_from_chat(intent)
    if preset is not None:
        return preset

    auto = try_import_from_chat(intent)
    if auto is not None:
        names = ", ".join(s.get("name") or s["id"] for s in auto.get("imported") or [])
        return {
            "ok": auto.get("ok", True),
            "status": "mcp",
            "message": (
                f"Configurei o MCP automaticamente: {names or 'ok'}. "
                + (auto.get("message") or "")
            ).strip(),
            "mcp": auto,
            "actions": [],
        }

    # Uso real das tools (HF etc.) — não só listar
    ran = try_run_huggingface(intent)
    if ran is not None:
        return ran

    servers = store.list_servers()
    if not servers:
        return {
            "ok": False,
            "status": "need_json",
            "message": (
                "Nenhum MCP ainda. Diga o serviço + token (ex.: “liga o MCP do "
                "Hugging Face, token hf_…”) ou cole o JSON em Ajustes → MCP."
            ),
            "actions": [],
        }

    lower = intent.lower()
    # listar tools
    if any(k in lower for k in ("lista", "listar", "quais tools", "ferramentas", "tools")):
        lines = []
        for s in servers:
            tools = ", ".join(t.get("name") or "?" for t in (s.get("tools") or [])[:12])
            lines.append(
                f"· {s['name']} ({s['status']}, {s.get('tool_count', 0)} tools)"
                + (f": {tools}" if tools else "")
            )
        return {
            "ok": True,
            "status": "mcp",
            "message": (
                "MCPs ligados:\n"
                + "\n".join(lines)
                + "\n\nComo usar no Chat Véu (não precisa configurar de novo):\n"
                "· “quem sou eu no huggingface”\n"
                "· “pesquise modelos whisper no huggingface”\n"
                "· “detalhes do openai/whisper-large-v3”"
            ),
            "actions": [],
        }

    # probe / re-ligar
    if any(k in lower for k in ("testa", "probe", "reconect", "religa", "re-liga")):
        results = [probe(s["id"]) for s in servers]
        ok_n = sum(1 for r in results if r.get("ok"))
        return {
            "ok": ok_n > 0,
            "status": "mcp",
            "message": f"Probe: {ok_n}/{len(results)} MCP live.",
            "mcp": {"probes": results},
            "actions": [],
        }

    live = [s for s in servers if s.get("status") == "live"]
    names = ", ".join(s["name"] for s in (live or servers)[:6])
    return {
        "ok": True,
        "status": "mcp",
        "message": (
            f"MCP ativos: {names or 'nenhum'}.\n"
            "No Chat Véu você só pede — não tem seletor de modelo pra MCP.\n"
            "Exemplos: “pesquise modelos qwen no huggingface” · "
            "“quem sou eu no huggingface” · “liste as tools do mcp”.\n"
            "ChatGPT/Claude/Grok: use os ícones na zona mente (ou cole API key em Ajustes)."
        ),
        "actions": [],
    }

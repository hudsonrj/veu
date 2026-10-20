"""Persistência de servidores MCP — metadados em data/, secrets no .env."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from veu.subscriptions import resolve_env_file, upsert_env


def _data_root() -> Path:
    env = os.environ.get("VEU_DATA_ROOT")
    root = Path(env) if env else Path.home() / ".veu" / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _data_root() / "mcp_servers.json"


def _mask(secret: str) -> str:
    k = (secret or "").strip()
    if not k:
        return ""
    if len(k) <= 10:
        return "••••"
    return f"{k[:2]}…{k[-2:]}"


def secret_env_name(server_id: str, key: str) -> str:
    sid = re.sub(r"[^A-Za-z0-9]", "_", (server_id or "").strip()).upper().strip("_")
    k = re.sub(r"[^A-Za-z0-9]", "_", (key or "").strip()).upper().strip("_")
    return f"VEU_MCP_{sid}_{k}"


def load_raw() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {"servers": [], "version": 1}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"servers": [], "version": 1}


def save_raw(data: dict[str, Any]) -> None:
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def public_server(row: dict[str, Any]) -> dict[str, Any]:
    env_keys = list((row.get("env_keys") or []))
    header_keys = list((row.get("header_keys") or []))
    env_masked = {}
    for k in env_keys:
        val = os.environ.get(secret_env_name(row["id"], k), "")
        env_masked[k] = _mask(val) if val else ""
    return {
        "id": row["id"],
        "name": row.get("name") or row["id"],
        "transport": row.get("transport") or "http",
        "url": row.get("url") or "",
        "command": row.get("command") or "",
        "args": list(row.get("args") or []),
        "cwd": row.get("cwd"),
        "env_keys": env_keys,
        "header_keys": header_keys,
        "env_masked": env_masked,
        "has_secrets": any(
            bool(os.environ.get(secret_env_name(row["id"], k), "").strip())
            for k in env_keys + header_keys
        ),
        "notes": row.get("notes") or "",
        "status": row.get("status") or "ready",
        "verified": bool(row.get("verified")),
        "last_error": row.get("last_error") or "",
        "last_probe": row.get("last_probe"),
        "tools": list(row.get("tools") or []),
        "tool_count": len(row.get("tools") or []),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def list_servers() -> list[dict[str, Any]]:
    return [public_server(s) for s in load_raw().get("servers") or []]


def get_raw(server_id: str) -> dict[str, Any] | None:
    for s in load_raw().get("servers") or []:
        if s.get("id") == server_id:
            return s
    return None


def resolve_env(row: dict[str, Any]) -> dict[str, str]:
    """Monta env efetivo do processo (valores do .env)."""
    out: dict[str, str] = {}
    for k in row.get("env_keys") or []:
        val = os.environ.get(secret_env_name(row["id"], k), "").strip()
        if val:
            out[str(k)] = val
    return out


def resolve_headers(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in row.get("header_keys") or []:
        val = os.environ.get(secret_env_name(row["id"], f"HDR_{k}"), "").strip()
        if not val:
            val = os.environ.get(secret_env_name(row["id"], k), "").strip()
        if val:
            out[str(k)] = val
    # headers não secretos salvos no json
    for k, v in (row.get("headers_public") or {}).items():
        if v and k not in out:
            out[str(k)] = str(v)
    return out


def upsert_normalized(cfg: dict[str, Any], *, probe: dict[str, Any] | None = None) -> dict[str, Any]:
    """Grava servidor normalizado; secrets de env/headers vão pro .env."""
    now = time.time()
    data = load_raw()
    servers: list[dict[str, Any]] = list(data.get("servers") or [])
    sid = cfg["id"]
    existing = next((s for s in servers if s.get("id") == sid), None)

    env_in = dict(cfg.get("env") or {})
    headers_in = dict(cfg.get("headers") or {})
    env_keys = sorted(env_in.keys())
    header_keys = sorted(headers_in.keys())
    headers_public: dict[str, str] = {}

    env_path = resolve_env_file()
    env_updates: dict[str, str] = {}
    for k, v in env_in.items():
        if v:
            env_updates[secret_env_name(sid, k)] = str(v)

    for k, v in headers_in.items():
        val = str(v)
        # Authorization / token → .env; demais podem ficar no json
        if re.search(r"(auth|token|key|secret|bearer)", k, re.I) or len(val) > 40:
            env_updates[secret_env_name(sid, f"HDR_{k}")] = val
        else:
            headers_public[k] = val

    # Hugging Face: Bearer do MCP também vira HF_TOKEN pro chat HybridLLM
    if sid in {"huggingface", "hf"} or "huggingface" in str(cfg.get("url") or "").lower():
        for k, v in list(headers_in.items()) + list(env_in.items()):
            val = str(v or "").strip()
            m = re.search(r"(hf_[A-Za-z0-9]{20,})", val)
            if m:
                env_updates["HF_TOKEN"] = m.group(1)
                env_updates["HUGGINGFACE_HUB_TOKEN"] = m.group(1)
                break
            if val.startswith("Bearer "):
                tok = val[7:].strip()
                if tok.startswith("hf_"):
                    env_updates["HF_TOKEN"] = tok
                    env_updates["HUGGINGFACE_HUB_TOKEN"] = tok
                    break

    if env_updates:
        upsert_env(env_path, env_updates)
        # hidrata processo atual
        for k, v in env_updates.items():
            os.environ[k] = v

    row = {
        "id": sid,
        "name": cfg.get("name") or sid,
        "transport": cfg.get("transport") or "http",
        "url": cfg.get("url") or "",
        "command": cfg.get("command") or "",
        "args": list(cfg.get("args") or []),
        "cwd": cfg.get("cwd"),
        "env_keys": env_keys,
        "header_keys": header_keys,
        "headers_public": headers_public,
        "notes": cfg.get("notes") or "",
        "status": (probe or {}).get("status") or (existing or {}).get("status") or "ready",
        "last_error": (probe or {}).get("error") or "",
        "last_probe": (probe or {}).get("probe") or (existing or {}).get("last_probe"),
        "tools": (probe or {}).get("tools") or (existing or {}).get("tools") or [],
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }

    if existing:
        servers = [row if s.get("id") == sid else s for s in servers]
    else:
        if not sid or sid == "mcp":
            row["id"] = f"mcp-{uuid.uuid4().hex[:8]}"
            sid = row["id"]
        servers.append(row)

    data["servers"] = servers
    data["version"] = 1
    save_raw(data)
    return public_server(row)


def update_probe(server_id: str, *, ok: bool, tools: list[dict[str, Any]] | None = None, error: str = "", probe: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = load_raw()
    servers = list(data.get("servers") or [])
    found = None
    for i, s in enumerate(servers):
        if s.get("id") != server_id:
            continue
        s = dict(s)
        s["status"] = "live" if ok else "error"
        s["last_error"] = error or ""
        s["tools"] = tools if tools is not None else s.get("tools") or []
        s["last_probe"] = probe or {"ok": ok, "at": time.time()}
        s["updated_at"] = time.time()
        servers[i] = s
        found = s
        break
    if not found:
        return None
    data["servers"] = servers
    save_raw(data)
    return public_server(found)


def delete_server(server_id: str) -> bool:
    data = load_raw()
    before = list(data.get("servers") or [])
    after = [s for s in before if s.get("id") != server_id]
    if len(after) == len(before):
        return False
    data["servers"] = after
    save_raw(data)
    return True

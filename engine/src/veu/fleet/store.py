"""Cadastro de servidores do Hudson — metadados em data/, segredo no .env do kernel.

Só hosts que ele cadastra. Senha nunca volta em claro na API (máscara como assinaturas).
"""

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
    return _data_root() / "servers.json"


def _mask(secret: str) -> str:
    k = (secret or "").strip()
    if not k:
        return ""
    if len(k) <= 10:
        return "••••"
    return f"{k[:2]}…{k[-2:]}"


def secret_env_name(server_id: str) -> str:
    """VEU_SRV_<HEX>_PASSWORD — id srv-ab12… → VEU_SRV_AB12…_PASSWORD."""
    slug = re.sub(r"[^A-Za-z0-9]", "_", (server_id or "").strip()).upper().strip("_")
    if slug.startswith("SRV_"):
        slug = slug[4:]
    if not slug:
        raise ValueError("id de servidor inválido")
    return f"VEU_SRV_{slug}_PASSWORD"


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


def _password_for(server_id: str) -> str:
    return os.environ.get(secret_env_name(server_id), "").strip()


def public_server(row: dict[str, Any], *, reveal: bool = False) -> dict[str, Any]:
    """Vista pública. Por padrão mascara host/IP/user e NÃO expõe secret_env."""
    from veu.auth import mask_host, mask_username

    sid = row["id"]
    secret = _password_for(sid)
    has_secret = bool(secret)
    host = (row.get("host") or "").strip()
    username = (row.get("username") or "root").strip()
    port = int(row.get("port") or 22)
    probe = row.get("last_probe")
    # Nunca devolver IP cru do probe sem reveal
    safe_probe = None
    if isinstance(probe, dict):
        safe_probe = {
            "ok": probe.get("ok"),
            "at": probe.get("at"),
            "hostname": probe.get("hostname") if reveal else None,
            "ip": probe.get("ip") if reveal else mask_host(str(probe.get("ip") or "")),
            "error": (probe.get("error") or "")[:120] if reveal else "",
        }
    base: dict[str, Any] = {
        "id": sid,
        "name": row.get("name") or (host if reveal else mask_host(host) or "servidor"),
        "port": port,
        "has_secret": has_secret,
        "secret_masked": "••••" if has_secret else "",
        "notes": row.get("notes") or "" if reveal else "",
        "last_probe": safe_probe,
        "last_status": row.get("last_status") or "unknown",
        "last_error": (row.get("last_error") or "") if reveal else "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "revealed": bool(reveal),
    }
    if reveal:
        base.update(
            {
                "host": host,
                "username": username,
                # secret_env só com reveal explícito — ainda assim só o NOME da var
                "secret_env": secret_env_name(sid),
            }
        )
    else:
        base.update(
            {
                "host": mask_host(host),
                "host_masked": mask_host(host),
                "username": mask_username(username),
                "username_masked": mask_username(username),
            }
        )
    return base


def list_servers(*, reveal: bool = False) -> list[dict[str, Any]]:
    return [public_server(s, reveal=reveal) for s in load_raw().get("servers") or []]


def get_raw(server_id: str) -> dict[str, Any] | None:
    for s in load_raw().get("servers") or []:
        if s.get("id") == server_id:
            return s
    return None


def require_registered(server_id: str) -> dict[str, Any]:
    """Só opera em host que o Hudson cadastrou — sem isso, para."""
    row = get_raw(server_id)
    if row is None:
        raise ValueError(
            "servidor não cadastrado — informe host/usuário/senha em Ajustes → servidores"
        )
    host = (row.get("host") or "").strip()
    if not host:
        raise ValueError("host em falta neste cadastro — edite em Ajustes → servidores")
    return row


def upsert(
    *,
    server_id: str | None,
    name: str,
    host: str,
    port: int,
    username: str,
    password: str | None,
    notes: str | None = None,
    clear_secret: bool = False,
) -> dict[str, Any]:
    host = (host or "").strip()
    if not host:
        raise ValueError("host obrigatório — informe o IP ou hostname do seu servidor")
    # Sem varredura: host vem só do formulário do Hudson
    if re.search(r"[\s;|&`$]", host):
        raise ValueError("host inválido")

    data = load_raw()
    servers: list[dict[str, Any]] = list(data.get("servers") or [])
    now = time.time()
    row: dict[str, Any] | None = None

    if server_id:
        for s in servers:
            if s.get("id") == server_id:
                row = s
                break
        if row is None:
            raise ValueError("servidor não encontrado")
    else:
        row = {
            "id": f"srv-{uuid.uuid4().hex[:10]}",
            "created_at": now,
        }
        servers.append(row)

    row["name"] = (name or host).strip()
    row["host"] = host
    row["port"] = int(port or 22)
    if row["port"] < 1 or row["port"] > 65535:
        raise ValueError("porta inválida")
    row["username"] = (username or "root").strip() or "root"
    row["notes"] = notes if notes is not None else row.get("notes") or ""
    row["updated_at"] = now

    env_key = secret_env_name(row["id"])
    env_path = resolve_env_file()
    if clear_secret:
        upsert_env(env_path, {env_key: ""})
    elif password is not None and password.strip():
        upsert_env(env_path, {env_key: password.strip()})
    elif not _password_for(row["id"]):
        # Novo cadastro sem senha — aceita metadados, mas avisa na resposta pública
        pass

    data["servers"] = servers
    save_raw(data)
    return public_server(row)


def delete(server_id: str) -> bool:
    data = load_raw()
    before = len(data.get("servers") or [])
    data["servers"] = [s for s in (data.get("servers") or []) if s.get("id") != server_id]
    if len(data["servers"]) == before:
        return False
    save_raw(data)
    try:
        upsert_env(resolve_env_file(), {secret_env_name(server_id): ""})
    except ValueError:
        pass
    return True


def credentials(server_id: str) -> tuple[dict[str, Any], str]:
    """(row, password) — uso interno SSH. Nunca exposto na API."""
    row = require_registered(server_id)
    secret = _password_for(server_id)
    if not secret:
        raise ValueError(
            f"senha em falta — grave em Ajustes → servidores "
            f"(env {secret_env_name(server_id)} no .env do kernel)"
        )
    return row, secret


def touch_probe(
    server_id: str, *, status: str, error: str = "", probe: dict[str, Any] | None = None
) -> None:
    data = load_raw()
    for s in data.get("servers") or []:
        if s.get("id") == server_id:
            s["last_status"] = status
            s["last_error"] = (error or "")[:400]
            s["last_probe"] = {"ts": time.time(), **(probe or {})}
            s["updated_at"] = time.time()
            break
    save_raw(data)

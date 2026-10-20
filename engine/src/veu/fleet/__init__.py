"""Frota Véu — servidores que o Hudson cadastra em Ajustes.

Escopo: cadastrar host, guardar senha no .env (mascarada na UI),
testar conexão, listar sites/serviços, ver status de manutenção.
Não varre rede. Não entra em host não cadastrado.
"""

from __future__ import annotations

from typing import Any

from veu.fleet import ssh as _ssh
from veu.fleet import store as _store


def list_servers(*, reveal: bool = False) -> list[dict[str, Any]]:
    return _store.list_servers(reveal=reveal)


def upsert_server(**kwargs: Any) -> dict[str, Any]:
    return _store.upsert(**kwargs)


def delete_server(server_id: str) -> bool:
    return _store.delete(server_id)


def _session(server_id: str) -> tuple[dict[str, Any], Any]:
    row, password = _store.credentials(server_id)
    client = _ssh.connect(
        host=str(row["host"]),
        port=int(row.get("port") or 22),
        username=str(row.get("username") or "root"),
        password=password,
    )
    return row, client


def test_connection(server_id: str) -> dict[str, Any]:
    """Testa SSH no host cadastrado."""
    row = _store.require_registered(server_id)
    try:
        _, client = _session(server_id)
        try:
            info = _ssh.probe(client)
        finally:
            client.close()
        status = "ok" if info.get("ok") else "error"
        _store.touch_probe(
            server_id,
            status=status,
            error=str(info.get("error") or ""),
            probe={k: info.get(k) for k in ("hostname", "uname", "uptime", "mem", "disk", "ip", "ms")},
        )
        return {"ok": bool(info.get("ok")), "server": _store.public_server(row), "probe": info}
    except Exception as e:  # noqa: BLE001 — devolve erro amigável à UI
        msg = str(e)
        _store.touch_probe(server_id, status="error", error=msg)
        return {
            "ok": False,
            "server": _store.public_server(row),
            "error": msg,
        }


def sites(server_id: str) -> dict[str, Any]:
    """Lista sites/serviços do host cadastrado."""
    row = _store.require_registered(server_id)
    _, client = _session(server_id)
    try:
        data = _ssh.list_sites(client)
    finally:
        client.close()
    return {"ok": bool(data.get("ok")), "server": _store.public_server(row), **data}


def maintenance(server_id: str) -> dict[str, Any]:
    """Status de manutenção (leitura) do host cadastrado."""
    row = _store.require_registered(server_id)
    _, client = _session(server_id)
    try:
        data = _ssh.maintenance_status(client)
    finally:
        client.close()
    return {"ok": bool(data.get("ok")), "server": _store.public_server(row), **data}


def _ssh_public(
    *,
    fleet_id: str | None,
    host: str | None,
    port: int,
    username: str | None,
    has_secret: bool,
    last_status: Any = None,
    last_probe: Any = None,
    needs_register: bool = False,
    reveal: bool = False,
) -> dict[str, Any]:
    from veu.auth import mask_host, mask_username

    host_s = (host or "").strip()
    user_s = (username or "root").strip()
    port_i = int(port or 22)
    out: dict[str, Any] = {
        "fleet_id": fleet_id,
        "port": port_i,
        "has_secret": bool(has_secret),
        "last_status": last_status,
        "needs_register": bool(needs_register),
        "revealed": bool(reveal),
    }
    if reveal:
        out.update(
            {
                "host": host_s,
                "username": user_s,
                "last_probe": last_probe,
                "command": f"ssh -p {port_i} {user_s}@{host_s}" if host_s else None,
            }
        )
    else:
        out.update(
            {
                "host": mask_host(host_s),
                "username": mask_username(user_s),
                "last_probe": None,
                "command": None,
                "command_hint": "SSH disponível — use o botão Conectar (sessão autenticada)",
            }
        )
    return out


def board(*, reveal: bool = False) -> dict[str, Any]:
    """Ícones de servidores: inventário live.json + frota cadastrada (SSH)."""
    # Matching interno usa dados reais; resposta aplica máscara.
    registered_raw = list(_store.load_raw().get("servers") or [])
    registered_pub = {
        str(s["id"]): _store.public_server(s, reveal=True) for s in registered_raw
    }
    try:
        from veu.bridges import control_live

        inv = control_live.servers_inventory()
    except Exception as exc:  # noqa: BLE001
        inv = {"ok": False, "servers": [], "error": str(exc)}

    live_servers = list(inv.get("servers") or [])
    used_fleet: set[str] = set()

    def _match_fleet(live: dict[str, Any]) -> dict[str, Any] | None:
        host_hint = str((live.get("ssh_hint") or {}).get("host") or "").strip()
        hostname = str(live.get("hostname") or "").lower()
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in registered_raw:
            pub = registered_pub[str(row["id"])]
            rhost = str(row.get("host") or "")
            rname = str(row.get("name") or "").lower()
            probe = row.get("last_probe") if isinstance(row.get("last_probe"), dict) else {}
            probe_host = str(probe.get("hostname") or "").lower()
            probe_ip = str(probe.get("ip") or "")
            score = 0
            if host_hint and rhost == host_hint:
                score = 100
            elif host_hint and probe_ip == host_hint:
                score = 80
            elif hostname and (hostname in rname or hostname == probe_host):
                score = 60
            elif live.get("id") == "contabo" and (
                rhost in {"169.58.19.232", "127.0.0.1", "localhost"}
                or probe_ip == "169.58.19.232"
                or probe_host == "vmi3441452"
            ):
                score = 50
            if not score:
                continue
            if pub.get("has_secret"):
                score += 15
            scored.append((score, row))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    cards: list[dict[str, Any]] = []
    for live in live_servers:
        fleet_row = _match_fleet(live)
        ssh = None
        if fleet_row:
            used_fleet.add(str(fleet_row["id"]))
            pub = registered_pub[str(fleet_row["id"])]
            ssh = _ssh_public(
                fleet_id=str(fleet_row["id"]),
                host=str(fleet_row.get("host") or ""),
                port=int(fleet_row.get("port") or 22),
                username=str(fleet_row.get("username") or "root"),
                has_secret=bool(pub.get("has_secret")),
                last_status=pub.get("last_status"),
                last_probe=pub.get("last_probe"),
                reveal=reveal,
            )
        else:
            hint = live.get("ssh_hint") or {}
            if hint.get("host"):
                ssh = _ssh_public(
                    fleet_id=None,
                    host=str(hint.get("host") or ""),
                    port=int(hint.get("port") or 22),
                    username=str(hint.get("username") or "root"),
                    has_secret=False,
                    needs_register=True,
                    reveal=reveal,
                )
        # Não vazar ssh_hint cru no card live
        live_safe = dict(live)
        if not reveal and "ssh_hint" in live_safe:
            live_safe["ssh_hint"] = {"available": bool((live.get("ssh_hint") or {}).get("host"))}
        cards.append(
            {
                **live_safe,
                "ssh": ssh,
                "kind": "live",
            }
        )

    # frota cadastrada sem inventário live (evita duplicar mesmo host/IP)
    linked_hosts = {
        str((c.get("ssh") or {}).get("host") or "")
        for c in cards
        if (c.get("ssh") or {}).get("host")
    }
    linked_hostnames = {
        str(c.get("hostname") or "").lower()
        for c in cards
        if c.get("hostname")
    }
    for row in registered_raw:
        rid = str(row.get("id") or "")
        if rid in used_fleet:
            continue
        rhost = str(row.get("host") or "")
        if rhost and rhost in linked_hosts:
            continue
        probe = row.get("last_probe") if isinstance(row.get("last_probe"), dict) else {}
        if str(probe.get("ip") or "") in linked_hosts:
            continue
        if str(probe.get("hostname") or "").lower() in linked_hostnames:
            continue
        if "contabo" in str(row.get("name") or "").lower() and any(
            c.get("id") == "contabo" for c in cards
        ):
            continue
        pub = registered_pub[rid]
        cards.append(
            {
                "id": rid,
                "hostname": row.get("name") or (rhost if reveal else pub.get("host")),
                "provider": "cadastrado",
                "os": "",
                "role": (row.get("notes") or "host na frota Véu") if reveal else "host na frota Véu",
                "domains": [],
                "apps": [],
                "apps_up": 0,
                "apps_total": 0,
                "glyph": "S",
                "hue": "#A8B4C0",
                "source": "fleet",
                "kind": "fleet",
                "ssh": _ssh_public(
                    fleet_id=rid,
                    host=rhost,
                    port=int(row.get("port") or 22),
                    username=str(row.get("username") or "root"),
                    has_secret=bool(pub.get("has_secret")),
                    last_status=pub.get("last_status"),
                    last_probe=pub.get("last_probe"),
                    reveal=reveal,
                ),
            }
        )

    return {
        "ok": True,
        "available": True,
        "revealed": bool(reveal),
        "updatedAt": inv.get("updatedAt"),
        "fleetHealth": inv.get("fleetHealth"),
        "fleetNotes": inv.get("fleetNotes") or [],
        "servers": cards,
        "counts": {
            "total": len(cards),
            "with_ssh": sum(1 for c in cards if (c.get("ssh") or {}).get("fleet_id")),
            "live": sum(1 for c in cards if c.get("kind") == "live"),
        },
    }


def ssh_launch(server_id: str, *, reveal: bool = False) -> dict[str, Any]:
    """Prepara SSH: comando + probe rápido se houver senha cadastrada.

    Comando/host reais só com reveal=True (sessão já autenticada pelo middleware).
    """
    board_data = board(reveal=True)  # matching interno
    card = next((c for c in board_data.get("servers") or [] if c.get("id") == server_id), None)
    if not card:
        try:
            row = _store.require_registered(server_id)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        cmd = f"ssh -p {row.get('port') or 22} {row.get('username') or 'root'}@{row['host']}"
        from veu.auth import mask_host

        return {
            "ok": True,
            "command": cmd if reveal else None,
            "fleet_id": server_id,
            "host": row["host"] if reveal else mask_host(str(row["host"])),
            "has_secret": True,
            "revealed": bool(reveal),
            "hint": "abra o terminal do host e rode o comando, ou use o botão SSH no SO",
        }

    ssh = card.get("ssh") or {}
    cmd = ssh.get("command")
    if not cmd:
        return {
            "ok": False,
            "error": "sem host SSH — cadastre este servidor em Ajustes → servidores",
            "server": {"id": card.get("id"), "hostname": card.get("hostname")},
        }
    from veu.auth import mask_host

    out: dict[str, Any] = {
        "ok": True,
        "command": cmd if reveal else None,
        "fleet_id": ssh.get("fleet_id"),
        "host": ssh.get("host") if reveal else mask_host(str(ssh.get("host") or "")),
        "has_secret": bool(ssh.get("has_secret")),
        "needs_register": bool(ssh.get("needs_register")),
        "revealed": bool(reveal),
        "server": {
            "id": card.get("id"),
            "hostname": card.get("hostname"),
            "provider": card.get("provider"),
            "apps_total": card.get("apps_total"),
        },
        "hint": (
            "host nativo: abre terminal com o comando"
            if ssh.get("has_secret") or ssh.get("host")
            else "cadastre a senha em Ajustes para probe SSH"
        ),
    }
    # probe se senha cadastrada — resultado de probe também mascara se !reveal
    fid = ssh.get("fleet_id")
    if fid and ssh.get("has_secret"):
        try:
            probe = test_connection(str(fid))
            raw_probe = probe.get("probe") if isinstance(probe.get("probe"), dict) else {}
            if reveal:
                out["probe"] = raw_probe
            else:
                out["probe"] = {
                    "ok": raw_probe.get("ok"),
                    "ms": raw_probe.get("ms"),
                    "hostname": None,
                    "ip": mask_host(str(raw_probe.get("ip") or "")),
                }
            out["probe_ok"] = probe.get("ok")
        except Exception as e:  # noqa: BLE001
            out["probe_ok"] = False
            out["probe_error"] = str(e) if reveal else "probe falhou"
    return out

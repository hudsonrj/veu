"""SSH só em hosts cadastrados — testar, listar sites/serviços, status de manutenção.

Somente leitura / inspeção. Sem exec arbitrário, sem reload, sem exploit.
"""

from __future__ import annotations

import time
from typing import Any

try:
    import paramiko
except ImportError:  # pragma: no cover
    paramiko = None  # type: ignore[assignment]


def _require_paramiko() -> None:
    if paramiko is None:
        raise RuntimeError(
            "paramiko não instalado no kernel — pip install paramiko no venv do Véu"
        )


def connect(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    timeout: float = 12.0,
) -> Any:
    """Abre SSH no host informado (já validado pelo store)."""
    _require_paramiko()
    host = (host or "").strip()
    if not host:
        raise ValueError("host em falta")
    if not (password or "").strip():
        raise ValueError("senha em falta")

    client = paramiko.SSHClient()
    # Hosts do Hudson — aceita chave do servidor na primeira conexão (mesmo padrão do host atual)
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=int(port or 22),
        username=username or "root",
        password=password,
        timeout=timeout,
        allow_agent=False,
        look_for_keys=False,
        banner_timeout=timeout,
        auth_timeout=timeout,
    )
    return client


def exec_readonly(client: Any, command: str, *, timeout: float = 45.0) -> dict[str, Any]:
    """Executa comando de inspeção já fixo no código — não aceita comando do cliente HTTP."""
    started = time.time()
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    try:
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
    finally:
        stdin.close()
    return {
        "ok": code == 0,
        "exit_code": code,
        "stdout": out[-12000:],
        "stderr": err[-4000:],
        "ms": int((time.time() - started) * 1000),
    }


def probe(client: Any) -> dict[str, Any]:
    """Teste de conexão + info básica do host."""
    script = r"""
set -e
echo HOST=$(hostname)
echo UNAME=$(uname -srm)
echo UPTIME=$(uptime -p 2>/dev/null || uptime | head -c 120)
echo MEM=$(free -h 2>/dev/null | awk '/Mem:/{print $3"/"$2}' || echo n/a)
echo DISK=$(df -h / | awk 'NR==2{print $3"/"$2" "$5}')
echo IP=$(hostname -I 2>/dev/null | awk '{print $1}')
"""
    r = exec_readonly(client, script, timeout=20)
    info: dict[str, str] = {}
    for line in (r.get("stdout") or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip().lower()] = v.strip()
    return {
        "ok": r["ok"],
        "hostname": info.get("host"),
        "uname": info.get("uname"),
        "uptime": info.get("uptime"),
        "mem": info.get("mem"),
        "disk": info.get("disk"),
        "ip": info.get("ip"),
        "ms": r["ms"],
        "error": "" if r["ok"] else (r.get("stderr") or "teste de conexão falhou"),
    }


def list_sites(client: Any) -> dict[str, Any]:
    """Lista vhosts / serviços publicados neste host (só leitura de configs locais)."""
    script = r"""
echo '###CADDY###'
if [ -f /etc/caddy/Caddyfile ]; then
  grep -E '^[a-zA-Z0-9*.-]+\s*\{|^[a-zA-Z0-9*.-]+\s*$' /etc/caddy/Caddyfile 2>/dev/null \
    | sed 's/[ {].*//' | grep -E '\.' | sort -u | head -80
fi
echo '###NGINX###'
ls /etc/nginx/sites-enabled 2>/dev/null | head -40
grep -RhoE 'server_name\s+[^;]+' /etc/nginx/sites-enabled 2>/dev/null \
  | sed 's/server_name//' | tr ' ' '\n' | grep -E '\.' | sort -u | head -40
echo '###APACHE###'
ls /etc/apache2/sites-enabled 2>/dev/null | head -20
echo '###DOCKER###'
docker ps --format '{{.Names}}\t{{.Ports}}\t{{.Status}}' 2>/dev/null | head -40
echo '###LISTEN###'
ss -lntp 2>/dev/null | grep -E ':80 |:443 |:8080|:8820|:8821' | head -30 || true
echo '###SERVICES###'
for s in caddy nginx apache2 docker veu-kernel veu-desktop; do
  st=$(systemctl is-active "$s" 2>/dev/null || echo n/a)
  echo "$s=$st"
done
"""
    r = exec_readonly(client, script, timeout=30)
    text = r.get("stdout") or ""
    sections: dict[str, list[str]] = {
        "caddy": [],
        "nginx": [],
        "apache": [],
        "docker": [],
        "listen": [],
        "services": [],
    }
    cur = None
    for line in text.splitlines():
        if line.startswith("###") and line.endswith("###"):
            cur = line.strip("#").lower()
            continue
        if not cur or not line.strip():
            continue
        if cur in sections:
            sections[cur].append(line.strip())

    sites: list[dict[str, str]] = []
    for host in sections["caddy"]:
        if host and not host.startswith("#"):
            sites.append({"name": host, "source": "caddy", "kind": "vhost"})
    for host in sections["nginx"]:
        if "." in host and " " not in host:
            sites.append({"name": host, "source": "nginx", "kind": "vhost"})
        elif host and "." not in host:
            sites.append({"name": host, "source": "nginx", "kind": "site-file"})
    for line in sections["docker"]:
        parts = line.split("\t")
        sites.append(
            {
                "name": parts[0] if parts else line,
                "source": "docker",
                "kind": "container",
                "detail": parts[1] if len(parts) > 1 else "",
                "status": parts[2] if len(parts) > 2 else "",
            }
        )

    services: dict[str, str] = {}
    for line in sections["services"]:
        if "=" in line:
            k, v = line.split("=", 1)
            services[k.strip()] = v.strip()

    seen: set[str] = set()
    uniq: list[dict[str, str]] = []
    for s in sites:
        key = f"{s.get('source')}:{s.get('name')}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)

    return {
        "ok": r["ok"] or bool(uniq) or bool(services),
        "sites": uniq,
        "services": services,
        "listen": sections["listen"][:30],
        "ms": r["ms"],
        "raw_error": r.get("stderr") or "",
    }


def maintenance_status(client: Any) -> dict[str, Any]:
    """Status de manutenção (só leitura) — load, disco, updates, serviços Véu."""
    script = r"""
echo '###UPTIME###'
uptime
echo '###MEM###'
free -h | head -2
echo '###DISK###'
df -h / | tail -1
echo '###UPDATES###'
(apt-get -s upgrade 2>/dev/null | grep -E '^[0-9]+ upgraded' || echo 'apt n/a')
echo '###VEU###'
systemctl is-active veu-kernel veu-desktop caddy 2>/dev/null || true
echo '###HEALTH###'
curl -sS -m 3 http://127.0.0.1:8821/health 2>/dev/null || echo 'kernel health n/a'
"""
    r = exec_readonly(client, script, timeout=45)
    text = r.get("stdout") or ""
    sections: dict[str, list[str]] = {
        "uptime": [],
        "mem": [],
        "disk": [],
        "updates": [],
        "veu": [],
        "health": [],
    }
    cur = None
    for line in text.splitlines():
        if line.startswith("###") and line.endswith("###"):
            cur = line.strip("#").lower()
            continue
        if not cur:
            continue
        if cur in sections:
            sections[cur].append(line.rstrip())

    veu_units = [x for x in sections["veu"] if x.strip()]
    return {
        "ok": True,
        "uptime": " ".join(sections["uptime"]).strip(),
        "mem": "\n".join(sections["mem"]).strip(),
        "disk": " ".join(sections["disk"]).strip(),
        "updates": " ".join(sections["updates"]).strip(),
        "veu_units": veu_units,
        "health_raw": "\n".join(sections["health"]).strip(),
        "ms": r["ms"],
        "error": r.get("stderr") or "",
    }

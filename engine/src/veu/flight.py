"""Flight readiness — go / no-go estilo SpaceX para o Véu OS."""

from __future__ import annotations

import os
import shutil
import time
from typing import Any, TYPE_CHECKING

from veu.subscriptions import PROVIDERS, provider_available

if TYPE_CHECKING:
    from veu.runtime import Runtime


def _check(name: str, ok: bool, detail: str, *, critical: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
        "critical": critical,
        "status": "go" if ok else ("no-go" if critical else "hold"),
    }


def readiness(rt: "Runtime") -> dict[str, Any]:
    """Checklist de voo — o Mission Control e /ready consomem isto."""
    checks: list[dict[str, Any]] = []

    pulse = rt.pulse()
    checks.append(
        _check("kernel", pulse.get("status") == "alive", "pulse alive", critical=True)
    )

    llm = pulse.get("llm") or {}
    llm_ok = bool(llm.get("openai") or llm.get("claude") or llm.get("xai") or llm.get("ollama"))
    checks.append(
        _check(
            "llm",
            llm_ok,
            "openai={oa} claude={cl} xai={xa} ollama={ol}".format(
                oa=llm.get("openai"),
                cl=llm.get("claude"),
                xa=llm.get("xai"),
                ol=llm.get("ollama"),
            ),
            critical=True,
        )
    )

    jev = pulse.get("jev") or {}
    # Honestidade: live só com SDK; key sozinha = ready
    jev_ok = jev.get("status") in {"live", "ready"} and bool(jev.get("key_configured"))
    checks.append(
        _check(
            "jev",
            jev_ok,
            f"status={jev.get('status')} sdk={jev.get('sdk')}",
            critical=False,
        )
    )

    notion = pulse.get("notion") == "live"
    checks.append(_check("notion", notion, str(pulse.get("notion")), critical=False))

    openrag = (pulse.get("openrag") or {}).get("status") == "live"
    checks.append(
        _check(
            "openrag",
            openrag,
            (pulse.get("openrag") or {}).get("base_url") or "off",
            critical=False,
        )
    )

    mem = pulse.get("memory") or {}
    checks.append(
        _check(
            "memory",
            bool(mem.get("root")),
            f"sessions={mem.get('sessions')} audit={mem.get('audit_events')}",
            critical=True,
        )
    )

    # Assinaturas dual-mode
    for pid in PROVIDERS:
        avail = provider_available(pid)  # type: ignore[arg-type]
        checks.append(
            _check(
                f"sub.{pid}",
                True,  # informativo — não bloqueia voo
                f"key={avail['api_key']} sub={avail['subscription']} mode={avail['auth_mode']}",
                critical=False,
            )
        )

    # Disco / memória do host
    try:
        disk = shutil.disk_usage("/")
        disk_ok = (disk.free / disk.total) > 0.08
        checks.append(
            _check(
                "disk",
                disk_ok,
                f"free={disk.free // (1024**3)}Gi total={disk.total // (1024**3)}Gi",
                critical=True,
            )
        )
    except OSError as e:
        checks.append(_check("disk", False, str(e), critical=True))

    meminfo_ok = True
    mem_detail = "n/a"
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            info = f.read()
        avail_kb = 0
        for line in info.splitlines():
            if line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
                break
        avail_gi = avail_kb / (1024**2)
        meminfo_ok = avail_gi >= 1.5
        mem_detail = f"available≈{avail_gi:.1f}Gi"
    except OSError:
        meminfo_ok = True
    checks.append(_check("host_memory", meminfo_ok, mem_detail, critical=False))

    ecc = pulse.get("ecc_agents") or 0
    checks.append(
        _check("ecc", ecc > 0, f"agents={ecc} skills={pulse.get('ecc_skills')}", critical=False)
    )

    critical_fail = [c for c in checks if c["critical"] and not c["ok"]]
    holds = [c for c in checks if not c["critical"] and not c["ok"]]
    go = len(critical_fail) == 0

    return {
        "status": "go" if go else "no-go",
        "go": go,
        "ts": time.time(),
        "product": "véu",
        "checks": checks,
        "critical_failures": [c["name"] for c in critical_fail],
        "holds": [c["name"] for c in holds],
        "summary": (
            f"GO · {len(checks) - len(critical_fail) - len(holds)}/{len(checks)} verdes"
            if go
            else f"NO-GO · críticos: {', '.join(c['name'] for c in critical_fail) or '—'}"
        ),
        "env": {
            "ecc_root": os.environ.get("VEU_ECC_ROOT"),
            "data_root": os.environ.get("VEU_DATA_ROOT") or str(PathHomeData()),
        },
    }


def PathHomeData() -> str:
    from pathlib import Path

    return str(Path.home() / ".veu" / "data")

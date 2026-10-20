"""9.3 — Autoteste dos conectores: leitura real, frescor, status honesto."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

# status honestos (roteiro)
HONEST = ("live", "lento", "parado", "sem-permissão")

# idade (horas) → lento / parado
DEFAULT_SLOW_H = 6.0
DEFAULT_STALE_H = 48.0


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state_path() -> Path:
    return _root() / "connector_selftest.json"


def _alerts_path() -> Path:
    return _root() / "nerve_alerts.jsonl"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"last": {}, "prev_status": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last": {}, "prev_status": {}}
    if not isinstance(data, dict):
        return {"last": {}, "prev_status": {}}
    data.setdefault("last", {})
    data.setdefault("prev_status", {})
    return data


def _save_state(data: dict[str, Any]) -> None:
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def stale_hours(connector_id: str) -> float:
    env = os.environ.get(f"VEU_NERVE_STALE_H_{connector_id.upper().replace('-', '_')}")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    global_env = os.environ.get("VEU_NERVE_STALE_HOURS")
    if global_env:
        try:
            return float(global_env)
        except ValueError:
            pass
    return DEFAULT_STALE_H


def slow_hours(connector_id: str) -> float:
    env = os.environ.get(f"VEU_NERVE_SLOW_H_{connector_id.upper().replace('-', '_')}")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return DEFAULT_SLOW_H


def classify_freshness(
    *,
    age_h: float | None,
    http_ok: bool,
    has_permission: bool,
    connector_id: str = "",
) -> tuple[str, str]:
    """Dado velho demais → parado mesmo com HTTP 200."""
    if not has_permission:
        return "sem-permissão", "sem credencial ou escopo"
    if not http_ok:
        return "parado", "leitura falhou"
    if age_h is None:
        return "live", "leitura ok · sem timestamp de frescor"
    stale = stale_hours(connector_id)
    slow = slow_hours(connector_id)
    if age_h >= stale:
        return "parado", f"dado velho demais ({age_h:.1f}h ≥ {stale:.0f}h)"
    if age_h >= slow:
        return "lento", f"frescor baixo ({age_h:.1f}h)"
    return "live", f"fresco ({age_h:.1f}h)"


def _probe_notion() -> dict[str, Any]:
    from veu.connectors.notion import NotionAdapter

    n = NotionAdapter()
    if not n.live:
        return {
            "ok": False,
            "has_permission": False,
            "age_h": None,
            "last_item": None,
            "detail": "NOTION_TOKEN ausente",
        }
    t0 = time.time()
    r = n.search("", page_size=1)
    latency_ms = int((time.time() - t0) * 1000)
    results = r.get("results") or []
    last = results[0] if results else None
    # Notion search não traz last_edited útil sempre — usa latência + ok
    age_h = 0.0 if r.get("ok") else None
    return {
        "ok": bool(r.get("ok")),
        "has_permission": True,
        "age_h": age_h,
        "last_item": {"title": (last or {}).get("title"), "id": (last or {}).get("id")} if last else None,
        "latency_ms": latency_ms,
        "detail": r.get("message") or "",
        "roundtrip": False,
    }


def _probe_openrag() -> dict[str, Any]:
    from veu.connectors.openrag import OpenRAGAdapter

    o = OpenRAGAdapter()
    if not o.live:
        return {
            "ok": False,
            "has_permission": False,
            "age_h": None,
            "last_item": None,
            "detail": "OPENRAG_API_KEY/URL ausente",
        }
    t0 = time.time()
    r = o.ask("ping Véu self-test", limit=1)
    latency_ms = int((time.time() - t0) * 1000)
    sources = r.get("sources") or []
    return {
        "ok": bool(r.get("ok")),
        "has_permission": True,
        "age_h": 0.0 if r.get("ok") else None,
        "last_item": {"n_sources": len(sources)},
        "latency_ms": latency_ms,
        "detail": (r.get("message") or "")[:200],
        "roundtrip": False,
    }


def _probe_mcp_bus() -> dict[str, Any]:
    from veu.mcp import store

    servers = store.list_servers()
    if not servers:
        return {
            "ok": False,
            "has_permission": True,
            "age_h": None,
            "last_item": None,
            "detail": "nenhum MCP cadastrado",
        }
    live = [s for s in servers if s.get("status") == "live"]
    # frescor pelo last_probe.at
    ages: list[float] = []
    now = time.time()
    for s in servers:
        probe = s.get("last_probe") or {}
        at = probe.get("at") if isinstance(probe, dict) else None
        if isinstance(at, (int, float)):
            ages.append((now - float(at)) / 3600.0)
    age_h = max(ages) if ages else (999.0 if not live else 0.0)
    return {
        "ok": bool(live),
        "has_permission": True,
        "age_h": age_h,
        "last_item": {"live": len(live), "total": len(servers)},
        "detail": f"{len(live)}/{len(servers)} MCP live",
        "roundtrip": False,
    }


def _probe_host() -> dict[str, Any]:
    # Host vive pela extensão — sem probe HTTP; usa live.json freshness se houver
    try:
        from veu.bridges import control_live

        raw = control_live.load_raw() or {}
        mtime = raw.get("_mtime")
        if mtime:
            age_h = (time.time() - float(mtime)) / 3600.0
            return {
                "ok": age_h < stale_hours("host-desktop"),
                "has_permission": True,
                "age_h": age_h,
                "last_item": {"path": raw.get("_path")},
                "detail": f"live.json · {age_h:.1f}h",
                "roundtrip": False,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "has_permission": True,
            "age_h": None,
            "last_item": None,
            "detail": str(exc)[:200],
            "roundtrip": False,
        }
    return {
        "ok": False,
        "has_permission": True,
        "age_h": None,
        "last_item": None,
        "detail": "sem live.json do Host",
        "roundtrip": False,
    }


def _probe_generic_declared(conn: Any) -> dict[str, Any]:
    """Conectores sem adapter: honesto com base no status declarado + sem leitura."""
    status = getattr(conn, "status", "planned")
    if status == "planned":
        return {
            "ok": False,
            "has_permission": False,
            "age_h": None,
            "last_item": None,
            "detail": "planejado — sem self-test de leitura",
            "roundtrip": False,
        }
    if status in {"ready", "live"}:
        # sem leitura real → não mente "live"
        return {
            "ok": False,
            "has_permission": status != "planned",
            "age_h": None,
            "last_item": None,
            "detail": "sem probe de leitura real configurado",
            "roundtrip": False,
            "declared": status,
        }
    return {
        "ok": False,
        "has_permission": False,
        "age_h": None,
        "last_item": None,
        "detail": f"status declarado: {status}",
        "roundtrip": False,
    }


_PROBES: dict[str, Callable[[], dict[str, Any]]] = {
    "notion": _probe_notion,
    "openrag": _probe_openrag,
    "mcp-bus": _probe_mcp_bus,
    "host-desktop": _probe_host,
}


def run_one(connector_id: str, *, inject: dict[str, Any] | None = None) -> dict[str, Any]:
    """Roda self-test de um conector. `inject` só para testes (simula leitura)."""
    if inject is not None:
        raw = dict(inject)
    else:
        probe_fn = _PROBES.get(connector_id)
        if probe_fn:
            try:
                raw = probe_fn()
            except Exception as exc:  # noqa: BLE001
                raw = {
                    "ok": False,
                    "has_permission": True,
                    "age_h": None,
                    "last_item": None,
                    "detail": str(exc)[:300],
                }
        else:
            # tenta pegar do registry
            try:
                from veu.connectors.registry import default_registry

                conn = default_registry().get(connector_id)
                raw = _probe_generic_declared(conn) if conn else {
                    "ok": False,
                    "has_permission": False,
                    "age_h": None,
                    "last_item": None,
                    "detail": "conector desconhecido",
                }
            except Exception as exc:  # noqa: BLE001
                raw = {
                    "ok": False,
                    "has_permission": False,
                    "age_h": None,
                    "last_item": None,
                    "detail": str(exc)[:200],
                }

    honest, reason = classify_freshness(
        age_h=raw.get("age_h"),
        http_ok=bool(raw.get("ok")),
        has_permission=bool(raw.get("has_permission", True)),
        connector_id=connector_id,
    )
    # se declared live mas sem probe → parado (não mente)
    if raw.get("declared") == "live" and honest != "live":
        reason = raw.get("detail") or reason

    result = {
        "id": connector_id,
        "status": honest,
        "reason": reason,
        "age_h": raw.get("age_h"),
        "last_item": raw.get("last_item"),
        "latency_ms": raw.get("latency_ms"),
        "roundtrip": bool(raw.get("roundtrip")),
        "detail": raw.get("detail") or "",
        "ts": time.time(),
    }
    return result


def _notify_whatsapp_nerve(connector_id: str, prev: str, curr: str, reason: str) -> None:
    msg = f"Véu · nervo {connector_id}: {prev} → {curr}. {reason}"
    try:
        with _alerts_path().open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": time.time(),
                        "connector": connector_id,
                        "from": prev,
                        "to": curr,
                        "reason": reason,
                        "msg": msg,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass
    url = (os.environ.get("VEU_WHATSAPP_ALERT_WEBHOOK") or "").strip()
    if url:
        try:
            import httpx

            httpx.post(url, json={"text": msg}, timeout=8.0)
        except Exception:  # noqa: BLE001
            pass


def audit_nerves(
    connector_ids: list[str] | None = None,
    *,
    inject_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Roda todos (ou lista) e alerta WhatsApp quando live→parado."""
    state = _load_state()
    prev_status: dict[str, str] = dict(state.get("prev_status") or {})

    if connector_ids is None:
        from veu.connectors.registry import default_registry

        connector_ids = [c.id for c in default_registry().all()]

    results: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for cid in connector_ids:
        inj = (inject_map or {}).get(cid)
        row = run_one(cid, inject=inj)
        results.append(row)
        old = prev_status.get(cid)
        new = row["status"]
        if old == "live" and new == "parado":
            _notify_whatsapp_nerve(cid, old, new, row.get("reason") or "")
            transitions.append({"id": cid, "from": old, "to": new, "reason": row.get("reason")})
        prev_status[cid] = new
        state.setdefault("last", {})[cid] = row

    state["prev_status"] = prev_status
    state["updated_at"] = time.time()
    _save_state(state)

    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    return {
        "ok": True,
        "results": results,
        "counts": counts,
        "transitions": transitions,
        "updated_at": state["updated_at"],
    }


def last_report() -> dict[str, Any]:
    state = _load_state()
    last = state.get("last") or {}
    results = list(last.values())
    counts: dict[str, int] = {}
    for r in results:
        st = str(r.get("status") or "")
        counts[st] = counts.get(st, 0) + 1
    return {
        "ok": True,
        "results": results,
        "counts": counts,
        "updated_at": state.get("updated_at"),
    }

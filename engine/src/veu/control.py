"""Central de controle — parar tudo, permissões e trilha de auditoria."""

from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

PermissionLevel = Literal["read", "write", "delete"]
GrantTTL = Literal["session", "7d", "30d", "forever"]

LEVELS: tuple[PermissionLevel, ...] = ("read", "write", "delete")


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state_path() -> Path:
    return _root() / "control.json"


def _audit_path() -> Path:
    return _root() / "control_audit.jsonl"


def _default_state() -> dict[str, Any]:
    return {
        "paused": False,
        "breath": "guided",
        "paused_at": None,
        "paused_by": None,
        "permissions": {},  # key → {read, write, delete, expires_at|null, granted_at, granted_by}
        "version": 1,
    }


class ControlCenter:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = _default_state()
        self._load()

    def _load(self) -> None:
        path = _state_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _default_state()
                base.update({k: data.get(k, base[k]) for k in base})
                base["permissions"] = dict(data.get("permissions") or {})
                self._state = base
        except (OSError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        path = _state_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _audit(
        self,
        *,
        who: str,
        what: str,
        target: str = "",
        permission: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "who": who,
            "what": what,
            "target": target,
            "permission": permission,
            **(extra or {}),
        }
        try:
            with _audit_path().open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass
        try:
            from veu.memory import Memory

            Memory().append(
                "control.audit",
                {
                    "who": who,
                    "what": what,
                    "target": target,
                    "permission": permission,
                },
                sink="audit",
            )
        except Exception:  # noqa: BLE001
            pass
        return event

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._expire_grants_locked()
            return {
                "ok": True,
                "paused": bool(self._state.get("paused")),
                "breath": self._state.get("breath") or "guided",
                "paused_at": self._state.get("paused_at"),
                "paused_by": self._state.get("paused_by"),
                "permissions": self._public_permissions_locked(),
            }

    def is_paused(self) -> bool:
        with self._lock:
            return bool(self._state.get("paused"))

    def preferred_breath(self) -> str:
        with self._lock:
            return str(self._state.get("breath") or "guided")

    def stop_all(self, *, who: str = "user") -> dict[str, Any]:
        """Cancela jobs, pausa executor, revoga sessões de agente, força guiado."""
        from veu import jobs as veu_jobs
        from veu import harness as veu_harness

        cancelled = veu_jobs.store.cancel_all_active()
        veu_jobs.store.set_paused(True)
        revoked = 0
        # evita importar api (FastAPI) — só o módulo harness / runtime se já estiver em cache
        try:
            mod = veu_harness
            if hasattr(mod, "harness") and hasattr(mod.harness, "revoke_all"):
                revoked = int(mod.harness.revoke_all(reason="stop-all") or 0)
        except Exception:  # noqa: BLE001
            revoked = 0
        try:
            import sys

            api_mod = sys.modules.get("veu.api")
            rt = getattr(api_mod, "rt", None) if api_mod else None
            if rt is not None and hasattr(rt, "harness") and hasattr(rt.harness, "revoke_all"):
                revoked = max(revoked, int(rt.harness.revoke_all(reason="stop-all") or 0))
        except Exception:  # noqa: BLE001
            pass

        with self._lock:
            self._state["paused"] = True
            self._state["breath"] = "guided"
            self._state["paused_at"] = time.time()
            self._state["paused_by"] = who
            self._save()

        event = self._audit(
            who=who,
            what="parar_tudo",
            target="executor",
            permission="",
            extra={"cancelled_jobs": cancelled, "revoked_sessions": revoked},
        )
        return {
            "ok": True,
            "paused": True,
            "breath": "guided",
            "cancelled_jobs": cancelled,
            "revoked_sessions": revoked,
            "audit": event,
        }

    def resume(self, *, who: str = "user", breath: str | None = None) -> dict[str, Any]:
        try:
            from veu import jobs as veu_jobs

            veu_jobs.store.set_paused(False)
        except Exception:  # noqa: BLE001
            pass
        with self._lock:
            self._state["paused"] = False
            if breath in {"guided", "semi", "free", "autonomous"}:
                self._state["breath"] = breath
            self._state["paused_at"] = None
            self._state["paused_by"] = None
            self._save()
            b = self._state["breath"]
        event = self._audit(who=who, what="liberar_executor", target="executor", extra={"breath": b})
        return {"ok": True, "paused": False, "breath": b, "audit": event}

    def set_breath(self, breath: str, *, who: str = "user") -> dict[str, Any]:
        if breath not in {"guided", "semi", "free", "autonomous"}:
            return {"ok": False, "error": "respiração inválida"}
        with self._lock:
            if self._state.get("paused") and breath != "guided":
                return {"ok": False, "error": "executor pausado — só guiado até liberar"}
            self._state["breath"] = breath
            self._save()
        self._audit(who=who, what="set_breath", target=breath)
        return {"ok": True, "breath": breath}

    # ── permissions ──────────────────────────────────────────────

    def _perm_key(self, kind: str, subject_id: str) -> str:
        return f"{kind}:{subject_id}"

    def _expire_grants_locked(self) -> None:
        now = time.time()
        dead: list[str] = []
        for key, row in (self._state.get("permissions") or {}).items():
            exp = row.get("expires_at")
            if exp is not None and float(exp) <= now:
                dead.append(key)
        for key in dead:
            self._state["permissions"].pop(key, None)
        if dead:
            self._save()

    def _public_permissions_locked(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for key, row in sorted((self._state.get("permissions") or {}).items()):
            kind, _, sid = key.partition(":")
            out.append(
                {
                    "key": key,
                    "kind": kind,
                    "id": sid,
                    "read": bool(row.get("read")),
                    "write": bool(row.get("write")),
                    "delete": bool(row.get("delete")),
                    "expires_at": row.get("expires_at"),
                    "ttl": row.get("ttl") or "forever",
                    "granted_at": row.get("granted_at"),
                    "granted_by": row.get("granted_by") or "",
                }
            )
        return out

    def list_permission_matrix(self) -> dict[str, Any]:
        """Tabela única: conectores + apps, default tudo off."""
        subjects: list[dict[str, Any]] = []
        try:
            from veu.connectors.registry import default_registry

            for c in default_registry().all():
                subjects.append({"kind": "connector", "id": c.id, "name": c.name})
        except Exception:  # noqa: BLE001
            pass
        apps = [
            ("settings", "Ajustes"),
            ("control", "Central de controle"),
            ("data", "Seus dados"),
            ("studio", "Studio"),
            ("servers", "Servidores"),
            ("files", "Arquivos"),
            ("chat", "Chat"),
            ("mission", "Missão"),
            ("mcp", "MCP"),
            ("credentials", "Credenciais"),
        ]
        for aid, name in apps:
            subjects.append({"kind": "app", "id": aid, "name": name})

        with self._lock:
            self._expire_grants_locked()
            grants = {p["key"]: p for p in self._public_permissions_locked()}

        rows = []
        for s in subjects:
            key = self._perm_key(s["kind"], s["id"])
            g = grants.get(key) or {}
            rows.append(
                {
                    "kind": s["kind"],
                    "id": s["id"],
                    "name": s["name"],
                    "read": bool(g.get("read")),
                    "write": bool(g.get("write")),
                    "delete": bool(g.get("delete")),
                    "expires_at": g.get("expires_at"),
                    "ttl": g.get("ttl") or ("forever" if g else None),
                    "granted": bool(g),
                }
            )
        return {"ok": True, "rows": rows, "paused": self.is_paused()}

    def grant(
        self,
        *,
        kind: str,
        subject_id: str,
        read: bool = False,
        write: bool = False,
        delete: bool = False,
        ttl: GrantTTL = "session",
        who: str = "user",
    ) -> dict[str, Any]:
        if kind not in {"connector", "app"}:
            return {"ok": False, "error": "kind inválido"}
        key = self._perm_key(kind, subject_id)
        now = time.time()
        expires: float | None
        if ttl == "session":
            expires = now + 12 * 3600
        elif ttl == "7d":
            expires = now + 7 * 86400
        elif ttl == "30d":
            expires = now + 30 * 86400
        else:
            expires = None

        row = {
            "read": bool(read),
            "write": bool(write),
            "delete": bool(delete),
            "ttl": ttl,
            "expires_at": expires,
            "granted_at": now,
            "granted_by": who,
        }
        with self._lock:
            if not (read or write or delete):
                self._state["permissions"].pop(key, None)
            else:
                self._state.setdefault("permissions", {})[key] = row
            self._save()

        levels = [lv for lv in LEVELS if row.get(lv)]
        self._audit(
            who=who,
            what="grant" if levels else "revoke",
            target=key,
            permission=",".join(levels) or "none",
            extra={"ttl": ttl, "expires_at": expires},
        )
        return {"ok": True, "key": key, "permission": row}

    def check(self, kind: str, subject_id: str, level: PermissionLevel) -> bool:
        key = self._perm_key(kind, subject_id)
        with self._lock:
            self._expire_grants_locked()
            row = (self._state.get("permissions") or {}).get(key) or {}
            return bool(row.get(level))

    def audit_rows(
        self,
        *,
        who: str | None = None,
        what: str | None = None,
        target: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        path = _audit_path()
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if who and who.lower() not in str(row.get("who") or "").lower():
                continue
            if what and what.lower() not in str(row.get("what") or "").lower():
                continue
            if target and target.lower() not in str(row.get("target") or "").lower():
                continue
            rows.append(row)
        return rows[-limit:]

    def audit_csv(
        self,
        *,
        who: str | None = None,
        what: str | None = None,
        target: str | None = None,
        limit: int = 2000,
    ) -> str:
        rows = self.audit_rows(who=who, what=what, target=target, limit=limit)
        buf = io.StringIO()
        w = csv.DictWriter(
            buf,
            fieldnames=["ts", "who", "what", "target", "permission", "id"],
            extrasaction="ignore",
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)
        return buf.getvalue()


control = ControlCenter()

"""Alvos seguros / protegidos — confirmação digitada para destrutivo."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

SafetyMark = Literal["seguro", "protegido"]
DESTRUCTIVE = frozenset(
    {
        "delete",
        "apagar",
        "overwrite",
        "sobrescrever",
        "restart",
        "reiniciar",
        "ssh_write",
        "ssh",
        "shell_write",
        "format",
        "rm",
    }
)


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path() -> Path:
    return _root() / "targets.json"


class TargetStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._marks: dict[str, dict[str, Any]] = {}
        self._advanced = False
        self._load()

    def _load(self) -> None:
        path = _path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._marks = dict(data.get("marks") or {})
            self._advanced = bool(data.get("advanced"))
        except (OSError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        path = _path()
        tmp = path.with_suffix(".tmp")
        payload = {"marks": self._marks, "advanced": self._advanced, "version": 1}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _key(self, kind: str, target_id: str) -> str:
        return f"{kind}:{target_id}"

    def get_mark(self, kind: str, target_id: str) -> SafetyMark:
        with self._lock:
            row = self._marks.get(self._key(kind, target_id))
            if not row:
                return "protegido"  # padrão
            m = str(row.get("mark") or "protegido")
            return "seguro" if m == "seguro" else "protegido"

    def set_mark(
        self,
        *,
        kind: str,
        target_id: str,
        mark: SafetyMark,
        name: str = "",
        who: str = "user",
    ) -> dict[str, Any]:
        if mark not in {"seguro", "protegido"}:
            return {"ok": False, "error": "marca inválida"}
        key = self._key(kind, target_id)
        with self._lock:
            self._marks[key] = {
                "kind": kind,
                "id": target_id,
                "name": name or target_id,
                "mark": mark,
                "updated_at": time.time(),
                "updated_by": who,
            }
            self._save()
            row = dict(self._marks[key])
        self._audit("set_mark", who=who, target=key, mark=mark)
        return {"ok": True, "target": row}

    def set_advanced(self, on: bool, *, who: str = "user") -> dict[str, Any]:
        with self._lock:
            self._advanced = bool(on)
            self._save()
        self._audit("advanced", who=who, target="", mark="on" if on else "off")
        return {"ok": True, "advanced": self._advanced}

    def is_advanced(self) -> bool:
        with self._lock:
            return bool(self._advanced)

    def list_targets(
        self,
        *,
        kind: str | None = None,
        destructive: bool = False,
        include_protected: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Lista alvos. Em ação destrutiva, só seguros (salvo modo avançado)."""
        show_protected = (
            include_protected if include_protected is not None else (self.is_advanced() or not destructive)
        )
        items: list[dict[str, Any]] = []

        # servidores cadastrados
        try:
            from veu import fleet

            for s in fleet.list_servers(reveal=False):
                sid = str(s.get("id") or "")
                name = str(s.get("name") or sid)
                mark = self.get_mark("server", sid)
                items.append(
                    {
                        "kind": "server",
                        "id": sid,
                        "name": name,
                        "mark": mark,
                    }
                )
        except Exception:  # noqa: BLE001
            pass

        # conectores
        try:
            from veu.connectors.registry import default_registry

            for c in default_registry().all():
                mark = self.get_mark("connector", c.id)
                items.append(
                    {
                        "kind": "connector",
                        "id": c.id,
                        "name": c.name,
                        "mark": mark,
                    }
                )
        except Exception:  # noqa: BLE001
            pass

        # pastas / alvos manuais
        with self._lock:
            for row in self._marks.values():
                if row.get("kind") in {"server", "connector"}:
                    continue
                items.append(
                    {
                        "kind": row.get("kind") or "folder",
                        "id": row.get("id"),
                        "name": row.get("name") or row.get("id"),
                        "mark": row.get("mark") or "protegido",
                    }
                )

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for it in items:
            k = f"{it['kind']}:{it['id']}"
            if k in seen:
                continue
            seen.add(k)
            if kind and it["kind"] != kind:
                continue
            if destructive and it["mark"] != "seguro" and not show_protected:
                continue
            if destructive and it["mark"] != "seguro" and not self.is_advanced():
                continue
            out.append(it)
        return out

    def authorize_destructive(
        self,
        *,
        kind: str,
        target_id: str,
        action: str,
        confirm_name: str | None = None,
        who: str = "user",
        breath: str = "guided",
    ) -> dict[str, Any]:
        """Bloqueia destrutivo em protegido sem digitar o nome (mesmo no livre)."""
        action_l = (action or "").lower().strip()
        is_dest = action_l in DESTRUCTIVE or any(d in action_l for d in DESTRUCTIVE)
        if not is_dest:
            return {"ok": True, "allowed": True, "destructive": False}

        mark = self.get_mark(kind, target_id)
        name = target_id
        with self._lock:
            row = self._marks.get(self._key(kind, target_id))
            if row and row.get("name"):
                name = str(row["name"])

        # listagem: só seguros por padrão
        if mark != "seguro" and not self.is_advanced():
            self._audit(
                "blocked_not_advanced",
                who=who,
                target=f"{kind}:{target_id}",
                mark=mark,
                action=action_l,
                breath=breath,
            )
            return {
                "ok": False,
                "allowed": False,
                "error": "alvo protegido — ative modo avançado para ver/usar",
                "mark": mark,
            }

        if mark == "protegido":
            expected = (name or target_id).strip()
            typed = (confirm_name or "").strip()
            if typed != expected:
                self._audit(
                    "blocked_no_confirm",
                    who=who,
                    target=f"{kind}:{target_id}",
                    mark=mark,
                    action=action_l,
                    breath=breath,
                )
                return {
                    "ok": False,
                    "allowed": False,
                    "error": "digite o nome do alvo para confirmar",
                    "mark": mark,
                    "expect": expected,
                }

        self._audit(
            "destructive_ok",
            who=who,
            target=f"{kind}:{target_id}",
            mark=mark,
            action=action_l,
            breath=breath,
            confirmed=bool(confirm_name),
        )
        return {"ok": True, "allowed": True, "destructive": True, "mark": mark}

    def _audit(self, what: str, **extra: Any) -> None:
        event = {
            "id": str(uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": "target.safety",
            "what": what,
            **extra,
        }
        try:
            path = _root() / "audit.jsonl"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass
        try:
            from veu.memory import Memory

            Memory().append("target.safety", event, sink="audit")
        except Exception:  # noqa: BLE001
            pass


targets = TargetStore()

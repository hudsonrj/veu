"""Soberania de dados — exportar tudo (sem segredos) e apagar por fonte."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from veu.integrity import sha256_file, sha256_bytes

SECRET_NAME_RE = re.compile(
    r"(password|secret|token|api[_-]?key|credential|private[_-]?key|auth)",
    re.I,
)
SECRET_ENV_PREFIXES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "VEU_SRV_",
    "TYPESAFE",
    "HF_TOKEN",
    "HUGGINGFACE",
)


def _root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _age_label(mtime: float | None) -> str | None:
    if mtime is None:
        return None
    age_s = max(0, time.time() - float(mtime))
    if age_s < 3600:
        return f"{int(age_s // 60)} min"
    if age_s < 86400:
        return f"{age_s / 3600:.1f} h"
    return f"{age_s / 86400:.1f} d"


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "bytes": 0, "age": None, "mtime": None}
    st = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "bytes": st.st_size,
        "mtime": st.st_mtime,
        "age": _age_label(st.st_mtime),
    }


def inventory() -> dict[str, Any]:
    """Onde cada tipo de dado mora e há quanto tempo."""
    root = _root()
    kinds = [
        {
            "id": "memory_audit",
            "label": "auditoria",
            "where": "disco",
            "file": root / "audit.jsonl",
            "source": "veu",
        },
        {
            "id": "decisions",
            "label": "decisões",
            "where": "disco",
            "file": root / "decisions.jsonl",
            "source": "veu",
        },
        {
            "id": "sessions",
            "label": "sessões",
            "where": "disco",
            "file": root / "sessions.jsonl",
            "source": "veu",
        },
        {
            "id": "jobs",
            "label": "jobs",
            "where": "disco",
            "file": root / "jobs.json",
            "source": "veu",
        },
        {
            "id": "servers",
            "label": "servidores (metadados)",
            "where": "disco",
            "file": root / "servers.json",
            "source": "veu",
        },
        {
            "id": "control",
            "label": "central de controle",
            "where": "disco",
            "file": root / "control.json",
            "source": "veu",
        },
        {
            "id": "targets",
            "label": "alvos seguro/protegido",
            "where": "disco",
            "file": root / "targets.json",
            "source": "veu",
        },
        {
            "id": "studio",
            "label": "studio / artefatos",
            "where": "disco",
            "file": root / "studio",
            "source": "studio",
        },
        {
            "id": "harness",
            "label": "harness",
            "where": "disco",
            "file": root / "harness.jsonl",
            "source": "veu",
        },
        {
            "id": "clone",
            "label": "clone",
            "where": "disco",
            "file": root / "clone.json",
            "source": "clone",
        },
        {
            "id": "projects_chatgpt",
            "label": "projetos ChatGPT",
            "where": "disco",
            "file": root / "projects" / "chatgpt.jsonl",
            "source": "chatgpt",
        },
        {
            "id": "projects_claude",
            "label": "projetos Claude",
            "where": "disco",
            "file": root / "projects" / "claude.jsonl",
            "source": "claude",
        },
        {
            "id": "workspaces",
            "label": "workspaces",
            "where": "disco",
            "file": root / "workspaces.json",
            "source": "veu",
        },
        {
            "id": "rag",
            "label": "OpenRAG (remoto)",
            "where": "RAG",
            "file": None,
            "source": "openrag",
            "note": "índice externo — não apaga pelo Véu sem conector",
        },
    ]
    rows = []
    for k in kinds:
        f = k.get("file")
        meta = _file_meta(f) if isinstance(f, Path) else {
            "path": None,
            "exists": False,
            "bytes": 0,
            "age": None,
            "mtime": None,
        }
        if isinstance(f, Path) and f.is_dir() and f.exists():
            total = sum(p.stat().st_size for p in f.rglob("*") if p.is_file())
            mtimes = [p.stat().st_mtime for p in f.rglob("*") if p.is_file()]
            meta = {
                "path": str(f),
                "exists": True,
                "bytes": total,
                "mtime": max(mtimes) if mtimes else None,
                "age": _age_label(max(mtimes) if mtimes else None),
            }
        rows.append(
            {
                "id": k["id"],
                "label": k["label"],
                "where": k["where"],
                "source": k["source"],
                "note": k.get("note") or "",
                **meta,
            }
        )
    return {
        "ok": True,
        "root": str(root),
        "items": rows,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _is_secret_path(name: str) -> bool:
    return bool(SECRET_NAME_RE.search(name))


def _scrub_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _is_secret_path(str(k)):
                out[k] = "***"
            else:
                out[k] = _scrub_obj(v)
        return out
    if isinstance(obj, list):
        return [_scrub_obj(x) for x in obj]
    return obj


def _safe_json_file(path: Path) -> bytes | None:
    if not path.exists() or not path.is_file():
        return None
    if _is_secret_path(path.name):
        return None
    try:
        if path.suffix in {".json", ".jsonl"}:
            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                return (json.dumps(_scrub_obj(data), ensure_ascii=False, indent=2) + "\n").encode()
            lines = []
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    lines.append(json.dumps(_scrub_obj(json.loads(line)), ensure_ascii=False))
                except json.JSONDecodeError:
                    continue
            return ("\n".join(lines) + ("\n" if lines else "")).encode()
        # texto genérico — só se não parecer segredo
        return path.read_bytes()
    except OSError:
        return None


def _public_subscriptions() -> dict[str, Any]:
    try:
        from veu import subscriptions as subs

        if hasattr(subs, "status_snapshot"):
            return _scrub_obj(subs.status_snapshot())
        if hasattr(subs, "board"):
            return _scrub_obj(subs.board())
    except Exception:  # noqa: BLE001
        pass
    return {"note": "sem assinaturas públicas"}


def export_all() -> dict[str, Any]:
    """Zip com memória, decisões, projetos, assinaturas, workspaces e config não secreta."""
    root = _root()
    exports_dir = root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = exports_dir / f"veu-export-{stamp}.zip"

    files: list[tuple[str, bytes]] = []

    for rel in (
        "audit.jsonl",
        "decisions.jsonl",
        "sessions.jsonl",
        "jobs.json",
        "jobs_history.jsonl",
        "servers.json",
        "control.json",
        "targets.json",
        "harness.jsonl",
        "workspaces.json",
        "clone.json",
        "routines.json",
    ):
        raw = _safe_json_file(root / rel)
        if raw is not None:
            files.append((f"data/{rel}", raw))

    # projetos por fonte
    proj = root / "projects"
    if proj.is_dir():
        for p in proj.rglob("*"):
            if p.is_file() and not _is_secret_path(p.name):
                raw = _safe_json_file(p)
                if raw is not None:
                    files.append((f"data/projects/{p.relative_to(proj)}", raw))

    # studio out (artefatos) — sem uploads brutos gigantes opcionalmente só out/
    studio_out = root / "studio" / "out"
    if studio_out.is_dir():
        for p in studio_out.rglob("*"):
            if p.is_file() and p.name != "manifest.json" and not _is_secret_path(p.name):
                try:
                    if p.stat().st_size > 5_000_000:
                        continue
                    files.append((f"data/studio/out/{p.name}", p.read_bytes()))
                except OSError:
                    continue

    # assinaturas públicas (sem keys)
    files.append(
        (
            "data/subscriptions_public.json",
            (json.dumps(_public_subscriptions(), ensure_ascii=False, indent=2) + "\n").encode(),
        )
    )

    # inventário
    files.append(
        (
            "data/inventory.json",
            (json.dumps(inventory(), ensure_ascii=False, indent=2) + "\n").encode(),
        )
    )

    # manifesto SHA-256
    artifacts = []
    for name, data in files:
        artifacts.append(
            {
                "nome": name,
                "tamanho": len(data),
                "sha256": sha256_bytes(data),
                "job_id": "export-all",
                "ts": time.time(),
            }
        )
    manifest = {
        "version": 1,
        "kind": "veu-export",
        "created": datetime.now(timezone.utc).isoformat(),
        "secrets_included": False,
        "artifacts": artifacts,
    }
    man_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    files.append(("manifest.json", man_bytes))

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)

    # selo do próprio zip
    from veu.integrity import seal_artifact

    seal = seal_artifact(zip_path, job_id="export-all")
    return {
        "ok": True,
        "path": str(zip_path),
        "bytes": zip_path.stat().st_size,
        "files": len(files),
        "sha256": sha256_file(zip_path),
        "manifest": seal.get("manifest"),
        "secrets_included": False,
    }


def preview_delete(source: str) -> dict[str, Any]:
    """Prévia do que será removido por fonte (ou total)."""
    src = (source or "").strip().lower()
    inv = inventory()
    if src in {"*", "all", "tudo", "total"}:
        items = [i for i in inv["items"] if i.get("exists")]
        return {
            "ok": True,
            "source": "total",
            "confirm_word": "APAGAR TUDO",
            "items": items,
            "count": len(items),
        }

    items = [i for i in inv["items"] if str(i.get("source") or "").lower() == src and i.get("exists")]
    # também varrer jsonl com campo source
    root = _root()
    matched_lines: dict[str, int] = {}
    for name in ("audit.jsonl", "decisions.jsonl", "sessions.jsonl"):
        path = root / name
        if not path.exists():
            continue
        n = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("source") or "").lower() == src:
                n += 1
        if n:
            matched_lines[name] = n
            items.append(
                {
                    "id": f"lines:{name}",
                    "label": f"{n} eventos em {name}",
                    "where": "disco",
                    "source": src,
                    "path": str(path),
                    "exists": True,
                    "bytes": 0,
                    "line_filter": True,
                }
            )

    return {
        "ok": True,
        "source": src,
        "confirm_word": src,
        "items": items,
        "line_matches": matched_lines,
        "count": len(items),
    }


def delete_by_source(*, source: str, confirm: str, who: str = "user") -> dict[str, Any]:
    preview = preview_delete(source)
    expected = str(preview.get("confirm_word") or "")
    if (confirm or "").strip() != expected:
        return {
            "ok": False,
            "error": "confirmação digitada inválida",
            "expect": expected,
            "preview": preview,
        }

    root = _root()
    src = preview["source"]
    removed: list[str] = []

    if src == "total":
        for item in preview["items"]:
            p = item.get("path")
            if not p:
                continue
            path = Path(p)
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.is_file():
                    path.unlink(missing_ok=True)
                removed.append(str(path))
            except OSError:
                pass
    else:
        # apaga arquivos cujo source bate
        for item in preview["items"]:
            if item.get("line_filter"):
                continue
            p = item.get("path")
            if not p:
                continue
            path = Path(p)
            try:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.is_file():
                    path.unlink(missing_ok=True)
                removed.append(str(path))
            except OSError:
                pass

        # filtra linhas com source
        for name in ("audit.jsonl", "decisions.jsonl", "sessions.jsonl"):
            path = root / name
            if not path.exists():
                continue
            keep: list[str] = []
            changed = False
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    keep.append(line)
                    continue
                if str(row.get("source") or "").lower() == src:
                    changed = True
                    continue
                keep.append(line)
            if changed:
                path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
                removed.append(f"{name}#source={src}")

        # projetos da fonte
        proj = root / "projects" / f"{src}.jsonl"
        if proj.exists():
            proj.unlink(missing_ok=True)
            removed.append(str(proj))

    try:
        from veu.memory import Memory

        Memory().append(
            "sovereignty.delete",
            {"deleted_source": src, "who": who, "removed": removed[:40]},
            sink="audit",
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "source": src,
        "removed": removed,
        "count": len(removed),
        "preview": preview,
    }

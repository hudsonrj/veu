"""REA (morluto/rea) — reverse engineer site/app e publicar evidência no GitHub.

Usa o CLI oficial `rea-agents` (https://github.com/morluto/rea · https://rea.tools).
Sites: CDP do Chrome Lite (:9337) + `analyze-web-bundle`.
Apps JS/Electron locais: `analyze-javascript-application`.
Publicação: cria repositório GitHub com README + evidência JSON.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CDP_HTTP = os.environ.get("VEU_LITE_CDP", "http://127.0.0.1:9337").rstrip("/")
REA_BIN = os.environ.get("VEU_REA_BIN", "").strip()  # opcional: caminho absoluto
REA_NPX = os.environ.get("VEU_REA_NPX", "npx")
REA_PKG = os.environ.get("VEU_REA_PKG", "rea-agents@latest")
JOB_TTL_SEC = 60 * 60 * 24 * 7


def _data_root() -> Path:
    root = Path(os.environ.get("VEU_DATA_ROOT") or (Path.home() / ".veu" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _jobs_dir() -> Path:
    d = _data_root() / "rea" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rea_cmd(*args: str) -> list[str]:
    if REA_BIN:
        return [REA_BIN, *args]
    return [REA_NPX, "-y", REA_PKG, *args]


def _run(
    argv: list[str],
    *,
    timeout: int = 180,
    cwd: str | None = None,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env={**os.environ, "CI": "1", "NO_COLOR": "1"},
            check=False,
        )
    except FileNotFoundError as e:
        return {"ok": False, "error": f"binário ausente: {e}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout {timeout}s", "cmd": argv[:4]}
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    data: Any = None
    if out:
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            # às vezes npm warn precede o JSON
            start = out.find("{")
            end = out.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(out[start : end + 1])
                except json.JSONDecodeError:
                    data = {"raw": out[-8000:]}
            else:
                data = {"raw": out[-8000:]}
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "data": data,
        "stderr": err[-4000:] if err else "",
        "cmd": argv[:6],
    }


def status() -> dict[str, Any]:
    """Doctor leve — REA instalável + CDP Lite."""
    ver = _run(_rea_cmd("--version"), timeout=60)
    cdp_ok = False
    cdp_browser = None
    try:
        with urllib.request.urlopen(f"{CDP_HTTP}/json/version", timeout=3) as r:
            j = json.loads(r.read().decode())
            cdp_ok = True
            cdp_browser = j.get("Browser")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass
    return {
        "ok": True,
        "product": "REA",
        "upstream": "https://github.com/morluto/rea",
        "site": "https://rea.tools",
        "cli": {
            "ok": bool(ver.get("ok") or ver.get("data") or ver.get("stderr")),
            "version": ver.get("data") or (ver.get("stderr") or "")[:120],
            "cmd": " ".join(_rea_cmd("--help")[:3]),
        },
        "cdp": {"ok": cdp_ok, "endpoint": CDP_HTTP, "browser": cdp_browser},
        "mcp": {
            "id": "rea",
            "transport": "stdio",
            "command": REA_NPX if not REA_BIN else REA_BIN,
            "args": (["-y", REA_PKG, "--mcp"] if not REA_BIN else ["--mcp"]),
        },
        "disclaimer": (
            "Use só em alvos que você possui ou tem autorização para inspecionar. "
            "REA faz análise estática / observação local — não bypass de DRM."
        ),
    }


def mcp_config() -> dict[str, Any]:
    st = status()
    return {
        "id": "rea",
        "name": "REA · reverse engineer anything",
        "transport": "stdio",
        "command": st["mcp"]["command"],
        "args": st["mcp"]["args"],
        "env": {},
        "notes": "https://github.com/morluto/rea · npx rea-agents@latest --mcp",
    }


def _save_job(job: dict[str, Any]) -> dict[str, Any]:
    jid = str(job["id"])
    path = _jobs_dir() / f"{jid}.json"
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def _load_job(job_id: str) -> dict[str, Any] | None:
    path = _jobs_dir() / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_jobs(limit: int = 20) -> dict[str, Any]:
    files = sorted(_jobs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    jobs = []
    for p in files[: max(1, min(limit, 50))]:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            jobs.append(
                {
                    "id": j.get("id"),
                    "target": j.get("target"),
                    "kind": j.get("kind"),
                    "status": j.get("status"),
                    "created": j.get("created"),
                    "publish": j.get("publish"),
                    "summary": j.get("summary"),
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    return {"ok": True, "jobs": jobs}


def get_job(job_id: str) -> dict[str, Any]:
    j = _load_job(job_id)
    if not j:
        return {"ok": False, "error": "job não encontrado"}
    return {"ok": True, "job": j}


def _slug(text: str) -> str:
    s = re.sub(r"^https?://", "", text.strip(), flags=re.I)
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "target")[:48]


def _cdp_new_page(url: str) -> dict[str, Any]:
    """Abre URL no Chrome Lite e devolve target id."""
    q = urllib.parse.quote(url, safe="")
    # Chrome DevTools: /json/new?{url}
    req = urllib.request.Request(
        f"{CDP_HTTP}/json/new?{q}",
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError:
        # alguns builds só aceitam GET
        with urllib.request.urlopen(f"{CDP_HTTP}/json/new?{q}", timeout=20) as r:
            return json.loads(r.read().decode())


def _cdp_list() -> list[dict[str, Any]]:
    with urllib.request.urlopen(f"{CDP_HTTP}/json/list", timeout=8) as r:
        data = json.loads(r.read().decode())
    return data if isinstance(data, list) else []


def _pick_target(url: str, created: dict[str, Any] | None) -> str | None:
    if created and created.get("id"):
        return str(created["id"])
    origin = urllib.parse.urlparse(url)
    want = f"{origin.scheme}://{origin.netloc}".rstrip("/")
    for t in _cdp_list():
        if t.get("type") not in (None, "page", "other"):
            continue
        tu = str(t.get("url") or "")
        if tu.startswith(want) or url in tu:
            return str(t.get("id"))
    # fallback: primeiro page
    for t in _cdp_list():
        if t.get("type") == "page" and t.get("id"):
            return str(t["id"])
    return None


def _summarize(evidence: Any, target: str, kind: str) -> dict[str, Any]:
    """Extrai resumo legível de evidência REA (estrutura varia por comando)."""
    if not isinstance(evidence, dict):
        return {
            "title": f"REA · {_slug(target)}",
            "target": target,
            "kind": kind,
            "notes": ["evidência bruta — veja evidence.json"],
        }
    # envelopes comuns
    body = evidence.get("evidence") or evidence.get("result") or evidence
    if not isinstance(body, dict):
        body = evidence
    modules = body.get("modules") or body.get("scripts") or []
    if isinstance(modules, dict):
        modules = list(modules.values())
    n_mod = len(modules) if isinstance(modules, list) else 0
    origins = body.get("origins") or body.get("allowed_origins") or []
    title = (
        body.get("title")
        or body.get("name")
        or body.get("application", {}).get("name")
        if isinstance(body.get("application"), dict)
        else None
    ) or f"REA · {_slug(target)}"
    notes: list[str] = []
    if n_mod:
        notes.append(f"{n_mod} módulos/scripts mapeados")
    if origins:
        notes.append(f"origins: {', '.join(map(str, origins))[:200]}")
    # campos de grafo JS
    for key in ("imports", "exports", "entrypoints", "electron"):
        if body.get(key):
            notes.append(f"tem {key}")
    if not notes:
        notes.append("análise concluída — ver evidence.json no publish")
    return {
        "title": str(title)[:120],
        "target": target,
        "kind": kind,
        "modules": n_mod,
        "notes": notes[:12],
        "keys": sorted(list(body.keys()))[:24] if isinstance(body, dict) else [],
    }


def analyze(
    *,
    target: str,
    kind: str = "url",
    observation_ms: int = 1500,
    fetch_source_maps: bool = True,
) -> dict[str, Any]:
    """Roda REA no alvo e persiste job."""
    target = (target or "").strip()
    if not target:
        return {"ok": False, "error": "informe URL, caminho ou app"}
    kind = (kind or "url").strip().lower()
    if kind in ("site", "web", "page"):
        kind = "url"
    if kind in ("js", "javascript", "electron", "dir"):
        kind = "path"

    job_id = f"rea-{int(time.time())}-{_slug(target)[:20]}"
    job: dict[str, Any] = {
        "id": job_id,
        "target": target,
        "kind": kind,
        "status": "running",
        "created": int(time.time()),
        "upstream": "https://github.com/morluto/rea",
    }
    _save_job(job)

    try:
        if kind == "url":
            if not re.match(r"^https?://", target, re.I):
                target = "https://" + target
                job["target"] = target
            # precisa CDP
            try:
                created = _cdp_new_page(target)
            except Exception as e:  # noqa: BLE001
                job["status"] = "error"
                job["error"] = f"Chrome Lite CDP falhou: {e}"
                _save_job(job)
                return {"ok": False, **job}
            time.sleep(max(0.8, observation_ms / 1000))
            tid = _pick_target(target, created)
            if not tid:
                job["status"] = "error"
                job["error"] = "nenhum target CDP para a URL"
                _save_job(job)
                return {"ok": False, **job}
            argv = _rea_cmd(
                "analyze-web-bundle",
                CDP_HTTP,
                tid,
                "--observation-ms",
                str(max(200, observation_ms)),
                "--format",
                "json",
            )
            if fetch_source_maps:
                argv.append("--fetch-source-maps")
            result = _run(argv, timeout=240)
        elif kind == "path":
            path = Path(target).expanduser()
            if not path.exists():
                job["status"] = "error"
                job["error"] = f"caminho não existe: {path}"
                _save_job(job)
                return {"ok": False, **job}
            argv = _rea_cmd(
                "analyze-javascript-application",
                str(path.resolve()),
                "--format",
                "json",
            )
            result = _run(argv, timeout=300)
        else:
            job["status"] = "error"
            job["error"] = f"kind desconhecido: {kind} (use url|path)"
            _save_job(job)
            return {"ok": False, **job}

        job["cli"] = {
            "ok": result.get("ok"),
            "code": result.get("code"),
            "stderr": result.get("stderr"),
            "cmd": result.get("cmd"),
        }
        evidence = result.get("data")
        job["evidence"] = evidence
        job["summary"] = _summarize(evidence, target, kind)
        if result.get("ok"):
            job["status"] = "done"
        else:
            job["status"] = "error"
            job["error"] = result.get("stderr") or result.get("error") or "REA retornou erro"
        _save_job(job)
        return {"ok": job["status"] == "done", "job": _public_job(job)}
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)
        _save_job(job)
        return {"ok": False, "job": _public_job(job)}


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    """Job sem evidência completa (pode ser enorme)."""
    return {
        "id": job.get("id"),
        "target": job.get("target"),
        "kind": job.get("kind"),
        "status": job.get("status"),
        "created": job.get("created"),
        "summary": job.get("summary"),
        "error": job.get("error"),
        "publish": job.get("publish"),
        "cli": job.get("cli"),
        "has_evidence": bool(job.get("evidence")),
    }


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def publish(
    job_id: str,
    *,
    repo: str | None = None,
    description: str | None = None,
    private: bool = True,
    owner: str | None = None,
) -> dict[str, Any]:
    """Publica evidência REA num repositório GitHub novo."""
    job = _load_job(job_id)
    if not job:
        return {"ok": False, "error": "job não encontrado"}
    if job.get("status") != "done" and not job.get("evidence"):
        return {"ok": False, "error": "job sem evidência para publicar"}
    if not _gh_available():
        return {
            "ok": False,
            "error": "gh CLI ausente no host — instale GitHub CLI ou exporte o pacote manualmente",
        }

    slug = _slug(str(job.get("target") or "target"))
    stamp = time.strftime("%Y%m%d")
    name = (repo or f"rea-{slug}-{stamp}").strip()
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")[:100]
    owner = (owner or os.environ.get("VEU_REA_GITHUB_OWNER") or "").strip() or None
    full = f"{owner}/{name}" if owner else name

    work = _jobs_dir() / job_id / "publish"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    summary = job.get("summary") or {}
    readme = f"""# {summary.get("title") or name}

Reconstrução / evidência gerada pelo **Véu OS** com [REA](https://github.com/morluto/rea)
([rea.tools](https://rea.tools)).

## Alvo

- **Target:** `{job.get("target")}`
- **Kind:** `{job.get("kind")}`
- **Job:** `{job_id}`
- **Quando:** {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(job.get("created") or time.time()))}

## Resumo

{chr(10).join(f"- {n}" for n in (summary.get("notes") or ["—"]))}

## Conteúdo

| Arquivo | Descrição |
|---------|-----------|
| `evidence.json` | Evidência completa do REA |
| `summary.json` | Resumo compacto |
| `DISCLAIMER.md` | Uso autorizado |

## Upstream

Ferramenta: [`morluto/rea`](https://github.com/morluto/rea) · MCP/CLI `rea-agents`.

```bash
npx -y rea-agents@latest --help
```
"""
    (work / "README.md").write_text(readme, encoding="utf-8")
    (work / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (work / "evidence.json").write_text(
        json.dumps(job.get("evidence"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (work / "DISCLAIMER.md").write_text(
        "Esta análise deve ser usada apenas em software/sites que você possui "
        "ou está autorizado a inspecionar. Não use para contornar proteções, "
        "DRM ou termos de serviço.\n\n"
        "Baseado no projeto REA (MIT) — https://github.com/morluto/rea\n",
        encoding="utf-8",
    )
    (work / ".gitignore").write_text("node_modules/\n.DS_Store\n", encoding="utf-8")

    desc = (
        description
        or f"REA reverse of {job.get('target')} via Véu OS"
    )[:200]

    # init git + create repo
    steps: list[dict[str, Any]] = []
    for argv in (
        ["git", "init", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "config", "user.email", "veu@local"],
        ["git", "config", "user.name", "Véu REA"],
        ["git", "commit", "-m", f"rea: {slug}"],
    ):
        r = _run(argv, timeout=60, cwd=str(work))
        steps.append({"cmd": argv[0:3], "ok": r.get("ok"), "err": r.get("stderr")[:200]})
        if argv[0:2] == ["git", "commit"] and not r.get("ok"):
            # empty commit edge
            pass

    create_argv = [
        "gh",
        "repo",
        "create",
        full,
        "--source",
        ".",
        "--remote",
        "origin",
        "--push",
        "--description",
        desc,
    ]
    create_argv.insert(3, "--private" if private else "--public")
    created = _run(create_argv, timeout=120, cwd=str(work))
    steps.append({"cmd": "gh repo create", "ok": created.get("ok"), "err": created.get("stderr")[:400]})

    html_url = None
    if created.get("ok"):
        # gh prints URL on stdout sometimes as raw
        raw = created.get("data")
        if isinstance(raw, dict) and raw.get("url"):
            html_url = raw["url"]
        else:
            view = _run(["gh", "repo", "view", full, "--json", "url"], timeout=30, cwd=str(work))
            if isinstance(view.get("data"), dict):
                html_url = view["data"].get("url")
            elif isinstance(view.get("data"), str):
                html_url = view["data"]
        # parse raw stderr/stdout for URL
        blob = str(created.get("data") or "") + "\n" + str(created.get("stderr") or "")
        m = re.search(r"https://github\.com/[\w.-]+/[\w.-]+", blob)
        if m:
            html_url = m.group(0)

    if not created.get("ok"):
        job["publish"] = {
            "ok": False,
            "error": created.get("stderr") or created.get("error") or "gh create falhou",
            "repo": full,
            "work": str(work),
            "steps": steps,
        }
        _save_job(job)
        return {"ok": False, **job["publish"]}

    job["publish"] = {
        "ok": True,
        "repo": full,
        "url": html_url or f"https://github.com/{full}",
        "private": private,
        "work": str(work),
        "steps": steps,
    }
    _save_job(job)
    return {"ok": True, "job": _public_job(job), "publish": job["publish"]}

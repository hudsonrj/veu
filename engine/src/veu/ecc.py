"""Catálogo ECC — agentes e skills como musculatura do Véu."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EccAgent(BaseModel):
    id: str
    title: str
    triggers: list[str] = Field(default_factory=list)
    role: str = ""
    description: str = ""
    tools: list[str] = Field(default_factory=list)
    can_do: list[str] = Field(default_factory=list)
    source: str = "core"  # core | vendor


class EccSkill(BaseModel):
    id: str
    title: str
    triggers: list[str] = Field(default_factory=list)
    description: str = ""
    can_do: list[str] = Field(default_factory=list)
    origin: str = ""
    source: str = "core"


# Núcleo mínimo embutido — o vendor ECC completo enriquece em runtime.
CORE_AGENTS: list[EccAgent] = [
    EccAgent(
        id="chief-of-staff",
        title="Chefe de gabinete",
        triggers=["whatsapp", "teams", "outlook", "gmail", "email", "slack", "chat", "mensagem", "inbox"],
        role="Triagem e resposta em canais de comunicação",
        description="Triagem multi-canal, rascunhos e follow-through.",
        can_do=[
            "Triar e-mail e mensagens",
            "Rascunhar respostas",
            "Priorizar o que precisa da sua OK",
        ],
    ),
    EccAgent(
        id="planner",
        title="Planejador",
        triggers=["plano", "planejar", "como fazer", "passo a passo", "estratégia"],
        role="Decompõe intenções em planos executáveis",
        description="Quebra pedidos grandes em passos acionáveis.",
        can_do=["Montar plano passo a passo", "Priorizar entregas", "Checklist do dia"],
    ),
    EccAgent(
        id="architect",
        title="Arquiteto",
        triggers=["arquitetura", "desenhar sistema", "escala", "design"],
        role="Desenho de sistema e trade-offs",
        description="Arquitetura, trade-offs e desenho de sistemas.",
        can_do=["Desenhar arquitetura", "Comparar trade-offs", "Revisar desenho"],
    ),
    EccAgent(
        id="code-reviewer",
        title="Revisor de código",
        triggers=["revisar código", "code review", "qualidade"],
        role="Qualidade e manutenibilidade",
        description="Review de qualidade e riscos.",
        can_do=["Revisar PR/diff", "Apontar riscos", "Sugerir melhorias"],
    ),
    EccAgent(
        id="doc-updater",
        title="Documentador",
        triggers=["notion", "documentar", "wiki", "docs"],
        role="Páginas, memória e documentação",
        description="Documentação e memória de projeto.",
        can_do=["Atualizar docs", "Organizar Notion/wiki", "Capturar decisões"],
    ),
]

CORE_SKILLS: list[EccSkill] = [
    EccSkill(
        id="agentic-os",
        title="Agentic OS",
        triggers=["sistema", "os", "autonomia", "kernel"],
        description="SO multi-agente persistente — kernel, memória, comandos.",
        can_do=["Estruturar SO agentic", "Memória file-first", "Roteamento de agentes"],
    ),
    EccSkill(
        id="continuous-agent-loop",
        title="Loop contínuo",
        triggers=["loop", "autônomo", "contínuo", "repetir"],
        description="Loops agentic que seguem até concluir.",
        can_do=["Rodar loop contínuo", "Retomar tarefa", "Autonomia semi/free"],
    ),
    EccSkill(
        id="browser-qa",
        title="Browser vivo",
        triggers=["browser", "página", "site", "web"],
        description="Navegação e QA em páginas reais.",
        can_do=["Abrir e inspecionar sites", "Fluxos web", "Smoke de UI"],
    ),
    EccSkill(
        id="api-connector-builder",
        title="Construtor de conectores",
        triggers=["api", "conectar", "webhook", "oauth"],
        description="Ligar APIs, OAuth e webhooks ao SO.",
        can_do=["Desenhar conector", "OAuth/webhook", "Mapear capabilities"],
    ),
]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    block = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        if key == "metadata" and val == "":
            continue
        if key.startswith("  ") or key.startswith("\t"):
            continue
        # nested metadata.origin
        if key in {"origin"} and "origin" not in meta:
            meta["origin"] = val
        meta[key] = val
    # metadata: origin: ECC style (two-line)
    for line in block.splitlines():
        m = re.match(r"^\s+origin:\s*(.+)$", line)
        if m:
            meta["origin"] = m.group(1).strip()
    return meta, body


def _can_do_from_text(*parts: str, limit: int = 6) -> list[str]:
    blob = " ".join(p for p in parts if p)
    # bullets do body
    bullets = re.findall(r"^[-*]\s+(.+)$", blob, re.M)
    out: list[str] = []
    for b in bullets:
        t = re.sub(r"\s+", " ", b).strip()
        if 8 <= len(t) <= 120 and t not in out:
            out.append(t)
        if len(out) >= limit:
            return out
    # frases da description
    desc = parts[0] if parts else ""
    for chunk in re.split(r"[.;]", desc):
        t = chunk.strip()
        if 12 <= len(t) <= 140 and t not in out:
            out.append(t[0].upper() + t[1:] if t else t)
        if len(out) >= limit:
            break
    return out[:limit]


def _titleize(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


class EccCatalog:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.agents = {a.id: a for a in CORE_AGENTS}
        self.skills = {s.id: s for s in CORE_SKILLS}
        if root:
            self._hydrate(root)

    def _hydrate(self, root: Path) -> None:
        agents_dir = root / "agents"
        if agents_dir.is_dir():
            for path in sorted(agents_dir.glob("*.md")):
                aid = path.stem
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                meta, body = _parse_frontmatter(text)
                name = str(meta.get("name") or aid)
                desc = str(meta.get("description") or "")
                tools_raw = meta.get("tools") or ""
                tools = (
                    [t.strip() for t in str(tools_raw).split(",") if t.strip()]
                    if tools_raw
                    else []
                )
                role = desc.split(".")[0].strip()[:160] if desc else ""
                # triggers from When to Activate / keywords in body
                triggers = re.findall(r'"([^"]{3,40})"', body)
                triggers = [t.lower() for t in triggers[:12]]
                can_do = _can_do_from_text(desc, body)
                title = _titleize(name) if name == aid else str(name)
                # keep PT titles for core ids
                existing = self.agents.get(aid)
                if existing and existing.source == "core":
                    existing.description = existing.description or desc
                    existing.tools = tools or existing.tools
                    existing.can_do = existing.can_do or can_do
                    existing.source = "vendor"
                    if desc and not existing.role:
                        existing.role = role
                    continue
                self.agents[aid] = EccAgent(
                    id=aid,
                    title=title if title else _titleize(aid),
                    triggers=triggers,
                    role=role,
                    description=desc[:500],
                    tools=tools,
                    can_do=can_do,
                    source="vendor",
                )

        skills_dir = root / "skills"
        if skills_dir.is_dir():
            for path in sorted(skills_dir.iterdir()):
                skill_md = path / "SKILL.md" if path.is_dir() else None
                if not skill_md or not skill_md.is_file():
                    continue
                sid = path.name
                try:
                    text = skill_md.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                meta, body = _parse_frontmatter(text)
                name = str(meta.get("name") or sid)
                desc = str(meta.get("description") or "")
                origin = str(meta.get("origin") or "")
                triggers = re.findall(r'"([^"]{3,40})"', body)
                # also "Use when ..." phrases
                triggers += re.findall(r"User says[^\n]*", body, re.I)[:2]
                triggers = [t.lower()[:40] for t in triggers[:12]]
                can_do = _can_do_from_text(desc, body)
                existing = self.skills.get(sid)
                if existing and existing.source == "core":
                    existing.description = existing.description or desc[:500]
                    existing.can_do = existing.can_do or can_do
                    existing.origin = origin or existing.origin
                    existing.source = "vendor"
                    continue
                self.skills[sid] = EccSkill(
                    id=sid,
                    title=_titleize(name) if name == sid else str(name),
                    triggers=triggers,
                    description=desc[:500],
                    can_do=can_do,
                    origin=origin,
                    source="vendor",
                )

    def match_agents(self, intent: str, limit: int = 3) -> list[EccAgent]:
        t = intent.lower()
        scored: list[tuple[float, EccAgent]] = []
        for agent in self.agents.values():
            score = sum(1.0 for tr in agent.triggers if tr in t)
            if agent.id.replace("-", " ") in t:
                score += 1.5
            if agent.title.lower() in t:
                score += 1.2
            if score:
                scored.append((score, agent))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:limit]]

    def match_skills(self, intent: str, limit: int = 3) -> list[EccSkill]:
        t = intent.lower()
        scored: list[tuple[float, EccSkill]] = []
        for skill in self.skills.values():
            score = sum(1.0 for tr in skill.triggers if tr in t)
            if skill.id.replace("-", " ") in t:
                score += 1.2
            if score:
                scored.append((score, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    def catalog(self) -> dict[str, Any]:
        agents = sorted(self.agents.values(), key=lambda a: a.title.lower())
        skills = sorted(self.skills.values(), key=lambda s: s.title.lower())
        return {
            "product": "ECC",
            "root": str(self.root or ""),
            "agents": [a.model_dump() for a in agents],
            "skills": [s.model_dump() for s in skills],
            "counts": {
                "agents": len(agents),
                "skills": len(skills),
                "vendor_agents": sum(1 for a in agents if a.source == "vendor"),
                "vendor_skills": sum(1 for s in skills if s.source == "vendor"),
            },
            "what_we_can_do": self._overview_can_do(agents, skills),
        }

    def _overview_can_do(self, agents: list[EccAgent], skills: list[EccSkill]) -> list[str]:
        base = [
            "Acionar agentes especialistas no chat (chefe de gabinete, planejador…)",
            "Usar skills ECC como musculatura das formações",
            "Triagem de canais, planos, docs, browser e conectores",
            "Harness agentic com tools conforme a respiração (guided/semi/free)",
        ]
        # amostra das skills mais “produto”
        for sid in (
            "agentic-os",
            "continuous-agent-loop",
            "browser-qa",
            "api-connector-builder",
            "documentation-lookup",
            "content-engine",
            "configure-ecc",
            "openclaw-persona-forge",
            "hermes-imports",
        ):
            s = self.skills.get(sid)
            if s and s.description:
                base.append(f"{s.title}: {s.description.split('.')[0].strip()}")
        # unique preserve order
        out: list[str] = []
        for x in base:
            if x not in out:
                out.append(x)
        return out[:12]

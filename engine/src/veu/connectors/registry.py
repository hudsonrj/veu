from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConnectorKind(str, Enum):
    COMM = "comm"  # mensagens / presença
    MAIL = "mail"
    WORKSPACE = "workspace"  # Notion, Docs, Drive…
    MCP = "mcp"
    API = "api"
    HOST_APP = "host_app"  # app nativo no Windows/Linux via automação
    BRIDGE = "bridge"  # runtime externo: OpenClaw / Hermes / Grok Bot


class Connector(BaseModel):
    """Um nervo: o Véu opera o app/serviço — não o reimplementa."""

    id: str
    name: str
    kind: ConnectorKind
    surface: str  # como o Véu toca: api | mcp | browser | desktop | hybrid
    status: str = "planned"  # planned | ready | live
    capabilities: list[str] = Field(default_factory=list)
    ecc_agents: list[str] = Field(default_factory=list)
    ecc_skills: list[str] = Field(default_factory=list)
    notes: str = ""

    def matches(self, text: str) -> float:
        t = text.lower()
        score = 0.0
        tokens = {self.id, self.name.lower(), *self.capabilities}
        for tok in tokens:
            if tok and tok.lower() in t:
                score += 1.0
        aliases = {
            "whatsapp": ["zap", "wpp", "wa"],
            "teams": ["microsoft teams", "ms teams"],
            "outlook": ["o365", "office 365", "hotmail"],
            "gmail": ["google mail", "e-mail google", "email google"],
            "google-chat": ["google chats", "hangouts", "gchat"],
            "google": ["google workspace", "workspace"],
            "notion": ["wiki", "base de conhecimento"],
            "openrag": ["rag", "ragpro", "base documental", "documentos", "open rag"],
            "grokbot": ["grok bot", "grok", "teammate", "always-on", "handoff"],
            "openclaw": ["claw", "clawhub", "gateway"],
            "hermes": ["nous", "learning loop", "skill distill"],
            "jev": ["typesafe", "system one", "decision"],
            "openai": ["gpt", "chatgpt", "assinatura openai"],
            "claude": ["anthropic", "assinatura claude", "sonnet", "opus"],
            "xai": ["x.ai", "grok", "assinatura xai", "assinatura grok"],
        }
        for alias in aliases.get(self.id, []):
            if alias in t:
                score += 1.2
        return score


class Registry:
    def __init__(self, connectors: list[Connector] | None = None) -> None:
        self._items = {c.id: c for c in (connectors or [])}

    def all(self) -> list[Connector]:
        return list(self._items.values())

    def get(self, connector_id: str) -> Connector | None:
        return self._items.get(connector_id)

    def match(self, intent: str, limit: int = 5) -> list[tuple[Connector, float]]:
        scored = [(c, c.matches(intent)) for c in self._items.values()]
        scored = [(c, s) for c, s in scored if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def as_dict(self) -> dict[str, Any]:
        return {"connectors": [c.model_dump() for c in self.all()]}


def default_registry() -> Registry:
    """Catálogo inicial — músculo da comunidade + APIs oficiais + automação do host."""
    items = [
        Connector(
            id="whatsapp",
            name="WhatsApp",
            kind=ConnectorKind.COMM,
            surface="web",
            status="live",
            capabilities=["qr", "whatsapp-web", "ler", "focar"],
            ecc_agents=["chief-of-staff"],
            ecc_skills=["continuous-agent-loop"],
            notes="WhatsApp Web · QR no celular · janela do SO",
        ),
        Connector(
            id="teams",
            name="Microsoft Teams",
            kind=ConnectorKind.COMM,
            surface="hybrid",
            status="planned",
            capabilities=["canais", "chats", "reuniões", "arquivos"],
            ecc_agents=["chief-of-staff"],
            notes="Graph API + app desktop/browser",
        ),
        Connector(
            id="outlook",
            name="Outlook",
            kind=ConnectorKind.MAIL,
            surface="api",
            status="planned",
            capabilities=["inbox", "rascunhos", "calendário", "triagem"],
            ecc_agents=["chief-of-staff"],
            notes="Microsoft Graph",
        ),
        Connector(
            id="gmail",
            name="Gmail",
            kind=ConnectorKind.MAIL,
            surface="api",
            status="planned",
            capabilities=["inbox", "rascunhos", "labels", "triagem"],
            ecc_agents=["chief-of-staff"],
            notes="Gmail API / gog CLI",
        ),
        Connector(
            id="google-chat",
            name="Google Chat",
            kind=ConnectorKind.COMM,
            surface="api",
            status="planned",
            capabilities=["espaços", "dms", "mencões"],
            ecc_agents=["chief-of-staff"],
        ),
        Connector(
            id="google",
            name="Google Workspace",
            kind=ConnectorKind.WORKSPACE,
            surface="hybrid",
            status="planned",
            capabilities=["drive", "docs", "sheets", "calendar", "meet"],
            ecc_agents=["chief-of-staff", "planner"],
            ecc_skills=["content-engine"],
        ),
        Connector(
            id="notion",
            name="Notion",
            kind=ConnectorKind.WORKSPACE,
            surface="api",
            status="ready",
            capabilities=["páginas", "databases", "busca", "memória"],
            ecc_agents=["doc-updater", "planner"],
            ecc_skills=["documentation-lookup", "context-and-decisions"],
            notes="API Notion — NOTION_TOKEN no .env do kernel",
        ),
        Connector(
            id="openrag",
            name="OpenRAG",
            kind=ConnectorKind.WORKSPACE,
            surface="api",
            status="planned",
            capabilities=["rag", "documentos", "busca", "chat"],
            ecc_agents=["doc-updater", "planner"],
            ecc_skills=["documentation-lookup", "context-and-decisions"],
            notes="OPENRAG_API_KEY + OPENRAG_URL (ragpro.ch8ai.com.br)",
        ),
        Connector(
            id="slack",
            name="Slack",
            kind=ConnectorKind.COMM,
            surface="mcp",
            status="ready",
            capabilities=["canais", "dms", "busca", "canvas"],
            ecc_agents=["chief-of-staff"],
            notes="MCP Slack",
        ),
        Connector(
            id="mcp-bus",
            name="Barramento MCP",
            kind=ConnectorKind.MCP,
            surface="mcp",
            status="ready",
            capabilities=["host", "tools", "resources", "prompts"],
            ecc_skills=["agentic-os", "configure-ecc"],
            notes="Qualquer servidor MCP vira nervo do Véu",
        ),
        Connector(
            id="api-bus",
            name="Barramento de APIs",
            kind=ConnectorKind.API,
            surface="api",
            status="ready",
            capabilities=["http", "oauth", "webhooks"],
            ecc_skills=["api-design", "api-connector-builder"],
        ),
        Connector(
            id="host-desktop",
            name="Máquina (Host)",
            kind=ConnectorKind.HOST_APP,
            surface="desktop",
            status="live",
            capabilities=["abrir", "focar", "calendário", "ler-aba", "shell"],
            ecc_skills=["agentic-os", "browser-qa"],
            notes="Use a janela Máquina no dock — não é card de status",
        ),
        Connector(
            id="openai",
            name="OpenAI",
            kind=ConnectorKind.API,
            surface="hybrid",
            status="ready",
            capabilities=["chat", "gpt", "api-key", "assinatura-chatgpt"],
            notes="API key e/ou ChatGPT Plus — Ajustes → assinaturas",
        ),
        Connector(
            id="claude",
            name="Claude",
            kind=ConnectorKind.API,
            surface="hybrid",
            status="ready",
            capabilities=["chat", "anthropic", "api-key", "assinatura-claude"],
            notes="API key e/ou Claude Pro — Ajustes → assinaturas",
        ),
        Connector(
            id="xai",
            name="Grok",
            kind=ConnectorKind.API,
            surface="hybrid",
            status="ready",
            capabilities=["chat", "grok", "api-key", "assinatura-grok"],
            notes="API key e/ou assinatura Grok — Ajustes → assinaturas",
        ),
        Connector(
            id="jev",
            name="Jev",
            kind=ConnectorKind.API,
            surface="api",
            status="planned",
            capabilities=["choice", "score", "noul", "route", "gate"],
            notes="TypeSafe System One — TYPESAFE_API_KEY; pin jev-1.13.0",
        ),
        Connector(
            id="openclaw",
            name="OpenClaw",
            kind=ConnectorKind.BRIDGE,
            surface="hybrid",
            status="planned",
            capabilities=["gateway", "canais", "tool-harness", "persona"],
            ecc_skills=["openclaw-persona-forge"],
            notes="Harness multi-canal — VEU_OPENCLAW_GATEWAY_URL; ver docs/AI-BRIDGES.md",
        ),
        Connector(
            id="hermes",
            name="Hermes",
            kind=ConnectorKind.BRIDGE,
            surface="hybrid",
            status="planned",
            capabilities=["learning-loop", "skill-distill", "memory-vault"],
            ecc_skills=["hermes-imports"],
            notes="Self-improving loop Nous — HERMES_HOME; ver docs/AI-BRIDGES.md",
        ),
        Connector(
            id="grokbot",
            name="Grok Bot",
            kind=ConnectorKind.BRIDGE,
            surface="api",
            status="planned",
            capabilities=["handoff", "inbound", "always-on", "cloud-pc"],
            ecc_agents=["chief-of-staff", "planner"],
            notes=(
                "Ponte bidirecional Véu↔Grok Bot. "
                "VEU_GROKBOT_WEBHOOK_URL / VEU_GROKBOT_API_BASE / XAI_API_KEY"
            ),
        ),
    ]
    return Registry(items)

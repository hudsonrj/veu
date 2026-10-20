import type { DesktopIcon, WinApp } from "./types";

/**
 * Produto = Véu (o OS). Ruflo = espinha por baixo (não é marca da UI).
 * Linha: Véu → Missão → Chat → Console → Browser
 */
export type IconZoneId = "espinha" | "mente" | "canais" | "workspace";

export type IconZone = {
  id: IconZoneId;
  label: string;
  hint: string;
  apps: WinApp[];
};

/**
 * Apps nativos na constelação do desktop.
 * Links web compatíveis (estilo ruOS Lite) ficam em DESKTOP_WEB_LINKS.
 */
export const DESKTOP_SURFACE: WinApp[] = [
  "ruos",
  "mission",
  "chat",
  "console",
  "registro",
  "playground",
  "chatgpt",
  "claudeai",
  "grok",
  "openrag",
  "notion",
  "inbox",
  "whatsapp",
  "slack",
  "gmail",
  "browser",
  "editor",
  "vscode",
  "rea",
  "esp32",
  "files",
  "servers",
  "settings",
];

/** Atalhos web compatíveis — abrem como aba no Browser do SO (ruOS Lite). */
export type DesktopWebLink = {
  id: string;
  label: string;
  hue: string;
  glyph: string;
  url: string;
  zone: IconZoneId;
  status?: "live" | "ready" | "planned";
};

export const DESKTOP_WEB_LINKS: DesktopWebLink[] = [
  {
    id: "web-github",
    label: "GitHub",
    hue: "#c4b5a0",
    glyph: "GH",
    url: "https://github.com",
    zone: "workspace",
    status: "live",
  },
  {
    id: "web-wiki",
    label: "Wikipedia",
    hue: "#9bb7ff",
    glyph: "Wᵢ",
    url: "https://www.wikipedia.org",
    zone: "workspace",
    status: "live",
  },
  {
    id: "web-calendar",
    label: "Calendar",
    hue: "#4285F4",
    glyph: "Cal",
    url: "https://calendar.google.com",
    zone: "canais",
    status: "ready",
  },
  {
    id: "web-drive",
    label: "Drive",
    hue: "#34A853",
    glyph: "D",
    url: "https://drive.google.com",
    zone: "canais",
    status: "ready",
  },
];

export const ICON_ZONES: IconZone[] = [
  {
    id: "espinha",
    label: "véu",
    hint: "Véu → Missão → Chat → Console",
    apps: ["ruos", "mission", "chat", "console", "registro"],
  },
  {
    id: "mente",
    label: "mente",
    hint: "IAs nativas + Notion",
    apps: ["playground", "chatgpt", "claudeai", "grok", "openrag", "notion"],
  },
  {
    id: "canais",
    label: "canais",
    hint: "mensagens e Google",
    apps: ["inbox", "whatsapp", "slack", "gmail"],
  },
  {
    id: "workspace",
    label: "workspace",
    hint: "Browser + editor + REA + placa + remote",
    apps: [
      "browser",
      "editor",
      "vscode",
      "rea",
      "esp32",
      "files",
      "servers",
      "settings",
    ],
  },
];

/** Hub de cada zona — âncora visual. */
export const ZONE_HUB: Record<IconZoneId, WinApp> = {
  espinha: "ruos",
  mente: "playground",
  canais: "inbox",
  workspace: "browser",
};

export const ZONE_HUE: Record<IconZoneId, string> = {
  espinha: "#e8c27a",
  mente: "#7fe7d4",
  canais: "#9bb7ff",
  workspace: "#c4b5a0",
};

export type AgentFeed = {
  from: WinApp;
  to: WinApp;
  /** feed = dados/fluxo; talk = diálogo; sync = estado compartilhado */
  kind: "feed" | "talk" | "sync";
};

/**
 * Poucas ligações — só a linha + hub→satélite.
 * (Antes: ~50 arcos cruzados = embolado.)
 */
export const AGENT_FEEDS: AgentFeed[] = [
  { from: "ruos", to: "mission", kind: "sync" },
  { from: "mission", to: "chat", kind: "talk" },
  { from: "chat", to: "console", kind: "feed" },
  { from: "playground", to: "chat", kind: "feed" },
  { from: "chatgpt", to: "playground", kind: "feed" },
  { from: "claudeai", to: "playground", kind: "feed" },
  { from: "grok", to: "playground", kind: "feed" },
  { from: "openrag", to: "playground", kind: "feed" },
  { from: "notion", to: "playground", kind: "feed" },
  { from: "inbox", to: "chat", kind: "feed" },
  { from: "whatsapp", to: "inbox", kind: "feed" },
  { from: "slack", to: "inbox", kind: "feed" },
  { from: "gmail", to: "inbox", kind: "feed" },
  { from: "browser", to: "ruos", kind: "sync" },
  { from: "rea", to: "browser", kind: "feed" },
  { from: "esp32", to: "ruos", kind: "sync" },
  { from: "files", to: "browser", kind: "feed" },
  { from: "servers", to: "console", kind: "sync" },
  { from: "settings", to: "ruos", kind: "sync" },
];

export const DESKTOP_ICONS: DesktopIcon[] = [
  { app: "ruflo", label: "Espinha", hue: "#79dfff", glyph: "◈", status: "live" },
  { app: "ruos", label: "Véu", hue: "#e8c27a", glyph: "◈", status: "live" },
  { app: "console", label: "Console", hue: "#7fe7d4", glyph: "›", status: "live" },
  { app: "registro", label: "Registro", hue: "#79dfff", glyph: "☰", status: "live" },
  { app: "control", label: "Controle", hue: "#f0a8a0", glyph: "⏹", status: "live" },
  { app: "data", label: "Seus dados", hue: "#7FE7D4", glyph: "◇", status: "live" },
  { app: "billing", label: "Assinaturas", hue: "#e8c27a", glyph: "¤", status: "live" },
  { app: "projects", label: "Projetos", hue: "#7fe7d4", glyph: "▣", status: "live" },
  { app: "togo", label: "Véu To Go", hue: "#c4b5a0", glyph: "⇄", status: "live" },
  { app: "mission", label: "Missão", hue: "#e8c27a", glyph: "◎", status: "live" },
  { app: "chat", label: "Chat", hue: "#e8c27a", glyph: "✦", status: "live" },
  { app: "ecosystem", label: "Ecossistema", hue: "#7fe7d4", glyph: "◎", status: "live" },
  { app: "companies", label: "Empresas", hue: "#E8C27A", glyph: "▣", status: "live" },
  { app: "agenda", label: "Agenda", hue: "#E8C27A", glyph: "◉", status: "live" },
  { app: "grokbot", label: "Grok Bot", hue: "#F0D7A2", glyph: "GB", status: "live" },
  { app: "hermes", label: "Hermes", hue: "#8FBF9F", glyph: "H", status: "live" },
  { app: "ecc", label: "ECC", hue: "#9EC9B0", glyph: "Σ", status: "live" },
  { app: "approvals", label: "Aprovações", hue: "#E8C27A", glyph: "✓", status: "live" },
  { app: "credentials", label: "Credenciais", hue: "#F0A8A0", glyph: "⌁", status: "live" },
  { app: "decisions", label: "Decisões", hue: "#E8C27A", glyph: "◎", status: "live" },
  { app: "productivity", label: "Produtividade", hue: "#7FE7D4", glyph: "◈", status: "live" },
  { app: "clone", label: "Clone", hue: "#A8E0D0", glyph: "◎", status: "live" },
  { app: "mental", label: "Saúde mental", hue: "#C4A8D8", glyph: "♡", status: "live" },
  { app: "routines", label: "Rotinas", hue: "#9EC9B0", glyph: "↻", status: "live" },
  { app: "settings", label: "Ajustes", hue: "#A8B4C0", glyph: "⚙", status: "live" },
  { app: "host", label: "Máquina", hue: "#D4B896", glyph: "⌘", status: "live" },
  { app: "playground", label: "Playground", hue: "#9EC9B0", glyph: "▷", status: "live" },
  { app: "chatgpt", label: "ChatGPT", hue: "#10A37F", glyph: "G", status: "live" },
  { app: "claudeai", label: "Claude", hue: "#D4A27F", glyph: "C", status: "live" },
  { app: "grok", label: "Grok", hue: "#E8C27A", glyph: "✶", status: "live" },
  { app: "codex", label: "Codex", hue: "#0D8C6C", glyph: "{ }", status: "live" },
  { app: "claudework", label: "Work", hue: "#C4895E", glyph: "W", status: "live" },
  { app: "notion", label: "Notion", hue: "#E8E8E8", glyph: "N", status: "live" },
  { app: "openrag", label: "OpenRAG", hue: "#7FE7D4", glyph: "R", status: "live" },
  { app: "asklife", label: "Minha vida", hue: "#7FE7D4", glyph: "?", status: "live" },
  { app: "usage", label: "Custos", hue: "#E8C27A", glyph: "$", status: "live" },
  { app: "mcp", label: "MCP", hue: "#A8B4C0", glyph: "M", status: "live" },
  { app: "inbox", label: "Inbox", hue: "#7FE7D4", glyph: "✉", status: "live" },
  { app: "whatsapp", label: "WhatsApp", hue: "#25D366", glyph: "W", status: "live" },
  { app: "slack", label: "Slack", hue: "#E01E5A", glyph: "S", status: "ready" },
  { app: "teams", label: "Teams", hue: "#6264A7", glyph: "T", status: "planned" },
  { app: "outlook", label: "Outlook", hue: "#0078D4", glyph: "O", status: "planned" },
  { app: "gmail", label: "Gmail", hue: "#EA4335", glyph: "G", status: "planned" },
  { app: "gchat", label: "Chat", hue: "#34A853", glyph: "C", status: "planned" },
  { app: "servers", label: "Servidores", hue: "#7FE7D4", glyph: "▣", status: "live" },
  { app: "studio", label: "Studio", hue: "#7FE7D4", glyph: "◇", status: "live" },
  { app: "files", label: "Arquivos", hue: "#c4b5a0", glyph: "F", status: "live" },
  { app: "editor", label: "Editor", hue: "#ce9178", glyph: "NP", status: "live" },
  { app: "vscode", label: "VS Code", hue: "#007ACC", glyph: "</>", status: "live" },
  { app: "rea", label: "REA", hue: "#9bb7ff", glyph: "RE", status: "live" },
  { app: "esp32", label: "Placa", hue: "#e8c27a", glyph: "▣", status: "live" },
  { app: "browser", label: "Browser", hue: "#9bb7ff", glyph: "B", status: "live" },
  { app: "google", label: "Workspace", hue: "#FBBC05", glyph: "g", status: "ready" },
];

export const ICON_BY_APP: Record<string, DesktopIcon> = Object.fromEntries(
  DESKTOP_ICONS.map((i) => [i.app, i]),
);

export const APP_TITLES: Record<WinApp, string> = {
  ruflo: "Espinha · Ruflo no Véu",
  ruos: "Véu · o SO",
  console: "Console · AI · Host · SSH",
  registro: "Registro · log ao vivo",
  billing: "Assinaturas e custos",
  projects: "Projetos · inventário",
  mission: "Missão · Véu",
  chat: "Chat · Véu",
  ecosystem: "Ecossistema",
  grokbot: "Grok Bot · dia a dia",
  hermes: "Hermes · learning loop",
  companies: "Empresas · projetos",
  servers: "Servidores · frota",
  agenda: "Agenda · fila viva",
  studio: "Studio · arquivos",
  ecc: "ECC · músculo do SO",
  playground: "Playground · IAs",
  chatgpt: "ChatGPT",
  claudeai: "Claude",
  grok: "Grok",
  codex: "Codex",
  claudework: "Claude Work",
  files: "Arquivos",
  editor: "Editor · Notepad++",
  vscode: "VS Code · Remote",
  rea: "REA · reverse → GitHub",
  esp32: "Placa · ESP32 CYD",
  browser: "Browser · Véu",
  whatsapp: "WhatsApp",
  teams: "Microsoft Teams",
  outlook: "Outlook",
  gmail: "Gmail",
  gchat: "Google Chat",
  google: "Google Workspace",
  notion: "Notion",
  slack: "Slack",
  openrag: "OpenRAG",
  asklife: "Pergunte à minha vida",
  usage: "Custos · uso",
  togo: "Véu To Go · portátil",
  approvals: "Aprovações · risco",
  credentials: "Credenciais · health",
  inbox: "Inbox unificada",
  decisions: "Diário de decisões",
  productivity: "Produtividade · indicadores",
  clone: "Clone · personalidade",
  mental: "Saúde mental · alertas",
  routines: "Rotinas · automações",
  mcp: "Barramento MCP",
  api: "APIs",
  host: "Máquina física",
  settings: "Ajustes",
  control: "Central de controle",
  data: "Seus dados",
};

/** Grupos de nervos no painel Ajustes. */
export const NERVE_GROUPS: { id: string; label: string; match: (id: string, kind: string) => boolean }[] = [
  {
    id: "pontes",
    label: "pontes IA",
    match: (id) => ["grokbot", "openclaw", "hermes"].includes(id),
  },
  {
    id: "assinaturas",
    label: "assinaturas",
    match: (id) =>
      ["openai", "claude", "xai", "chatgpt", "claudeai", "grok", "codex", "claudework"].includes(id),
  },
  {
    id: "mente",
    label: "mente",
    match: (id) => ["notion", "openrag", "mcp-bus", "mcp"].includes(id),
  },
  {
    id: "canais",
    label: "canais",
    match: (id) =>
      ["whatsapp", "slack", "teams", "outlook", "gmail", "google-chat", "gchat", "google"].includes(id),
  },
  {
    id: "host",
    label: "host & APIs",
    match: (id, kind) =>
      ["host-desktop", "api-bus", "api"].includes(id) || kind === "api" || kind === "desktop",
  },
];

export function defaultGeom(app: WinApp, index: number) {
  const offset = (index % 5) * 18;
  if (app === "ruflo" || app === "ruos") {
    return { x: 24 + offset, y: 20 + offset, w: 820, h: 580 };
  }
  if (app === "console") {
    return { x: 72 + offset, y: 48 + offset, w: 880, h: 560 };
  }
  if (app === "registro") {
    return { x: 80 + offset, y: 40 + offset, w: 860, h: 560 };
  }
  if (app === "browser") {
    return { x: 64 + offset, y: 36 + offset, w: 960, h: 640 };
  }
  if (app === "rea") {
    return { x: 56 + offset, y: 32 + offset, w: 920, h: 640 };
  }
  if (app === "esp32") {
    return { x: 48 + offset, y: 28 + offset, w: 900, h: 620 };
  }
  if (app === "mission") {
    return { x: 36 + offset, y: 28 + offset, w: 920, h: 620 };
  }
  if (app === "grokbot") {
    return { x: 48 + offset, y: 36 + offset, w: 1080, h: 680 };
  }
  if (app === "settings") {
    return { x: 48 + offset, y: 40 + offset, w: 860, h: 560 };
  }
  if (app === "ecc") {
    return { x: 56 + offset, y: 36 + offset, w: 900, h: 600 };
  }
  if (app === "playground") {
    return { x: 72 + offset, y: 36 + offset, w: 920, h: 620 };
  }
  if (app === "companies" || app === "productivity" || app === "clone" || app === "mental") {
    return { x: 40 + offset, y: 28 + offset, w: 980, h: 640 };
  }
  if (app === "servers") {
    return { x: 56 + offset, y: 32 + offset, w: 960, h: 620 };
  }
  if (app === "agenda" || app === "hermes" || app === "studio") {
    return { x: 64 + offset, y: 32 + offset, w: 900, h: 600 };
  }
  if (
    app === "chatgpt" ||
    app === "claudeai" ||
    app === "grok" ||
    app === "codex" ||
    app === "claudework"
  ) {
    return { x: 120 + offset, y: 40 + offset, w: 520, h: 560 };
  }
  const wide = app === "ecosystem" || app === "chat" || app === "files";
  return {
    x: 200 + offset,
    y: 48 + offset,
    w: wide ? 720 : 480,
    h: wide ? 520 : 400,
  };
}

/**
 * 11.1 — Manifesto de app: registro único para lançador/dock.
 * Permissões default off; concessão na central de controle (9.8).
 */
import type { WinApp } from "./types";
import { APP_TITLES, DESKTOP_ICONS } from "./catalog";

export type AppPermission =
  | "conector:gmail:ler"
  | "conector:whatsapp:ler"
  | "conector:notion:ler"
  | "host:shell"
  | "host:files"
  | "mcp:call"
  | "llm:chat"
  | "rag:ask"
  | "servers:ssh";

export type AppManifest = {
  id: WinApp;
  nome: string;
  icone: string;
  grupo: "espinha" | "mente" | "canais" | "workspace" | "sistema" | "custos";
  entrada: "component";
  tamanho_padrao: { w: number; h: number };
  permissoes: AppPermission[];
  singleton: boolean;
  hue: string;
};

const SIZE: Record<string, { w: number; h: number }> = {
  chat: { w: 520, h: 640 },
  browser: { w: 900, h: 640 },
  console: { w: 720, h: 480 },
  mission: { w: 860, h: 620 },
  settings: { w: 640, h: 560 },
  default: { w: 720, h: 520 },
};

function iconMeta(app: WinApp) {
  return DESKTOP_ICONS.find((i) => i.app === app);
}

function build(app: WinApp, grupo: AppManifest["grupo"], permissoes: AppPermission[] = []): AppManifest {
  const meta = iconMeta(app);
  return {
    id: app,
    nome: APP_TITLES[app] || app,
    icone: meta?.glyph || "·",
    grupo,
    entrada: "component",
    tamanho_padrao: SIZE[app] || SIZE.default,
    permissoes,
    singleton: true,
    hue: meta?.hue || "#e8c27a",
  };
}

/** Registro completo dos apps atuais — visual/comportamento inalterados. */
export const APP_MANIFEST: AppManifest[] = [
  build("ruos", "espinha"),
  build("mission", "espinha"),
  build("chat", "espinha", ["llm:chat"]),
  build("console", "espinha", ["host:shell", "servers:ssh"]),
  build("registro", "espinha"),
  build("ruflo", "espinha"),
  build("playground", "mente", ["llm:chat"]),
  build("chatgpt", "mente", ["llm:chat"]),
  build("claudeai", "mente", ["llm:chat"]),
  build("grok", "mente", ["llm:chat"]),
  build("codex", "mente", ["llm:chat"]),
  build("openrag", "mente", ["rag:ask"]),
  build("asklife", "mente", ["rag:ask"]),
  build("ecc", "mente"),
  build("hermes", "mente"),
  build("grokbot", "mente"),
  build("inbox", "canais", ["conector:gmail:ler", "conector:whatsapp:ler"]),
  build("whatsapp", "canais", ["conector:whatsapp:ler"]),
  build("slack", "canais"),
  build("teams", "canais"),
  build("outlook", "canais", ["conector:gmail:ler"]),
  build("gmail", "canais", ["conector:gmail:ler"]),
  build("gchat", "canais"),
  build("notion", "canais", ["conector:notion:ler"]),
  build("browser", "workspace"),
  build("editor", "workspace"),
  build("vscode", "workspace"),
  build("files", "workspace", ["host:files"]),
  build("servers", "workspace", ["servers:ssh"]),
  build("host", "workspace", ["host:shell", "host:files"]),
  build("rea", "workspace"),
  build("esp32", "workspace"),
  build("mcp", "workspace", ["mcp:call"]),
  build("api", "workspace"),
  build("google", "workspace"),
  build("claudework", "workspace"),
  build("companies", "workspace"),
  build("agenda", "workspace"),
  build("studio", "workspace"),
  build("ecosystem", "sistema"),
  build("settings", "sistema"),
  build("approvals", "sistema"),
  build("credentials", "sistema"),
  build("decisions", "sistema"),
  build("routines", "sistema"),
  build("productivity", "sistema"),
  build("clone", "sistema"),
  build("mental", "sistema"),
  build("usage", "custos"),
  build("togo", "sistema"),
];

const BY_ID = new Map(APP_MANIFEST.map((m) => [m.id, m]));

export function getAppManifest(id: WinApp): AppManifest | undefined {
  return BY_ID.get(id);
}

const GRANTS_KEY = "veu-app-grants";

/** Concessões persistidas localmente até a central 9.8 no servidor. */
export function loadGrants(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(GRANTS_KEY) || "{}") as Record<string, boolean>;
  } catch {
    return {};
  }
}

export function saveGrants(grants: Record<string, boolean>): void {
  localStorage.setItem(GRANTS_KEY, JSON.stringify(grants));
}

export function hasPermission(app: WinApp, grantOverride?: Record<string, boolean>): { ok: boolean; missing: AppPermission[] } {
  const m = getAppManifest(app);
  if (!m || m.permissoes.length === 0) return { ok: true, missing: [] };
  // Sem política salva ainda: não bloqueia (até a central 9.8 gravar concessões).
  if (!grantOverride && localStorage.getItem(GRANTS_KEY) === null) {
    return { ok: true, missing: [] };
  }
  const grants = grantOverride || loadGrants();
  const missing = m.permissoes.filter((p) => !grants[p]);
  return { ok: missing.length === 0, missing };
}

export function dockPinned(): WinApp[] {
  try {
    const raw = localStorage.getItem("veu-dock-pinned");
    if (raw) return JSON.parse(raw) as WinApp[];
  } catch {
    /* ignore */
  }
  return [
    "ruos",
    "mission",
    "chat",
    "console",
    "browser",
    "chatgpt",
    "claudeai",
    "grok",
    "playground",
    "notion",
    "openrag",
    "inbox",
    "whatsapp",
    "gmail",
    "rea",
    "files",
    "servers",
    "settings",
  ];
}

export function setDockPinned(apps: WinApp[]): void {
  localStorage.setItem("veu-dock-pinned", JSON.stringify(apps));
}

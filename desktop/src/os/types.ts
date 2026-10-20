export type WinId = string;

export type WinApp =
  | "mission"
  | "chat"
  | "ecosystem"
  | "whatsapp"
  | "teams"
  | "outlook"
  | "gmail"
  | "gchat"
  | "google"
  | "notion"
  | "slack"
  | "openrag"
  | "mcp"
  | "api"
  | "host"
  | "files"
  | "editor"
  | "vscode"
  | "browser"
  | "grokbot"
  | "ecc"
  | "chatgpt"
  | "claudeai"
  | "grok"
  | "codex"
  | "claudework"
  | "playground"
  | "hermes"
  | "agenda"
  | "studio"
  | "companies"
  | "servers"
  | "usage"
  | "billing"
  | "projects"
  | "credentials"
  | "approvals"
  | "asklife"
  | "inbox"
  | "decisions"
  | "routines"
  | "productivity"
  | "clone"
  | "mental"
  | "ruflo"
  | "ruos"
  | "console"
  | "registro"
  | "control"
  | "togo"
  | "data"
  | "settings"
  | "rea"
  | "esp32";

export type OsWindow = {
  id: WinId;
  app: WinApp;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
  minimized: boolean;
};

export type DesktopIcon = {
  app: WinApp;
  label: string;
  hue: string;
  glyph: string;
  status?: "live" | "ready" | "planned";
};

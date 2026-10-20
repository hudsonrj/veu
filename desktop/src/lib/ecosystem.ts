/** Agentes e nervos visíveis no desktop — ecossistema do SO. */

export type EcoNode = {
  id: string;
  label: string;
  kind: "kernel" | "agent" | "nerve" | "model";
  x: number; // 0–1 relative
  y: number;
};

export type EcoLink = {
  from: string;
  to: string;
};

export type AppIcon = {
  id: string;
  label: string;
  status: "live" | "ready" | "planned";
  hue: string;
  glyph: string; // simple letter/mark drawn in SVG
};

export const ECO_NODES: EcoNode[] = [
  { id: "kernel", label: "véu", kind: "kernel", x: 0.5, y: 0.48 },
  { id: "chief", label: "gabinete", kind: "agent", x: 0.22, y: 0.28 },
  { id: "planner", label: "plano", kind: "agent", x: 0.78, y: 0.28 },
  { id: "architect", label: "arquiteto", kind: "agent", x: 0.18, y: 0.62 },
  { id: "docs", label: "docs", kind: "agent", x: 0.82, y: 0.62 },
  { id: "openai", label: "openai", kind: "model", x: 0.5, y: 0.16 },
  { id: "jev", label: "jev", kind: "model", x: 0.62, y: 0.22 },
  { id: "ollama", label: "ollama", kind: "model", x: 0.35, y: 0.82 },
  { id: "openrag", label: "openrag", kind: "model", x: 0.65, y: 0.82 },
  { id: "notion", label: "notion", kind: "nerve", x: 0.88, y: 0.45 },
  { id: "comms", label: "comms", kind: "nerve", x: 0.12, y: 0.45 },
  { id: "openclaw", label: "openclaw", kind: "nerve", x: 0.28, y: 0.12 },
  { id: "hermes", label: "hermes", kind: "nerve", x: 0.72, y: 0.12 },
  { id: "grokbot", label: "grok bot", kind: "nerve", x: 0.5, y: 0.92 },
];

export const ECO_LINKS: EcoLink[] = [
  { from: "openai", to: "kernel" },
  { from: "jev", to: "kernel" },
  { from: "ollama", to: "kernel" },
  { from: "openrag", to: "kernel" },
  { from: "kernel", to: "chief" },
  { from: "kernel", to: "planner" },
  { from: "kernel", to: "architect" },
  { from: "kernel", to: "docs" },
  { from: "chief", to: "comms" },
  { from: "docs", to: "notion" },
  { from: "planner", to: "docs" },
  { from: "chief", to: "planner" },
  { from: "openclaw", to: "comms" },
  { from: "openclaw", to: "kernel" },
  { from: "hermes", to: "kernel" },
  { from: "hermes", to: "planner" },
  { from: "kernel", to: "grokbot" },
  { from: "chief", to: "grokbot" },
];

export const APP_ICONS: AppIcon[] = [
  { id: "whatsapp", label: "WhatsApp", status: "live", hue: "#25D366", glyph: "W" },
  { id: "teams", label: "Teams", status: "planned", hue: "#6264A7", glyph: "T" },
  { id: "outlook", label: "Outlook", status: "planned", hue: "#0078D4", glyph: "O" },
  { id: "gmail", label: "Gmail", status: "planned", hue: "#EA4335", glyph: "G" },
  { id: "gchat", label: "Google Chat", status: "planned", hue: "#34A853", glyph: "C" },
  { id: "google", label: "Workspace", status: "planned", hue: "#FBBC05", glyph: "g" },
  { id: "notion", label: "Notion", status: "ready", hue: "#E8C27A", glyph: "N" },
  { id: "slack", label: "Slack", status: "ready", hue: "#E01E5A", glyph: "S" },
  { id: "openrag", label: "OpenRAG", status: "ready", hue: "#7FE7D4", glyph: "R" },
  { id: "mcp", label: "MCP", status: "ready", hue: "#A8B4C0", glyph: "M" },
  { id: "ecc", label: "ECC", status: "live", hue: "#9EC9B0", glyph: "Σ" },
  { id: "api", label: "APIs", status: "ready", hue: "#9BB7FF", glyph: "A" },
  { id: "host", label: "Host apps", status: "planned", hue: "#C4B5A0", glyph: "H" },
  { id: "openclaw", label: "OpenClaw", status: "planned", hue: "#D4A574", glyph: "C" },
  { id: "hermes", label: "Hermes", status: "planned", hue: "#8FBF9F", glyph: "H" },
  { id: "grokbot", label: "Grok Bot", status: "ready", hue: "#E8C27A", glyph: "X" },
];

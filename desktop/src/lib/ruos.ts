import { apiFetch, KERNEL } from "./kernel";

export type RuosDesktop = {
  id: string;
  name: string;
  kind: string;
  profile?: string;
  state: string;
  host?: string;
  viewer?: string | null;
  heartbeat_at?: number | null;
  stop_at_hint?: string;
  agents?: number;
  tags?: string[];
  lite?: Record<string, unknown>;
  rustdesk_id?: string;
  note?: string;
};

export type RuosBoard = {
  ok: boolean;
  desktops: RuosDesktop[];
  counts: Record<string, number>;
  lite_session?: Record<string, unknown>;
  mcp?: { url?: string; configured?: boolean };
  actions?: string[];
  copy?: Record<string, string>;
};

export type RuosKeys = {
  ok: boolean;
  vault: string;
  model_keys: {
    present: Record<string, boolean>;
    slots: string[];
    meta_llm: string;
    any: boolean;
    copy: string;
    empty_hint: string;
  };
  routing: {
    mode: string;
    current: string;
    keys_present_llm: boolean;
    copy: string;
    options: { id: string; label: string }[];
    provider?: string;
  };
  custom_keys: { id: string; name: string }[];
  website_signins: { id: string; site: string; username: string }[];
  mcp_tokens: { id: string; label: string; scope: string; fp?: string }[];
  slack: { enabled: boolean; webhook_set: boolean };
  tailscale: { set: boolean; fp?: string | null };
};

export type RufloSnapshot = {
  pulse: {
    theme?: string;
    palette?: string;
    control?: { level?: string; approval?: string; active?: boolean };
    swarm?: { active?: boolean; agents?: { id: string; role: string; status: string }[]; topology?: string };
    plugins?: { total: number; enabled: number; by_category?: Record<string, number>; core?: string[] };
    missions?: { open: number; total: number };
    architecture?: string[];
    assets?: Record<string, string>;
    cli?: { available?: boolean; version?: string | null };
  };
  plugins: {
    id: string;
    name: string;
    category: string;
    description: string;
    enabled: boolean;
  }[];
  missions: { id: string; goal: string; status: string; ts: number }[];
  architecture: { spine: string; flow: string[]; source: string };
  events: { ts: number; kind: string }[];
};

export async function fetchRuosBoard(q = ""): Promise<RuosBoard | null> {
  try {
    const r = await apiFetch(`${KERNEL}/ruos/desktops?q=${encodeURIComponent(q)}`);
    if (!r.ok) return null;
    return (await r.json()) as RuosBoard;
  } catch {
    return null;
  }
}

export async function fetchRuosKeys(): Promise<RuosKeys | null> {
  try {
    const r = await apiFetch(`${KERNEL}/ruos/keys`);
    if (!r.ok) return null;
    return (await r.json()) as RuosKeys;
  } catch {
    return null;
  }
}

export async function fetchRuflo(): Promise<RufloSnapshot | null> {
  try {
    const r = await apiFetch(`${KERNEL}/ruflo`);
    if (!r.ok) return null;
    return (await r.json()) as RufloSnapshot;
  } catch {
    return null;
  }
}

export async function ruosPost(path: string, body?: Record<string, unknown>) {
  const r = await apiFetch(`${KERNEL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

export async function rufloPost(path: string, body?: Record<string, unknown>) {
  return ruosPost(path, body);
}

/** Slash actions do AI Console (ruOS / ruflo). */
export const CONSOLE_ACTIONS = [
  { id: "/run", hint: "run a shell command on the selected desktop" },
  { id: "/install", hint: "install an allowlisted app" },
  { id: "/status", hint: "desktop + swarm status" },
  { id: "/open", hint: "open a URL or app window" },
  { id: "/swarm", hint: "init or inspect swarm" },
  { id: "/cluster", hint: "cluster dispatch across fleet" },
  { id: "/fleet", hint: "list desktops in fleet" },
] as const;

export const CONSOLE_APPS = [
  "@browser",
  "@vscode",
  "@chatgpt",
  "@claude",
  "@files",
  "@terminal",
  "@ruflo",
] as const;

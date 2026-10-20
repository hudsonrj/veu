import type { AutonomyBreath } from "../components/AutonomyOrbit";
import { clearPrivateCaches } from "./sw-cache";

/** Prefer env; no browser, fall back to local kernel. Same-origin when env empty. */
function resolveKernel(): string {
  const fromEnv = (import.meta.env.VITE_VEU_KERNEL as string | undefined)?.replace(
    /\/$/,
    "",
  );
  if (fromEnv) return fromEnv;
  if (typeof window !== "undefined" && window.location?.origin) {
    // Caddy em veu.ch8ai.com.br proxy /chat → :8821
    return window.location.origin;
  }
  return "http://127.0.0.1:8821";
}

const KERNEL = resolveKernel();

/** Fetch autenticado — cookie de sessão + CSRF header em mutations. */
export async function apiFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (method !== "GET" && method !== "HEAD" && !headers.has("X-Veu-CSRF")) {
    headers.set("X-Veu-CSRF", "1");
  }
  const res = await fetch(input, {
    ...init,
    headers,
    credentials: "include",
  });
  if (
    res.status === 401 &&
    typeof window !== "undefined" &&
    !input.includes("/auth/")
  ) {
    void clearPrivateCaches();
    window.dispatchEvent(new CustomEvent("veu:auth-required"));
  }
  return res;
}

export type AuthStatus = {
  ok: boolean;
  configured: boolean;
  authenticated: boolean;
  subject?: string | null;
  methods?: { password?: boolean; google?: boolean };
  google_client_id?: string | null;
};

export async function fetchAuthStatus(): Promise<AuthStatus | null> {
  try {
    const res = await fetch(`${KERNEL}/auth/status`, { credentials: "include" });
    if (!res.ok) return null;
    return (await res.json()) as AuthStatus;
  } catch {
    return null;
  }
}

export async function loginWithPassword(password: string): Promise<boolean> {
  const res = await fetch(`${KERNEL}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Veu-CSRF": "1" },
    body: JSON.stringify({ password }),
  });
  return res.ok;
}

export function googleLoginUrl(): string {
  return `${KERNEL}/auth/google`;
}

export async function logoutSession(): Promise<void> {
  try {
    await fetch(`${KERNEL}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: { "X-Veu-CSRF": "1" },
    });
  } finally {
    await clearPrivateCaches();
  }
}

export type ChatEvent =
  | { type: "thinking"; text: string }
  | { type: "status"; text: string }
  | {
      type: "harness";
      active: boolean;
      session?: { id: string; tools: string[]; risk_ceiling: string; route: string };
    }
  | { type: "plan"; formation: FormationPayload }
  | { type: "step"; index: number; step: { id: string; label: string; actor: string }; state: string }
  | { type: "reply"; text: string }
  | {
      type: "action";
      action?: string;
      url?: string;
      app?: string;
      payload?: Record<string, unknown>;
    }
  | { type: "done"; formation: FormationPayload };

export type FormationPayload = {
  intent: string;
  breath: string;
  kind: string;
  title: string;
  reply: string;
  connectors: { id: string; name: string; surface: string; status: string }[];
  agents: { id: string; title: string; role: string }[];
  skills: { id: string; title: string }[];
  steps: { id: string; label: string; actor: string }[];
  status: string;
};

export type KernelPulse = {
  ok: boolean;
  status?: string;
  product?: string;
  error?: string;
};

export type MissionAction = {
  id: string;
  label: string;
  intent: string;
  agent?: string;
};

export type MissionProject = {
  id: string;
  intent: string;
  route: string;
  kind: string;
  state: string;
  breath?: string;
  tools: string[];
  risk?: string;
  ts?: number;
  ended?: number;
};

export type MissionAgent = {
  id: string;
  title: string;
  role: string;
  triggers?: string[];
};

export type FlightCheck = {
  name: string;
  ok: boolean;
  detail: string;
  critical: boolean;
  status: string;
};

export type FlightBoard = {
  status: string;
  go: boolean;
  summary: string;
  checks: FlightCheck[];
  critical_failures: string[];
  holds: string[];
};

export type MissionJob = {
  id: string;
  intent?: string;
  route?: string;
  state?: string;
  breath?: string;
  progress?: { phase?: string; percent?: number | null; message?: string };
  has_report?: boolean;
  result?: { summary?: string };
  error?: string | null;
};

export type MissionSnapshot = {
  status: string;
  harness: { active: boolean; session: Record<string, unknown> | null };
  projects: MissionProject[];
  agents: MissionAgent[];
  nerves: { id: string; name: string; status: string; kind: string }[];
  jev: { status?: string; model?: string; name?: string };
  bridges: Record<string, { status?: string; name?: string }>;
  memory: { sessions?: number; decisions?: number; audit_events?: number };
  llm: Record<string, unknown>;
  actions: MissionAction[];
  flight?: FlightBoard;
  jobs?: MissionJob[];
  job_counts?: Record<string, number>;
};

export async function fetchFlight(): Promise<FlightBoard | null> {
  try {
    const res = await fetch(`${KERNEL}/ready`);
    if (!res.ok) return null;
    return (await res.json()) as FlightBoard;
  } catch {
    return null;
  }
}

export async function fetchMission(): Promise<MissionSnapshot | null> {
  try {
    const res = await apiFetch(`${KERNEL}/mission`);
    if (!res.ok) return null;
    return (await res.json()) as MissionSnapshot;
  } catch {
    return null;
  }
}

export type SubscriptionSlot = {
  id: "openai" | "claude" | "xai";
  name: string;
  product?: string;
  status: string;
  configured: boolean;
  auth_mode?: "api_key" | "subscription" | "both";
  modes?: {
    api_key: {
      available: boolean;
      configured: boolean;
      key_env: string;
      key_masked: string;
      hint: string;
    };
    subscription: {
      available: boolean;
      status: string;
      configured: boolean;
      login_url: string;
      hint: string;
      linked_at?: string | null;
    };
  };
  key_env: string;
  model_env: string;
  model: string;
  key_masked: string;
  hint: string;
};

export async function fetchSubscriptions(): Promise<SubscriptionSlot[]> {
  try {
    const res = await apiFetch(`${KERNEL}/subscriptions`);
    if (!res.ok) return [];
    const data = (await res.json()) as { subscriptions?: SubscriptionSlot[] };
    return data.subscriptions || [];
  } catch {
    return [];
  }
}

export async function connectSubscription(
  provider: "openai" | "claude" | "xai",
  apiKey: string,
  model?: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/subscriptions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        api_key: apiKey,
        model: model || undefined,
      }),
    });
    if (!res.ok) {
      const detail = await res.text();
      return { ok: false, error: detail.slice(0, 200) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

/** Login de assinatura — NUNCA a home do chat. */
export const SUBSCRIPTION_LOGIN_URL: Record<
  "openai" | "claude" | "xai",
  string
> = {
  openai: "https://chatgpt.com/auth/login",
  claude: "https://claude.ai/login",
  xai: "https://accounts.x.ai/sign-in",
};

/** Chat do produto — só para modo assinatura (compose), não para “ligar”. */
export const SUBSCRIPTION_CHAT_URL: Record<"openai" | "claude" | "xai", string> =
  {
    openai: "https://chatgpt.com/",
    claude: "https://claude.ai/new",
    xai: "https://grok.com/",
  };

function looksLikeChatHome(url: string): boolean {
  try {
    const u = new URL(url);
    const path = (u.pathname || "/").replace(/\/+$/, "") || "/";
    // homes e “new chat” sem /auth|/login|/sign-in
    if (/\/(auth|login|sign-in|signin)/i.test(u.pathname)) return false;
    if (u.hostname.includes("accounts.")) return false;
    if (path === "/" || path === "/new" || path === "/chat") return true;
    return false;
  } catch {
    return true;
  }
}

export function subscriptionLoginUrl(
  provider: "openai" | "claude" | "xai",
  candidate?: string | null,
): string {
  const fallback = SUBSCRIPTION_LOGIN_URL[provider];
  if (!candidate) return fallback;
  if (looksLikeChatHome(candidate)) return fallback;
  return candidate;
}

export async function linkSubscriptionAccount(
  provider: "openai" | "claude" | "xai",
): Promise<{ ok: boolean; url?: string; message?: string; error?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/subscriptions/link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider }),
    });
    if (!res.ok) {
      return { ok: false, error: (await res.text()).slice(0, 200) };
    }
    const data = (await res.json()) as {
      url?: string;
      message?: string;
      action?: string;
    };
    // Sempre URL de login/auth — nunca chatgpt.com/ · claude.ai/new · grok.com/
    const url = subscriptionLoginUrl(provider, data.url);
    return {
      ok: true,
      url,
      message:
        data.message ||
        `Abra o login da assinatura (${url}) e volte para confirmar.`,
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function confirmSubscriptionAccount(
  provider: "openai" | "claude" | "xai",
): Promise<{ ok: boolean; message?: string; error?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/subscriptions/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider }),
    });
    if (!res.ok) {
      return { ok: false, error: (await res.text()).slice(0, 200) };
    }
    const data = (await res.json()) as { message?: string };
    return { ok: true, message: data.message };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function disconnectSubscription(
  provider: "openai" | "claude" | "xai",
  path: "api_key" | "subscription" | "both" = "both",
): Promise<boolean> {
  try {
    const res = await fetch(
      `${KERNEL}/subscriptions/${provider}?path=${encodeURIComponent(path)}`,
      { method: "DELETE" },
    );
    return res.ok;
  } catch {
    return false;
  }
}

export type ServerSlot = {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  secret_env: string;
  has_secret: boolean;
  secret_masked: string;
  notes?: string;
  last_status?: string;
  last_error?: string;
  last_probe?: Record<string, unknown>;
};

export async function fetchServers(): Promise<ServerSlot[]> {
  try {
    const res = await apiFetch(`${KERNEL}/servers`);
    if (!res.ok) return [];
    const data = (await res.json()) as { servers?: ServerSlot[] };
    return data.servers || [];
  } catch {
    return [];
  }
}

export async function upsertServer(body: {
  id?: string;
  name?: string;
  host: string;
  port?: number;
  username?: string;
  password?: string;
  notes?: string;
  clear_secret?: boolean;
}): Promise<{ ok: boolean; server?: ServerSlot; error?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/servers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = (await res.json()) as {
      ok?: boolean;
      server?: ServerSlot;
      error?: string;
    };
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || `HTTP ${res.status}` };
    }
    return { ok: true, server: data.server };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function deleteServer(id: string): Promise<boolean> {
  try {
    const res = await apiFetch(`${KERNEL}/servers/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function testServer(
  id: string,
): Promise<{ ok: boolean; probe?: Record<string, unknown>; error?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/servers/${encodeURIComponent(id)}/test`, {
      method: "POST",
    });
    const data = (await res.json()) as {
      ok?: boolean;
      probe?: Record<string, unknown>;
      error?: string;
    };
    return {
      ok: !!data.ok,
      probe: data.probe,
      error: data.error,
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function fetchServerSites(
  id: string,
): Promise<{
  ok: boolean;
  sites?: { name: string; source: string; kind: string; detail?: string; status?: string }[];
  services?: Record<string, string>;
  error?: string;
}> {
  try {
    const res = await apiFetch(`${KERNEL}/servers/${encodeURIComponent(id)}/sites`);
    return (await res.json()) as {
      ok: boolean;
      sites?: { name: string; source: string; kind: string; detail?: string; status?: string }[];
      services?: Record<string, string>;
      error?: string;
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function fetchServerMaintenance(
  id: string,
): Promise<{
  ok: boolean;
  uptime?: string;
  mem?: string;
  disk?: string;
  updates?: string;
  veu_units?: string[];
  health_raw?: string;
  error?: string;
}> {
  try {
    const res = await fetch(
      `${KERNEL}/servers/${encodeURIComponent(id)}/maintenance`,
    );
    return (await res.json()) as {
      ok: boolean;
      uptime?: string;
      mem?: string;
      disk?: string;
      updates?: string;
      veu_units?: string[];
      health_raw?: string;
      error?: string;
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export type GrokInboxItem = {
  id?: string;
  ts?: number;
  kind?: string;
  priority?: string;
  title?: string;
  message?: string;
  job_id?: string;
  state?: string;
  needs_action?: boolean;
  agent?: string;
  decisions?: unknown[];
};

export type GrokRemoteCapability = {
  id: string;
  label: string;
  hint: string;
  ask: string;
};

export type GrokSideboard = {
  ok?: boolean;
  available?: boolean;
  policy?: string;
  updatedAt?: string;
  path?: string;
  error?: string;
  health?: {
    fleet?: string;
    updatedAt?: string;
    source_note?: string;
    needs_login?: string[];
    needs_login_count?: number;
    channels?: Record<string, number>;
    unread?: number;
    needs_approval?: number;
    inbox_total?: number;
    agenda_open?: number;
    agenda_cancelled?: number;
    tasks?: Record<string, number>;
    meetings?: number;
    last_agendas?: string;
    last_teams?: string;
  };
  productivity?: {
    doing?: number;
    blocked?: number;
    todo?: number;
    deferred?: number;
    outbound?: number;
    done_signals?: number;
    counsel_headline?: string;
    focus?: string;
  };
  insights?: { id?: string; title?: string; body?: string; company?: string }[];
  agenda?: {
    id?: string;
    title?: string;
    start?: string;
    end?: string;
    company?: string;
    source?: string;
    cancelled?: boolean;
    status?: string;
    location?: string;
  }[];
  inbox?: {
    id?: string;
    at?: string;
    channel?: string;
    company?: string;
    sender?: string;
    subject?: string;
    preview?: string;
    unread?: boolean;
    needsApproval?: boolean;
    why?: string;
    projectId?: string;
  }[];
  meetings?: {
    id?: string;
    empresa?: string;
    title?: string;
    when?: string;
    bullets?: string[];
    behavior?: string;
    source?: string;
    summary?: string;
    noteId?: string;
    handoff?: string;
  }[];
  tasks?: {
    id?: string;
    title?: string;
    status?: string;
    owner?: string;
    company?: string;
    due?: string;
    priority?: string;
    note?: string;
    projectId?: string;
  }[];
  agents?: { id?: string; name?: string; label?: string; hint?: string }[];
};

export type GrokBrief = {
  ok?: boolean;
  status?: string;
  webhook_configured?: boolean;
  tip?: string;
  decisions?: GrokInboxItem[];
  important?: GrokInboxItem[];
  inbox?: GrokInboxItem[];
  running?: {
    job_id?: string;
    intent?: string;
    state?: string;
    agent?: string;
    breath?: string;
    ts?: number;
  }[];
  agents?: { id: string; label: string; hint: string }[];
  remote_capabilities?: GrokRemoteCapability[];
  sideboard?: GrokSideboard;
  counts?: Record<string, number>;
  last_health?: { ok?: boolean; ts?: number } | null;
};

export async function fetchGrokBrief(): Promise<GrokBrief | null> {
  try {
    const res = await apiFetch(`${KERNEL}/bridge/grokbot/brief`);
    if (!res.ok) return null;
    return (await res.json()) as GrokBrief;
  } catch {
    return null;
  }
}

export async function fetchGrokSideboard(): Promise<GrokSideboard | null> {
  try {
    const res = await apiFetch(`${KERNEL}/bridge/grokbot/sideboard`);
    if (!res.ok) return null;
    return (await res.json()) as GrokSideboard;
  } catch {
    return null;
  }
}

export type CompanyProject = {
  id: string;
  name: string;
  summary?: string;
  status?: string;
  company?: string;
  glyph?: string;
  hue?: string;
  counts?: Record<string, number>;
  tasks?: GrokSideboard["tasks"];
  messages?: GrokSideboard["inbox"];
  meetings?: GrokSideboard["meetings"];
  agenda?: GrokSideboard["agenda"];
};

export type CompanyFolder = {
  id: string;
  name: string;
  glyph?: string;
  hue?: string;
  counts?: Record<string, number>;
  projects?: CompanyProject[];
  loose?: {
    tasks?: GrokSideboard["tasks"];
    messages?: GrokSideboard["inbox"];
    meetings?: GrokSideboard["meetings"];
    agenda?: GrokSideboard["agenda"];
  };
};

export type CompaniesTree = {
  ok?: boolean;
  available?: boolean;
  updatedAt?: string;
  error?: string;
  companies?: CompanyFolder[];
  counts?: Record<string, number>;
};

export async function fetchCompaniesTree(): Promise<CompaniesTree | null> {
  try {
    const res = await apiFetch(`${KERNEL}/bridge/control/companies`);
    if (!res.ok) return null;
    return (await res.json()) as CompaniesTree;
  } catch {
    return null;
  }
}

export async function fetchMeetingDetail(meetingId: string): Promise<{
  ok?: boolean;
  meeting?: NonNullable<GrokSideboard["meetings"]>[number] & { summary?: string };
  company?: string;
  shallow?: boolean;
  needs_grok?: boolean;
  ask?: string;
  error?: string;
} | null> {
  try {
    const res = await fetch(
      `${KERNEL}/bridge/control/meetings/${encodeURIComponent(meetingId)}`,
    );
    if (!res.ok) return null;
    return (await res.json()) as {
      ok?: boolean;
      meeting?: NonNullable<GrokSideboard["meetings"]>[number] & { summary?: string };
      company?: string;
      shallow?: boolean;
      needs_grok?: boolean;
      ask?: string;
      error?: string;
    };
  } catch {
    return null;
  }
}

export async function askGrokBot(body: {
  intent: string;
  breath?: AutonomyBreath;
  agent?: string | null;
  via?: "os" | "agent" | "chat";
}): Promise<{ ok: boolean; message?: string; error?: string; delivered?: boolean }> {
  try {
    const res = await apiFetch(`${KERNEL}/bridge/grokbot/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent: body.intent,
        breath: body.breath || "semi",
        agent: body.agent || undefined,
        via: body.via || (body.agent ? "agent" : "os"),
      }),
    });
    const data = (await res.json()) as {
      ok?: boolean;
      message?: string;
      error?: string;
      delivered?: boolean;
    };
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || `HTTP ${res.status}` };
    }
    return {
      ok: true,
      message: data.message,
      delivered: data.delivered,
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function approveGrokJob(
  jobId: string,
  note = "",
): Promise<{ ok: boolean; message?: string; error?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/bridge/grokbot/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, note }),
    });
    const data = (await res.json()) as {
      ok?: boolean;
      message?: string;
      error?: string;
    };
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || `HTTP ${res.status}` };
    }
    return { ok: true, message: data.message };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export type EccAgent = {
  id: string;
  title: string;
  role?: string;
  description?: string;
  triggers?: string[];
  tools?: string[];
  can_do?: string[];
  source?: string;
};

export type EccSkill = {
  id: string;
  title: string;
  description?: string;
  triggers?: string[];
  can_do?: string[];
  origin?: string;
  source?: string;
};

export type EccCatalog = {
  product?: string;
  root?: string;
  agents: EccAgent[];
  skills: EccSkill[];
  counts?: {
    agents?: number;
    skills?: number;
    vendor_agents?: number;
    vendor_skills?: number;
  };
  what_we_can_do?: string[];
};

export type McpServer = {
  id: string;
  name: string;
  transport: string;
  url?: string;
  command?: string;
  args?: string[];
  status?: string;
  tool_count?: number;
  tools?: { name?: string; description?: string }[];
  last_error?: string;
  env_masked?: Record<string, string>;
};

export async function fetchMcpServers(): Promise<McpServer[]> {
  try {
    const res = await apiFetch(`${KERNEL}/mcp`);
    if (!res.ok) return [];
    const data = (await res.json()) as { servers?: McpServer[] };
    return data.servers || [];
  } catch {
    return [];
  }
}

export async function importMcpJson(
  config: unknown,
  probe = false,
  confirm = false,
): Promise<{
  ok: boolean;
  message?: string;
  error?: string;
  imported?: McpServer[];
  preview?: boolean;
  items?: unknown[];
  hash?: string;
  errors?: string[];
  note?: string;
}> {
  try {
    const res = await apiFetch(`${KERNEL}/mcp/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config, probe, confirm }),
    });
    const data = (await res.json()) as {
      ok?: boolean;
      message?: string;
      error?: string;
      imported?: McpServer[];
      preview?: boolean;
      items?: unknown[];
      hash?: string;
      errors?: string[];
      note?: string;
    };
    if (!res.ok || (data.ok === false && !data.preview && !data.items)) {
      return {
        ok: false,
        error: data.error || (data.errors || []).join("; ") || `HTTP ${res.status}`,
        errors: data.errors,
        items: data.items,
        preview: data.preview,
      };
    }
    return {
      ok: data.ok !== false || Boolean(data.preview),
      message: data.message || data.note,
      imported: data.imported,
      preview: data.preview,
      items: data.items,
      hash: data.hash,
      errors: data.errors,
      note: data.note,
    };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function approveMcpServer(
  id: string,
): Promise<{ ok: boolean; error?: string; message?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/mcp/${encodeURIComponent(id)}/approve`, {
      method: "POST",
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || `HTTP ${res.status}` };
    }
    return { ok: true, message: "aprovado · probe em modo guiado" };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function probeMcpServer(
  id: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await apiFetch(`${KERNEL}/mcp/${encodeURIComponent(id)}/probe`, {
      method: "POST",
    });
    const data = (await res.json()) as { ok?: boolean; error?: string };
    return { ok: !!data.ok, error: data.error };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "falha" };
  }
}

export async function deleteMcpServer(id: string): Promise<boolean> {
  try {
    const res = await apiFetch(`${KERNEL}/mcp/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchEccCatalog(): Promise<EccCatalog | null> {
  try {
    const res = await apiFetch(`${KERNEL}/ecc`);
    if (!res.ok) return null;
    return (await res.json()) as EccCatalog;
  } catch {
    return null;
  }
}

export async function probeKernel(timeoutMs = 4000): Promise<KernelPulse> {
  const ctrl = new AbortController();
  const t = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    // /healthz é público. /pulse exige sessão e marcava "kernel · off" antes do login.
    const res = await fetch(`${KERNEL}/healthz`, {
      signal: ctrl.signal,
      credentials: "include",
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const data = (await res.json()) as { status?: string; product?: string };
    return {
      ok:
        data.status === "ok" ||
        data.status === "alive" ||
        !!data.product,
      status: data.status,
      product: data.product,
    };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : "kernel unreachable",
    };
  } finally {
    window.clearTimeout(t);
  }
}

export async function streamChat(
  message: string,
  breath: AutonomyBreath,
  onEvent: (ev: ChatEvent) => void,
): Promise<FormationPayload | null> {
  const res = await apiFetch(`${KERNEL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, breath }),
  });
  if (!res.ok || !res.body) throw new Error(`kernel ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let last: FormationPayload | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const ev = JSON.parse(line.slice(6)) as ChatEvent;
      onEvent(ev);
      if (ev.type === "done") last = ev.formation;
      if (ev.type === "plan") last = ev.formation;
    }
  }
  return last;
}

export { KERNEL };

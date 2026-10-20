/**
 * Ponte Véu ↔ extensão do browser ↔ máquina física.
 *
 * O SO web fala com a extensão via `window.postMessage`.
 * A extensão (e opcionalmente Native Messaging) executa no host Windows/Linux.
 */

export type BridgeStatus = "missing" | "connected" | "error";

export type BridgeInfo = {
  status: BridgeStatus;
  version?: string;
  platform?: string; // win32 | linux | darwin
  capabilities: string[];
  message: string;
};

export type BridgeRequest =
  | { type: "veu.ping" }
  | { type: "veu.host.info" }
  | { type: "veu.host.openApp"; app: string }
  | { type: "veu.host.focusApp"; app: string }
  | { type: "veu.host.listTabs" }
  | { type: "veu.host.readSurface"; app: string }
  | { type: "veu.host.openUrl"; url: string }
  | {
      type: "veu.host.askSubscription";
      app: string;
      url: string;
      prompt?: string;
    }
  | { type: "veu.host.shell"; command: string; cwd?: string }
  | { type: "veu.host.ssh"; command: string }
  | { type: "veu.host.readPath"; path: string }
  | { type: "veu.host.listDir"; path: string }
  | { type: "veu.host.runPreset"; preset: string };

export type BridgeResponse = {
  ok: boolean;
  type: string;
  data?: unknown;
  error?: string;
};

const SOURCE = "veu-os";
const EXT_SOURCE = "veu-extension";

function connectedFrom(data: Record<string, unknown>): BridgeInfo {
  const nested = (data.data || {}) as Record<string, unknown>;
  const platform = (data.platform || nested.platform) as string | undefined;
  const version = (data.version || nested.version) as string | undefined;
  const capabilities = (data.capabilities ||
    nested.capabilities || ["ping", "openApp", "shell", "fs"]) as string[];
  return {
    status: "connected",
    version,
    platform,
    capabilities,
    message: `Ligada à máquina física (${platform || "host"})`,
  };
}

function isExtHello(data: unknown): data is Record<string, unknown> {
  if (!data || typeof data !== "object") return false;
  const d = data as Record<string, unknown>;
  if (d.source !== EXT_SOURCE) return false;
  return (
    d.type === "veu.pong" ||
    d.type === "veu.ready" ||
    d.type === "veu.host.info.result"
  );
}

/** Detecta a extensão com retries — content script pode injetar depois do boot. */
export function probeBridge(timeoutMs = 2500): Promise<BridgeInfo> {
  return new Promise((resolve) => {
    let done = false;
    let attempts = 0;
    const maxAttempts = 6;
    const started = Date.now();

    const finish = (info: BridgeInfo) => {
      if (done) return;
      done = true;
      window.clearInterval(pingTimer);
      window.clearTimeout(deadline);
      window.removeEventListener("message", onMsg);
      resolve(info);
    };

    function onMsg(ev: MessageEvent) {
      if (ev.source !== window) return;
      if (!isExtHello(ev.data)) return;
      finish(connectedFrom(ev.data));
    }

    const ping = () => {
      if (done) return;
      attempts += 1;
      window.postMessage({ source: SOURCE, type: "veu.ping" }, "*");
      if (attempts === 1 || attempts === 3) {
        window.postMessage({ source: SOURCE, type: "veu.host.info" }, "*");
      }
      if (attempts >= maxAttempts && Date.now() - started > timeoutMs) {
        finish({
          status: "missing",
          capabilities: [],
          message:
            "Extensão Véu Host não detectada — instale v0.3.6 e recarregue esta aba",
        });
      }
    };

    window.addEventListener("message", onMsg);
    const pingTimer = window.setInterval(ping, 350);
    ping();

    const deadline = window.setTimeout(() => {
      finish({
        status: "missing",
        capabilities: [],
        message:
          "Extensão ausente — chrome://extensions → Véu Host 0.3.6 (Recarregar) → F5 em veu.ch8ai.com.br",
      });
    }, timeoutMs);
  });
}

/** Atalhos seguros no PC local (Native Messaging / extensão). */
export function runHostPreset(preset: string, timeoutMs = 10000) {
  return callBridge({ type: "veu.host.runPreset", preset }, timeoutMs);
}

export function callBridge(req: BridgeRequest, timeoutMs = 8000): Promise<BridgeResponse> {
  return new Promise((resolve) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    let done = false;
    const timer = window.setTimeout(() => {
      if (done) return;
      done = true;
      window.removeEventListener("message", onMsg);
      resolve({
        ok: false,
        type: req.type,
        error: "timeout — extensão ausente ou sem resposta",
      });
    }, timeoutMs);

    function onMsg(ev: MessageEvent) {
      if (ev.source !== window) return;
      const data = ev.data;
      if (!data || data.source !== EXT_SOURCE || data.replyTo !== id) return;
      if (done) return;
      done = true;
      window.clearTimeout(timer);
      window.removeEventListener("message", onMsg);
      resolve({
        ok: !!data.ok,
        type: data.type || req.type,
        data: data.data,
        error: data.error,
      });
    }

    window.addEventListener("message", onMsg);
    window.postMessage({ source: SOURCE, id, ...req }, "*");
  });
}

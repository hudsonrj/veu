import { useCallback, useEffect, useState } from "react";
import { apiFetch,
  KERNEL,
  fetchSubscriptions,
  type SubscriptionSlot,
 } from "../../lib/kernel";
import { callBridge, probeBridge } from "../../bridge/hostBridge";
import { openUrlNow } from "../../lib/openUrl";
import {
  subscriptionLoginUrl,
  SUBSCRIPTION_LOGIN_URL,
} from "../../lib/kernel";

export type AiSurfaceId = "chatgpt" | "claude" | "grok" | "codex" | "claude-work";

type Props = {
  surface: AiSurfaceId;
};

type Turn = { id: string; role: "you" | "ai"; text: string };
type Mode = "api" | "subscription";

const META: Record<
  AiSurfaceId,
  {
    title: string;
    provider: "openai" | "claude" | "xai";
    hue: string;
    openUrl: string;
    loginUrl: string;
    hostApp: string;
    kind: "chat" | "work";
  }
> = {
  chatgpt: {
    title: "ChatGPT",
    provider: "openai",
    hue: "#10A37F",
    openUrl: "https://chatgpt.com/",
    loginUrl: "https://chatgpt.com/auth/login",
    hostApp: "chatgpt",
    kind: "chat",
  },
  claude: {
    title: "Claude",
    provider: "claude",
    hue: "#D4A27F",
    openUrl: "https://claude.ai/new",
    loginUrl: "https://claude.ai/login",
    hostApp: "claude",
    kind: "chat",
  },
  grok: {
    title: "Grok",
    provider: "xai",
    hue: "#E8C27A",
    openUrl: "https://grok.com/",
    loginUrl: "https://accounts.x.ai/sign-in",
    hostApp: "grok",
    kind: "chat",
  },
  codex: {
    title: "Codex",
    provider: "openai",
    hue: "#0D8C6C",
    openUrl: "https://chatgpt.com/codex",
    loginUrl: "https://chatgpt.com/auth/login",
    hostApp: "chatgpt",
    kind: "work",
  },
  "claude-work": {
    title: "Claude Work",
    provider: "claude",
    hue: "#C4895E",
    openUrl: "https://claude.ai/projects",
    loginUrl: "https://claude.ai/login",
    hostApp: "claude",
    kind: "work",
  },
};

const QUICK: Partial<Record<AiSurfaceId, string[]>> = {
  chatgpt: ["resuma o que importa hoje", "me ajude a planejar a semana"],
  claude: ["revise este raciocínio", "monte um plano claro"],
  grok: ["visão direta sem enrolação", "o que está em alta agora?"],
  codex: ["explique este bug", "escreva um teste mínimo"],
  "claude-work": ["organize o projeto", "checklist do que falta"],
};

export function AiChatApp({ surface }: Props) {
  const meta = META[surface];
  const [slot, setSlot] = useState<SubscriptionSlot | null>(null);
  const [mode, setMode] = useState<Mode>("subscription");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hostOk, setHostOk] = useState(false);

  const reload = useCallback(async () => {
    const [subs, bridge] = await Promise.all([
      fetchSubscriptions(),
      probeBridge(1200),
    ]);
    const s = subs.find((x) => x.id === meta.provider) || null;
    setSlot(s);
    setHostOk(bridge.status === "connected");
    const api = !!s?.modes?.api_key?.configured;
    const sub = s?.modes?.subscription?.status === "linked";
    // Preferência: assinatura se ligada; senão API; senão assinatura mesmo assim
    setMode((prev) => {
      if (prev === "api" && api) return "api";
      if (sub || !api) return "subscription";
      return "api";
    });
  }, [meta.provider]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    setTurns([]);
    setDraft("");
    setErr(null);
  }, [surface]);

  const apiOk = !!slot?.modes?.api_key?.configured;
  const subOk = slot?.modes?.subscription?.status === "linked";
  const pending = slot?.modes?.subscription?.status === "pending";

  const sendViaSubscription = async (
    msg: string,
    onWait?: (hint: string) => void,
  ) => {
    const res = await apiFetch(`${KERNEL}/llm/subscription-compose`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: meta.provider,
        message: msg,
        surface,
      }),
    });
    const raw = await res.text();
    const data = raw
      ? (JSON.parse(raw) as {
          ok?: boolean;
          url?: string;
          app?: string;
          product?: string;
          error?: string;
          hint?: string;
        })
      : {};
    if (!data.ok || !data.url) {
      throw new Error(data.error || "não montou o pedido da assinatura");
    }

    const app = data.app || meta.hostApp;
    onWait?.(
      `Pedindo via assinatura ${data.product || meta.title}… a resposta volta pra esta janela.`,
    );

    if (hostOk) {
      // Um turno completo na extensão: abre aba, envia, lê resposta, devolve aqui
      try {
        const turn = await callBridge(
          {
            type: "veu.host.askSubscription",
            app,
            url: data.url,
            prompt: msg,
          },
          55_000,
        );
        const payload = (turn.data || {}) as { reply?: string };
        if (turn.ok && payload.reply && payload.reply.trim().length > 12) {
          return payload.reply.trim();
        }
        // fallback: readSurface simples
        onWait?.("Ainda gerando… lendo a aba de novo.");
        const surface = await callBridge(
          { type: "veu.host.readSurface", app },
          10_000,
        );
        const items = ((surface.data || {}) as { items?: string[] }).items || [];
        const head = msg.slice(0, 40).toLowerCase();
        const candidates = items
          .map((t) => String(t || "").trim())
          .filter((t) => t.length > 24)
          .filter((t) => !head || !t.toLowerCase().includes(head));
        if (candidates.length) {
          return candidates[candidates.length - 1];
        }
        if (payload.reply) return payload.reply.trim();
        throw new Error(
          turn.error ||
            "Sem texto na aba ainda — confirme o login (confirmei o login) e tente de novo.",
        );
      } catch (e) {
        throw e instanceof Error
          ? e
          : new Error("Host não trouxe a resposta pra janela");
      }
    }

    // Sem Host: abre a URL e avisa — sem fingir que já respondeu
    openUrlNow(data.url);
    return (
      `Abri ${data.product || meta.title} no browser. ` +
      `Instale/ative a extensão Véu Host pra a resposta voltar pra esta janela.`
    );
  };

  const sendViaApi = async (msg: string) => {
    const res = await apiFetch(`${KERNEL}/llm/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        provider: meta.provider,
        force: true,
        stay_in_veu: true,
        fallback_local: true,
      }),
    });
    const raw = await res.text();
    const data = raw
      ? (JSON.parse(raw) as {
          ok?: boolean;
          text?: string;
          error?: string;
          provider?: string;
          model?: string;
        })
      : {};
    const text = (data.text || "").trim();
    const rejected =
      /api key .* rejeitada|incorrect api key|invalid_api_key/i.test(
        text + " " + (data.error || ""),
      );
    return {
      text:
        text ||
        data.error ||
        "Sem resposta — tente assinatura ou outra key.",
      rejected,
      provider: data.provider,
      model: data.model,
    };
  };

  const send = async (text: string) => {
    const msg = text.trim();
    if (!msg || busy) return;
    setBusy(true);
    setErr(null);
    const waitId = `${Date.now()}-w`;
    setTurns((t) => [
      ...t,
      { id: `${Date.now()}-u`, role: "you", text: msg },
      {
        id: waitId,
        role: "ai",
        text:
          mode === "subscription"
            ? `… pedindo via assinatura ${meta.title} · a resposta entra aqui`
            : "…",
      },
    ]);
    setDraft("");

    const patchWait = (hint: string) => {
      setTurns((t) =>
        t.map((x) => (x.id === waitId ? { ...x, text: `… ${hint}` } : x)),
      );
    };

    try {
      let reply = "";
      let metaLine = "";

      if (mode === "subscription") {
        reply = await sendViaSubscription(msg, patchWait);
        metaLine = `assinatura · ${meta.title}`;
      } else {
        const api = await sendViaApi(msg);
        if (api.rejected) {
          // Não cai pra assinatura/browser — key ruim vaza JSON e some do Véu.
          // O kernel já tenta Ollama; só mostra o texto limpo + pedido de key.
          reply =
            api.text ||
            `API key de ${meta.title} inválida. Cole uma key nova em Ajustes → assinaturas, ou use Ollama local.`;
          metaLine = `${api.provider || "veu"} · key inválida`;
        } else {
          reply = api.text;
          metaLine = `${api.provider || meta.provider} · ${api.model || "api"}`;
        }
      }

      setTurns((t) =>
        t.map((x) =>
          x.id === waitId
            ? { ...x, text: `${reply}\n· ${metaLine}` }
            : x,
        ),
      );
    } catch (e) {
      const m = e instanceof Error ? e.message : "falha";
      setErr(m);
      setTurns((t) =>
        t.map((x) => (x.id === waitId ? { ...x, text: m } : x)),
      );
    } finally {
      setBusy(false);
    }
  };

  const linkSub = async () => {
    try {
      const res = await apiFetch(`${KERNEL}/subscriptions/link`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: meta.provider }),
      });
      const data = (await res.json()) as {
        ok?: boolean;
        url?: string;
        message?: string;
      };
      // Login/auth da assinatura — nunca a página do chat
      const login = subscriptionLoginUrl(
        meta.provider,
        data.url || meta.loginUrl || SUBSCRIPTION_LOGIN_URL[meta.provider],
      );
      if (hostOk) {
        try {
          await callBridge({ type: "veu.host.openUrl", url: login }, 5000);
        } catch {
          openUrlNow(login);
        }
      } else {
        openUrlNow(login);
      }
      setErr(
        data.message ||
          `Login da assinatura · ${login} · entre e clique em confirmei`,
      );
      void reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
    }
  };

  const confirmSub = async () => {
    try {
      const res = await apiFetch(`${KERNEL}/subscriptions/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: meta.provider }),
      });
      const data = (await res.json()) as { ok?: boolean; message?: string; error?: string };
      setErr(data.ok ? data.message || "assinatura ligada" : data.error || "falha");
      void reload();
      setMode("subscription");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
    }
  };

  return (
    <div className="aichat" style={{ ["--hue" as string]: meta.hue }}>
      <header className="aichat__head">
        <h2>{meta.title}</h2>
        <div className="aichat__modes" role="tablist">
          <button
            type="button"
            className={mode === "subscription" ? "is-on" : ""}
            onClick={() => setMode("subscription")}
          >
            assinatura
          </button>
          <button
            type="button"
            className={mode === "api" ? "is-on" : ""}
            onClick={() => setMode("api")}
          >
            api
          </button>
        </div>
      </header>

      <div className="aichat__status">
        <span className={subOk ? "is-live" : pending ? "is-pend" : ""}>
          conta {subOk ? "ligada" : pending ? "pending" : "off"}
        </span>
        <span className={apiOk ? "is-live" : ""}>api {apiOk ? "on" : "off"}</span>
        <span className={hostOk ? "is-live" : ""}>host {hostOk ? "on" : "off"}</span>
      </div>

      {!subOk ? (
        <div className="aichat__linkrow">
          <button type="button" onClick={() => void linkSub()}>
            abrir login da assinatura
          </button>
          <button type="button" onClick={() => void confirmSub()}>
            confirmei o login
          </button>
          <button
            type="button"
            className="aichat__ghost"
            title="Só o chat — não liga a assinatura"
            onClick={() => openUrlNow(meta.openUrl)}
          >
            abrir chat (sem ligar)
          </button>
        </div>
      ) : (
        <div className="aichat__linkrow">
          <button
            type="button"
            className="aichat__ghost"
            onClick={() => openUrlNow(meta.openUrl)}
          >
            abrir {meta.title} no Host
          </button>
        </div>
      )}

      <div className="aichat__stream">
        {turns.length === 0 ? (
          <p className="aichat__empty">
            {mode === "subscription"
              ? `Modo assinatura · ${meta.title} responde nesta janela (Host lê a aba logada).`
              : `Modo API · responde aqui no Véu com a key.`}
          </p>
        ) : (
          turns.map((t) => (
            <p key={t.id} className={`aichat__turn is-${t.role}`}>
              <span>{t.role === "you" ? "você" : meta.title}</span>
              {t.text}
            </p>
          ))
        )}
      </div>

      <div className="aichat__quick">
        {(QUICK[surface] || []).map((q) => (
          <button key={q} type="button" disabled={busy} onClick={() => void send(q)}>
            {q}
          </button>
        ))}
      </div>

      <form
        className="aichat__form"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <textarea
          rows={2}
          value={draft}
          disabled={busy}
          placeholder={
            mode === "subscription"
              ? `pedir via assinatura ${meta.title}…`
              : `falar via API ${meta.title}…`
          }
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(draft);
            }
          }}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          {busy ? "…" : "enviar"}
        </button>
      </form>
      {err ? <p className="aichat__err">{err}</p> : null}

      <style>{`
        .aichat {
          height: 100%;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          padding: 0.85rem 1rem;
          color: #e8ebe6;
          background:
            radial-gradient(ellipse at 0% 0%, color-mix(in srgb, var(--hue) 22%, transparent), transparent 50%),
            linear-gradient(165deg, #121418, #0c0e12 60%);
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .aichat__head {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 0.75rem;
        }
        .aichat__head h2 {
          margin: 0;
          font-family: "IBM Plex Serif", Georgia, serif;
          font-weight: 500;
          font-size: 1.35rem;
          color: color-mix(in srgb, var(--hue) 70%, #fff);
        }
        .aichat__modes {
          display: flex;
          border: 1px solid color-mix(in srgb, var(--hue) 40%, transparent);
        }
        .aichat__modes button {
          border: 0;
          background: transparent;
          color: #9aa3ad;
          padding: 0.35rem 0.7rem;
          font-size: 0.72rem;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          cursor: pointer;
        }
        .aichat__modes button.is-on {
          background: color-mix(in srgb, var(--hue) 22%, transparent);
          color: #fff;
        }
        .aichat__status {
          display: flex;
          gap: 0.75rem;
          font-size: 0.68rem;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: #6b7480;
        }
        .aichat__status .is-live { color: #8fbf9f; }
        .aichat__status .is-pend { color: #d4b896; }
        .aichat__linkrow {
          display: flex;
          gap: 0.4rem;
          flex-wrap: wrap;
        }
        .aichat__linkrow button {
          border: 1px solid color-mix(in srgb, var(--hue) 45%, transparent);
          background: color-mix(in srgb, var(--hue) 12%, transparent);
          color: #eef2f0;
          padding: 0.35rem 0.65rem;
          font-size: 0.75rem;
          cursor: pointer;
        }
        .aichat__linkrow button.aichat__ghost {
          background: transparent;
          border-color: rgba(255,255,255,0.14);
          color: #9aa3ad;
        }
        .aichat__stream {
          flex: 1;
          min-height: 0;
          overflow: auto;
          display: flex;
          flex-direction: column;
          gap: 0.55rem;
        }
        .aichat__empty {
          margin: auto 0;
          color: #8a949e;
          font-size: 0.92rem;
          font-weight: 300;
        }
        .aichat__turn {
          margin: 0;
          padding: 0.55rem 0.7rem;
          font-size: 0.9rem;
          line-height: 1.4;
          white-space: pre-wrap;
        }
        .aichat__turn span {
          display: block;
          font-size: 0.65rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 0.2rem;
          opacity: 0.6;
        }
        .aichat__turn.is-you {
          background: rgba(255,255,255,0.04);
          align-self: flex-end;
          max-width: 92%;
        }
        .aichat__turn.is-ai {
          background: color-mix(in srgb, var(--hue) 12%, rgba(0,0,0,0.25));
          border: 1px solid color-mix(in srgb, var(--hue) 22%, transparent);
          max-width: 96%;
        }
        .aichat__quick {
          display: flex;
          flex-wrap: wrap;
          gap: 0.35rem;
        }
        .aichat__quick button {
          border: 1px solid rgba(255,255,255,0.1);
          background: rgba(255,255,255,0.03);
          color: #b8c0c8;
          padding: 0.25rem 0.65rem;
          font-size: 0.72rem;
          cursor: pointer;
        }
        .aichat__form {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.5rem;
        }
        .aichat__form textarea {
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(0,0,0,0.3);
          color: #e8ebe6;
          padding: 0.5rem 0.65rem;
          resize: none;
          font: inherit;
        }
        .aichat__form button {
          align-self: end;
          border: 1px solid color-mix(in srgb, var(--hue) 50%, transparent);
          background: color-mix(in srgb, var(--hue) 18%, transparent);
          color: #fff;
          padding: 0.5rem 0.85rem;
          cursor: pointer;
        }
        .aichat__form button:disabled { opacity: 0.4; }
        .aichat__err { margin: 0; color: #e8a0a0; font-size: 0.8rem; }
      `}</style>
    </div>
  );
}

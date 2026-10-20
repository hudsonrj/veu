import { useEffect, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";
import type { WinApp } from "../types";
import { HostApp } from "./HostApp";
import { FilesApp } from "./FilesApp";
import { WhatsAppApp } from "./WhatsAppApp";

type Connector = {
  id: string;
  name: string;
  status: string;
  notes?: string;
  capabilities?: string[];
  surface?: string;
};

/** WinApp do desktop → id no catálogo do kernel */
const APP_TO_CONNECTOR: Partial<Record<WinApp, string>> = {
  whatsapp: "whatsapp",
  teams: "teams",
  outlook: "outlook",
  gmail: "gmail",
  gchat: "google-chat",
  google: "google",
  notion: "notion",
  slack: "slack",
  openrag: "openrag",
  mcp: "mcp-bus",
  api: "api-bus",
  host: "host-desktop",
  files: "host-desktop",
  browser: "host-desktop",
};

const FALLBACK: Partial<Record<WinApp, { blurb: string; next: string }>> = {
  browser: {
    blurb: "Navegação como superfície do SO.",
    next: "Host · abra URLs e foque abas pela extensão",
  },
  settings: {
    blurb: "Integrações, modelos, pontes, skills e políticas.",
    next: "use o app Ajustes no dock",
  },
};

function statusLabel(status: string) {
  if (status === "live") return "live";
  if (status === "ready") return "pronto";
  return "planejado";
}

/**
 * Fallback só para apps sem janela própria.
 * Host / Arquivos NÃO caem mais em card de status — abrem a ferramenta real.
 */
export function NerveApp({ app }: { app: WinApp }) {
  // Uso real — nunca mensagem "nervo · pronto"
  if (app === "host") return <HostApp />;
  if (app === "files") return <FilesApp />;
  if (app === "whatsapp") return <WhatsAppApp />;
  // browser / ruflo / ruos têm apps próprios — não devem cair aqui

  const [conn, setConn] = useState<Connector | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const cid = APP_TO_CONNECTOR[app];
    if (!cid) return;
    let cancelled = false;
    const load = async () => {
      try {
        const r = await apiFetch(`${KERNEL}/connectors`);
        const data = (await r.json()) as { connectors?: Connector[] };
        const hit = (data.connectors || []).find((c) => c.id === cid) || null;
        if (!cancelled) {
          setConn(hit);
          setErr(null);
        }
      } catch {
        if (!cancelled) setErr("kernel offline");
      }
    };
    void load();
    const id = window.setInterval(load, 12_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [app]);

  const fallback = FALLBACK[app];
  const status = conn?.status || (err ? "offline" : "…");
  const live = status === "live";

  return (
    <div className="nerve">
      <p className="nerve__kicker">superfície · {conn?.name || app}</p>
      <p className={`nerve__status is-${status}`}>{statusLabel(status)}</p>
      <p className="nerve__blurb">
        {conn
          ? `${conn.name} · ${conn.surface || "api"}${
              conn.capabilities?.length
                ? ` — ${conn.capabilities.slice(0, 4).join(" · ")}`
                : ""
            }`
          : fallback?.blurb || "App integrado do Véu."}
      </p>
      <p className="nerve__next">
        {err
          ? `kernel · ${err}`
          : live
            ? conn?.notes || "operacional"
            : conn?.notes
              ? conn.notes
              : fallback?.next
                ? fallback.next
                : "em construção — use Ajustes ou o dock"}
      </p>
      {app === "browser" ? (
        <div className="nerve__actions">
          <p className="nerve__hint">
            Abra a extensão Véu Host no Chrome/Edge do seu PC. Depois use a janela{" "}
            <strong>Máquina</strong> no dock para abrir Gmail, Agenda, Grok…
          </p>
        </div>
      ) : null}
      <style>{`
        .nerve { padding: 1.1rem; display: grid; gap: 0.55rem; height: 100%; }
        .nerve__kicker {
          margin: 0; font-family: var(--font-mono); font-size: 0.65rem;
          letter-spacing: 0.16em; color: var(--signal); text-transform: lowercase;
        }
        .nerve__status {
          margin: 0; font-family: var(--font-mono); font-size: 0.78rem;
          letter-spacing: 0.12em; text-transform: lowercase;
          color: var(--mist-dim);
        }
        .nerve__status.is-live { color: var(--filament); }
        .nerve__status.is-ready { color: var(--signal); }
        .nerve__blurb {
          margin: 0; font-size: 1.05rem; font-weight: 300; line-height: 1.5;
          color: var(--mist);
        }
        .nerve__next {
          margin: 0; font-family: var(--font-mono); font-size: 0.72rem;
          letter-spacing: 0.04em; color: var(--filament);
        }
        .nerve__hint {
          margin: 0.4rem 0 0; font-size: 0.85rem; color: var(--mist-dim); line-height: 1.4;
        }
      `}</style>
    </div>
  );
}

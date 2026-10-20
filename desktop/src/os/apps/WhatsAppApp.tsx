import { useCallback, useEffect, useState } from "react";
import { callBridge, probeBridge, type BridgeInfo } from "../../bridge/hostBridge";

type Surface = {
  items?: string[];
  title?: string;
  url?: string;
  note?: string;
  count?: number;
};

/**
 * WhatsApp Web · QR no telefone.
 * Não é card de status: abre web.whatsapp.com (Host) e lê conversas da aba.
 */
export function WhatsAppApp() {
  const [bridge, setBridge] = useState<BridgeInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<"idle" | "qr" | "linked" | "reading">("idle");
  const [log, setLog] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const refreshBridge = useCallback(async () => {
    const info = await probeBridge(1200);
    setBridge(info);
    return info;
  }, []);

  useEffect(() => {
    void refreshBridge();
    const id = window.setInterval(() => void refreshBridge(), 8000);
    return () => window.clearInterval(id);
  }, [refreshBridge]);

  const connected = bridge?.status === "connected";

  const openQr = async () => {
    setBusy(true);
    setErr(null);
    setLog(null);
    try {
      const info = await refreshBridge();
      if (info.status !== "connected") {
        setErr("Extensão Véu Host off — instale 0.3.6 e recarregue esta aba.");
        return;
      }
      // Abre WhatsApp Web — a página mostra o QR para o celular
      await callBridge({ type: "veu.host.openUrl", url: "https://web.whatsapp.com/" }, 6000);
      try {
        await callBridge({ type: "veu.host.focusApp", app: "whatsapp" }, 4000);
      } catch {
        /* ok */
      }
      setPhase("qr");
      setLog(
        "WhatsApp Web aberto no Host. No celular: WhatsApp → Aparelhos conectados → Conectar um aparelho → aponte a câmera no QR.",
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha ao abrir");
    } finally {
      setBusy(false);
    }
  };

  const readInbox = async () => {
    setBusy(true);
    setErr(null);
    setPhase("reading");
    try {
      const info = await refreshBridge();
      if (info.status !== "connected") {
        setErr("Host off — sem extensão não dá pra ler a aba do WP Web.");
        return;
      }
      const res = await callBridge({ type: "veu.host.readSurface", app: "whatsapp" }, 12000);
      if (!res.ok) {
        setErr(res.error || "não li a aba — faça login pelo QR e tente de novo");
        setPhase("qr");
        return;
      }
      const data = (res.data || {}) as Surface;
      const items = (data.items || []).map(String).filter(Boolean);
      setMsgs(items);
      if (items.length) {
        setPhase("linked");
        setLog(`Lidas ${items.length} linha(s) da aba · ${data.title || "WhatsApp Web"}`);
      } else {
        setPhase("qr");
        setLog(
          data.note ||
            "Ainda sem conversas legíveis — escaneie o QR e espere a lista carregar.",
        );
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
      setPhase("qr");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wa">
      <header className="wa__head">
        <div>
          <p className="wa__kicker">whatsapp web · qr</p>
          <h2>WhatsApp</h2>
          <p className="wa__sub">
            Conecte pelo QR no celular — mesma sessão do WhatsApp Web no seu browser.
          </p>
        </div>
        <div className={`wa__badge is-${connected ? "on" : "off"}`}>
          <i />
          host {connected ? "on" : "off"}
        </div>
      </header>

      <section className="wa__qr" aria-label="conectar">
        <div className="wa__qr-frame" aria-hidden>
          <div className="wa__qr-mark">
            <span />
            <span />
            <span />
            <span />
            <em>QR</em>
          </div>
          <p>O QR aparece no WhatsApp Web</p>
        </div>
        <div className="wa__steps">
          <ol>
            <li>Clique em <strong>abrir WhatsApp Web</strong></li>
            <li>No telefone: <strong>Aparelhos conectados</strong></li>
            <li>Aponte a câmera no QR da aba</li>
            <li>Volte aqui e clique em <strong>ler conversas</strong></li>
          </ol>
          <div className="wa__actions">
            <button
              type="button"
              className="wa__primary"
              disabled={busy}
              onClick={() => void openQr()}
            >
              {busy && phase !== "reading" ? "…" : "abrir WhatsApp Web (QR)"}
            </button>
            <button type="button" disabled={busy || !connected} onClick={() => void readInbox()}>
              {busy && phase === "reading" ? "…" : "ler conversas"}
            </button>
            <button
              type="button"
              disabled={busy || !connected}
              onClick={() =>
                void callBridge({ type: "veu.host.focusApp", app: "whatsapp" }, 4000)
              }
            >
              focar aba
            </button>
          </div>
        </div>
      </section>

      <section className="wa__inbox">
        <h3>
          conversas <em>{msgs.length || "—"}</em>
        </h3>
        {msgs.length === 0 ? (
          <p className="wa__empty">
            {phase === "qr"
              ? "Escaneie o QR e depois leia as conversas."
              : "Nada ainda — conecte pelo QR do WhatsApp Web."}
          </p>
        ) : (
          <ul>
            {msgs.map((m, i) => (
              <li key={`${i}-${m.slice(0, 12)}`}>{m}</li>
            ))}
          </ul>
        )}
      </section>

      {log ? <p className="wa__foot">{log}</p> : null}
      {err ? <p className="wa__err">{err}</p> : null}

      {!connected ? (
        <ol className="wa__howto">
          <li>
            Instale <strong>Véu Host 0.3.7</strong> em <code>chrome://extensions</code>
          </li>
          <li>
            Abra <code>https://veu.ch8ai.com.br</code> e confirme host · on no topo
          </li>
          <li>Volte e use abrir WhatsApp Web (QR)</li>
        </ol>
      ) : null}

      <style>{`
        .wa {
          height: 100%;
          overflow: auto;
          padding: 0.9rem 1rem;
          display: grid;
          gap: 0.75rem;
          align-content: start;
          color: var(--os-ink, #e8ebe6);
          background:
            radial-gradient(ellipse at 10% 0%, rgba(37,211,102,0.16), transparent 45%),
            linear-gradient(165deg, #0e1612, #0a0e0c 70%);
          font-family: var(--os-font, "IBM Plex Sans", sans-serif);
        }
        .wa__head { display: flex; justify-content: space-between; gap: 0.75rem; }
        .wa__kicker {
          margin: 0; font-size: 0.62rem; letter-spacing: 0.16em;
          text-transform: uppercase; color: #25d366;
        }
        .wa__head h2 {
          margin: 0.12rem 0 0;
          font-family: var(--os-display, "IBM Plex Serif", Georgia, serif);
          font-weight: 500; font-size: 1.45rem;
        }
        .wa__sub { margin: 0.25rem 0 0; font-size: 0.84rem; color: var(--os-muted, #8a939c); max-width: 28rem; }
        .wa__badge {
          align-self: start; display: flex; align-items: center; gap: 0.35rem;
          border: 1px solid rgba(37,211,102,0.35); padding: 0.35rem 0.6rem;
          font-size: 0.68rem; letter-spacing: 0.06em; text-transform: uppercase; color: #7a8a80;
        }
        .wa__badge.is-on { color: #25d366; }
        .wa__badge i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
        .wa__qr {
          display: grid;
          grid-template-columns: minmax(140px, 180px) 1fr;
          gap: 0.85rem;
          border: 1px solid rgba(37,211,102,0.22);
          background: rgba(0,0,0,0.25);
          padding: 0.85rem;
        }
        @media (max-width: 560px) {
          .wa__qr { grid-template-columns: 1fr; }
        }
        .wa__qr-frame {
          display: grid;
          place-items: center;
          gap: 0.4rem;
          aspect-ratio: 1;
          border: 1px dashed rgba(37,211,102,0.4);
          background:
            repeating-linear-gradient(0deg, transparent, transparent 7px, rgba(37,211,102,0.04) 7px, rgba(37,211,102,0.04) 8px),
            repeating-linear-gradient(90deg, transparent, transparent 7px, rgba(37,211,102,0.04) 7px, rgba(37,211,102,0.04) 8px);
        }
        .wa__qr-frame p {
          margin: 0; font-size: 0.65rem; letter-spacing: 0.06em;
          text-transform: uppercase; color: #6b7a70; text-align: center;
        }
        .wa__qr-mark {
          position: relative; width: 72px; height: 72px;
        }
        .wa__qr-mark span {
          position: absolute; width: 18px; height: 18px;
          border: 2px solid #25d366;
        }
        .wa__qr-mark span:nth-child(1) { top: 0; left: 0; border-right: 0; border-bottom: 0; }
        .wa__qr-mark span:nth-child(2) { top: 0; right: 0; border-left: 0; border-bottom: 0; }
        .wa__qr-mark span:nth-child(3) { bottom: 0; left: 0; border-right: 0; border-top: 0; }
        .wa__qr-mark span:nth-child(4) { bottom: 0; right: 0; border-left: 0; border-top: 0; }
        .wa__qr-mark em {
          position: absolute; inset: 0; display: grid; place-items: center;
          font-style: normal; font-size: 0.85rem; letter-spacing: 0.12em;
          color: #25d366; font-weight: 600;
        }
        .wa__steps ol {
          margin: 0 0 0.7rem; padding-left: 1.1rem;
          font-size: 0.86rem; line-height: 1.55; color: #c5d0c8;
        }
        .wa__actions { display: flex; flex-wrap: wrap; gap: 0.4rem; }
        .wa__actions button {
          border: 1px solid rgba(37,211,102,0.35);
          background: transparent; color: #c8e6d0;
          padding: 0.4rem 0.7rem; font-size: 0.75rem; cursor: pointer;
        }
        .wa__actions button:disabled { opacity: 0.4; cursor: default; }
        .wa__primary {
          background: rgba(37,211,102,0.16) !important;
          border-color: rgba(37,211,102,0.5) !important;
          color: #e8fff0 !important;
        }
        .wa__inbox {
          border: 1px solid rgba(255,255,255,0.08);
          background: rgba(0,0,0,0.22);
          padding: 0.65rem 0.75rem;
          min-height: 8rem;
        }
        .wa__inbox h3 {
          margin: 0 0 0.45rem; font-size: 0.66rem; letter-spacing: 0.1em;
          text-transform: uppercase; color: #25d366; font-weight: 500;
        }
        .wa__inbox h3 em { font-style: normal; color: #6b7a70; margin-left: 0.3rem; }
        .wa__empty { margin: 0; font-size: 0.8rem; color: #6b7a70; }
        .wa__inbox ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
        .wa__inbox li {
          font-size: 0.82rem; padding: 0.4rem 0.5rem;
          border-left: 2px solid rgba(37,211,102,0.45);
          background: rgba(37,211,102,0.05);
        }
        .wa__foot { margin: 0; color: #8fbf9f; font-size: 0.8rem; line-height: 1.4; }
        .wa__err { margin: 0; color: #e8a0a0; font-size: 0.8rem; }
        .wa__howto {
          margin: 0; padding-left: 1.1rem; color: #7a8a80;
          font-size: 0.8rem; line-height: 1.45;
        }
        .wa__howto code { font-family: var(--os-mono, monospace); color: #c8e6d0; font-size: 0.85em; }
      `}</style>
    </div>
  );
}

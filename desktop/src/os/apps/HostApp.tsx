import { useEffect, useState } from "react";
import {
  callBridge,
  probeBridge,
  runHostPreset,
  type BridgeInfo,
} from "../../bridge/hostBridge";

const APPS = [
  { id: "gmail", label: "gmail" },
  { id: "calendar", label: "agenda" },
  { id: "notion", label: "notion" },
  { id: "slack", label: "slack" },
  { id: "grok", label: "grok" },
  { id: "terminal", label: "terminal" },
  { id: "explorer", label: "arquivos" },
] as const;

const PRESETS = [
  { id: "whoami", label: "whoami" },
  { id: "date", label: "hora" },
  { id: "home-list", label: "listar home" },
] as const;

export function HostApp() {
  const [bridge, setBridge] = useState<BridgeInfo | null>(null);
  const [log, setLog] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [shellCmd, setShellCmd] = useState("");

  const refresh = async () => {
    const info = await probeBridge(1000);
    setBridge(info);
  };

  useEffect(() => {
    void refresh();
  }, []);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      const res = await fn();
      setLog(`${label}\n${JSON.stringify(res, null, 2)}`);
      await refresh();
    } catch (e) {
      setLog(`${label}\n${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const connected = bridge?.status === "connected";

  return (
    <div className="host-app">
      <p className="host-app__kicker">máquina · uso real</p>
      <h3 className="host-app__title">Abrir apps no seu PC</h3>
      <p className="host-app__body">
        {connected
          ? "Extensão ligada — escolha um app abaixo para abrir/focar na máquina."
          : "Instale a extensão Véu Host para controlar Gmail, Agenda, Grok e o terminal daqui."}
      </p>

      <div className={`host-app__status is-${bridge?.status || "missing"}`}>
        {bridge?.message || "detectando…"}
        {bridge?.version ? ` · v${bridge.version}` : ""}
      </div>

      <div className="host-app__block">
        <h4>apps</h4>
        <div className="host-app__actions">
          <button type="button" disabled={busy} onClick={() => void refresh()}>
            redetectar
          </button>
          {APPS.map((a) => (
            <button
              key={a.id}
              type="button"
              disabled={busy || !connected}
              onClick={() =>
                void run(a.label, () =>
                  a.id === "terminal" || a.id === "explorer"
                    ? runHostPreset(a.id)
                    : callBridge({ type: "veu.host.openApp", app: a.id }),
                )
              }
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      <div className="host-app__block">
        <h4>presets seguros</h4>
        <div className="host-app__actions">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={busy || !connected}
              onClick={() => void run(p.label, () => runHostPreset(p.id))}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="host-app__block">
        <h4>shell (VEU_HOST_ALLOW_SHELL=1)</h4>
        <div className="host-app__shell">
          <input
            type="text"
            placeholder="comando curto no PC local"
            value={shellCmd}
            onChange={(e) => setShellCmd(e.target.value)}
            disabled={busy || !connected}
          />
          <button
            type="button"
            disabled={busy || !connected || !shellCmd.trim()}
            onClick={() =>
              void run("shell", () =>
                callBridge({
                  type: "veu.host.shell",
                  command: shellCmd.trim(),
                }),
              )
            }
          >
            executar
          </button>
        </div>
      </div>

      {!connected && (
        <ol className="host-app__howto">
          <li>
            Abra{" "}
            <a href="/veu-host-install.htm" style={{ color: "var(--signal)" }}>
              instruções
            </a>{" "}
            ou baixe direto{" "}
            <a href="/veu-host-0.3.7.tar.gz" style={{ color: "var(--signal)" }}>
              veu-host-0.3.7.tar.gz
            </a>
            .
          </li>
          <li>
            Em <code>chrome://extensions</code> → modo desenvolvedor → carregar
            a pasta descompactada → F5 no Véu.
          </li>
          <li>
            Use <code>https://veu.ch8ai.com.br</code> e dê F5 — topo: <em>host · ok</em>.
          </li>
        </ol>
      )}

      {log && <pre className="host-app__log">{log}</pre>}

      <style>{`
        .host-app { padding: 1rem 1.1rem; display: grid; gap: 0.7rem; }
        .host-app__kicker {
          margin: 0; font-family: var(--font-mono); font-size: 0.65rem;
          letter-spacing: 0.16em; color: var(--signal); text-transform: lowercase;
        }
        .host-app__title {
          margin: 0; font-family: var(--font-display); font-size: 1.35rem;
        }
        .host-app__body {
          margin: 0; color: var(--mist-dim); font-weight: 300; line-height: 1.5;
        }
        .host-app__status {
          font-family: var(--font-mono); font-size: 0.75rem; letter-spacing: 0.04em;
          padding: 0.55rem 0.7rem; border: 1px solid rgba(236,242,248,0.1);
        }
        .host-app__status.is-connected { color: var(--signal); border-color: rgba(127,231,212,0.35); }
        .host-app__status.is-missing { color: var(--mist-dim); }
        .host-app__block h4 {
          margin: 0 0 0.35rem;
          font-family: var(--font-mono);
          font-size: 0.6rem;
          letter-spacing: 0.12em;
          color: var(--signal);
          text-transform: lowercase;
          font-weight: 500;
        }
        .host-app__actions { display: flex; flex-wrap: wrap; gap: 0.45rem; }
        .host-app__actions button, .host-app__shell button {
          border: 1px solid rgba(232,194,122,0.35); background: transparent;
          color: var(--filament); padding: 0.45rem 0.7rem; cursor: pointer;
          font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.08em;
          text-transform: lowercase;
        }
        .host-app__actions button:disabled, .host-app__shell button:disabled {
          opacity: 0.4; cursor: default;
        }
        .host-app__shell {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.4rem;
        }
        .host-app__shell input {
          border: 1px solid rgba(127,231,212,0.22);
          background: rgba(7,9,12,0.55);
          color: var(--mist);
          padding: 0.45rem 0.55rem;
          font-family: var(--font-mono);
          font-size: 0.72rem;
        }
        .host-app__howto {
          margin: 0; padding-left: 1.1rem; color: var(--mist-dim);
          font-size: 0.85rem; line-height: 1.5;
        }
        .host-app__howto code {
          font-family: var(--font-mono); color: var(--filament); font-size: 0.8em;
        }
        .host-app__log {
          margin: 0; padding: 0.7rem; overflow: auto; max-height: 160px;
          background: rgba(0,0,0,0.35); color: var(--mist);
          font-family: var(--font-mono); font-size: 0.68rem;
        }
      `}</style>
    </div>
  );
}

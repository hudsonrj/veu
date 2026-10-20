import { useCallback, useEffect, useState } from "react";
import {
  callBridge,
  probeBridge,
  type BridgeInfo,
} from "../../bridge/hostBridge";
import { apiFetch, KERNEL  } from "../../lib/kernel";

type Entry = {
  name?: string;
  path?: string;
  type?: string;
  is_dir?: boolean;
};

type StudioAction = {
  id: string;
  label: string;
  hint?: string;
  kinds?: string[];
};

type MenuState = {
  entry: Entry;
  kind: string;
  actions: StudioAction[];
};

/** Arquivos da máquina — duplo-clique abre menu de ações do Studio. */
export function FilesApp() {
  const [bridge, setBridge] = useState<BridgeInfo | null>(null);
  const [native, setNative] = useState<boolean | null>(null);
  const [nativeNote, setNativeNote] = useState<string>("");
  const [path, setPath] = useState<string>("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [log, setLog] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [result, setResult] = useState<string>("");

  const refresh = useCallback(async () => {
    const info = await probeBridge(2000);
    setBridge(info);
    if (info.status !== "connected") {
      setNative(false);
      setNativeNote("instale / recarregue a Véu Host 0.3.3");
      return;
    }
    const res = await callBridge({ type: "veu.host.info" }, 5000);
    const data = (res.data || {}) as Record<string, unknown>;
    const ok = !!(res.ok && (data.nativeConnected || data.native));
    setNative(ok);
    setNativeNote(
      ok
        ? `host nativo ok · ${String(data.nativeHost || "com.veu.host")}`
        : String(
            data.nativeError ||
              data.note ||
              res.error ||
              "Recarregue a extensão 0.3.3 e feche/abra o Chrome (host nativo)",
          ),
    );
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const list = async (target?: string) => {
    setBusy(true);
    setMenu(null);
    try {
      const p = target ?? path;
      const res = await callBridge(
        { type: "veu.host.listDir", path: p || "." },
        10000,
      );
      setLog(JSON.stringify(res, null, 2));
      if (res.ok) {
        const data = (res.data || {}) as { path?: string; entries?: Entry[] };
        if (data.path) setPath(data.path);
        setEntries(Array.isArray(data.entries) ? data.entries : []);
      } else {
        setEntries([]);
      }
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const openMenu = async (entry: Entry) => {
    if (!entry.path || entry.is_dir || entry.type === "dir") return;
    setBusy(true);
    setResult("");
    try {
      const name = entry.name || entry.path.split(/[/\\]/).pop() || "file";
      const res = await fetch(
        `${KERNEL}/studio/actions?path=${encodeURIComponent(entry.path)}&filename=${encodeURIComponent(name)}`,
      );
      const raw = await res.text();
      const data = raw
        ? (JSON.parse(raw) as {
            kind?: string;
            actions?: StudioAction[];
          })
        : {};
      setMenu({
        entry,
        kind: data.kind || "binary",
        actions: data.actions || [],
      });
    } catch (e) {
      setResult(e instanceof Error ? e.message : "falha ao montar menu");
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (actionId: string) => {
    if (!menu?.entry.path) return;
    setBusy(true);
    setResult("executando…");
    try {
      const name =
        menu.entry.name || menu.entry.path.split(/[/\\]/).pop() || "file";
      // lê texto do host quando possível
      let text = "";
      const read = await callBridge(
        { type: "veu.host.readPath", path: menu.entry.path },
        12000,
      );
      if (read.ok) {
        const data = (read.data || {}) as { text?: string };
        text = data.text || "";
      }

      let assetId: string | undefined;
      if (text) {
        const fd = new FormData();
        fd.append("filename", name);
        fd.append("text", text);
        fd.append("path", menu.entry.path);
        const up = await apiFetch(`${KERNEL}/studio/from-text`, {
          method: "POST",
          body: fd,
        });
        const upRaw = await up.text();
        const upData = upRaw
          ? (JSON.parse(upRaw) as { asset?: { id?: string } })
          : {};
        assetId = upData.asset?.id;
      }

      const res = await apiFetch(`${KERNEL}/studio/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: actionId,
          asset_id: assetId,
          path: menu.entry.path,
          filename: name,
          text: text || undefined,
        }),
      });
      const raw = await res.text();
      const data = raw
        ? (JSON.parse(raw) as {
            job?: {
              result?: { message?: string; text?: string };
              decision?: { executor?: string; reason?: string };
              status?: string;
            };
            error?: string;
          })
        : {};
      const job = data.job;
      const msg =
        job?.result?.text ||
        job?.result?.message ||
        data.error ||
        "sem saída";
      const who = job?.decision
        ? `\n· via ${job.decision.executor} — ${job.decision.reason}`
        : "";
      setResult(`${msg}${who}`);
    } catch (e) {
      setResult(e instanceof Error ? e.message : "falha");
    } finally {
      setBusy(false);
    }
  };

  const extOk = bridge?.status === "connected";
  const status = native ? "live" : extOk ? "ready" : "missing";

  return (
    <div className="files">
      <p className="files__kicker">arquivos · máquina física</p>
      <p className={`files__status is-${status}`}>
        {status === "live"
          ? "live · native messaging"
          : status === "ready"
            ? "extensão ok · falta host nativo"
            : "extensão ausente"}
      </p>
      <p className="files__blurb">
        Duplo-clique num arquivo → menu de ações (analisar, transcrever, RAG,
        DW, Hermes, Grok Bot).
      </p>
      <p className="files__hint">{nativeNote || bridge?.message}</p>

      <div className="files__actions">
        <button type="button" disabled={busy} onClick={() => void refresh()}>
          redetectar
        </button>
        <button
          type="button"
          disabled={busy || !extOk}
          onClick={() => void list(".")}
        >
          listar pasta
        </button>
        <a className="files__link" href="/extension/#native">
          instalar host
        </a>
      </div>

      {path ? <p className="files__path">{path}</p> : null}

      {entries.length > 0 && (
        <ul className="files__list">
          {entries.slice(0, 60).map((e, i) => {
            const isDir = !!(e.is_dir || e.type === "dir");
            return (
              <li key={`${e.path || e.name || i}`}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    if (isDir && e.path) void list(e.path);
                  }}
                  onDoubleClick={() => {
                    if (!isDir) void openMenu(e);
                    else if (e.path) void list(e.path);
                  }}
                >
                  {isDir ? "📁" : "·"} {e.name || e.path}
                  {!isDir ? (
                    <em className="files__dbl">duplo-clique</em>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {menu ? (
        <div className="files__menu">
          <header>
            <strong>{menu.entry.name || menu.entry.path}</strong>
            <span>{menu.kind}</span>
            <button type="button" onClick={() => setMenu(null)}>
              fechar
            </button>
          </header>
          <div className="files__menu-actions">
            {menu.actions.map((a) => (
              <button
                key={a.id}
                type="button"
                disabled={busy}
                title={a.hint}
                onClick={() => void runAction(a.id)}
              >
                {a.label}
              </button>
            ))}
          </div>
          {result ? <pre className="files__result">{result}</pre> : null}
        </div>
      ) : null}

      {log ? <pre className="files__log">{log}</pre> : null}

      <style>{`
        .files {
          padding: 1rem 1.1rem;
          display: grid;
          gap: 0.5rem;
          height: 100%;
          min-height: 0;
          overflow: auto;
        }
        .files__kicker {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.16em;
          color: var(--signal);
        }
        .files__status {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.78rem;
          letter-spacing: 0.08em;
          color: var(--mist-dim);
        }
        .files__status.is-live { color: var(--filament); }
        .files__status.is-ready { color: var(--signal); }
        .files__blurb {
          margin: 0;
          font-size: 1rem;
          font-weight: 300;
          line-height: 1.45;
          color: var(--mist);
        }
        .files__hint {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          color: var(--mist-dim);
        }
        .files__actions {
          display: flex;
          flex-wrap: wrap;
          gap: 0.4rem;
          align-items: center;
        }
        .files__actions button, .files__link {
          border: 1px solid rgba(232,194,122,0.35);
          background: transparent;
          color: var(--filament);
          padding: 0.4rem 0.65rem;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.06em;
          cursor: pointer;
          text-decoration: none;
        }
        .files__actions button:disabled { opacity: 0.4; cursor: default; }
        .files__path {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.7rem;
          color: var(--signal);
          word-break: break-all;
        }
        .files__list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 0.15rem;
        }
        .files__list button {
          width: 100%;
          border: 0;
          background: transparent;
          color: var(--mist);
          font-family: var(--font-mono);
          font-size: 0.72rem;
          text-align: left;
          padding: 0.3rem 0.2rem;
          cursor: pointer;
          display: flex;
          gap: 0.5rem;
          align-items: baseline;
        }
        .files__list button:hover {
          background: rgba(232,194,122,0.08);
        }
        .files__dbl {
          margin-left: auto;
          font-style: normal;
          font-size: 0.6rem;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--mist-dim);
          opacity: 0.7;
        }
        .files__menu {
          border: 1px solid rgba(127,231,212,0.3);
          background: rgba(0,0,0,0.35);
          padding: 0.7rem;
          display: grid;
          gap: 0.5rem;
        }
        .files__menu header {
          display: flex;
          gap: 0.5rem;
          align-items: center;
          flex-wrap: wrap;
        }
        .files__menu header strong {
          font-size: 0.85rem;
          color: var(--filament);
        }
        .files__menu header span {
          font-family: var(--font-mono);
          font-size: 0.65rem;
          color: #7fe7d4;
          text-transform: uppercase;
        }
        .files__menu header button {
          margin-left: auto;
          border: 1px solid rgba(255,255,255,0.15);
          background: transparent;
          color: var(--mist-dim);
          font-size: 0.65rem;
          padding: 0.2rem 0.45rem;
          cursor: pointer;
        }
        .files__menu-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 0.35rem;
        }
        .files__menu-actions button {
          border: 1px solid rgba(127,231,212,0.35);
          background: rgba(127,231,212,0.08);
          color: #c8f0e6;
          padding: 0.35rem 0.6rem;
          font-size: 0.72rem;
          cursor: pointer;
        }
        .files__menu-actions button:disabled { opacity: 0.4; }
        .files__result {
          margin: 0;
          padding: 0.55rem;
          max-height: 180px;
          overflow: auto;
          background: rgba(0,0,0,0.4);
          font-family: var(--font-mono);
          font-size: 0.68rem;
          white-space: pre-wrap;
          color: var(--mist);
        }
        .files__log {
          margin: 0;
          padding: 0.6rem;
          max-height: 100px;
          overflow: auto;
          background: rgba(0,0,0,0.35);
          font-family: var(--font-mono);
          font-size: 0.65rem;
          color: var(--mist-dim);
        }
      `}</style>
    </div>
  );
}

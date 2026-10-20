import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";
import { callBridge, probeBridge, type BridgeInfo } from "../../bridge/hostBridge";

type ServerApp = {
  id?: string;
  name?: string;
  status?: string;
  cpu?: number;
  ram?: number;
  domain?: string;
};

type ServerCard = {
  id: string;
  hostname?: string;
  provider?: string;
  os?: string;
  reverseProxy?: string;
  domains?: string[];
  role?: string;
  apps?: ServerApp[];
  apps_up?: number;
  apps_total?: number;
  glyph?: string;
  hue?: string;
  source?: string;
  kind?: string;
  ssh?: {
    fleet_id?: string | null;
    host?: string;
    port?: number;
    username?: string;
    has_secret?: boolean;
    needs_register?: boolean;
    command?: string;
    last_status?: string;
    last_probe?: Record<string, unknown>;
  };
};

type Board = {
  ok?: boolean;
  updatedAt?: string;
  fleetHealth?: string;
  servers?: ServerCard[];
  counts?: Record<string, number>;
  fleetNotes?: { text?: string; agent?: string }[];
};

async function fetchBoard(): Promise<Board | null> {
  try {
    const res = await apiFetch(`${KERNEL}/servers/board`);
    if (!res.ok) return null;
    return (await res.json()) as Board;
  } catch {
    return null;
  }
}

async function requestSsh(id: string) {
  const res = await apiFetch(
    `${KERNEL}/servers/${encodeURIComponent(id)}/ssh?reveal=1`,
    { method: "POST" },
  );
  return (await res.json()) as {
    ok?: boolean;
    command?: string;
    has_secret?: boolean;
    needs_register?: boolean;
    probe?: Record<string, unknown>;
    probe_ok?: boolean;
    error?: string;
    hint?: string;
  };
}

/** Pastas/ícones de servidores — inventário live + SSH na frota. */
export function ServersApp() {
  const [board, setBoard] = useState<Board | null>(null);
  const [selected, setSelected] = useState<ServerCard | null>(null);
  const [host, setHost] = useState<BridgeInfo | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [b, h] = await Promise.all([fetchBoard(), probeBridge(1200)]);
    setBoard(b);
    setHost(h);
    setErr(b?.ok ? null : "board indisponível");
    if (selected && b?.servers) {
      const next = b.servers.find((s) => s.id === selected.id);
      if (next) setSelected(next);
    }
  }, [selected]);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 60_000);
    return () => window.clearInterval(id);
  }, [reload]);

  const openSsh = async (card: ServerCard) => {
    setBusy(`ssh:${card.id}`);
    setNote(null);
    try {
      const r = await requestSsh(card.id);
      if (!r.ok || !r.command) {
        setNote(r.error || "sem comando SSH — cadastre o host em Ajustes → servidores");
        return;
      }
      const cmd = r.command;
      try {
        await navigator.clipboard.writeText(cmd);
      } catch {
        /* ignore */
      }

      if (host?.status === "connected") {
        const br = await callBridge({ type: "veu.host.ssh", command: cmd }, 12_000);
        if (br.ok) {
          setNote(
            `terminal aberto · ${cmd}` +
              (r.probe_ok === false ? " · probe falhou (senha?)" : "") +
              (r.probe_ok ? " · probe ok" : ""),
          );
          return;
        }
        // fallback: abre terminal vazio
        await callBridge({ type: "veu.host.openApp", app: "terminal" });
        setNote(
          `comando copiado: ${cmd} — cole no terminal` +
            (br.error ? ` (${br.error})` : ""),
        );
        return;
      }

      setNote(
        `comando copiado: ${cmd}` +
          (r.needs_register
            ? " · cadastre a senha em Ajustes para probe"
            : " · instale Véu Host para abrir o terminal"),
      );
    } finally {
      setBusy(null);
      void reload();
    }
  };

  const servers = board?.servers || [];

  return (
    <div className="srv">
      <header className="srv__head">
        <div>
          <p className="srv__kicker">servidores · live + frota</p>
          <h2 className="srv__title">máquinas</h2>
          <p className="srv__sub">
            inventário do Control (apps/domínios) + SSH nos hosts cadastrados.
            frota · {board?.fleetHealth || "—"} ·{" "}
            {board?.counts?.total ?? 0} ícone(s)
          </p>
        </div>
        <button type="button" onClick={() => void reload()}>
          atualizar
        </button>
      </header>

      {err ? <p className="srv__err">{err}</p> : null}
      {note ? <p className="srv__note">{note}</p> : null}

      <div className={`srv__split${selected ? " has-detail" : ""}`}>
        <div className="srv__icons">
          {servers.map((s) => (
            <button
              key={s.id}
              type="button"
              className={`srv__icon${selected?.id === s.id ? " is-on" : ""}`}
              style={{ ["--hue" as string]: s.hue || "#E8C27A" }}
              onClick={() => setSelected(s)}
              onDoubleClick={() => void openSsh(s)}
              title="duplo-clique · SSH"
            >
              <span className="srv__glyph" aria-hidden>
                {s.glyph || "S"}
              </span>
              <strong>{s.hostname || s.id}</strong>
              <em>
                {s.provider || s.kind}
                {s.apps_total
                  ? ` · ${s.apps_up ?? 0}/${s.apps_total} up`
                  : ""}
              </em>
              <i className={s.ssh?.fleet_id || s.ssh?.command ? "is-ssh" : ""}>
                {s.ssh?.has_secret
                  ? "ssh · ok"
                  : s.ssh?.command
                    ? "ssh · hint"
                    : "ssh · —"}
              </i>
            </button>
          ))}
          {!servers.length ? (
            <p className="srv__empty">nenhum servidor no live/frota</p>
          ) : null}
        </div>

        {selected ? (
          <aside className="srv__detail">
            <header>
              <p className="srv__kicker">{selected.provider || selected.kind}</p>
              <button type="button" onClick={() => setSelected(null)}>
                fechar
              </button>
            </header>
            <h3>{selected.hostname}</h3>
            <p className="srv__role">{selected.role || "—"}</p>
            <p className="srv__meta">
              {selected.os}
              {selected.reverseProxy ? ` · ${selected.reverseProxy}` : ""}
            </p>

            {(selected.domains || []).length ? (
              <div className="srv__block">
                <h4>domínios</h4>
                <ul>
                  {(selected.domains || []).map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="srv__block">
              <h4>
                o que tem aqui{" "}
                <em>
                  {selected.apps_up ?? 0}/{selected.apps_total ?? 0} up
                </em>
              </h4>
              {(selected.apps || []).length === 0 ? (
                <p className="srv__empty">sem inventário de apps no live</p>
              ) : (
                <ul className="srv__apps">
                  {(selected.apps || []).map((a) => (
                    <li key={a.id || a.name}>
                      <strong>{a.name}</strong>
                      <span className={`is-${a.status || "unknown"}`}>
                        {a.status || "—"}
                      </span>
                      <em>
                        {[
                          a.domain,
                          a.cpu != null ? `cpu ${a.cpu}` : "",
                          a.ram != null ? `ram ${a.ram}` : "",
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </em>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="srv__block">
              <h4>ssh</h4>
              <p className="srv__cmd">{selected.ssh?.command || "cadastre o host em Ajustes"}</p>
              {selected.ssh?.last_probe ? (
                <p className="srv__meta">
                  último probe ·{" "}
                  {String(
                    (selected.ssh.last_probe as { hostname?: string }).hostname ||
                      selected.ssh.last_status ||
                      "",
                  )}
                </p>
              ) : null}
              <div className="srv__actions">
                <button
                  type="button"
                  disabled={!!busy || !selected.ssh?.command}
                  onClick={() => void openSsh(selected)}
                >
                  {busy === `ssh:${selected.id}` ? "…" : "abrir SSH"}
                </button>
                <button
                  type="button"
                  disabled={!selected.ssh?.command}
                  onClick={() => {
                    const c = selected.ssh?.command;
                    if (c) void navigator.clipboard.writeText(c);
                    setNote(c ? `copiado · ${c}` : null);
                  }}
                >
                  copiar comando
                </button>
              </div>
              <p className="srv__hint">
                host · {host?.status === "connected" ? "ok" : "off"} — SSH abre
                terminal na máquina física via Véu Host. Duplo-clique no ícone
                também.
              </p>
            </div>
          </aside>
        ) : null}
      </div>

      <style>{`
        .srv {
          height: 100%;
          min-height: 0;
          display: grid;
          grid-template-rows: auto auto 1fr;
          gap: 0.45rem;
          padding: 0.65rem 0.75rem 0.7rem;
          color: var(--mist);
          overflow: hidden;
        }
        .srv__head {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
          align-items: flex-start;
        }
        .srv__kicker {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.54rem;
          letter-spacing: 0.14em;
          color: var(--signal);
          text-transform: lowercase;
        }
        .srv__title {
          margin: 0.1rem 0 0;
          font-family: var(--font-display);
          font-size: 1.25rem;
          color: var(--filament);
          font-weight: 700;
        }
        .srv__sub {
          margin: 0.2rem 0 0;
          font-size: 0.72rem;
          color: var(--mist-dim);
          max-width: 34rem;
          line-height: 1.35;
        }
        .srv__head button, .srv__detail header button, .srv__actions button {
          border: 1px solid rgba(236,242,248,0.16);
          background: transparent;
          color: var(--mist-dim);
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.08em;
          text-transform: lowercase;
          padding: 0.3rem 0.5rem;
          cursor: pointer;
        }
        .srv__head button:hover, .srv__detail header button:hover,
        .srv__actions button:hover:not(:disabled) {
          border-color: rgba(232,194,122,0.45);
          color: var(--filament);
        }
        .srv__actions button:disabled { opacity: 0.35; cursor: default; }
        .srv__err { margin: 0; color: #e8a07a; font-size: 0.7rem; }
        .srv__note { margin: 0; color: var(--filament); font-size: 0.7rem; }
        .srv__split {
          min-height: 0;
          display: grid;
          grid-template-columns: 1fr;
          gap: 0.5rem;
          overflow: hidden;
        }
        .srv__split.has-detail {
          grid-template-columns: minmax(0, 1fr) minmax(260px, 0.95fr);
        }
        .srv__icons {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(7.4rem, 1fr));
          gap: 0.45rem;
          align-content: start;
          overflow: auto;
          scrollbar-width: thin;
        }
        .srv__icon {
          display: grid;
          justify-items: center;
          gap: 0.22rem;
          text-align: center;
          padding: 0.55rem 0.4rem 0.45rem;
          border: 1px solid color-mix(in srgb, var(--hue) 35%, transparent);
          background: rgba(7,9,12,0.42);
          color: var(--mist);
          cursor: pointer;
        }
        .srv__icon.is-on, .srv__icon:hover {
          border-color: var(--hue);
          color: var(--filament);
        }
        .srv__glyph {
          width: 2.5rem;
          height: 2.5rem;
          display: grid;
          place-items: center;
          border: 1px solid color-mix(in srgb, var(--hue) 55%, transparent);
          color: var(--hue);
          font-family: var(--font-display);
          font-size: 1.05rem;
          font-weight: 700;
          background: color-mix(in srgb, var(--hue) 12%, transparent);
        }
        .srv__icon strong { font-size: 0.7rem; font-weight: 500; line-height: 1.25; }
        .srv__icon em, .srv__icon i {
          font-style: normal;
          font-size: 0.52rem;
          color: var(--mist-dim);
          line-height: 1.3;
        }
        .srv__icon i.is-ssh { color: var(--signal); }
        .srv__detail {
          min-height: 0;
          overflow: auto;
          scrollbar-width: thin;
          padding: 0.55rem 0.6rem;
          border: 1px solid rgba(127,231,212,0.16);
          background: rgba(6,10,12,0.55);
          display: grid;
          align-content: start;
          gap: 0.4rem;
        }
        .srv__detail header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .srv__detail h3 {
          margin: 0;
          font-family: var(--font-display);
          font-size: 1.05rem;
          color: var(--filament);
        }
        .srv__role { margin: 0; font-size: 0.72rem; line-height: 1.4; color: var(--mist); }
        .srv__meta, .srv__hint {
          margin: 0;
          font-size: 0.62rem;
          color: var(--mist-dim);
          line-height: 1.35;
        }
        .srv__block h4 {
          margin: 0 0 0.25rem;
          font-family: var(--font-mono);
          font-size: 0.54rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
          color: var(--signal);
          display: flex;
          justify-content: space-between;
        }
        .srv__block h4 em { font-style: normal; color: var(--mist-dim); }
        .srv__block ul { margin: 0; padding-left: 1rem; }
        .srv__block li { font-size: 0.68rem; color: var(--mist-dim); }
        .srv__apps {
          list-style: none;
          padding: 0;
          display: grid;
          gap: 0.3rem;
        }
        .srv__apps li {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.1rem 0.4rem;
          padding-bottom: 0.28rem;
          border-bottom: 1px solid rgba(232,194,122,0.08);
        }
        .srv__apps strong { font-size: 0.72rem; color: var(--mist); font-weight: 500; }
        .srv__apps span {
          font-family: var(--font-mono);
          font-size: 0.52rem;
          letter-spacing: 0.06em;
          text-transform: lowercase;
        }
        .srv__apps span.is-up { color: var(--signal); }
        .srv__apps em {
          grid-column: 1 / -1;
          font-style: normal;
          font-size: 0.58rem;
          color: var(--mist-dim);
        }
        .srv__cmd {
          margin: 0 0 0.3rem;
          font-family: var(--font-mono);
          font-size: 0.64rem;
          color: var(--filament);
          word-break: break-all;
        }
        .srv__actions { display: flex; flex-wrap: wrap; gap: 0.3rem; }
        .srv__empty { margin: 0.3rem 0; font-size: 0.7rem; color: var(--mist-dim); }
        @media (max-width: 720px) {
          .srv__split.has-detail { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";

type Hit = {
  id?: string;
  title?: string;
  url?: string;
  object?: string;
};

/** Notion — busca real no workspace. */
export function NotionApp() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"live" | "ready" | "off">("off");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const res = await apiFetch(`${KERNEL}/notion/pulse`);
      const data = (await res.json()) as { status?: string };
      setStatus(data.status === "live" ? "live" : "ready");
    } catch {
      setStatus("off");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const search = async (query?: string) => {
    const text = (query ?? q).trim();
    if (!text) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch(`${KERNEL}/notion/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: text, page_size: 12 }),
      });
      const raw = await res.text();
      const data = raw
        ? (JSON.parse(raw) as {
            ok?: boolean;
            results?: Hit[];
            message?: string;
            error?: string;
          })
        : {};
      setHits(data.results || []);
      setMsg(data.message || null);
      if (!data.ok) setErr(data.error || data.message || "busca falhou");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
      setHits([]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ntn">
      <header className="ntn__bar">
        <div className={`ntn__pip is-${status}`} />
        <span>{status === "live" ? "workspace online" : "configure NOTION_TOKEN"}</span>
      </header>

      <form
        className="ntn__form"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <input
          value={q}
          disabled={busy}
          placeholder="buscar páginas e databases…"
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <button type="submit" disabled={busy || !q.trim()}>
          {busy ? "…" : "buscar"}
        </button>
      </form>

      <div className="ntn__chips">
        {["plano", "reunião", "véu", "decisões"].map((c) => (
          <button
            key={c}
            type="button"
            disabled={busy}
            onClick={() => {
              setQ(c);
              void search(c);
            }}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="ntn__results">
        {hits.length === 0 ? (
          <p className="ntn__empty">
            {msg || "Digite e busque — resultados aparecem aqui."}
          </p>
        ) : (
          <ul>
            {hits.map((h) => (
              <li key={h.id || h.url || h.title}>
                <strong>{h.title || "(sem título)"}</strong>
                <span>{h.object || "page"}</span>
                {h.url ? (
                  <a href={h.url} target="_blank" rel="noreferrer">
                    abrir
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
      {err ? <p className="ntn__err">{err}</p> : null}

      <style>{`
        .ntn {
          height: 100%;
          display: grid;
          grid-template-rows: auto auto auto 1fr auto;
          gap: 0.55rem;
          padding: 0.75rem 0.85rem;
          background: linear-gradient(165deg, #121214, #0c0c0e 70%);
          color: #ececec;
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .ntn__bar {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.72rem;
          color: #8a8a8a;
        }
        .ntn__pip {
          width: 7px; height: 7px; border-radius: 50%; background: #555;
        }
        .ntn__pip.is-live { background: #e8e8e8; }
        .ntn__pip.is-ready { background: #d4b896; }
        .ntn__form {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.4rem;
        }
        .ntn__form input {
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(0,0,0,0.35);
          color: #ececec;
          padding: 0.55rem 0.65rem;
          font: inherit;
        }
        .ntn__form button {
          border: 1px solid rgba(232,232,232,0.35);
          background: rgba(255,255,255,0.08);
          color: #fff;
          padding: 0 0.85rem;
          cursor: pointer;
        }
        .ntn__chips {
          display: flex;
          flex-wrap: wrap;
          gap: 0.3rem;
        }
        .ntn__chips button {
          border: 1px solid rgba(255,255,255,0.1);
          background: transparent;
          color: #a8a8a8;
          padding: 0.25rem 0.55rem;
          font-size: 0.72rem;
          cursor: pointer;
        }
        .ntn__results {
          min-height: 0;
          overflow: auto;
        }
        .ntn__empty {
          margin: 1rem 0;
          color: #7a7a7a;
          font-size: 0.9rem;
        }
        .ntn__results ul {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 0.35rem;
        }
        .ntn__results li {
          display: grid;
          grid-template-columns: 1fr auto auto;
          gap: 0.5rem;
          align-items: center;
          padding: 0.55rem 0.6rem;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.06);
        }
        .ntn__results strong {
          font-weight: 500;
          font-size: 0.9rem;
        }
        .ntn__results span {
          font-size: 0.65rem;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: #7a7a7a;
        }
        .ntn__results a {
          color: #e8e8e8;
          font-size: 0.72rem;
        }
        .ntn__err { margin: 0; color: #e8a0a0; font-size: 0.78rem; }
      `}</style>
    </div>
  );
}

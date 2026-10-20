import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";

type Source = {
  title?: string;
  url?: string;
  score?: number;
  snippet?: string;
  content?: string;
};

type Turn = {
  id: string;
  role: "you" | "rag";
  text: string;
  sources?: Source[];
};

const SUGGESTIONS = [
  "o que há de mais relevante na base agora?",
  "resuma os documentos recentes em 5 bullets",
  "quais decisões de arquitetura estão documentadas?",
  "procure menções a Hermes ou Grok Bot",
];

/** OpenRAG — pergunta real à base documental. */
export function OpenRagApp() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"live" | "ready" | "off">("off");
  const [base, setBase] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const reload = useCallback(async () => {
    try {
      const res = await apiFetch(`${KERNEL}/openrag/pulse`);
      const data = (await res.json()) as {
        status?: string;
        base_url?: string | null;
        key_configured?: boolean;
      };
      setStatus(data.status === "live" ? "live" : data.key_configured ? "ready" : "off");
      setBase(data.base_url || "");
    } catch {
      setStatus("off");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setErr(null);
    setTurns((t) => [...t, { id: `${Date.now()}-u`, role: "you", text: q }]);
    setDraft("");
    try {
      const res = await apiFetch(`${KERNEL}/openrag/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: q, limit: 8 }),
      });
      const raw = await res.text();
      const data = raw
        ? (JSON.parse(raw) as {
            ok?: boolean;
            answer?: string;
            message?: string;
            sources?: Source[];
            error?: string;
          })
        : {};
      const answer =
        (data.answer || "").trim() ||
        data.message ||
        data.error ||
        "sem resposta da base";
      setTurns((t) => [
        ...t,
        {
          id: `${Date.now()}-a`,
          role: "rag",
          text: answer,
          sources: Array.isArray(data.sources) ? data.sources : [],
        },
      ]);
      if (!data.ok) setErr(data.message || data.error || "consulta falhou");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
      setTurns((t) => [
        ...t,
        {
          id: `${Date.now()}-e`,
          role: "rag",
          text: "Não consegui falar com a base agora.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="orag">
      <header className="orag__bar">
        <div className={`orag__pip is-${status}`} />
        <span>{status === "live" ? "base online" : status === "ready" ? "sem chave" : "offline"}</span>
        {base ? <em>{base.replace(/^https?:\/\//, "")}</em> : null}
      </header>

      <div className="orag__stream">
        {turns.length === 0 ? (
          <div className="orag__empty">
            <p>Pergunte à base documental.</p>
            <div className="orag__chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" disabled={busy} onClick={() => void ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((t) => (
            <article key={t.id} className={`orag__turn is-${t.role}`}>
              <span>{t.role === "you" ? "você" : "openrag"}</span>
              <p>{t.text}</p>
              {t.sources && t.sources.length > 0 ? (
                <ul className="orag__sources">
                  {t.sources.slice(0, 6).map((s, i) => (
                    <li key={i}>
                      <strong>{s.title || s.url || `fonte ${i + 1}`}</strong>
                      {s.snippet || s.content ? (
                        <em>{String(s.snippet || s.content).slice(0, 160)}</em>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))
        )}
        {busy ? <p className="orag__busy">consultando a base…</p> : null}
        <div ref={bottomRef} />
      </div>

      <form
        className="orag__form"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(draft);
        }}
      >
        <textarea
          rows={2}
          value={draft}
          disabled={busy}
          placeholder="perguntar à base…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(draft);
            }
          }}
        />
        <button type="submit" disabled={busy || !draft.trim()}>
          {busy ? "…" : "perguntar"}
        </button>
      </form>
      {err ? <p className="orag__err">{err}</p> : null}

      <style>{`
        .orag {
          height: 100%;
          display: grid;
          grid-template-rows: auto 1fr auto auto;
          gap: 0.5rem;
          padding: 0.75rem 0.85rem;
          background: linear-gradient(165deg, #0e1416, #0a1012 70%);
          color: #e4eeea;
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .orag__bar {
          display: flex;
          align-items: center;
          gap: 0.45rem;
          font-size: 0.72rem;
          letter-spacing: 0.04em;
          color: #8a9a94;
        }
        .orag__bar em {
          margin-left: auto;
          font-style: normal;
          font-family: "IBM Plex Mono", monospace;
          font-size: 0.65rem;
          color: #6b7a74;
        }
        .orag__pip {
          width: 7px; height: 7px; border-radius: 50%;
          background: #5a6560;
        }
        .orag__pip.is-live { background: #7fe7d4; }
        .orag__pip.is-ready { background: #d4b896; }
        .orag__stream {
          min-height: 0;
          overflow: auto;
          display: flex;
          flex-direction: column;
          gap: 0.55rem;
        }
        .orag__empty {
          margin: auto 0;
          display: grid;
          gap: 0.7rem;
        }
        .orag__empty p {
          margin: 0;
          font-size: 1.05rem;
          font-weight: 300;
          color: #c5d0cb;
        }
        .orag__chips {
          display: flex;
          flex-wrap: wrap;
          gap: 0.35rem;
        }
        .orag__chips button {
          border: 1px solid rgba(127,231,212,0.25);
          background: rgba(127,231,212,0.06);
          color: #b8d4cc;
          padding: 0.35rem 0.6rem;
          font-size: 0.75rem;
          cursor: pointer;
          text-align: left;
        }
        .orag__turn {
          padding: 0.55rem 0.65rem;
          max-width: 96%;
        }
        .orag__turn span {
          display: block;
          font-size: 0.62rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          opacity: 0.55;
          margin-bottom: 0.2rem;
        }
        .orag__turn p {
          margin: 0;
          font-size: 0.92rem;
          line-height: 1.45;
          white-space: pre-wrap;
        }
        .orag__turn.is-you {
          align-self: flex-end;
          background: rgba(255,255,255,0.04);
        }
        .orag__turn.is-rag {
          align-self: flex-start;
          background: rgba(127,231,212,0.08);
          border: 1px solid rgba(127,231,212,0.18);
        }
        .orag__sources {
          list-style: none;
          margin: 0.55rem 0 0;
          padding: 0;
          display: grid;
          gap: 0.35rem;
        }
        .orag__sources li {
          display: grid;
          gap: 0.1rem;
          padding: 0.35rem 0.45rem;
          background: rgba(0,0,0,0.25);
          font-size: 0.72rem;
        }
        .orag__sources strong { font-weight: 500; color: #7fe7d4; }
        .orag__sources em {
          font-style: normal;
          color: #8a9a94;
        }
        .orag__busy {
          margin: 0;
          font-size: 0.75rem;
          color: #7fe7d4;
        }
        .orag__form {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.45rem;
        }
        .orag__form textarea {
          border: 1px solid rgba(255,255,255,0.1);
          background: rgba(0,0,0,0.35);
          color: #e4eeea;
          padding: 0.5rem 0.6rem;
          font: inherit;
          resize: none;
        }
        .orag__form button {
          align-self: end;
          border: 1px solid rgba(127,231,212,0.45);
          background: rgba(127,231,212,0.14);
          color: #e8faf6;
          padding: 0.5rem 0.85rem;
          cursor: pointer;
        }
        .orag__form button:disabled { opacity: 0.4; cursor: default; }
        .orag__err { margin: 0; color: #e8a0a0; font-size: 0.78rem; }
      `}</style>
    </div>
  );
}

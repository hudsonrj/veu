import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Dims = Record<string, number>;
type Msg = { ts?: number; role?: string; text?: string };

type Status = {
  percent?: number;
  label?: string;
  dimensions?: Dims;
  traits?: Record<string, string[]>;
  note?: string;
  stats?: { samples?: number; corrections?: number; chat_turns?: number };
};

function Ring({ pct }: { pct: number }) {
  const r = 54;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.max(0, Math.min(100, pct)) / 100) * c;
  return (
    <svg className="clone-ring" viewBox="0 0 140 140" aria-label={`${pct}% clone`}>
      <circle cx="70" cy="70" r={r} className="clone-ring__track" />
      <circle
        cx="70"
        cy="70"
        r={r}
        className="clone-ring__fill"
        strokeDasharray={`${c} ${c}`}
        strokeDashoffset={offset}
      />
      <text x="70" y="68" textAnchor="middle" className="clone-ring__pct">
        {pct}%
      </text>
      <text x="70" y="88" textAnchor="middle" className="clone-ring__sub">
        clone
      </text>
    </svg>
  );
}

export function CloneApp() {
  const [st, setSt] = useState<Status | null>(null);
  const [history, setHistory] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [correctFor, setCorrectFor] = useState<string | null>(null);
  const [better, setBetter] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    const [s, h] = await Promise.all([
      apiFetch(`${KERNEL}/clone/status`),
      apiFetch(`${KERNEL}/clone/history?limit=40`),
    ]);
    setSt(await s.json());
    const hj = await h.json();
    setHistory(hj.chat || []);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  const harvest = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await apiFetch(`${KERNEL}/clone/harvest`, { method: "POST", body: "{}" });
      const j = await r.json();
      setSt(j);
      setNote(j.ok ? `absorveu ${j.added ?? 0} falas do SO` : j.error || "falha");
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    const msg = text.trim();
    if (!msg) return;
    setBusy(true);
    setText("");
    try {
      const r = await apiFetch(`${KERNEL}/clone/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      const j = await r.json();
      if (j.ok) {
        setSt(j);
        setHistory(j.history || []);
        setCorrectFor(j.reply || null);
      } else {
        setNote(j.error || "falha");
      }
    } finally {
      setBusy(false);
    }
  };

  const submitCorrect = async () => {
    if (!better.trim()) return;
    setBusy(true);
    try {
      const r = await apiFetch(`${KERNEL}/clone/correct`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clone_said: correctFor || "", better: better.trim() }),
      });
      const j = await r.json();
      setSt(j);
      setBetter("");
      setNote("correção guardada — % sobe com feedback");
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const pct = st?.percent ?? 0;
  const dims = st?.dimensions || {};

  return (
    <div className="panel-app clone">
      <header className="panel-app__head">
        <h2>Clone</h2>
        <button type="button" onClick={() => void harvest()} disabled={busy}>
          {busy ? "…" : "absorver SO"}
        </button>
      </header>
      <p className="panel-app__meta">
        {st?.note ||
          "Reúne seu jeito de falar e agir. Converse aqui para treinar — corrija quando sair do personagem."}
      </p>

      <div className="clone-top">
        <Ring pct={pct} />
        <div className="clone-top__meta">
          <strong>{st?.label || "esboço"}</strong>
          <span>
            {st?.stats?.samples ?? 0} falas · {st?.stats?.corrections ?? 0} correções ·{" "}
            {st?.stats?.chat_turns ?? 0} turnos
          </span>
          <ul className="clone-dims">
            {Object.entries(dims).map(([k, v]) => (
              <li key={k}>
                <span>{k}</span>
                <span className="clone-dims__bar">
                  <i style={{ width: `${v}%` }} />
                </span>
                <em>{v}%</em>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {st?.traits ? (
        <div className="clone-traits">
          {(["tone", "vocabulary", "habits", "values", "avoid"] as const).map((key) => {
            const items = st.traits?.[key] || [];
            if (!items.length) return null;
            const label: Record<string, string> = {
              tone: "tom",
              vocabulary: "vocabulário",
              habits: "comportamento",
              values: "valores",
              avoid: "evitar",
            };
            return (
              <p key={key}>
                <strong>{label[key]}</strong> {items.slice(-6).join(" · ")}
              </p>
            );
          })}
        </div>
      ) : null}

      <div className="clone-chat">
        {history.map((m, i) => (
          <div key={i} className={`clone-bubble clone-bubble--${m.role || "user"}`}>
            <span>{m.role === "clone" ? "clone" : "você"}</span>
            <p>{m.text}</p>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {correctFor ? (
        <div className="clone-correct">
          <p>Corrigir a última fala do clone:</p>
          <input
            value={better}
            onChange={(e) => setBetter(e.target.value)}
            placeholder="como você diria de verdade…"
          />
          <button type="button" disabled={busy || !better.trim()} onClick={() => void submitCorrect()}>
            ensinar
          </button>
        </div>
      ) : null}

      {note ? <p className="prod__note">{note}</p> : null}

      <form
        className="panel-app__form"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="fale como você — o clone aprende (tom: … / evite: … / valor: …)"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !text.trim()}>
          {busy ? "…" : "treinar"}
        </button>
      </form>

      <style>{`
        .clone-top {
          display: grid;
          grid-template-columns: 9rem 1fr;
          gap: 1rem;
          align-items: center;
          margin: 0 0 1rem;
        }
        .clone-ring { width: 8.5rem; height: 8.5rem; }
        .clone-ring__track {
          fill: none;
          stroke: rgba(255,255,255,0.08);
          stroke-width: 10;
        }
        .clone-ring__fill {
          fill: none;
          stroke: url(#none);
          stroke: #7fe7d4;
          stroke-width: 10;
          stroke-linecap: round;
          transform: rotate(-90deg);
          transform-origin: 70px 70px;
          transition: stroke-dashoffset 0.6s ease;
        }
        .clone-ring__pct {
          fill: var(--ink, #f4efe6);
          font-size: 1.6rem;
          font-family: var(--font-display, Syne, sans-serif);
          font-weight: 600;
        }
        .clone-ring__sub {
          fill: var(--os-muted, #9aa3ad);
          font-size: 0.7rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
        }
        .clone-top__meta strong {
          display: block;
          font-size: 1.1rem;
          margin-bottom: 0.2rem;
        }
        .clone-top__meta > span {
          font-size: 0.72rem;
          color: var(--os-muted, #9aa3ad);
        }
        .clone-dims {
          list-style: none;
          margin: 0.65rem 0 0;
          padding: 0;
          display: grid;
          gap: 0.28rem;
        }
        .clone-dims li {
          display: grid;
          grid-template-columns: 6.2rem 1fr 2.2rem;
          gap: 0.4rem;
          align-items: center;
          font-size: 0.7rem;
        }
        .clone-dims__bar {
          height: 0.35rem;
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(127,231,212,0.15);
        }
        .clone-dims__bar i {
          display: block;
          height: 100%;
          background: linear-gradient(90deg, #7fe7d4, #e8c27a);
        }
        .clone-dims em { font-style: normal; text-align: right; font-family: var(--font-mono, ui-monospace, monospace); }
        .clone-traits {
          margin: 0 0 0.85rem;
          font-size: 0.75rem;
          color: var(--os-muted, #9aa3ad);
        }
        .clone-traits p { margin: 0.2rem 0; }
        .clone-traits strong { color: var(--ink, #f4efe6); margin-right: 0.35rem; }
        .clone-chat {
          flex: 1;
          min-height: 10rem;
          max-height: 18rem;
          overflow: auto;
          display: flex;
          flex-direction: column;
          gap: 0.55rem;
          margin: 0 0 0.75rem;
          padding: 0.5rem 0;
          border-top: 1px solid rgba(232,194,122,0.12);
          border-bottom: 1px solid rgba(232,194,122,0.12);
        }
        .clone-bubble span {
          font-size: 0.65rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--os-muted, #9aa3ad);
        }
        .clone-bubble p { margin: 0.15rem 0 0; font-size: 0.88rem; }
        .clone-bubble--clone p { color: #7fe7d4; }
        .clone-correct {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.4rem;
          margin: 0 0 0.65rem;
          align-items: center;
        }
        .clone-correct p {
          grid-column: 1 / -1;
          margin: 0;
          font-size: 0.72rem;
          color: var(--os-muted, #9aa3ad);
        }
        .clone-correct input {
          padding: 0.5rem 0.65rem;
          border: 1px solid rgba(232,194,122,0.2);
          background: rgba(0,0,0,0.25);
          color: inherit;
        }
        @media (max-width: 743px) {
          .clone-top { grid-template-columns: 1fr; justify-items: center; text-align: center; }
          .clone-dims li { grid-template-columns: 5rem 1fr 2rem; }
        }
      `}</style>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Alert = {
  id: string;
  kind?: string;
  level?: string;
  title?: string;
  body?: string;
  ts?: number;
  acked?: boolean;
};

type Area = { id: string; label: string; open?: number; hint?: string };

type Board = {
  disclaimer?: string;
  averages_7d?: { mood?: number | null; energy?: number | null; focus?: number | null; n?: number };
  open_alerts?: Alert[];
  areas?: Area[];
  checkins?: { ts?: number; mood?: number; energy?: number; focus?: number; note?: string }[];
  triggers?: { ts?: number; kind?: string; title?: string; intensity?: number }[];
  trend?: { ts?: number; mood?: number; energy?: number; focus?: number }[];
};

function fmt(ts?: number) {
  if (!ts) return "";
  return new Date(ts * (ts < 1e12 ? 1000 : 1)).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ScoreRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <label className="mh-score">
      <span>{label}</span>
      <div>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={value === n ? "is-on" : ""}
            onClick={() => onChange(n)}
          >
            {n}
          </button>
        ))}
      </div>
    </label>
  );
}

export function MentalHealthApp() {
  const [board, setBoard] = useState<Board | null>(null);
  const [mood, setMood] = useState(3);
  const [energy, setEnergy] = useState(3);
  const [focus, setFocus] = useState(3);
  const [note, setNote] = useState("");
  const [trigTitle, setTrigTitle] = useState("");
  const [trigKind, setTrigKind] = useState("gatilho");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await apiFetch(`${KERNEL}/mental/board`);
    setBoard(await r.json());
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 45_000);
    return () => window.clearInterval(id);
  }, [load]);

  const checkin = async () => {
    setBusy(true);
    try {
      await apiFetch(`${KERNEL}/mental/checkin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood, energy, focus, note }),
      });
      setNote("");
      setFlash("check-in guardado");
      await load();
    } finally {
      setBusy(false);
    }
  };

  const scan = async () => {
    setBusy(true);
    try {
      const r = await apiFetch(`${KERNEL}/mental/scan`, { method: "POST", body: "{}" });
      const j = await r.json();
      setFlash(`scan · ${(j.created || []).length} alerta(s)`);
      setBoard(j);
    } finally {
      setBusy(false);
    }
  };

  const ack = async (id: string) => {
    await apiFetch(`${KERNEL}/mental/alerts/${id}/ack`, { method: "POST", body: "{}" });
    await load();
  };

  const addTrigger = async () => {
    if (!trigTitle.trim()) return;
    setBusy(true);
    try {
      await apiFetch(`${KERNEL}/mental/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: trigKind, title: trigTitle.trim(), intensity: 3 }),
      });
      setTrigTitle("");
      setFlash("gatilho registrado");
      await load();
    } finally {
      setBusy(false);
    }
  };

  const avg = board?.averages_7d || {};

  return (
    <div className="panel-app mh">
      <header className="panel-app__head">
        <h2>Saúde mental</h2>
        <button type="button" onClick={() => void scan()} disabled={busy}>
          {busy ? "…" : "varrer sinais"}
        </button>
      </header>
      <p className="panel-app__meta">{board?.disclaimer}</p>
      {flash ? <p className="prod__note">{flash}</p> : null}

      <div className="mh-avgs">
        <div>
          <strong>{avg.mood ?? "—"}</strong>
          <span>humor 7d</span>
        </div>
        <div>
          <strong>{avg.energy ?? "—"}</strong>
          <span>energia 7d</span>
        </div>
        <div>
          <strong>{avg.focus ?? "—"}</strong>
          <span>foco 7d</span>
        </div>
        <div>
          <strong>{avg.n ?? 0}</strong>
          <span>check-ins</span>
        </div>
      </div>

      <section className="mh-section">
        <h3>áreas</h3>
        <div className="mh-areas">
          {(board?.areas || []).map((a) => (
            <div key={a.id} className={`mh-area${(a.open || 0) > 0 ? " is-hot" : ""}`}>
              <strong>{a.label}</strong>
              <span>{a.open || 0} alerta(s)</span>
              <em>{a.hint}</em>
            </div>
          ))}
        </div>
      </section>

      <section className="mh-section">
        <h3>alertas abertos</h3>
        <ul className="panel-app__list">
          {(board?.open_alerts || []).map((a) => (
            <li key={a.id} className={`mh-alert mh-alert--${a.level || "info"}`}>
              <div>
                <strong>{a.title}</strong>
                <span className="seal">{a.kind}</span>
                <span className="seal">{a.level}</span>
                <p>{a.body}</p>
                <em>{fmt(a.ts)}</em>
              </div>
              <button type="button" onClick={() => void ack(a.id)}>
                ok, ciente
              </button>
            </li>
          ))}
          {!board?.open_alerts?.length ? (
            <li className="muted">sem alertas abertos — faça um check-in ou varra sinais</li>
          ) : null}
        </ul>
      </section>

      <section className="mh-section">
        <h3>check-in agora</h3>
        <ScoreRow label="humor" value={mood} onChange={setMood} />
        <ScoreRow label="energia" value={energy} onChange={setEnergy} />
        <ScoreRow label="foco" value={focus} onChange={setFocus} />
        <form
          className="panel-app__form"
          onSubmit={(e) => {
            e.preventDefault();
            void checkin();
          }}
        >
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="opcional: o que pesa hoje…"
          />
          <button type="submit" disabled={busy}>
            registrar
          </button>
        </form>
      </section>

      <section className="mh-section">
        <h3>registrar gatilho</h3>
        <div className="mh-trig">
          <select value={trigKind} onChange={(e) => setTrigKind(e.target.value)}>
            <option value="gatilho">gatilho</option>
            <option value="toc">TOC / checagem</option>
            <option value="procrastinacao">procrastinação</option>
            <option value="burnout">burnout</option>
            <option value="sobrecarga">sobrecarga</option>
            <option value="depressao">humor baixo</option>
            <option value="ansiedade">ansiedade</option>
          </select>
          <input
            value={trigTitle}
            onChange={(e) => setTrigTitle(e.target.value)}
            placeholder="o que disparou…"
          />
          <button type="button" disabled={busy || !trigTitle.trim()} onClick={() => void addTrigger()}>
            salvar
          </button>
        </div>
      </section>

      <section className="mh-section">
        <h3>tendência</h3>
        <ul className="mh-trend">
          {(board?.trend || []).map((t, i) => (
            <li key={i}>
              <span>{fmt(t.ts)}</span>
              <span>H{t.mood}</span>
              <span>E{t.energy}</span>
              <span>F{t.focus}</span>
            </li>
          ))}
          {!board?.trend?.length ? <li className="muted">ainda sem tendência</li> : null}
        </ul>
      </section>

      <p className="mh-cvv">
        Em crise no Brasil: <strong>CVV 188</strong> (24h, grátis) ·{" "}
        <a href="https://www.cvv.org.br/" target="_blank" rel="noreferrer">
          cvv.org.br
        </a>
      </p>

      <style>{`
        .mh-avgs {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 0.5rem;
          margin: 0 0 1rem;
        }
        .mh-avgs div {
          padding: 0.6rem;
          border: 1px solid rgba(232,194,122,0.14);
          background: rgba(7,9,12,0.3);
          text-align: center;
        }
        .mh-avgs strong { display: block; font-size: 1.2rem; }
        .mh-avgs span { font-size: 0.65rem; color: var(--os-muted, #9aa3ad); letter-spacing: 0.04em; }
        .mh-section { margin: 0 0 1rem; }
        .mh-section h3 {
          margin: 0 0 0.45rem;
          font-size: 0.72rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--os-muted, #9aa3ad);
          font-weight: 500;
        }
        .mh-areas {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
          gap: 0.45rem;
        }
        .mh-area {
          padding: 0.55rem 0.6rem;
          border: 1px solid rgba(232,194,122,0.12);
          font-size: 0.75rem;
        }
        .mh-area.is-hot { border-color: rgba(240,140,100,0.45); }
        .mh-area strong { display: block; margin-bottom: 0.15rem; }
        .mh-area span { color: var(--filament, #e8c27a); font-size: 0.68rem; }
        .mh-area em { display: block; margin-top: 0.25rem; font-style: normal; font-size: 0.65rem; color: var(--os-muted, #9aa3ad); }
        .mh-alert { align-items: start; }
        .mh-alert--high { border-left: 2px solid #f09070; padding-left: 0.5rem; }
        .mh-alert--watch { border-left: 2px solid #e8c27a; padding-left: 0.5rem; }
        .mh-score {
          display: grid;
          grid-template-columns: 4.5rem 1fr;
          gap: 0.5rem;
          align-items: center;
          margin: 0 0 0.45rem;
          font-size: 0.78rem;
        }
        .mh-score button {
          margin-right: 0.25rem;
          min-width: 2rem;
          padding: 0.35rem 0.45rem;
        }
        .mh-score button.is-on {
          background: rgba(232,194,122,0.25);
          border-color: rgba(232,194,122,0.5);
        }
        .mh-trig {
          display: grid;
          grid-template-columns: 7.5rem 1fr auto;
          gap: 0.4rem;
        }
        .mh-trig select, .mh-trig input {
          padding: 0.5rem;
          border: 1px solid rgba(232,194,122,0.2);
          background: rgba(0,0,0,0.25);
          color: inherit;
        }
        .mh-trend { list-style: none; margin: 0; padding: 0; font-size: 0.72rem; font-family: var(--font-mono, ui-monospace, monospace); }
        .mh-trend li { display: grid; grid-template-columns: 7rem repeat(3, 2rem); gap: 0.4rem; padding: 0.2rem 0; }
        .mh-cvv { margin: 1rem 0 0; font-size: 0.78rem; color: var(--os-muted, #9aa3ad); }
        .mh-cvv a { color: #7fe7d4; }
        @media (max-width: 743px) {
          .mh-avgs { grid-template-columns: repeat(2, 1fr); }
          .mh-trig { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}

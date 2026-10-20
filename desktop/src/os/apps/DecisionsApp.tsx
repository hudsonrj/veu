import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Decision = {
  id?: string;
  ts?: string | number;
  kind?: string;
  title?: string;
  why?: string;
  outcome?: string | boolean;
};

type Action = {
  id: string;
  title: string;
  status?: string;
  source?: string;
  help?: string;
  company?: string;
  updated?: number;
};

function fmt(ts?: string | number) {
  if (ts == null) return "";
  const d = typeof ts === "number" ? new Date(ts * (ts < 1e12 ? 1000 : 1)) : new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 19);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DecisionsApp() {
  const [rows, setRows] = useState<Decision[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [pulse, setPulse] = useState<{ decisions?: number; sessions?: number } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [r, a] = await Promise.all([
      apiFetch(`${KERNEL}/decisions?limit=60`),
      apiFetch(`${KERNEL}/autonomous/board?limit=40`),
    ]);
    const j = await r.json();
    const board = await a.json();
    setRows(j.decisions || []);
    setPulse(j.pulse || null);
    setActions(board.actions || []);
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 25_000);
    return () => window.clearInterval(id);
  }, [load]);

  const mark = async (id: string, status: "done" | "updated" | "dismissed") => {
    setBusy(true);
    try {
      await apiFetch(`${KERNEL}/autonomous/actions/${id}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note: `diário · ${status}` }),
      });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const openActions = actions.filter((a) =>
    ["open", "updated", "in_progress"].includes(a.status || "open"),
  );
  const doneActions = actions.filter((a) => a.status === "done").slice(0, 12);

  return (
    <div className="panel-app">
      <header className="panel-app__head">
        <h2>Diário de decisões</h2>
        <span>
          {pulse?.decisions ?? rows.length} decisões
          {pulse?.sessions != null ? ` · ${pulse.sessions} sessões` : ""}
          {openActions.length ? ` · ${openActions.length} ações abertas` : ""}
        </span>
      </header>
      <p className="panel-app__meta">
        O que foi decidido fica guardado. Ações do modo autônomo podem ser marcadas como feitas ou
        atualizadas aqui — ou no app Produtividade.
      </p>

      {openActions.length ? (
        <>
          <h3 className="dec-h">ações a tratar</h3>
          <ul className="panel-app__list">
            {openActions.map((a) => (
              <li key={a.id}>
                <div>
                  <strong>{a.title}</strong>
                  <span className="seal">{a.source}</span>
                  <p>{a.help || "—"}</p>
                  <em>{a.company || a.status}</em>
                </div>
                <div className="dec-btns">
                  <button type="button" disabled={busy} onClick={() => void mark(a.id, "done")}>
                    feita
                  </button>
                  <button type="button" disabled={busy} onClick={() => void mark(a.id, "updated")}>
                    atualizar
                  </button>
                  <button type="button" disabled={busy} onClick={() => void mark(a.id, "dismissed")}>
                    descartar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {doneActions.length ? (
        <>
          <h3 className="dec-h">ações feitas</h3>
          <ul className="panel-app__list">
            {doneActions.map((a) => (
              <li key={a.id}>
                <div>
                  <strong>{a.title}</strong>
                  <span className="seal">done</span>
                  <em>{fmt(a.updated)}</em>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <h3 className="dec-h">histórico</h3>
      <ul className="panel-app__list">
        {rows.map((d, i) => (
          <li key={d.id || i}>
            <div>
              <strong>{d.title}</strong>
              <span className="seal">{d.kind}</span>
              <p>{d.why || "—"}</p>
              <em>
                {fmt(d.ts)}
                {d.outcome != null && d.outcome !== ""
                  ? ` · resultado: ${String(d.outcome)}`
                  : ""}
              </em>
            </div>
          </li>
        ))}
        {!rows.length ? <li className="muted">ainda sem decisões registradas</li> : null}
      </ul>
      <style>{`
        .dec-h {
          margin: 0.85rem 0 0.4rem;
          font-size: 0.72rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--os-muted, #9aa3ad);
          font-weight: 500;
        }
        .dec-btns { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.35rem; }
        .dec-btns button {
          font-size: 0.72rem;
          padding: 0.4rem 0.65rem;
          background: rgba(12, 14, 18, 0.92);
          color: #e8ebe6;
          border: 1px solid rgba(232, 194, 122, 0.35);
        }
      `}</style>
    </div>
  );
}

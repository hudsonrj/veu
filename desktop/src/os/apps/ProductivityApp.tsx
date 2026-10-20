import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type ChartRow = { label: string; value: number };
type Action = {
  id: string;
  title: string;
  help?: string;
  status?: string;
  source?: string;
  company?: string;
  subject?: string;
  suggested?: string;
  priority?: string;
};

type Snap = {
  ok?: boolean;
  available?: boolean;
  updatedAt?: string;
  note?: string;
  indicators?: Record<string, number>;
  charts?: {
    hours_by_company?: ChartRow[];
    tasks_by_status?: ChartRow[];
    inbox_by_channel?: ChartRow[];
    actions_pipeline?: ChartRow[];
  };
  companies?: string[];
  projects?: { id?: string; name?: string; summary?: string; company?: string }[];
  study?: { id?: string; title?: string; body?: string; company?: string; kind?: string }[];
  tasks_open?: { id?: string; title?: string; status?: string; company?: string; due?: string }[];
  actions?: Action[];
};

type Tab = "visao" | "acoes" | "estudo";

function BarChart({ rows, unit }: { rows: ChartRow[]; unit?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (!rows.length) return <p className="muted">sem dados</p>;
  return (
    <ul className="prod-bars">
      {rows.map((r) => (
        <li key={r.label}>
          <span className="prod-bars__label">{r.label}</span>
          <span className="prod-bars__track">
            <span
              className="prod-bars__fill"
              style={{ width: `${Math.round((r.value / max) * 100)}%` }}
            />
          </span>
          <span className="prod-bars__val">
            {r.value}
            {unit || ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="prod-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export function ProductivityApp({
  breath,
  onRequestScan,
}: {
  breath?: string;
  onRequestScan?: () => void;
}) {
  const [tab, setTab] = useState<Tab>(breath === "autonomous" ? "acoes" : "visao");
  const [snap, setSnap] = useState<Snap | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await apiFetch(`${KERNEL}/productivity`);
      const j = (await r.json()) as Snap;
      setSnap(j);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
    } finally {
      setBusy(false);
    }
  }, []);

  const scan = useCallback(async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await apiFetch(`${KERNEL}/autonomous/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const j = await r.json();
      setNote(
        j.ok
          ? `scan · ${j.upserted ?? 0} propostas · ${j.elapsed_ms ?? "?"}ms`
          : j.error || "scan falhou",
      );
      onRequestScan?.();
      await load();
      setTab("acoes");
    } catch (e) {
      setNote(e instanceof Error ? e.message : "falha no scan");
    } finally {
      setBusy(false);
    }
  }, [load, onRequestScan]);

  const decide = async (
    id: string,
    status: "done" | "dismissed" | "updated" | "in_progress" | "open",
  ) => {
    setBusy(true);
    try {
      await apiFetch(`${KERNEL}/autonomous/actions/${id}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, note: status === "done" ? "feita no SO" : "" }),
      });
      await load();
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 40_000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (breath === "autonomous") {
      setTab("acoes");
      void scan();
    }
    // only when breath flips to autonomous
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [breath]);

  const ind = snap?.indicators || {};
  const charts = snap?.charts || {};
  const actionRows = (snap?.actions || []).filter((a) =>
    tab === "acoes"
      ? ["open", "updated", "in_progress"].includes(a.status || "open")
      : true,
  );

  return (
    <div className="panel-app prod">
      <header className="panel-app__head">
        <h2>Produtividade</h2>
        <div className="prod__head-actions">
          <button type="button" onClick={() => void scan()} disabled={busy}>
            {busy ? "…" : "varrer agora"}
          </button>
          <button type="button" onClick={() => void load()} disabled={busy}>
            atualizar
          </button>
        </div>
      </header>
      <p className="panel-app__meta">
        {snap?.note || "indicadores do live.json + ações do modo autônomo"}
        {snap?.updatedAt ? ` · live ${String(snap.updatedAt).slice(0, 19)}` : ""}
      </p>
      {note ? <p className="prod__note">{note}</p> : null}
      {err ? <p className="panel-app__warn">{err}</p> : null}

      <div className="panel-app__tabs">
        {(
          [
            ["visao", "visão"],
            ["acoes", "ações"],
            ["estudo", "estudar"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? "is-on" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "visao" ? (
        <>
          <div className="prod-stats">
            <Stat label="horas em reuniões" value={ind.meeting_hours ?? 0} />
            <Stat label="reuniões" value={ind.meetings ?? 0} />
            <Stat label="tarefas abertas" value={ind.tasks_open ?? 0} />
            <Stat label="tarefas feitas" value={ind.tasks_done ?? 0} />
            <Stat label="empresas" value={ind.companies ?? 0} />
            <Stat label="projetos" value={ind.projects ?? 0} />
            <Stat label="ações abertas" value={ind.actions_open ?? 0} />
            <Stat label="ações feitas" value={ind.actions_done ?? 0} />
            <Stat label="fila de estudo" value={ind.study_queue ?? 0} />
            <Stat label="inbox" value={ind.inbox ?? 0} />
          </div>

          <section className="prod-section">
            <h3>horas por empresa</h3>
            <BarChart rows={charts.hours_by_company || []} unit="h" />
          </section>
          <section className="prod-section">
            <h3>tarefas por status</h3>
            <BarChart rows={charts.tasks_by_status || []} />
          </section>
          <section className="prod-section">
            <h3>inbox por canal</h3>
            <BarChart rows={charts.inbox_by_channel || []} />
          </section>
          <section className="prod-section">
            <h3>pipeline de ações</h3>
            <BarChart rows={charts.actions_pipeline || []} />
          </section>

          <section className="prod-section">
            <h3>projetos</h3>
            <ul className="panel-app__list">
              {(snap?.projects || []).map((p) => (
                <li key={p.id || p.name}>
                  <div>
                    <strong>{p.name}</strong>
                    <span>
                      {p.company || "—"}
                      {p.summary ? ` · ${p.summary}` : ""}
                    </span>
                  </div>
                </li>
              ))}
              {!snap?.projects?.length ? <li className="muted">sem projetos no live</li> : null}
            </ul>
          </section>

          <section className="prod-section">
            <h3>tarefas em aberto</h3>
            <ul className="panel-app__list">
              {(snap?.tasks_open || []).map((t) => (
                <li key={t.id || t.title}>
                  <div>
                    <strong>{t.title}</strong>
                    <span>
                      {t.status}
                      {t.company ? ` · ${t.company}` : ""}
                      {t.due ? ` · ${t.due}` : ""}
                    </span>
                  </div>
                </li>
              ))}
              {!snap?.tasks_open?.length ? <li className="muted">nada em aberto</li> : null}
            </ul>
          </section>
        </>
      ) : null}

      {tab === "acoes" ? (
        <ul className="panel-app__list prod-actions">
          {actionRows.map((a) => (
            <li key={a.id}>
              <div>
                <strong>{a.title}</strong>
                <span className="seal">{a.source}</span>
                {a.priority === "high" ? <span className="seal seal--hot">alta</span> : null}
                <p>{a.help}</p>
                <em>
                  {[a.company, a.subject, a.suggested].filter(Boolean).join(" · ")}
                </em>
              </div>
              <div className="prod-actions__btns">
                <button type="button" disabled={busy} onClick={() => void decide(a.id, "in_progress")}>
                  agir
                </button>
                <button type="button" disabled={busy} onClick={() => void decide(a.id, "done")}>
                  feita
                </button>
                <button type="button" disabled={busy} onClick={() => void decide(a.id, "updated")}>
                  atualizar
                </button>
                <button type="button" disabled={busy} onClick={() => void decide(a.id, "dismissed")}>
                  descartar
                </button>
              </div>
            </li>
          ))}
          {!actionRows.length ? (
            <li className="muted">
              sem ações abertas — escolha respiração <em>autônomo</em> ou clique em varrer agora
            </li>
          ) : null}
        </ul>
      ) : null}

      {tab === "estudo" ? (
        <ul className="panel-app__list">
          {(snap?.study || []).map((s) => (
            <li key={s.id || s.title}>
              <div>
                <strong>{s.title}</strong>
                <span className="seal">{s.kind}</span>
                <p>{s.body}</p>
                <em>{s.company || "—"}</em>
              </div>
            </li>
          ))}
          {!snap?.study?.length ? (
            <li className="muted">nada na fila de estudo / assuntos a tratar</li>
          ) : null}
        </ul>
      ) : null}

      <style>{`
        .prod__head-actions { display: flex; gap: 0.4rem; }
        .prod__note { margin: 0 0 0.6rem; font-size: 0.78rem; color: var(--filament, #e8c27a); }
        .prod-stats {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(7.2rem, 1fr));
          gap: 0.55rem;
          margin: 0 0 1rem;
        }
        .prod-stat {
          padding: 0.65rem 0.7rem;
          border: 1px solid rgba(232,194,122,0.16);
          background: rgba(7,9,12,0.35);
        }
        .prod-stat strong {
          display: block;
          font-size: 1.25rem;
          font-family: var(--font-display, Syne, sans-serif);
          color: var(--os-ink, #e8ebe6);
        }
        .prod-stat span {
          font-size: 0.68rem;
          letter-spacing: 0.04em;
          color: var(--os-muted, #9aa3ad);
          text-transform: lowercase;
        }
        .prod-section { margin: 0 0 1.1rem; }
        .prod-section h3 {
          margin: 0 0 0.45rem;
          font-size: 0.78rem;
          letter-spacing: 0.08em;
          text-transform: lowercase;
          color: var(--os-muted, #9aa3ad);
          font-weight: 500;
        }
        .prod-bars { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem; }
        .prod-bars li {
          display: grid;
          grid-template-columns: 6.5rem 1fr 2.4rem;
          gap: 0.45rem;
          align-items: center;
          font-size: 0.72rem;
        }
        .prod-bars__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .prod-bars__track {
          height: 0.45rem;
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(232,194,122,0.12);
        }
        .prod-bars__fill {
          display: block;
          height: 100%;
          background: linear-gradient(90deg, rgba(232,194,122,0.85), rgba(127,231,212,0.7));
        }
        .prod-bars__val { text-align: right; font-family: var(--font-mono, ui-monospace, monospace); }
        .prod-actions li { display: grid; gap: 0.55rem; }
        .prod-actions__btns { display: flex; flex-wrap: wrap; gap: 0.35rem; }
        .prod-actions__btns button {
          font-size: 0.72rem;
          padding: 0.4rem 0.65rem;
          background: rgba(12, 14, 18, 0.92);
          color: #e8ebe6;
          border: 1px solid rgba(232, 194, 122, 0.35);
        }
        .prod-actions__btns button:first-child {
          border-color: rgba(127, 231, 212, 0.45);
          color: #b8f5ea;
        }
        .seal--hot { border-color: rgba(240,120,100,0.45); color: #f0a08a; }
        @media (max-width: 743px) {
          .prod-bars li { grid-template-columns: 4.5rem 1fr 2rem; }
          .prod-stats { grid-template-columns: repeat(2, 1fr); }
        }
      `}</style>
    </div>
  );
}

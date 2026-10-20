import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Routine = {
  id: string;
  title: string;
  cron: string;
  intent: string;
  breath: string;
  enabled: boolean;
  last_run?: number | null;
};

export function RoutinesApp() {
  const [rows, setRows] = useState<Routine[]>([]);
  const [runs, setRuns] = useState<{ title?: string; ts?: number; job_id?: string }[]>([]);
  const [title, setTitle] = useState("Briefing da manhã");
  const [cron, setCron] = useState("0 9 * * 1-5");
  const [intent, setIntent] = useState("monte o briefing do dia e diga o que importa");
  const [note, setNote] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const r = await apiFetch(`${KERNEL}/routines`);
    const j = await r.json();
    setRows(j.routines || []);
    setRuns(j.runs || []);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const save = async () => {
    const r = await apiFetch(`${KERNEL}/routines`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, cron, intent, breath: "guided", enabled: true }),
    });
    const j = await r.json();
    setNote(j.ok ? "rotina salva" : j.error || "falha");
    await reload();
  };

  return (
    <div className="panel-app">
      <header className="panel-app__head">
        <h2>Rotinas</h2>
        <button
          type="button"
          onClick={() =>
            void apiFetch(`${KERNEL}/routines/tick`, { method: "POST" }).then(() => reload())
          }
        >
          tick agora
        </button>
      </header>
      <p className="panel-app__meta">
        Cron simples: <code>minuto hora * * dias</code> — ex. <code>0 9 * * 1-5</code> (seg–sex 09:00)
      </p>
      <div className="panel-app__form" style={{ flexDirection: "column", alignItems: "stretch" }}>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="título" />
        <input value={cron} onChange={(e) => setCron(e.target.value)} placeholder="cron" />
        <input value={intent} onChange={(e) => setIntent(e.target.value)} placeholder="intenção" />
        <button type="button" onClick={() => void save()}>
          criar rotina
        </button>
      </div>
      {note ? <p>{note}</p> : null}
      <ul className="panel-app__list">
        {rows.map((r) => (
          <li key={r.id}>
            <div>
              <strong>{r.title}</strong>
              <em>
                {r.cron} · {r.enabled ? "on" : "off"}
              </em>
              <p>{r.intent}</p>
            </div>
            <button
              type="button"
              className="danger"
              onClick={() =>
                void apiFetch(`${KERNEL}/routines/${encodeURIComponent(r.id)}`, {
                  method: "DELETE",
                }).then(() => reload())
              }
            >
              apagar
            </button>
          </li>
        ))}
        {!rows.length ? <li className="muted">nenhuma rotina ainda</li> : null}
      </ul>
      <h3>Últimos disparos</h3>
      <ul className="panel-app__list">
        {runs.slice(0, 8).map((r, i) => (
          <li key={i}>
            <span>{r.title}</span>
            <em>{r.job_id}</em>
          </li>
        ))}
      </ul>
    </div>
  );
}

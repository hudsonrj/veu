import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Item = {
  id: string;
  intent: string;
  risk: string;
  breath: string;
  status?: string;
  created?: number;
};

export function ApprovalsApp() {
  const [pending, setPending] = useState<Item[]>([]);
  const [recent, setRecent] = useState<Item[]>([]);

  const reload = useCallback(async () => {
    const r = await apiFetch(`${KERNEL}/approvals`);
    const j = await r.json();
    setPending(j.pending || []);
    setRecent(j.recent || []);
  }, []);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 8_000);
    return () => window.clearInterval(id);
  }, [reload]);

  const decide = async (id: string, approve: boolean) => {
    await apiFetch(`${KERNEL}/approvals/${encodeURIComponent(id)}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approve }),
    });
    await reload();
  };

  return (
    <div className="panel-app">
      <header className="panel-app__head">
        <h2>Aprovações</h2>
        <span>{pending.length} pendente(s)</span>
      </header>
      <ul className="panel-app__list">
        {pending.map((p) => (
          <li key={p.id}>
            <div>
              <strong>{p.intent}</strong>
              <span className={`seal seal--${p.risk}`}>{p.risk}</span>
              <em>{p.breath}</em>
            </div>
            <div className="panel-app__row-actions">
              <button type="button" onClick={() => void decide(p.id, true)}>
                aprovar
              </button>
              <button type="button" className="danger" onClick={() => void decide(p.id, false)}>
                recusar
              </button>
            </div>
          </li>
        ))}
        {!pending.length ? <li className="muted">fila limpa</li> : null}
      </ul>
      <h3>Recentes</h3>
      <ul className="panel-app__list">
        {recent.slice(0, 8).map((p) => (
          <li key={p.id}>
            <span>{p.intent}</span>
            <em>{p.status}</em>
          </li>
        ))}
      </ul>
    </div>
  );
}

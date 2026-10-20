import { useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Usage = {
  period: string;
  calls: number;
  tokens: number;
  cost_usd: number;
  ranking?: { agent: string; cost: number; calls: number }[];
  series?: { day: string; cost_usd: number }[];
  budget?: { budget_usd: number; spent_usd: number } | null;
};

export function UsageApp() {
  const [period, setPeriod] = useState("today");
  const [data, setData] = useState<Usage | null>(null);

  useEffect(() => {
    let alive = true;
    void apiFetch(`${KERNEL}/usage?period=${period}`)
      .then((r) => r.json())
      .then((j) => {
        if (alive) setData(j as Usage);
      });
    return () => {
      alive = false;
    };
  }, [period]);

  return (
    <div className="panel-app">
      <header className="panel-app__head">
        <h2>Custos</h2>
        <div className="panel-app__tabs">
          {["today", "7d", "30d"].map((p) => (
            <button key={p} type="button" className={period === p ? "is-on" : ""} onClick={() => setPeriod(p)}>
              {p}
            </button>
          ))}
        </div>
      </header>
      <div className="panel-app__cards">
        <div>
          <span>total</span>
          <strong>${(data?.cost_usd ?? 0).toFixed(4)}</strong>
        </div>
        <div>
          <span>chamadas</span>
          <strong>{data?.calls ?? 0}</strong>
        </div>
        <div>
          <span>tokens</span>
          <strong>{data?.tokens ?? 0}</strong>
        </div>
      </div>
      {data?.budget ? (
        <p className="panel-app__warn">
          orçamento ${data.budget.budget_usd} · gasto ${data.budget.spent_usd}
        </p>
      ) : null}
      <h3>Agentes mais caros</h3>
      <ul className="panel-app__list">
        {(data?.ranking || []).map((r) => (
          <li key={r.agent}>
            <span>{r.agent}</span>
            <em>${r.cost.toFixed(4)} · {r.calls}×</em>
          </li>
        ))}
        {!data?.ranking?.length ? <li className="muted">sem uso registrado ainda</li> : null}
      </ul>
    </div>
  );
}

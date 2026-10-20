import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Account = {
  id: string;
  provider?: string;
  status: string;
  age_h?: number | null;
  limit_h?: number;
  note?: string;
  relogin_url?: string;
};

export function CredentialsApp() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [fresh, setFresh] = useState<{ age_h?: number; status?: string } | null>(null);

  const reload = useCallback(async () => {
    const r = await apiFetch(`${KERNEL}/credentials`);
    const j = await r.json();
    setAccounts(j.accounts || []);
    setFresh(j.freshness || null);
  }, []);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 60_000);
    return () => window.clearInterval(id);
  }, [reload]);

  return (
    <div className="panel-app">
      <header className="panel-app__head">
        <h2>Credenciais</h2>
        <button type="button" onClick={() => void reload()}>
          atualizar
        </button>
      </header>
      {fresh ? (
        <p className="panel-app__meta">
          live.json · {fresh.status || "?"}
          {fresh.age_h != null ? ` · ${fresh.age_h}h atrás` : ""}
        </p>
      ) : null}
      <ul className="panel-app__list">
        {accounts.map((a) => (
          <li key={a.id}>
            <div>
              <strong>{a.id}</strong>
              <span className={`seal seal--${a.status}`}>{a.status}</span>
              {a.age_h != null ? <em>{a.age_h}h</em> : null}
              {a.note ? <p>{a.note}</p> : null}
            </div>
            <div className="panel-app__row-actions">
              {a.relogin_url ? (
                <a href={a.relogin_url} target="_blank" rel="noreferrer">
                  re-logar
                </a>
              ) : null}
              <button
                type="button"
                onClick={() =>
                  void apiFetch(`${KERNEL}/credentials/${encodeURIComponent(a.id)}/relogin-ok`, {
                    method: "POST",
                  }).then(() => reload())
                }
              >
                marquei ok
              </button>
            </div>
          </li>
        ))}
        {!accounts.length ? <li className="muted">nenhuma conta sinalizada</li> : null}
      </ul>
    </div>
  );
}

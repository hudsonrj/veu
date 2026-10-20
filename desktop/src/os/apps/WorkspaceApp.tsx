import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL, googleLoginUrl } from "../../lib/kernel";

type Tab = "drive" | "docs" | "sheets" | "calendar" | "gmail";

type Status = {
  connected?: boolean;
  email?: string | null;
  note?: string;
  surfaces?: string[];
};

type DriveFile = {
  id: string;
  name: string;
  surface: string;
  modified?: string;
  url?: string;
  owner?: string;
};

type CalEvent = {
  id: string;
  title: string;
  start?: string;
  end?: string;
  location?: string;
  url?: string;
};

type Mail = {
  id: string;
  from: string;
  subject: string;
  date?: string;
  snippet?: string;
};

/** Google Workspace real — usa o mesmo login Google do Véu. */
export function WorkspaceApp() {
  const [tab, setTab] = useState<Tab>("drive");
  const [status, setStatus] = useState<Status | null>(null);
  const [q, setQ] = useState("");
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [mails, setMails] = useState<Mail[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reloadStatus = useCallback(async () => {
    const r = await apiFetch(`${KERNEL}/workspace/status`);
    setStatus(await r.json());
  }, []);

  const load = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      await reloadStatus();
      if (tab === "calendar") {
        const r = await apiFetch(`${KERNEL}/workspace/calendar?limit=20`);
        const j = await r.json();
        if (!j.ok) setErr(j.error || "falha calendar");
        setEvents(j.events || []);
        setFiles([]);
        setMails([]);
      } else if (tab === "gmail") {
        const r = await apiFetch(`${KERNEL}/workspace/gmail?limit=12`);
        const j = await r.json();
        if (!j.ok) setErr(j.error || "falha gmail");
        setMails(j.messages || []);
        setFiles([]);
        setEvents([]);
      } else {
        const kind = tab === "drive" ? "" : tab;
        const params = new URLSearchParams({
          limit: "25",
          kind,
          ...(q.trim() ? { q: q.trim() } : {}),
        });
        const r = await apiFetch(`${KERNEL}/workspace/drive?${params}`);
        const j = await r.json();
        if (!j.ok) setErr(j.error || "falha drive");
        setFiles(j.files || []);
        setEvents([]);
        setMails([]);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
    } finally {
      setBusy(false);
    }
  }, [tab, q, reloadStatus]);

  useEffect(() => {
    void load();
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const connected = !!status?.connected;

  return (
    <div className="panel-app gw">
      <header className="panel-app__head">
        <h2>Google Workspace</h2>
        <button type="button" onClick={() => void load()} disabled={busy}>
          {busy ? "…" : "atualizar"}
        </button>
      </header>

      <p className="gw__meta">
        {connected
          ? `conectado · ${status?.email || "conta Google"}`
          : "sem token Workspace — entre de novo com Google (o login já pede Drive/Docs/Sheets/Calendar/Gmail)"}
      </p>

      {!connected ? (
        <p className="gw__cta">
          <a href={googleLoginUrl()}>entrar com Google · autorizar Workspace</a>
        </p>
      ) : null}

      <div className="panel-app__tabs">
        {(["drive", "docs", "sheets", "calendar", "gmail"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={tab === t ? "is-on" : ""}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "drive" || tab === "docs" || tab === "sheets" ? (
        <form
          className="panel-app__form"
          onSubmit={(e) => {
            e.preventDefault();
            void load();
          }}
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="buscar no Drive…"
          />
          <button type="submit" disabled={busy}>
            buscar
          </button>
        </form>
      ) : null}

      {err ? <p className="panel-app__warn">{err}</p> : null}

      {tab === "calendar" ? (
        <ul className="panel-app__list">
          {events.map((ev) => (
            <li key={ev.id}>
              <div>
                <strong>{ev.title}</strong>
                <span>
                  {ev.start || "?"}
                  {ev.location ? ` · ${ev.location}` : ""}
                </span>
              </div>
              {ev.url ? (
                <a href={ev.url} target="_blank" rel="noreferrer">
                  abrir
                </a>
              ) : null}
            </li>
          ))}
          {!events.length && !busy ? <li className="muted">sem eventos à frente</li> : null}
        </ul>
      ) : null}

      {tab === "gmail" ? (
        <ul className="panel-app__list">
          {mails.map((m) => (
            <li key={m.id}>
              <div>
                <strong>{m.subject}</strong>
                <span>{m.from}</span>
                <em>{m.snippet}</em>
              </div>
            </li>
          ))}
          {!mails.length && !busy ? <li className="muted">inbox vazia / sem API</li> : null}
        </ul>
      ) : null}

      {tab === "drive" || tab === "docs" || tab === "sheets" ? (
        <ul className="panel-app__list">
          {files.map((f) => (
            <li key={f.id}>
              <div>
                <strong>{f.name}</strong>
                <span>
                  {f.surface}
                  {f.modified ? ` · ${f.modified.slice(0, 10)}` : ""}
                </span>
              </div>
              {f.url ? (
                <a href={f.url} target="_blank" rel="noreferrer">
                  abrir
                </a>
              ) : null}
            </li>
          ))}
          {!files.length && !busy ? <li className="muted">nada encontrado</li> : null}
        </ul>
      ) : null}

      <style>{`
        .gw__meta { margin: 0 0 0.75rem; font-size: 0.8rem; color: var(--os-muted); }
        .gw__cta a {
          display: inline-block;
          margin-bottom: 0.85rem;
          padding: 0.65rem 0.9rem;
          border: 1px solid var(--os-line);
          color: var(--os-ink);
          text-decoration: none;
        }
        .gw em { display: block; font-style: normal; font-size: 0.72rem; color: var(--os-muted); margin-top: 0.2rem; }
        .gw .panel-app__list span { display: block; font-size: 0.72rem; color: var(--os-muted); }
      `}</style>
    </div>
  );
}

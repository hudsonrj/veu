/**
 * REA — Reverse Engineer Anything (morluto/rea) no Véu SO.
 * Entra URL/app → analisa (CLI/MCP) → publica evidência num repositório GitHub.
 */
import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type ReaStatus = {
  ok?: boolean;
  product?: string;
  upstream?: string;
  site?: string;
  cli?: { ok?: boolean; version?: unknown; cmd?: string };
  cdp?: { ok?: boolean; endpoint?: string; browser?: string };
  mcp?: { id?: string; command?: string; args?: string[] };
  disclaimer?: string;
};

type JobSummary = {
  title?: string;
  target?: string;
  kind?: string;
  modules?: number;
  notes?: string[];
  keys?: string[];
};

type Job = {
  id: string;
  target?: string;
  kind?: string;
  status?: string;
  created?: number;
  summary?: JobSummary;
  error?: string;
  publish?: {
    ok?: boolean;
    url?: string;
    repo?: string;
    error?: string;
  };
  has_evidence?: boolean;
};

export function ReaApp() {
  const [st, setSt] = useState<ReaStatus | null>(null);
  const [target, setTarget] = useState("https://");
  const [kind, setKind] = useState<"url" | "path">("url");
  const [repo, setRepo] = useState("");
  const [privateRepo, setPrivateRepo] = useState(true);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<"idle" | "analyzing" | "publishing">("idle");
  const [job, setJob] = useState<Job | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [mcpNote, setMcpNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [s, j] = await Promise.all([
      apiFetch(`${KERNEL}/rea/status`),
      apiFetch(`${KERNEL}/rea/jobs?limit=12`),
    ]);
    setSt(await s.json());
    const jj = await j.json();
    setJobs(jj.jobs || []);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const analyze = async () => {
    const t = target.trim();
    if (!t || t === "https://") {
      setNote("informe a URL do site ou o caminho do app");
      return;
    }
    setBusy(true);
    setPhase("analyzing");
    setNote(null);
    setJob(null);
    try {
      const r = await apiFetch(`${KERNEL}/rea/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: t,
          kind,
          observation_ms: 2000,
          fetch_source_maps: true,
        }),
      });
      const j = await r.json();
      if (!j.ok) {
        setNote(j.error || j.job?.error || `falha HTTP ${r.status}`);
        setJob(j.job || null);
      } else {
        setJob(j.job);
        setNote("análise pronta — revise o resumo e publique");
      }
      await refresh();
    } catch (e) {
      setNote(e instanceof Error ? e.message : "erro de rede");
    } finally {
      setBusy(false);
      setPhase("idle");
    }
  };

  const publish = async () => {
    if (!job?.id) return;
    setBusy(true);
    setPhase("publishing");
    setNote(null);
    try {
      const r = await apiFetch(
        `${KERNEL}/rea/jobs/${encodeURIComponent(job.id)}/publish`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            repo: repo.trim() || undefined,
            private: privateRepo,
            description: `REA reverse of ${job.target} via Véu`,
          }),
        },
      );
      const j = await r.json();
      if (!j.ok) {
        setNote(j.error || j.publish?.error || "publish falhou");
        if (j.job) setJob(j.job);
      } else {
        setJob(j.job);
        setNote(j.publish?.url ? `publicado: ${j.publish.url}` : "publicado");
      }
      await refresh();
    } catch (e) {
      setNote(e instanceof Error ? e.message : "erro de rede");
    } finally {
      setBusy(false);
      setPhase("idle");
    }
  };

  const registerMcp = async () => {
    setMcpNote(null);
    try {
      const r = await apiFetch(`${KERNEL}/rea/mcp/register`, { method: "POST" });
      const j = await r.json();
      setMcpNote(
        j.ok
          ? `MCP REA no barramento · id=${j.id || "rea"}`
          : j.error || "não registrou",
      );
      await refresh();
    } catch (e) {
      setMcpNote(e instanceof Error ? e.message : "erro");
    }
  };

  const cdpOk = st?.cdp?.ok;
  const cliOk = st?.cli?.ok;

  return (
    <div className="panel-app rea">
      <header className="rea__head">
        <div>
          <p className="rea__eyebrow">morluto/rea · rea.tools</p>
          <h2>REA · reverse engineer anything</h2>
          <p className="rea__lede">
            Coloque um site ou app, o Véu inspeciona com REA e publica a
            evidência num repositório GitHub.
          </p>
        </div>
        <div className="rea__pills" aria-label="status">
          <span className={`rea__pill ${cliOk ? "is-on" : "is-off"}`}>
            cli · {cliOk ? "ok" : "…"}
          </span>
          <span className={`rea__pill ${cdpOk ? "is-on" : "is-off"}`}>
            chrome lite · {cdpOk ? "ok" : "off"}
          </span>
        </div>
      </header>

      <p className="rea__disc">{st?.disclaimer}</p>

      <section className="rea__form">
        <label className="rea__field">
          <span>tipo</span>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as "url" | "path")}
            disabled={busy}
          >
            <option value="url">site (URL)</option>
            <option value="path">app JS/Electron (caminho local)</option>
          </select>
        </label>
        <label className="rea__field rea__field--grow">
          <span>{kind === "url" ? "URL" : "caminho"}</span>
          <input
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder={
              kind === "url"
                ? "https://exemplo.com/app"
                : "/caminho/para/app-ou-asar"
            }
            disabled={busy}
            spellCheck={false}
          />
        </label>
        <button
          type="button"
          className="rea__go"
          disabled={busy}
          onClick={() => void analyze()}
        >
          {phase === "analyzing" ? "analisando…" : "reverter"}
        </button>
      </section>

      {note ? <p className="rea__note">{note}</p> : null}

      {job ? (
        <section className="rea__job">
          <header>
            <h3>{job.summary?.title || job.id}</h3>
            <span className={`rea__status is-${job.status || "idle"}`}>
              {job.status}
            </span>
          </header>
          <p className="rea__meta">
            <code>{job.target}</code> · {job.kind}
            {job.summary?.modules != null
              ? ` · ${job.summary.modules} módulos`
              : ""}
          </p>
          {job.error ? <p className="rea__err">{job.error}</p> : null}
          <ul className="rea__notes">
            {(job.summary?.notes || []).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>

          {job.status === "done" || job.has_evidence ? (
            <div className="rea__publish">
              <label className="rea__field">
                <span>repo (opcional)</span>
                <input
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                  placeholder="rea-meu-alvo-20261020"
                  disabled={busy}
                  spellCheck={false}
                />
              </label>
              <label className="rea__check">
                <input
                  type="checkbox"
                  checked={privateRepo}
                  onChange={(e) => setPrivateRepo(e.target.checked)}
                  disabled={busy}
                />
                privado
              </label>
              <button
                type="button"
                className="rea__go"
                disabled={busy}
                onClick={() => void publish()}
              >
                {phase === "publishing" ? "publicando…" : "publicar no GitHub"}
              </button>
              {job.publish?.url ? (
                <a
                  className="rea__link"
                  href={job.publish.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {job.publish.url}
                </a>
              ) : null}
              {job.publish?.error ? (
                <p className="rea__err">{job.publish.error}</p>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="rea__mcp">
        <button type="button" onClick={() => void registerMcp()} disabled={busy}>
          registrar MCP REA no Véu
        </button>
        {mcpNote ? <span>{mcpNote}</span> : null}
        <a href="https://github.com/morluto/rea" target="_blank" rel="noreferrer">
          github.com/morluto/rea
        </a>
        <a href="https://rea.tools" target="_blank" rel="noreferrer">
          rea.tools
        </a>
      </section>

      {jobs.length ? (
        <section className="rea__history">
          <h3>jobs recentes</h3>
          <ul>
            {jobs.map((j) => (
              <li key={j.id}>
                <button
                  type="button"
                  onClick={() => {
                    setJob(j);
                    setTarget(j.target || target);
                    setKind((j.kind as "url" | "path") || "url");
                  }}
                >
                  <strong>{j.summary?.title || j.id}</strong>
                  <span>
                    {j.status} · {j.target}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <style>{`
        .rea {
          height: 100%;
          overflow: auto;
          padding: 1rem 1.1rem 1.4rem;
          color: var(--mist, #ecf2f8);
        }
        .rea__head {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          align-items: flex-start;
          margin-bottom: 0.75rem;
        }
        .rea__eyebrow {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
          color: #9bb7ff;
        }
        .rea h2 {
          margin: 0.15rem 0 0.35rem;
          font-family: var(--font-display);
          font-size: 1.35rem;
          font-weight: 700;
        }
        .rea__lede {
          margin: 0;
          max-width: 36rem;
          color: #a8b4c0;
          font-size: 0.88rem;
          line-height: 1.4;
        }
        .rea__pills { display: flex; flex-wrap: wrap; gap: 0.35rem; }
        .rea__pill {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.08em;
          padding: 0.28rem 0.5rem;
          border: 1px solid rgba(155, 183, 255, 0.28);
          border-radius: 999px;
        }
        .rea__pill.is-on { color: #7fe7d4; border-color: rgba(127,231,212,0.4); }
        .rea__pill.is-off { color: #f0a8a0; }
        .rea__disc {
          margin: 0 0 0.9rem;
          font-size: 0.72rem;
          color: #8a939c;
          line-height: 1.35;
        }
        .rea__form {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
          align-items: flex-end;
          margin-bottom: 0.75rem;
        }
        .rea__field {
          display: grid;
          gap: 0.25rem;
          min-width: 7rem;
        }
        .rea__field--grow { flex: 1 1 14rem; }
        .rea__field span {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: #8a939c;
        }
        .rea__field input,
        .rea__field select {
          appearance: none;
          background: rgba(7, 9, 12, 0.65);
          border: 1px solid rgba(155, 183, 255, 0.28);
          color: inherit;
          padding: 0.45rem 0.55rem;
          font: inherit;
          font-size: 0.85rem;
          border-radius: 0.35rem;
        }
        .rea__go {
          appearance: none;
          cursor: pointer;
          border: 0;
          background: #9bb7ff;
          color: #0a0c10;
          font-family: var(--font-mono);
          font-size: 0.72rem;
          letter-spacing: 0.06em;
          padding: 0.55rem 0.9rem;
          border-radius: 0.35rem;
          font-weight: 600;
        }
        .rea__go:disabled { opacity: 0.55; cursor: wait; }
        .rea__note {
          margin: 0 0 0.75rem;
          font-family: var(--font-mono);
          font-size: 0.72rem;
          color: #e8c27a;
        }
        .rea__job {
          border: 1px solid rgba(155, 183, 255, 0.22);
          background: rgba(7, 9, 12, 0.45);
          padding: 0.75rem 0.85rem;
          margin-bottom: 0.9rem;
          border-radius: 0.45rem;
        }
        .rea__job header {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
          align-items: baseline;
        }
        .rea__job h3 {
          margin: 0;
          font-size: 1rem;
          font-family: var(--font-display);
        }
        .rea__status {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
        }
        .rea__status.is-done { color: #7fe7d4; }
        .rea__status.is-error { color: #f0a8a0; }
        .rea__status.is-running { color: #e8c27a; }
        .rea__meta {
          margin: 0.35rem 0 0.5rem;
          font-size: 0.75rem;
          color: #a8b4c0;
          word-break: break-all;
        }
        .rea__notes {
          margin: 0 0 0.75rem;
          padding-left: 1.1rem;
          font-size: 0.82rem;
          color: #c8d0dc;
        }
        .rea__err { color: #f0a8a0; font-size: 0.78rem; }
        .rea__publish {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
          align-items: flex-end;
          padding-top: 0.5rem;
          border-top: 1px solid rgba(155, 183, 255, 0.14);
        }
        .rea__check {
          display: flex;
          align-items: center;
          gap: 0.35rem;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          color: #a8b4c0;
        }
        .rea__link {
          color: #9bb7ff;
          font-family: var(--font-mono);
          font-size: 0.72rem;
          word-break: break-all;
        }
        .rea__mcp {
          display: flex;
          flex-wrap: wrap;
          gap: 0.65rem;
          align-items: center;
          margin: 0.5rem 0 1rem;
          font-size: 0.75rem;
        }
        .rea__mcp button {
          appearance: none;
          cursor: pointer;
          border: 1px solid rgba(232, 194, 122, 0.35);
          background: transparent;
          color: #e8c27a;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          padding: 0.4rem 0.65rem;
          border-radius: 0.35rem;
        }
        .rea__mcp a { color: #9bb7ff; }
        .rea__history h3 {
          margin: 0 0 0.45rem;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
          color: #8a939c;
        }
        .rea__history ul {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 0.35rem;
        }
        .rea__history button {
          appearance: none;
          width: 100%;
          text-align: left;
          cursor: pointer;
          border: 1px solid rgba(155, 183, 255, 0.16);
          background: rgba(7, 9, 12, 0.35);
          color: inherit;
          padding: 0.45rem 0.55rem;
          border-radius: 0.35rem;
          display: grid;
          gap: 0.15rem;
        }
        .rea__history button span {
          font-size: 0.7rem;
          color: #8a939c;
          word-break: break-all;
        }
      `}</style>
    </div>
  );
}

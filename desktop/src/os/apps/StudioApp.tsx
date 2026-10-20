import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";

type Asset = {
  id: string;
  filename?: string;
  kind?: string;
  bytes?: number;
  actions?: { id: string; label: string; hint?: string }[];
};

type Job = {
  id?: string;
  action?: string;
  filename?: string;
  status?: string;
  decision?: { executor?: string; reason?: string };
  result?: { message?: string; text?: string; artifact?: string };
};

/** Studio — upload, análise, RAG, planilha, geração, delegação. */
export function StudioApp() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Asset | null>(null);
  const [prompt, setPrompt] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [a, j] = await Promise.all([
        apiFetch(`${KERNEL}/studio/assets`).then((r) => r.json()),
        apiFetch(`${KERNEL}/studio/jobs`).then((r) => r.json()),
      ]);
      setAssets((a as { assets?: Asset[] }).assets || []);
      setJobs((j as { jobs?: Job[] }).jobs || []);
    } catch {
      setErr("kernel offline");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const uploadFile = async (file: File) => {
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch(`${KERNEL}/studio/upload`, { method: "POST", body: fd });
      const raw = await res.text();
      const data = raw ? (JSON.parse(raw) as { ok?: boolean; asset?: Asset; error?: string }) : {};
      if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
      if (data.asset) setSelected(data.asset);
      void reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "upload falhou");
    } finally {
      setBusy(false);
    }
  };

  const runAction = async (action: string) => {
    if (!selected?.id) {
      setErr("selecione ou envie um arquivo");
      return;
    }
    setBusy(true);
    setErr(null);
    setOut("rodando…");
    try {
      const res = await apiFetch(`${KERNEL}/studio/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          asset_id: selected.id,
          prompt: prompt.trim() || null,
        }),
      });
      const raw = await res.text();
      const data = raw
        ? (JSON.parse(raw) as {
            ok?: boolean;
            job?: Job;
            error?: string;
          })
        : {};
      const job = data.job;
      const text =
        job?.result?.text ||
        job?.result?.message ||
        data.error ||
        (data.ok ? "ok" : "falha");
      setOut(text);
      void reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
      setOut("");
    } finally {
      setBusy(false);
    }
  };

  const actions = selected?.actions || [];

  return (
    <div className="st">
      <header className="st__head">
        <div>
          <p className="st__kicker">studio · arquivos vivos</p>
          <h2>upload · analisar · gerar</h2>
          <p className="st__sub">
            Texto, PDF, áudio, planilha, imagem. O SO decide: local, Hermes ou
            Grok Bot.
          </p>
        </div>
      </header>

      <div
        className={`st__drop${dragOver ? " is-over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) void uploadFile(f);
        }}
        onClick={() => inputRef.current?.click()}
      >
        <p>solte o arquivo aqui ou clique para escolher</p>
        <input
          ref={inputRef}
          type="file"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void uploadFile(f);
            e.target.value = "";
          }}
        />
      </div>

      <div className="st__grid">
        <section className="st__panel">
          <h3>assets</h3>
          {assets.length === 0 ? (
            <p className="st__empty">nenhum arquivo ainda</p>
          ) : (
            <ul>
              {assets.slice(0, 20).map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    className={selected?.id === a.id ? "is-on" : ""}
                    disabled={busy}
                    onClick={() => setSelected(a)}
                  >
                    <strong>{a.filename || a.id}</strong>
                    <span>
                      {a.kind} · {a.bytes ?? 0} B
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="st__panel">
          <h3>ações {selected ? `· ${selected.filename}` : ""}</h3>
          {!selected ? (
            <p className="st__empty">selecione um asset</p>
          ) : (
            <>
              <textarea
                rows={2}
                value={prompt}
                disabled={busy}
                placeholder="pedido opcional (ex.: foque em riscos)…"
                onChange={(e) => setPrompt(e.target.value)}
              />
              <div className="st__actions">
                {actions.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    disabled={busy}
                    title={a.hint}
                    onClick={() => void runAction(a.id)}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </>
          )}
          {out ? <pre className="st__out">{out}</pre> : null}
        </section>

        <section className="st__panel st__panel--wide">
          <h3>jobs recentes</h3>
          {jobs.length === 0 ? (
            <p className="st__empty">sem jobs</p>
          ) : (
            <ul className="st__jobs">
              {jobs.slice(0, 12).map((j) => (
                <li key={j.id}>
                  <strong>
                    {j.action} · {j.filename}
                  </strong>
                  <span>
                    {j.status} · {j.decision?.executor} ·{" "}
                    {(j.result?.message || "").slice(0, 120)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {err ? <p className="st__err">{err}</p> : null}

      <style>{`
        .st {
          height: 100%;
          overflow: auto;
          padding: 0.9rem 1rem;
          display: grid;
          gap: 0.7rem;
          color: #e8ebe6;
          background:
            radial-gradient(ellipse at 0% 100%, rgba(127,231,212,0.1), transparent 40%),
            linear-gradient(165deg, #111418, #0c0e12 70%);
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .st__kicker {
          margin: 0;
          font-size: 0.65rem;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: #7fe7d4;
        }
        .st__head h2 {
          margin: 0.15rem 0 0;
          font-family: "IBM Plex Serif", Georgia, serif;
          font-weight: 500;
          font-size: 1.35rem;
        }
        .st__sub {
          margin: 0.25rem 0 0;
          font-size: 0.82rem;
          color: #9aa3ad;
        }
        .st__drop {
          border: 1px dashed rgba(127,231,212,0.35);
          background: rgba(127,231,212,0.04);
          padding: 1.2rem;
          text-align: center;
          cursor: pointer;
          color: #9aa3ad;
          font-size: 0.88rem;
        }
        .st__drop.is-over {
          border-color: #7fe7d4;
          color: #7fe7d4;
        }
        .st__grid {
          display: grid;
          grid-template-columns: 1fr 1.2fr;
          gap: 0.55rem;
        }
        .st__panel {
          border: 1px solid rgba(255,255,255,0.08);
          background: rgba(0,0,0,0.22);
          padding: 0.6rem 0.7rem;
          min-height: 10rem;
        }
        .st__panel--wide { grid-column: 1 / -1; min-height: auto; }
        .st__panel h3 {
          margin: 0 0 0.45rem;
          font-size: 0.68rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: #7fe7d4;
          font-weight: 500;
        }
        .st__empty { margin: 0; font-size: 0.78rem; color: #6b7480; }
        .st__panel ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.3rem; }
        .st__panel li button {
          width: 100%;
          text-align: left;
          border: 1px solid transparent;
          background: transparent;
          color: inherit;
          padding: 0.35rem 0.4rem;
          cursor: pointer;
          display: grid;
          gap: 0.1rem;
        }
        .st__panel li button.is-on {
          border-color: rgba(127,231,212,0.35);
          background: rgba(127,231,212,0.08);
        }
        .st__panel li strong { font-size: 0.82rem; font-weight: 500; }
        .st__panel li span { font-size: 0.68rem; color: #7a8490; }
        .st__panel textarea {
          width: 100%;
          border: 1px solid rgba(255,255,255,0.1);
          background: rgba(0,0,0,0.3);
          color: #e8ebe6;
          padding: 0.4rem;
          font: inherit;
          margin-bottom: 0.45rem;
          resize: vertical;
        }
        .st__actions {
          display: flex;
          flex-wrap: wrap;
          gap: 0.3rem;
        }
        .st__actions button {
          border: 1px solid rgba(127,231,212,0.35);
          background: rgba(127,231,212,0.08);
          color: #c8f0e6;
          padding: 0.3rem 0.55rem;
          font-size: 0.72rem;
          cursor: pointer;
        }
        .st__actions button:disabled { opacity: 0.4; }
        .st__out {
          margin: 0.55rem 0 0;
          padding: 0.5rem;
          max-height: 180px;
          overflow: auto;
          background: rgba(0,0,0,0.35);
          font-size: 0.75rem;
          white-space: pre-wrap;
          color: #c5cdc8;
        }
        .st__jobs li {
          display: grid;
          gap: 0.1rem;
          padding: 0.3rem 0;
          border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .st__err { margin: 0; color: #e8a0a0; font-size: 0.8rem; }
        @media (max-width: 720px) {
          .st__grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}

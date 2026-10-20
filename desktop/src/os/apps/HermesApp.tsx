import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";

type Agent = { id: string; label: string; hint: string };

type HermesPulse = {
  status?: string;
  home?: string | null;
  api_url?: string | null;
  observations?: number;
  proposals?: number;
  queue_depth?: number;
  running?: number;
  queued?: number;
  patterns?: string[];
  agents?: Agent[];
  preferred_agent?: Agent;
};

type QueueBoard = {
  running?: Job[];
  queued?: Job[];
  done?: Job[];
  proposals?: Proposal[];
  counts?: Record<string, number>;
  status?: string;
  agents?: Agent[];
  preferred_agent?: Agent;
};

type Job = {
  job_id?: string;
  intent?: string;
  state?: string;
  message?: string;
  agent?: string;
  agent_label?: string;
  ts?: number;
};

type Proposal = {
  id?: string;
  pattern?: string;
  repeats?: number;
  message?: string;
};

const QUICK = [
  "distilar skill do que eu mais repito",
  "observe o padrão de triagem de e-mail",
  "proponha uma skill ECC a partir do Studio",
  "liste o que aprendeu hoje",
];

const FALLBACK_AGENTS: Agent[] = [
  { id: "hermes-operator", label: "operador", hint: "learning loop padrão" },
  { id: "skill-distiller", label: "distilador", hint: "padrões → skill ECC" },
  { id: "memory-curator", label: "curador", hint: "memória e vault" },
  { id: "architect", label: "arquiteto", hint: "desenho técnico" },
  { id: "planner", label: "planejador", hint: "passos e checklist" },
  { id: "chief-of-staff", label: "chefe de gabinete", hint: "triagem do dia" },
  { id: "code-reviewer", label: "revisor", hint: "qualidade de código" },
];

function ago(ts?: number) {
  if (!ts) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

/** Hermes — learning loop · escolha de agente · fila. */
export function HermesApp() {
  const [pulse, setPulse] = useState<HermesPulse | null>(null);
  const [board, setBoard] = useState<QueueBoard | null>(null);
  const [intent, setIntent] = useState("");
  const [agentId, setAgentId] = useState("hermes-operator");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const agents =
    pulse?.agents || board?.agents || FALLBACK_AGENTS;
  const preferred =
    pulse?.preferred_agent ||
    board?.preferred_agent ||
    agents.find((a) => a.id === agentId) ||
    agents[0];

  const reload = useCallback(async () => {
    try {
      const [p, q] = await Promise.all([
        apiFetch(`${KERNEL}/bridge/hermes/pulse`).then((r) => r.json()),
        apiFetch(`${KERNEL}/bridge/hermes/queue`).then((r) => r.json()),
      ]);
      const pp = p as HermesPulse;
      const qq = q as QueueBoard;
      setPulse(pp);
      setBoard(qq);
      const pref = pp.preferred_agent?.id || qq.preferred_agent?.id;
      if (pref) setAgentId(pref);
      setErr(null);
    } catch {
      setErr("kernel offline");
    }
  }, []);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 8000);
    return () => window.clearInterval(id);
  }, [reload]);

  const prefer = async (id: string) => {
    setAgentId(id);
    try {
      await apiFetch(`${KERNEL}/bridge/hermes/prefer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: id }),
      });
      void reload();
    } catch {
      /* local only */
    }
  };

  const ask = async (text: string) => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await apiFetch(`${KERNEL}/bridge/hermes/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: t, source: "os", agent: agentId }),
      });
      const data = (await res.json()) as {
        ok?: boolean;
        message?: string;
        error?: string;
        agent?: Agent;
      };
      const who = data.agent?.label ? ` · ${data.agent.label}` : "";
      setMsg((data.message || data.error || (data.ok ? "ok" : "falha")) + who);
      if (data.ok) setIntent("");
      void reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "falha");
    } finally {
      setBusy(false);
    }
  };

  const status = pulse?.status || board?.status || "planned";
  const current = agents.find((a) => a.id === agentId) || preferred;

  return (
    <div className="hm">
      <header className="hm__head">
        <div>
          <p className="hm__kicker">hermes · learning loop</p>
          <h2>operador que aprende</h2>
          <p className="hm__sub">
            Escolha o agente e peça. Jobs entram na fila com esse responsável.
          </p>
        </div>
        <div className={`hm__badge is-${status}`}>
          <i />
          {status}
        </div>
      </header>

      <section className="hm__agent">
        <label>
          <span>agente</span>
          <select
            value={agentId}
            disabled={busy}
            onChange={(e) => void prefer(e.target.value)}
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
        <p className="hm__agent-hint">{current?.hint}</p>
        <div className="hm__agent-chips">
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              className={a.id === agentId ? "is-on" : ""}
              disabled={busy}
              title={a.hint}
              onClick={() => void prefer(a.id)}
            >
              {a.label}
            </button>
          ))}
        </div>
      </section>

      <section className="hm__ask">
        <label>
          <span>pedir · {current?.label || "operador"}</span>
          <textarea
            rows={2}
            value={intent}
            disabled={busy}
            placeholder="ex.: distilar skill de triagem de e-mail…"
            onChange={(e) => setIntent(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="hm__go"
          disabled={busy || !intent.trim()}
          onClick={() => void ask(intent)}
        >
          {busy ? "…" : `enfileirar · ${current?.label || "agente"}`}
        </button>
        <div className="hm__chips">
          {QUICK.map((q) => (
            <button key={q} type="button" disabled={busy} onClick={() => void ask(q)}>
              {q}
            </button>
          ))}
        </div>
      </section>

      <div className="hm__grid">
        <section className="hm__panel">
          <h3>
            executando <em>{(board?.running || []).length}</em>
          </h3>
          {(board?.running || []).length === 0 ? (
            <p className="hm__empty">nada rodando</p>
          ) : (
            <ul>
              {(board?.running || []).map((j) => (
                <li key={j.job_id}>
                  <em className="hm__who">{j.agent_label || j.agent || "—"}</em>
                  <strong>{j.intent || j.job_id}</strong>
                  <span>
                    {j.state} · {ago(j.ts)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="hm__panel">
          <h3>
            fila <em>{(board?.queued || []).length}</em>
          </h3>
          {(board?.queued || []).length === 0 ? (
            <p className="hm__empty">fila vazia</p>
          ) : (
            <ul>
              {(board?.queued || []).map((j) => (
                <li key={j.job_id}>
                  <em className="hm__who">{j.agent_label || j.agent || "—"}</em>
                  <strong>{j.intent || j.job_id}</strong>
                  <span>{ago(j.ts)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="hm__panel">
          <h3>
            skills propostas <em>{(board?.proposals || []).length}</em>
          </h3>
          {(board?.proposals || []).length === 0 ? (
            <p className="hm__empty">ainda sem padrão repetido</p>
          ) : (
            <ul>
              {(board?.proposals || []).map((p) => (
                <li key={p.id}>
                  <strong>{p.pattern}</strong>
                  <span>
                    ×{p.repeats} · {p.message}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="hm__panel">
          <h3>estado</h3>
          <ul className="hm__stats">
            <li>preferido · {preferred?.label || agentId}</li>
            <li>observações · {pulse?.observations ?? 0}</li>
            <li>propostas · {pulse?.proposals ?? 0}</li>
            <li>api · {pulse?.api_url || "local loop"}</li>
          </ul>
        </section>
      </div>

      {msg ? <p className="hm__foot">{msg}</p> : null}
      {err ? <p className="hm__err">{err}</p> : null}

      <style>{`
        .hm {
          height: 100%;
          overflow: auto;
          padding: 0.9rem 1rem;
          display: grid;
          gap: 0.7rem;
          color: #e6ebe8;
          background:
            radial-gradient(ellipse at 10% 0%, rgba(143,191,159,0.18), transparent 45%),
            linear-gradient(165deg, #101412, #0b0e0c 70%);
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .hm__head { display: flex; justify-content: space-between; gap: 0.75rem; }
        .hm__kicker {
          margin: 0; font-size: 0.65rem; letter-spacing: 0.16em;
          text-transform: uppercase; color: #8fbf9f;
        }
        .hm__head h2 {
          margin: 0.15rem 0 0; font-family: "IBM Plex Serif", Georgia, serif;
          font-weight: 500; font-size: 1.4rem;
        }
        .hm__sub { margin: 0.25rem 0 0; font-size: 0.82rem; color: #9aa89e; max-width: 34rem; }
        .hm__badge {
          align-self: start; display: flex; align-items: center; gap: 0.35rem;
          border: 1px solid rgba(143,191,159,0.35); padding: 0.35rem 0.6rem;
          font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; color: #9aa89e;
        }
        .hm__badge.is-live { color: #8fbf9f; }
        .hm__badge.is-ready { color: #d4b896; }
        .hm__badge i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
        .hm__agent, .hm__ask {
          border: 1px solid rgba(143,191,159,0.2); padding: 0.7rem;
          background: rgba(0,0,0,0.22); display: grid; gap: 0.45rem;
        }
        .hm__agent label span, .hm__ask label span, .hm__panel h3 {
          display: block; font-size: 0.68rem; letter-spacing: 0.1em;
          text-transform: uppercase; color: #8fbf9f; margin-bottom: 0.3rem;
        }
        .hm__agent select {
          width: 100%; max-width: 280px; border: 1px solid rgba(255,255,255,0.12);
          background: rgba(0,0,0,0.35); color: #e6ebe8; padding: 0.4rem 0.5rem; font: inherit;
        }
        .hm__agent-hint { margin: 0; font-size: 0.78rem; color: #8a9a90; }
        .hm__agent-chips, .hm__chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
        .hm__agent-chips button, .hm__chips button {
          border: 1px solid rgba(255,255,255,0.1); background: transparent;
          color: #a8b8ae; padding: 0.25rem 0.55rem; font-size: 0.7rem; cursor: pointer;
        }
        .hm__agent-chips button.is-on {
          border-color: rgba(143,191,159,0.55); background: rgba(143,191,159,0.15); color: #e8f2ea;
        }
        .hm__ask textarea {
          width: 100%; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.35);
          color: #e6ebe8; padding: 0.45rem 0.55rem; font: inherit; resize: vertical;
        }
        .hm__go {
          justify-self: start; border: 1px solid rgba(143,191,159,0.5);
          background: rgba(143,191,159,0.15); color: #e8f2ea; padding: 0.4rem 0.85rem;
          cursor: pointer; font-size: 0.8rem;
        }
        .hm__go:disabled { opacity: 0.4; cursor: default; }
        .hm__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.55rem; }
        .hm__panel {
          border: 1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,0.2);
          padding: 0.6rem 0.7rem; min-height: 7rem;
        }
        .hm__panel h3 em { font-style: normal; color: #7a8a80; margin-left: 0.35rem; }
        .hm__empty { margin: 0; font-size: 0.78rem; color: #6b7a70; }
        .hm__panel ul, .hm__stats { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
        .hm__panel li { display: grid; gap: 0.1rem; }
        .hm__who {
          font-style: normal; font-size: 0.62rem; letter-spacing: 0.08em;
          text-transform: uppercase; color: #8fbf9f;
        }
        .hm__panel strong { font-size: 0.82rem; font-weight: 500; }
        .hm__panel span, .hm__stats li { font-size: 0.7rem; color: #8a9a90; }
        .hm__foot { margin: 0; color: #8fbf9f; font-size: 0.8rem; }
        .hm__err { margin: 0; color: #e8a0a0; font-size: 0.8rem; }
        @media (max-width: 720px) { .hm__grid { grid-template-columns: 1fr; } }
      `}</style>
    </div>
  );
}

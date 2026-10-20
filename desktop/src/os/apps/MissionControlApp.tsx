import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  fetchMission,
  type MissionAction,
  type MissionAgent,
  type MissionProject,
  type MissionSnapshot,
} from "../../lib/kernel";

type Props = {
  onLaunch: (intent: string, opts?: { breath?: "guided" | "semi" | "free" | "autonomous" }) => void;
  onOpenAgent: (agentId: string) => void;
};

function stateTone(state: string): string {
  const s = (state || "").toLowerCase();
  if (s === "done" || s === "live") return "ok";
  if (s === "activated" || s === "running" || s === "active") return "run";
  if (s.includes("fail") || s.includes("error")) return "bad";
  return "idle";
}

function ago(ts?: number): string {
  if (!ts) return "—";
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h`;
}

/** Centro de comando do Véu — ações autônomas, agentes, projetos ao vivo. */
export function MissionControlApp({ onLaunch, onOpenAgent }: Props) {
  const [snap, setSnap] = useState<MissionSnapshot | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    let pollId: number | null = null;
    const pull = async () => {
      const m = await fetchMission();
      if (alive && m) setSnap(m);
      if (alive) setTick((t) => t + 1);
    };
    void pull();

    const startPoll = () => {
      if (pollId != null) return;
      pollId = window.setInterval(pull, 4000);
    };

    let stopStream: (() => void) | null = null;
    void import("../../lib/stream").then(({ connectKernelStream }) => {
      if (!alive) return;
      stopStream = connectKernelStream({
        onEvent: (type) => {
          if (type === "job" || type === "mission" || type === "hello") {
            void pull();
          }
        },
        onStatus: (status) => {
          if (status === "live" && pollId != null) {
            window.clearInterval(pollId);
            pollId = null;
          }
          if (status === "fallback") startPoll();
        },
      });
    });

    // fallback inicial curto até SSE conectar
    const boot = window.setTimeout(() => {
      if (alive && pollId == null) startPoll();
    }, 8000);

    return () => {
      alive = false;
      window.clearTimeout(boot);
      if (pollId != null) window.clearInterval(pollId);
      stopStream?.();
    };
  }, []);

  const projects = snap?.projects ?? [];
  const actions = snap?.actions ?? [];
  const agents = snap?.agents ?? [];
  const active = !!snap?.harness?.active;

  const flight = snap?.flight;
  const jevLine = useMemo(() => {
    if (!snap?.jev) return "jev · …";
    return `jev · ${snap.jev.status || "?"} · ${snap.jev.model || "router"}`;
  }, [snap]);

  const memLine = useMemo(() => {
    const m = snap?.memory;
    if (!m) return "memória · …";
    return `memória · ${m.sessions ?? 0} sessões · ${m.decisions ?? 0} decisões`;
  }, [snap]);

  return (
    <div className="mc">
      <header className="mc__hero">
        <motion.p
          className="mc__eyebrow"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          mission control · flight deck
        </motion.p>
        <motion.h1
          className="mc__brand"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        >
          véu
        </motion.h1>
        <motion.p
          className="mc__tag"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.15 }}
        >
          peça pouco. o SO decide o caminho, aciona agentes e mostra cada passo ao vivo.
        </motion.p>
        <div className={`mc__flight ${flight?.go ? "is-go" : "is-nogo"}`}>
          <strong>{flight?.go ? "GO" : "NO-GO"}</strong>
          <span>{flight?.summary || "checando readiness…"}</span>
        </div>
        <div className="mc__vitals">
          <span className={`mc__pulse ${active ? "is-hot" : ""}`}>
            harness · {active ? "ativo" : "em espera"}
          </span>
          <span>{jevLine}</span>
          <span>{memLine}</span>
          <span className="mc__tick">sync · {tick}</span>
        </div>
        {flight?.checks?.length ? (
          <div className="mc__checks" aria-label="checklist de voo">
            {flight.checks
              .filter((c) => c.critical || !c.ok)
              .slice(0, 8)
              .map((c) => (
                <span key={c.name} className={`mc__check is-${c.status}`}>
                  {c.name} · {c.ok ? "go" : c.status}
                </span>
              ))}
          </div>
        ) : null}
      </header>

      <section className="mc__actions" aria-label="ações autônomas">
        <p className="mc__sec">ações autônomas</p>
        <div className="mc__action-row">
          {actions.map((a: MissionAction, i: number) => (
            <motion.button
              key={a.id}
              type="button"
              className="mc__action"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.04 * i }}
              whileTap={{ scale: 0.98 }}
              onClick={() =>
                onLaunch(a.intent, {
                  breath: a.id === "free-run" ? "free" : a.id === "grok-handoff" ? "semi" : "guided",
                })
              }
            >
              <span className="mc__action-label">{a.label}</span>
              <span className="mc__action-agent">{a.agent || "véu"}</span>
            </motion.button>
          ))}
        </div>
      </section>

      <div className="mc__grid">
        <section className="mc__projects" aria-label="projetos ao vivo">
          <p className="mc__sec">projetos · tempo real</p>
          <AnimatePresence mode="popLayout">
            {projects.length === 0 ? (
              <p className="mc__empty">ainda sem missões — dispare uma ação acima</p>
            ) : (
              projects.map((p: MissionProject) => (
                <motion.button
                  key={`${p.id}-${p.state}-${p.ts}`}
                  type="button"
                  className={`mc__proj is-${stateTone(p.state)}`}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  onClick={() => onLaunch(p.intent)}
                >
                  <span className="mc__proj-dot" />
                  <span className="mc__proj-body">
                    <strong>{p.intent}</strong>
                    <em>
                      {p.route} · {p.state} · {ago(p.ts)}
                      {p.tools?.length ? ` · ${p.tools.length} tools` : ""}
                    </em>
                  </span>
                </motion.button>
              ))
            )}
          </AnimatePresence>
        </section>

        <section className="mc__agents" aria-label="agentes">
          <p className="mc__sec">agentes · ligação direta</p>
          <div className="mc__agent-list">
            {agents.slice(0, 12).map((a: MissionAgent, i: number) => (
              <motion.button
                key={a.id}
                type="button"
                className="mc__agent"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.03 * i }}
                onClick={() => onOpenAgent(a.id)}
                title={a.role}
              >
                <span>{a.title}</span>
                <em>{a.id}</em>
              </motion.button>
            ))}
          </div>
          <p className="mc__sec" style={{ marginTop: "1.25rem" }}>
            nervos vivos
          </p>
          <p className="mc__nerves">
            {(snap?.nerves || [])
              .slice(0, 10)
              .map((n) => `${n.name}·${n.status}`)
              .join("  ·  ") || "—"}
          </p>
        </section>
      </div>

      <style>{`
        .mc {
          height: 100%;
          display: grid;
          grid-template-rows: auto auto 1fr;
          gap: 1.1rem;
          padding: 1.1rem 1.25rem 1.25rem;
          overflow: auto;
        }
        .mc__hero {
          display: grid;
          gap: 0.35rem;
        }
        .mc__eyebrow {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.22em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .mc__brand {
          margin: 0;
          font-family: var(--font-display);
          font-weight: 800;
          font-size: clamp(2.8rem, 7vw, 4.2rem);
          letter-spacing: -0.04em;
          line-height: 0.95;
          background: linear-gradient(120deg, #f3e6c4 0%, #e8c27a 45%, #7fe7d4 100%);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }
        .mc__tag {
          margin: 0.35rem 0 0;
          max-width: 42rem;
          color: var(--mist-dim);
          font-weight: 300;
          font-size: 1.02rem;
          line-height: 1.45;
        }
        .mc__flight {
          margin-top: 0.85rem;
          display: flex;
          align-items: baseline;
          gap: 0.75rem;
          flex-wrap: wrap;
          font-family: var(--font-mono);
          letter-spacing: 0.08em;
          text-transform: lowercase;
        }
        .mc__flight strong {
          font-family: var(--font-display);
          font-size: 1.35rem;
          letter-spacing: 0.12em;
        }
        .mc__flight.is-go strong { color: var(--signal); }
        .mc__flight.is-nogo strong { color: var(--danger); }
        .mc__flight span { color: var(--mist-dim); font-size: 0.72rem; }
        .mc__vitals {
          margin-top: 0.55rem;
          display: flex;
          flex-wrap: wrap;
          gap: 0.65rem 1.1rem;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.08em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .mc__pulse.is-hot {
          color: var(--filament);
        }
        .mc__tick { opacity: 0.55; }
        .mc__checks {
          margin-top: 0.55rem;
          display: flex;
          flex-wrap: wrap;
          gap: 0.4rem 0.85rem;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.06em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .mc__check.is-go { color: var(--signal); }
        .mc__check.is-no-go { color: var(--danger); }
        .mc__check.is-hold { color: var(--filament); }
        .mc__sec {
          margin: 0 0 0.55rem;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.16em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .mc__action-row {
          display: flex;
          flex-wrap: wrap;
          gap: 0.55rem;
        }
        .mc__action {
          appearance: none;
          border: 1px solid rgba(232, 194, 122, 0.35);
          background: linear-gradient(
            180deg,
            rgba(232, 194, 122, 0.1),
            rgba(7, 9, 12, 0.2)
          );
          color: var(--mist);
          padding: 0.7rem 0.95rem;
          cursor: pointer;
          display: grid;
          gap: 0.2rem;
          text-align: left;
          min-width: 8.5rem;
          transition: border-color 0.2s ease, background 0.2s ease;
        }
        .mc__action:hover {
          border-color: rgba(232, 194, 122, 0.75);
          background: rgba(232, 194, 122, 0.16);
        }
        .mc__action-label {
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 0.95rem;
          letter-spacing: -0.01em;
          color: var(--filament);
        }
        .mc__action-agent {
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.1em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .mc__grid {
          display: grid;
          grid-template-columns: 1.35fr 1fr;
          gap: 1.25rem;
          min-height: 0;
        }
        @media (max-width: 820px) {
          .mc__grid { grid-template-columns: 1fr; }
        }
        .mc__projects, .mc__agents {
          min-height: 0;
        }
        .mc__empty {
          margin: 0;
          color: var(--mist-dim);
          font-weight: 300;
          font-size: 0.9rem;
        }
        .mc__proj {
          width: 100%;
          appearance: none;
          border: 0;
          border-top: 1px solid rgba(236, 242, 248, 0.08);
          background: transparent;
          color: inherit;
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 0.7rem;
          align-items: start;
          padding: 0.7rem 0;
          cursor: pointer;
          text-align: left;
        }
        .mc__proj-dot {
          width: 0.45rem;
          height: 0.45rem;
          margin-top: 0.4rem;
          border-radius: 50%;
          background: var(--mist-dim);
        }
        .mc__proj.is-run .mc__proj-dot {
          background: var(--filament);
          box-shadow: 0 0 12px rgba(232, 194, 122, 0.55);
        }
        .mc__proj.is-ok .mc__proj-dot { background: var(--signal); }
        .mc__proj.is-bad .mc__proj-dot { background: var(--danger); }
        .mc__proj-body {
          display: grid;
          gap: 0.25rem;
          min-width: 0;
        }
        .mc__proj-body strong {
          font-weight: 400;
          font-size: 0.92rem;
          color: var(--mist);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .mc__proj-body em {
          font-style: normal;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.06em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .mc__agent-list {
          display: grid;
          gap: 0.35rem;
        }
        .mc__agent {
          appearance: none;
          border: 0;
          border-left: 1px solid rgba(127, 231, 212, 0.28);
          background: transparent;
          color: inherit;
          display: flex;
          justify-content: space-between;
          gap: 0.75rem;
          padding: 0.45rem 0.2rem 0.45rem 0.7rem;
          cursor: pointer;
          text-align: left;
          transition: border-color 0.2s ease, color 0.2s ease;
        }
        .mc__agent:hover {
          border-left-color: var(--signal);
          color: var(--signal);
        }
        .mc__agent span {
          font-size: 0.88rem;
          font-weight: 400;
        }
        .mc__agent em {
          font-style: normal;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.06em;
          color: var(--mist-dim);
        }
        .mc__nerves {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.04em;
          line-height: 1.55;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
      `}</style>
    </div>
  );
}

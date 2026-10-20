import { useEffect, useMemo, useState } from "react";
import { ECO_LINKS, ECO_NODES, type EcoNode } from "../lib/ecosystem";

type Props = {
  activeAgentIds?: string[];
  pulsing?: boolean;
};

function colorFor(kind: EcoNode["kind"]) {
  switch (kind) {
    case "kernel":
      return "#e8c27a";
    case "agent":
      return "#7fe7d4";
    case "model":
      return "#9bb7ff";
    default:
      return "#c4b5a0";
  }
}

/** Mapa vivo: agentes, modelos e nervos ligados ao kernel. */
export function EcosystemStage({ activeAgentIds = [], pulsing = true }: Props) {
  const [tick, setTick] = useState(0);
  const W = 720;
  const H = 420;

  useEffect(() => {
    if (!pulsing) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 80);
    return () => window.clearInterval(id);
  }, [pulsing]);

  const nodes = useMemo(
    () =>
      ECO_NODES.map((n) => ({
        ...n,
        px: n.x * W,
        py: n.y * H,
      })),
    [],
  );

  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);

  return (
    <div className="eco">
      <header className="eco__head">
        <p className="eco__kicker">ecossistema</p>
        <h2 className="eco__title">agentes · modelos · nervos</h2>
        <p className="eco__sub">o SO em funcionamento — ligações vivas entre as peças</p>
      </header>

      <svg className="eco__canvas" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Mapa do ecossistema Véu">
        <defs>
          <radialGradient id="ecoGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(232,194,122,0.22)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>
        <circle cx={W / 2} cy={H / 2} r={150} fill="url(#ecoGlow)" />

        {ECO_LINKS.map((link, i) => {
          const a = byId[link.from];
          const b = byId[link.to];
          if (!a || !b) return null;
          const progress = ((tick * 0.04 + i * 0.17) % 1);
          const mx = a.px + (b.px - a.px) * progress;
          const my = a.py + (b.py - a.py) * progress;
          return (
            <g key={`${link.from}-${link.to}`}>
              <line
                x1={a.px}
                y1={a.py}
                x2={b.px}
                y2={b.py}
                stroke="rgba(127,231,212,0.22)"
                strokeWidth={1.2}
              />
              <circle cx={mx} cy={my} r={2.4} fill="#e8c27a" opacity={0.9} />
            </g>
          );
        })}

        {nodes.map((n) => {
          const active = activeAgentIds.includes(n.id) || n.kind === "kernel";
          const r = n.kind === "kernel" ? 28 : 18;
          return (
            <g key={n.id} transform={`translate(${n.px}, ${n.py})`}>
              <circle
                r={r + (active ? 4 : 0)}
                fill="rgba(7,9,12,0.75)"
                stroke={colorFor(n.kind)}
                strokeWidth={active ? 2.2 : 1.2}
                opacity={0.95}
              />
              {n.kind === "kernel" && (
                <circle r={r + 10} fill="none" stroke="rgba(232,194,122,0.25)" strokeWidth={1}>
                  <animate attributeName="r" values={`${r + 8};${r + 16};${r + 8}`} dur="3s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0.15;0.5" dur="3s" repeatCount="indefinite" />
                </circle>
              )}
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fill={colorFor(n.kind)}
                fontSize={n.kind === "kernel" ? 13 : 10}
                fontFamily="IBM Plex Mono, monospace"
                letterSpacing="0.06em"
              >
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>

      <ul className="eco__legend">
        <li><i style={{ background: "#e8c27a" }} /> kernel</li>
        <li><i style={{ background: "#7fe7d4" }} /> agentes</li>
        <li><i style={{ background: "#9bb7ff" }} /> modelos</li>
        <li><i style={{ background: "#c4b5a0" }} /> nervos</li>
      </ul>

      <style>{`
        .eco {
          width: min(860px, 100%);
          display: grid;
          gap: 0.75rem;
        }
        .eco__kicker {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.18em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .eco__title {
          margin: 0.35rem 0 0;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: clamp(1.5rem, 3.5vw, 2.1rem);
          letter-spacing: -0.02em;
        }
        .eco__sub {
          margin: 0.35rem 0 0;
          color: var(--mist-dim);
          font-weight: 300;
          font-size: 0.95rem;
        }
        .eco__canvas {
          width: 100%;
          height: auto;
          border-top: 1px solid rgba(232, 194, 122, 0.22);
          background: linear-gradient(180deg, rgba(232,194,122,0.04), transparent 40%);
        }
        .eco__legend {
          list-style: none;
          margin: 0;
          padding: 0;
          display: flex;
          flex-wrap: wrap;
          gap: 0.85rem 1.25rem;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--mist-dim);
        }
        .eco__legend i {
          display: inline-block;
          width: 0.45rem;
          height: 0.45rem;
          border-radius: 50%;
          margin-right: 0.4rem;
          vertical-align: middle;
        }
      `}</style>
    </div>
  );
}

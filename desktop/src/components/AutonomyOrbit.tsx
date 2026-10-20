import { motion } from "framer-motion";

export type AutonomyBreath = "guided" | "semi" | "free" | "autonomous";

const LABELS: Record<AutonomyBreath, string> = {
  guided: "guiado",
  semi: "semi",
  free: "livre",
  autonomous: "autônomo",
};

const ORDER: AutonomyBreath[] = ["guided", "semi", "free", "autonomous"];

type Props = {
  value: AutonomyBreath;
  onChange: (v: AutonomyBreath) => void;
};

export function AutonomyOrbit({ value, onChange }: Props) {
  return (
    <div className="orbit" role="radiogroup" aria-label="Respiração de autonomia">
      {ORDER.map((key) => {
        const active = key === value;
        return (
          <button
            key={key}
            type="button"
            role="radio"
            aria-checked={active}
            className={`orbit__node${active ? " is-active" : ""}`}
            onClick={() => onChange(key)}
            title={
              key === "autonomous"
                ? "percorre o SO e agentes e traz propostas para você escolher"
                : LABELS[key]
            }
          >
            {active && (
              <motion.span
                layoutId="orbit-glow"
                className="orbit__glow"
                transition={{ type: "spring", stiffness: 380, damping: 28 }}
              />
            )}
            <span className="orbit__label">{LABELS[key]}</span>
          </button>
        );
      })}
      <style>{`
        .orbit {
          display: inline-flex;
          flex-wrap: wrap;
          gap: 0.35rem;
          padding: 0.3rem;
          border: 1px solid rgba(232, 194, 122, 0.18);
          background: rgba(7, 9, 12, 0.45);
          backdrop-filter: blur(12px);
          max-width: 100%;
        }
        .orbit__node {
          position: relative;
          border: 0;
          background: transparent;
          padding: 0.45rem 0.75rem;
          cursor: pointer;
          color: var(--mist-dim);
        }
        .orbit__node.is-active {
          color: var(--ink);
        }
        .orbit__glow {
          position: absolute;
          inset: 0;
          background: linear-gradient(120deg, var(--filament), #f0d7a2);
          z-index: 0;
        }
        .orbit__label {
          position: relative;
          z-index: 1;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
        }
      `}</style>
    </div>
  );
}

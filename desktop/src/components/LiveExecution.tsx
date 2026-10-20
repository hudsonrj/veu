import { motion, AnimatePresence } from "framer-motion";

export type LiveStep = {
  index: number;
  label: string;
  actor: string;
  state: "running" | "done" | "pending";
};

type Props = {
  thinking?: string;
  steps: LiveStep[];
  title?: string;
  nerves?: string[];
};

/** Construção e execução em tempo real — o SO sendo administrado na sua frente. */
export function LiveExecution({ thinking, steps, title, nerves }: Props) {
  if (!thinking && steps.length === 0 && !title) return null;

  return (
    <div className="live">
      {title && <h2 className="live__title">{title}</h2>}
      {nerves && nerves.length > 0 && (
        <p className="live__nerves">nervos · {nerves.join(" · ")}</p>
      )}
      <AnimatePresence>
        {thinking && (
          <motion.p
            key={thinking}
            className="live__think"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0.4, 1, 0.4] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.6, repeat: Infinity }}
          >
            {thinking}
          </motion.p>
        )}
      </AnimatePresence>
      <ol className="live__steps">
        {steps.map((s) => (
          <motion.li
            key={`${s.index}-${s.label}`}
            className={`live__step is-${s.state}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <span className="live__mark" />
            <span className="live__label">{s.label}</span>
            <span className="live__actor">{s.actor}</span>
          </motion.li>
        ))}
      </ol>
      <style>{`
        .live {
          width: min(720px, 100%);
          margin-top: 0.5rem;
          padding-top: 1rem;
          border-top: 1px solid rgba(232, 194, 122, 0.22);
        }
        .live__title {
          margin: 0;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: clamp(1.4rem, 3.5vw, 2rem);
          letter-spacing: -0.02em;
        }
        .live__nerves {
          margin: 0.45rem 0 0;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .live__think {
          margin: 0.9rem 0 0;
          font-family: var(--font-mono);
          font-size: 0.75rem;
          letter-spacing: 0.06em;
          color: var(--filament);
        }
        .live__steps {
          list-style: none;
          margin: 1rem 0 0;
          padding: 0;
          display: grid;
          gap: 0.55rem;
        }
        .live__step {
          display: grid;
          grid-template-columns: auto 1fr auto;
          gap: 0.7rem;
          align-items: baseline;
          font-size: 0.82rem;
        }
        .live__mark {
          width: 0.45rem;
          height: 0.45rem;
          margin-top: 0.35rem;
          border-radius: 50%;
          background: var(--mist-dim);
        }
        .live__step.is-running .live__mark {
          background: var(--filament);
          box-shadow: 0 0 10px rgba(232, 194, 122, 0.55);
        }
        .live__step.is-done .live__mark {
          background: var(--signal);
        }
        .live__label {
          color: var(--mist);
          font-weight: 300;
        }
        .live__actor {
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.08em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
      `}</style>
    </div>
  );
}

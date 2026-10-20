import { motion } from "framer-motion";
import type { AutonomyBreath } from "./AutonomyOrbit";

export type Formation = {
  id: string;
  intent: string;
  title: string;
  kind: "browser" | "files" | "system" | "mcp" | "hybrid" | "comm" | "workspace";
  breath: AutonomyBreath;
  threads: string[];
  status: string;
};

type Props = {
  formations: Formation[];
  breath: AutonomyBreath;
};

const KIND_LABEL: Record<Formation["kind"], string> = {
  browser: "navegação viva",
  files: "tecido de arquivos",
  system: "pulso do sistema",
  mcp: "nervo MCP",
  hybrid: "hibridismo",
  comm: "comunicação viva",
  workspace: "workspace vivo",
};

export function FormationStage({ formations }: Props) {
  const lead = formations[0];
  const rest = formations.slice(1);

  return (
    <div className="formations">
      <motion.article
        key={lead.id}
        className="formation formation--lead"
        initial={{ opacity: 0, y: 40, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.65, ease: [0.16, 1, 0.3, 1] }}
      >
        <p className="formation__kind">{KIND_LABEL[lead.kind]}</p>
        <h2 className="formation__title">{lead.title}</h2>
        <p className="formation__intent">“{lead.intent}”</p>
        <ul className="formation__threads">
          {lead.threads.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
        <p className="formation__status">{lead.status}</p>
      </motion.article>

      {rest.length > 0 && (
        <div className="formations__echo">
          {rest.map((f, i) => (
            <motion.div
              key={f.id}
              className="formation formation--echo"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 0.55 - i * 0.1, x: 0 }}
              transition={{ delay: 0.1 * i }}
            >
              <span>{KIND_LABEL[f.kind]}</span>
              <strong>{f.title}</strong>
            </motion.div>
          ))}
        </div>
      )}

      <style>{`
        .formations {
          width: min(880px, 100%);
          display: grid;
          gap: 1.25rem;
        }
        .formation--lead {
          padding: 1.75rem 1.5rem 1.5rem;
          border-top: 1px solid rgba(232, 194, 122, 0.35);
          background: linear-gradient(
            180deg,
            rgba(232, 194, 122, 0.06),
            rgba(7, 9, 12, 0.15)
          );
        }
        .formation__kind {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.18em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .formation__title {
          margin: 0.7rem 0 0;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: clamp(1.8rem, 4.5vw, 2.8rem);
          line-height: 1.05;
          letter-spacing: -0.02em;
        }
        .formation__intent {
          margin: 1rem 0 0;
          color: var(--mist-dim);
          font-weight: 300;
          font-size: 1.05rem;
        }
        .formation__threads {
          margin: 1.4rem 0 0;
          padding: 0;
          list-style: none;
          display: grid;
          gap: 0.55rem;
        }
        .formation__threads li {
          font-family: var(--font-mono);
          font-size: 0.78rem;
          letter-spacing: 0.04em;
          color: var(--mist);
          padding-left: 1rem;
          position: relative;
        }
        .formation__threads li::before {
          content: "";
          position: absolute;
          left: 0;
          top: 0.55em;
          width: 0.4rem;
          height: 1px;
          background: var(--filament);
        }
        .formation__status {
          margin: 1.5rem 0 0;
          font-size: 0.85rem;
          color: var(--filament);
        }
        .formations__echo {
          display: grid;
          gap: 0.5rem;
        }
        .formation--echo {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          padding: 0.65rem 0;
          border-top: 1px solid rgba(236, 242, 248, 0.08);
          font-size: 0.8rem;
        }
        .formation--echo span {
          font-family: var(--font-mono);
          color: var(--mist-dim);
          letter-spacing: 0.08em;
          text-transform: lowercase;
        }
        .formation--echo strong {
          font-weight: 500;
        }
      `}</style>
    </div>
  );
}

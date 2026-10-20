import { motion } from "framer-motion";
import type { ReactNode } from "react";

export type ChatTurn = {
  id: string;
  role: "user" | "veu" | "system";
  text: string;
};

type Props = {
  turns: ChatTurn[];
};

const LINK_RE =
  /(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g;

function linkify(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(LINK_RE)) {
    const start = m.index ?? 0;
    if (start > last) parts.push(text.slice(last, start));
    const href = m[0];
    parts.push(
      <a
        key={`${start}-${href}`}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="nchat__link"
      >
        {href}
      </a>,
    );
    last = start + href.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length ? parts : [text];
}

/** Chat nativo do SO — conversa com o administrador de IA. */
export function NativeChat({ turns }: Props) {
  if (turns.length === 0) return null;

  return (
    <div className="nchat" aria-live="polite">
      {turns.map((t) => (
        <motion.div
          key={t.id}
          className={`nchat__turn nchat__turn--${t.role}`}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <span className="nchat__who">
            {t.role === "user" ? "você" : t.role === "veu" ? "véu" : "sistema"}
          </span>
          <p className="nchat__text">{linkify(t.text)}</p>
        </motion.div>
      ))}
      <style>{`
        .nchat {
          width: min(720px, 100%);
          display: grid;
          gap: 1.1rem;
          max-height: min(42vh, 420px);
          overflow: auto;
          padding-right: 0.25rem;
        }
        .nchat__turn {
          display: grid;
          gap: 0.35rem;
        }
        .nchat__who {
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.16em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .nchat__turn--user .nchat__who {
          color: var(--filament);
        }
        .nchat__turn--system .nchat__who {
          color: var(--mist-dim);
        }
        .nchat__text {
          margin: 0;
          font-weight: 300;
          font-size: clamp(0.95rem, 2vw, 1.1rem);
          line-height: 1.55;
          color: var(--mist);
          white-space: pre-wrap;
        }
        .nchat__turn--user .nchat__text {
          color: var(--mist-dim);
        }
        .nchat__link {
          color: var(--filament);
          text-decoration: underline;
          text-underline-offset: 0.15em;
          word-break: break-all;
        }
      `}</style>
    </div>
  );
}

import { motion } from "framer-motion";
import { APP_ICONS, type AppIcon } from "../lib/ecosystem";

type Props = {
  onSelect?: (app: AppIcon) => void;
  activeId?: string;
};

/** Ícones das ferramentas e apps integrados — nervos do SO. */
export function AppRail({ onSelect, activeId }: Props) {
  return (
    <nav className="rail" aria-label="Ferramentas e aplicativos integrados">
      {APP_ICONS.map((app, i) => (
        <motion.button
          key={app.id}
          type="button"
          className={`rail__item${activeId === app.id ? " is-active" : ""}`}
          style={{ ["--hue" as string]: app.hue }}
          title={`${app.label} · ${app.status}`}
          onClick={() => onSelect?.(app)}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.03 }}
        >
          <span className="rail__glyph" aria-hidden>
            {app.glyph}
          </span>
          <span className="rail__label">{app.label}</span>
          <span className={`rail__dot is-${app.status}`} />
        </motion.button>
      ))}
      <style>{`
        .rail {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(4.6rem, 1fr));
          gap: 0.55rem;
          width: min(860px, 100%);
        }
        .rail__item {
          position: relative;
          display: grid;
          justify-items: center;
          gap: 0.35rem;
          padding: 0.7rem 0.35rem 0.55rem;
          border: 1px solid rgba(236, 242, 248, 0.08);
          background: rgba(7, 9, 12, 0.35);
          color: var(--mist);
          cursor: pointer;
          backdrop-filter: blur(8px);
          transition: border-color 0.2s ease, background 0.2s ease;
        }
        .rail__item:hover,
        .rail__item.is-active {
          border-color: color-mix(in srgb, var(--hue) 55%, transparent);
          background: color-mix(in srgb, var(--hue) 12%, rgba(7, 9, 12, 0.5));
        }
        .rail__glyph {
          width: 2rem;
          height: 2rem;
          display: grid;
          place-items: center;
          border-radius: 0.35rem;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 0.95rem;
          color: var(--ink);
          background: var(--hue);
        }
        .rail__label {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.04em;
          text-align: center;
          color: var(--mist-dim);
          line-height: 1.2;
        }
        .rail__dot {
          position: absolute;
          top: 0.35rem;
          right: 0.35rem;
          width: 0.35rem;
          height: 0.35rem;
          border-radius: 50%;
          background: rgba(236,242,248,0.25);
        }
        .rail__dot.is-ready { background: var(--signal); }
        .rail__dot.is-live { background: var(--filament); box-shadow: 0 0 8px rgba(232,194,122,0.6); }
        .rail__dot.is-planned { background: rgba(236,242,248,0.22); }
      `}</style>
    </nav>
  );
}

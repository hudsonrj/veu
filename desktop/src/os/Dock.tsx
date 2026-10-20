import type { OsWindow, WinApp } from "./types";
import { APP_TITLES, DESKTOP_ICONS } from "./catalog";

type Props = {
  windows: OsWindow[];
  onOpen: (app: WinApp) => void;
  onFocus: (id: string) => void;
  onRestore: (id: string) => void;
  compact?: boolean;
  activeApp?: WinApp;
};

/** Dock = atalho do núcleo; o resto vive nas zonas do desktop. */
const DOCK_APPS: WinApp[] = [
  "ruflo",
  "ruos",
  "mission",
  "chat",
  "browser",
  "productivity",
  "clone",
  "mental",
  "agenda",
  "hermes",
  "studio",
  "playground",
  "chatgpt",
  "claudeai",
  "grok",
  "whatsapp",
  "ecc",
  "settings",
  "host",
];

const DOCK_COMPACT: WinApp[] = [
  "ruflo",
  "ruos",
  "mission",
  "chat",
  "browser",
  "productivity",
  "clone",
  "mental",
  "inbox",
  "agenda",
  "grokbot",
  "approvals",
  "settings",
];

export function Dock({
  windows,
  onOpen,
  onFocus,
  onRestore,
  compact,
  activeApp,
}: Props) {
  const apps = compact ? DOCK_COMPACT : DOCK_APPS;
  return (
    <footer className={`dock${compact ? " dock--compact" : ""}`}>
      <div className="dock__inner">
        {apps.map((app) => {
          const meta = DESKTOP_ICONS.find((i) => i.app === app);
          const openWins = windows.filter((w) => w.app === app);
          const running = compact ? activeApp === app : openWins.length > 0;
          const minimized = !compact && openWins.every((w) => w.minimized) && openWins.length > 0;
          return (
            <button
              key={app}
              type="button"
              className={`dock__btn${running ? " is-running" : ""}`}
              style={{ ["--hue" as string]: meta?.hue || "#e8c27a" }}
              title={APP_TITLES[app]}
              onClick={() => {
                if (compact) {
                  onOpen(app);
                  return;
                }
                if (!openWins.length) onOpen(app);
                else if (minimized) onRestore(openWins[0].id);
                else onFocus(openWins[0].id);
              }}
            >
              <span>{meta?.glyph || "·"}</span>
              {running && <i className={`dock__pip${minimized ? " is-min" : ""}`} />}
            </button>
          );
        })}
      </div>
      <style>{`
        .dock {
          position: relative;
          z-index: 60;
          display: flex;
          justify-content: center;
          padding: 0.35rem 0 0.45rem;
          pointer-events: none;
          min-width: 0;
        }
        .dock__inner {
          pointer-events: auto;
          display: flex;
          gap: 0.35rem;
          padding: 0.4rem;
          max-width: 100%;
          overflow-x: auto;
          -webkit-overflow-scrolling: touch;
          scrollbar-width: none;
          background: rgba(7, 9, 12, 0.72);
          border: 1px solid rgba(232, 194, 122, 0.22);
          backdrop-filter: blur(16px);
        }
        .dock__inner::-webkit-scrollbar { display: none; }
        .dock__btn {
          position: relative;
          flex: 0 0 auto;
          width: 2.5rem;
          height: 2.5rem;
          border: 0;
          border-radius: 0.4rem;
          background: color-mix(in srgb, var(--hue) 85%, #111);
          color: #0a0c10;
          font-family: var(--font-display);
          font-weight: 700;
          cursor: pointer;
        }
        .dock--compact .dock__btn {
          width: 2.65rem;
          height: 2.65rem;
        }
        .dock__btn.is-running {
          box-shadow: 0 0 0 1px rgba(232,194,122,0.45);
        }
        .dock__pip {
          position: absolute;
          left: 50%;
          bottom: 0.15rem;
          width: 0.28rem;
          height: 0.28rem;
          border-radius: 50%;
          transform: translateX(-50%);
          background: var(--ink);
        }
        .dock__pip.is-min { opacity: 0.35; }
        @media (min-width: 744px) {
          .dock__inner { gap: 0.45rem; padding: 0.45rem; }
        }
      `}</style>
    </footer>
  );
}

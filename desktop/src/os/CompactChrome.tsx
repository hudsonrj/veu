import { DESKTOP_ICONS } from "./catalog";
import type { WinApp } from "./types";

/** Atalhos principais na superfície compacta (phone / tablet). */
const LAUNCHER: WinApp[] = [
  "ruos",
  "mission",
  "chat",
  "console",
  "browser",
  "rea",
  "esp32",
  "chatgpt",
  "claudeai",
  "grok",
  "notion",
  "servers",
  "productivity",
  "clone",
  "mental",
  "inbox",
  "agenda",
  "grokbot",
  "companies",
  "asklife",
  "control",
  "data",
  "settings",
];

type Props = {
  active: WinApp;
  onOpen: (app: WinApp) => void;
  title: string;
  showDayToggle?: boolean;
  dayOpen?: boolean;
  onToggleDay?: () => void;
};

export function CompactChrome({
  active,
  onOpen,
  title,
  showDayToggle,
  dayOpen,
  onToggleDay,
}: Props) {
  return (
    <>
      <div className="os__surface-head">
        <h1>{title}</h1>
        {showDayToggle ? (
          <button type="button" onClick={onToggleDay} aria-pressed={dayOpen}>
            {dayOpen ? "fechar dia" : "dia"}
          </button>
        ) : null}
      </div>
      <nav className="os__launcher" aria-label="Apps">
        {LAUNCHER.map((app) => {
          const meta = DESKTOP_ICONS.find((i) => i.app === app);
          return (
            <button
              key={app}
              type="button"
              className={active === app ? "is-on" : ""}
              style={{ ["--hue" as string]: meta?.hue || "#e8c27a" }}
              onClick={() => onOpen(app)}
            >
              <span aria-hidden>{meta?.glyph || "·"}</span>
              <em>{meta?.label || app}</em>
            </button>
          );
        })}
      </nav>
    </>
  );
}

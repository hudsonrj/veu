/**
 * Dock de categorias (padrão ruOS: zonas → hub → apps).
 * Quatro pastas na base; clique abre o conteúdo em anel (círculo).
 * Sem scroll aninhado no desktop.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  DESKTOP_ICONS,
  DESKTOP_WEB_LINKS,
  ICON_BY_APP,
  ICON_ZONES,
  ZONE_HUE,
  type IconZoneId,
} from "./catalog";
import type { WinApp } from "./types";

export type ShelfItem =
  | { kind: "app"; app: WinApp; label: string; hue: string; glyph: string }
  | {
      kind: "link";
      id: string;
      label: string;
      hue: string;
      glyph: string;
      url: string;
    };

export type ShelfCategory = {
  id: IconZoneId;
  label: string;
  hint: string;
  hue: string;
  glyph: string;
  items: ShelfItem[];
};

const CAT_GLYPH: Record<IconZoneId, string> = {
  espinha: "◈",
  mente: "◎",
  canais: "⇄",
  workspace: "▣",
};

function itemForApp(app: WinApp): ShelfItem {
  const meta = ICON_BY_APP[app] || DESKTOP_ICONS.find((i) => i.app === app);
  return {
    kind: "app",
    app,
    label: meta?.label || app,
    hue: meta?.hue || "#e8c27a",
    glyph: meta?.glyph || "·",
  };
}

/** Mesmas zonas da constelação DesktopIcons (ruOS). */
export const SHELF_CATEGORIES: ShelfCategory[] = ICON_ZONES.map((z) => {
  const apps = z.apps.map(itemForApp);
  const links: ShelfItem[] = DESKTOP_WEB_LINKS.filter((l) => l.zone === z.id).map(
    (l) => ({
      kind: "link",
      id: l.id,
      label: l.label,
      hue: l.hue,
      glyph: l.glyph,
      url: l.url,
    }),
  );
  return {
    id: z.id,
    label: z.label,
    hint: z.hint,
    hue: ZONE_HUE[z.id],
    glyph: CAT_GLYPH[z.id],
    items: [...apps, ...links],
  };
});

export const SHELF_ITEMS: ShelfItem[] = SHELF_CATEGORIES.flatMap((c) => c.items);

type Props = {
  onOpen: (app: WinApp) => void;
  onOpenUrl: (url: string, title?: string) => void;
};

/** Posições em anel dentro do painel (centro = hub visual). */
function ringSlots(
  n: number,
  size: number,
): { x: number; y: number; i: number }[] {
  if (n <= 0) return [];
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.34;
  if (n === 1) return [{ x: cx, y: cy, i: 0 }];
  const start = -Math.PI / 2;
  return Array.from({ length: n }, (_, i) => {
    const ang = start + (i / n) * Math.PI * 2;
    return {
      x: cx + Math.cos(ang) * r,
      y: cy + Math.sin(ang) * r,
      i,
    };
  });
}

export function AppsShelf({ onOpen, onOpenUrl }: Props) {
  const [openId, setOpenId] = useState<IconZoneId | null>(null);
  const rootRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!openId) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpenId(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenId(null);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [openId]);

  const openCat = SHELF_CATEGORIES.find((c) => c.id === openId) || null;
  const ringSize = 280;
  const slots = useMemo(
    () => ringSlots(openCat?.items.length || 0, ringSize),
    [openCat?.items.length],
  );

  return (
    <nav
      ref={rootRef}
      className={`apps-shelf${openId ? " is-open" : ""}`}
      aria-label="Categorias do Véu"
    >
      {openCat ? (
        <div
          className="apps-shelf__panel"
          style={{ ["--cat-hue" as string]: openCat.hue }}
          role="dialog"
          aria-label={`${openCat.label}: ${openCat.hint}`}
        >
          <header className="apps-shelf__panel-h">
            <span className="apps-shelf__panel-mark" aria-hidden>
              {openCat.glyph}
            </span>
            <div>
              <p className="apps-shelf__panel-label">{openCat.label}</p>
              <p className="apps-shelf__panel-hint">{openCat.hint}</p>
            </div>
            <button
              type="button"
              className="apps-shelf__close"
              aria-label="Fechar"
              onClick={() => setOpenId(null)}
            >
              ×
            </button>
          </header>
          <div
            className="apps-shelf__ring"
            style={{ width: ringSize, height: ringSize }}
          >
            <div className="apps-shelf__orbit" aria-hidden />
            <div className="apps-shelf__hub" aria-hidden>
              {openCat.glyph}
            </div>
            {openCat.items.map((item, idx) => {
              const key = item.kind === "app" ? item.app : item.id;
              const slot = slots[idx] || { x: ringSize / 2, y: ringSize / 2 };
              return (
                <button
                  key={key}
                  type="button"
                  className={`apps-shelf__app${item.kind === "link" ? " is-web" : ""}`}
                  style={{
                    ["--hue" as string]: item.hue,
                    left: slot.x,
                    top: slot.y,
                    animationDelay: `${idx * 28}ms`,
                  }}
                  title={
                    item.kind === "link"
                      ? `${item.label} · Browser do SO`
                      : item.label
                  }
                  onClick={() => {
                    if (item.kind === "app") onOpen(item.app);
                    else onOpenUrl(item.url, item.label);
                    setOpenId(null);
                  }}
                >
                  <span className="apps-shelf__glyph" aria-hidden>
                    {item.glyph}
                  </span>
                  <span className="apps-shelf__name">{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="apps-shelf__folders" role="toolbar" aria-label="Abrir categoria">
        {SHELF_CATEGORIES.map((cat) => {
          const on = openId === cat.id;
          return (
            <button
              key={cat.id}
              type="button"
              className={`apps-shelf__folder${on ? " is-on" : ""}`}
              style={{ ["--hue" as string]: cat.hue }}
              aria-expanded={on}
              title={`${cat.label} · ${cat.hint}`}
              onClick={() =>
                setOpenId((cur) => (cur === cat.id ? null : cat.id))
              }
            >
              <span className="apps-shelf__folder-glyph" aria-hidden>
                {cat.glyph}
              </span>
              <span className="apps-shelf__folder-label">{cat.label}</span>
              <span className="apps-shelf__folder-count" aria-hidden>
                {cat.items.length}
              </span>
            </button>
          );
        })}
      </div>

      <style>{`
        .apps-shelf {
          position: absolute;
          left: 50%;
          transform: translateX(-50%);
          bottom: calc(var(--veu-dock-h, 4.25rem) + 0.7rem);
          z-index: 8;
          pointer-events: none;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.55rem;
          width: min(22rem, calc(100% - 1.5rem - var(--veu-rail-w, 0px)));
        }
        .apps-shelf__folders {
          pointer-events: auto;
          display: flex;
          gap: 0.55rem;
          padding: 0.45rem 0.55rem;
          background: rgba(7, 9, 12, 0.82);
          border: 1px solid rgba(232, 194, 122, 0.24);
          backdrop-filter: blur(14px);
        }
        .apps-shelf__folder {
          appearance: none;
          cursor: pointer;
          display: grid;
          grid-template-rows: auto auto;
          grid-template-columns: auto;
          justify-items: center;
          gap: 0.22rem;
          min-width: 4.6rem;
          padding: 0.35rem 0.45rem 0.4rem;
          border: 1px solid transparent;
          background: transparent;
          color: var(--mist, #ecf2f8);
          font: inherit;
          position: relative;
        }
        .apps-shelf__folder.is-on,
        .apps-shelf__folder:hover {
          border-color: color-mix(in srgb, var(--hue) 55%, transparent);
          background: color-mix(in srgb, var(--hue) 12%, transparent);
        }
        .apps-shelf__folder-glyph {
          width: 2.7rem;
          height: 2.7rem;
          display: grid;
          place-items: center;
          border-radius: 50%;
          background: color-mix(in srgb, var(--hue) 86%, #0a0c10);
          color: #0a0c10;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 1rem;
          box-shadow: 0 6px 16px rgba(0,0,0,0.45);
        }
        .apps-shelf__folder-label {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: color-mix(in srgb, var(--hue) 80%, #ecf2f8);
        }
        .apps-shelf__folder-count {
          position: absolute;
          top: 0.2rem;
          right: 0.25rem;
          min-width: 1rem;
          height: 1rem;
          padding: 0 0.22rem;
          border-radius: 0.35rem;
          background: rgba(10, 12, 16, 0.85);
          border: 1px solid color-mix(in srgb, var(--hue) 45%, transparent);
          color: var(--hue);
          font-family: var(--font-mono);
          font-size: 0.5rem;
          line-height: 1rem;
          text-align: center;
        }
        .apps-shelf__panel {
          pointer-events: auto;
          width: 100%;
          padding: 0.65rem 0.7rem 0.85rem;
          background: rgba(7, 9, 12, 0.94);
          border: 1px solid color-mix(in srgb, var(--cat-hue) 40%, transparent);
          backdrop-filter: blur(16px);
          box-shadow: 0 18px 40px rgba(0,0,0,0.45);
          animation: apps-shelf-rise 160ms ease-out;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        @keyframes apps-shelf-rise {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .apps-shelf__panel-h {
          display: flex;
          align-items: center;
          gap: 0.55rem;
          margin-bottom: 0.35rem;
          width: 100%;
        }
        .apps-shelf__panel-mark {
          width: 1.85rem;
          height: 1.85rem;
          display: grid;
          place-items: center;
          border-radius: 50%;
          background: color-mix(in srgb, var(--cat-hue) 85%, #0a0c10);
          color: #0a0c10;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 0.85rem;
          flex: 0 0 auto;
        }
        .apps-shelf__panel-label {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.14em;
          text-transform: lowercase;
          color: var(--cat-hue);
        }
        .apps-shelf__panel-hint {
          margin: 0.1rem 0 0;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          color: #8a939c;
        }
        .apps-shelf__close {
          appearance: none;
          margin-left: auto;
          cursor: pointer;
          width: 1.6rem;
          height: 1.6rem;
          border: 1px solid rgba(232,194,122,0.25);
          background: transparent;
          color: #c8d0dc;
          font-size: 1rem;
          line-height: 1;
        }
        .apps-shelf__ring {
          position: relative;
          margin: 0.15rem auto 0.2rem;
          flex: 0 0 auto;
        }
        .apps-shelf__orbit {
          position: absolute;
          inset: 12%;
          border-radius: 50%;
          border: 1px dashed color-mix(in srgb, var(--cat-hue) 35%, transparent);
          pointer-events: none;
        }
        .apps-shelf__hub {
          position: absolute;
          left: 50%;
          top: 50%;
          width: 2.2rem;
          height: 2.2rem;
          margin: -1.1rem 0 0 -1.1rem;
          display: grid;
          place-items: center;
          border-radius: 50%;
          background: color-mix(in srgb, var(--cat-hue) 55%, #0a0c10);
          color: #0a0c10;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 0.9rem;
          opacity: 0.55;
          pointer-events: none;
        }
        .apps-shelf__app {
          appearance: none;
          cursor: pointer;
          position: absolute;
          width: 4.2rem;
          margin-left: -2.1rem;
          margin-top: -1.6rem;
          display: grid;
          justify-items: center;
          gap: 0.22rem;
          padding: 0.2rem;
          border: 0;
          background: transparent;
          color: var(--mist, #ecf2f8);
          font: inherit;
          animation: apps-shelf-pop 220ms ease-out both;
        }
        @keyframes apps-shelf-pop {
          from { opacity: 0; transform: scale(0.7); }
          to { opacity: 1; transform: scale(1); }
        }
        .apps-shelf__glyph {
          width: 2.45rem;
          height: 2.45rem;
          display: grid;
          place-items: center;
          border-radius: 50%;
          background: color-mix(in srgb, var(--hue) 88%, #0a0c10);
          color: #0a0c10;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 0.8rem;
          box-shadow: 0 5px 14px rgba(0,0,0,0.4);
        }
        .apps-shelf__app.is-web .apps-shelf__glyph {
          outline: 1px dashed rgba(155, 183, 255, 0.55);
          outline-offset: 1px;
        }
        .apps-shelf__app:hover .apps-shelf__glyph {
          box-shadow:
            0 0 0 1px color-mix(in srgb, var(--hue) 70%, #fff),
            0 0 16px color-mix(in srgb, var(--hue) 40%, transparent);
        }
        .apps-shelf__name {
          font-family: var(--font-mono);
          font-size: 0.52rem;
          text-align: center;
          line-height: 1.15;
          max-width: 4.2rem;
          text-shadow: 0 1px 8px rgba(0,0,0,0.9);
        }
        @media (max-width: 767px) {
          .apps-shelf { display: none; }
        }
      `}</style>
    </nav>
  );
}

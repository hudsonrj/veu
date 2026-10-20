import { useRef, type ReactNode, type PointerEvent as ReactPointerEvent } from "react";
import type { OsWindow } from "./types";

type Props = {
  win: OsWindow;
  children: ReactNode;
  onFocus: (id: string) => void;
  onClose: (id: string) => void;
  onMinimize: (id: string) => void;
  onMove: (id: string, x: number, y: number) => void;
  onResize: (id: string, geom: { x: number; y: number; w: number; h: number }) => void;
};

type ResizeDir = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const MIN_W = 320;
const MIN_H = 220;

export function WindowFrame({
  win,
  children,
  onFocus,
  onClose,
  onMinimize,
  onMove,
  onResize,
}: Props) {
  const drag = useRef<{ ox: number; oy: number; sx: number; sy: number } | null>(null);
  const resize = useRef<{
    dir: ResizeDir;
    ox: number;
    oy: number;
    x: number;
    y: number;
    w: number;
    h: number;
  } | null>(null);

  if (win.minimized) return null;

  const onWindowPointerDown = () => {
    onFocus(win.id);
  };

  const onDragPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    onFocus(win.id);
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { ox: e.clientX, oy: e.clientY, sx: win.x, sy: win.y };
  };

  const onDragPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.ox;
    const dy = e.clientY - drag.current.oy;
    onMove(win.id, Math.max(0, drag.current.sx + dx), Math.max(0, drag.current.sy + dy));
  };

  const onDragPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drag.current) {
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {
        /* already released */
      }
    }
    drag.current = null;
  };

  const onResizePointerDown = (dir: ResizeDir) => (e: ReactPointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    e.preventDefault();
    onFocus(win.id);
    e.currentTarget.setPointerCapture(e.pointerId);
    resize.current = {
      dir,
      ox: e.clientX,
      oy: e.clientY,
      x: win.x,
      y: win.y,
      w: win.w,
      h: win.h,
    };
  };

  const onResizePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const r = resize.current;
    if (!r) return;
    const dx = e.clientX - r.ox;
    const dy = e.clientY - r.oy;
    let { x, y, w, h } = r;
    const maxW = typeof window !== "undefined" ? Math.max(MIN_W, window.innerWidth - 8) : 2400;
    const maxH = typeof window !== "undefined" ? Math.max(MIN_H, window.innerHeight - 48) : 1600;

    if (r.dir.includes("e")) w = Math.min(maxW, Math.max(MIN_W, r.w + dx));
    if (r.dir.includes("s")) h = Math.min(maxH, Math.max(MIN_H, r.h + dy));
    if (r.dir.includes("w")) {
      const nextW = Math.min(maxW, Math.max(MIN_W, r.w - dx));
      x = r.x + (r.w - nextW);
      w = nextW;
      if (x < 0) {
        w += x;
        x = 0;
      }
    }
    if (r.dir.includes("n")) {
      const nextH = Math.min(maxH, Math.max(MIN_H, r.h - dy));
      y = r.y + (r.h - nextH);
      h = nextH;
      if (y < 0) {
        h += y;
        y = 0;
      }
    }
    onResize(win.id, { x, y, w, h });
  };

  const onResizePointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (resize.current) {
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {
        /* already released */
      }
    }
    resize.current = null;
  };

  const stop = (e: ReactPointerEvent | React.MouseEvent) => {
    e.stopPropagation();
  };

  const edge = (dir: ResizeDir) => (
    <div
      key={dir}
      className={`win__resize win__resize--${dir}`}
      onPointerDown={onResizePointerDown(dir)}
      onPointerMove={onResizePointerMove}
      onPointerUp={onResizePointerUp}
      onPointerCancel={onResizePointerUp}
      aria-hidden
    />
  );

  return (
    <div
      className="win"
      style={{
        left: win.x,
        top: win.y,
        width: win.w,
        height: win.h,
        zIndex: win.z,
      }}
      onPointerDown={onWindowPointerDown}
    >
      <div className="win__bar">
        <div
          className="win__drag"
          onPointerDown={onDragPointerDown}
          onPointerMove={onDragPointerMove}
          onPointerUp={onDragPointerUp}
          onPointerCancel={onDragPointerUp}
        >
          <span className="win__title">{win.title}</span>
        </div>
        <div className="win__actions" onPointerDown={stop}>
          <button
            type="button"
            aria-label="Minimizar"
            onPointerDown={stop}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onMinimize(win.id);
            }}
          >
            –
          </button>
          <button
            type="button"
            aria-label="Fechar"
            onPointerDown={stop}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onClose(win.id);
            }}
          >
            ×
          </button>
        </div>
      </div>
      <div className="win__body">{children}</div>
      {(["n", "s", "e", "w", "ne", "nw", "se", "sw"] as ResizeDir[]).map(edge)}
      <style>{`
        .win {
          position: absolute;
          display: grid;
          grid-template-rows: auto 1fr;
          background: rgba(8, 12, 18, 0.94);
          border: 1px solid rgba(121, 223, 255, 0.22);
          box-shadow:
            0 24px 80px rgba(0,0,0,0.55),
            0 0 0 1px rgba(8, 8, 12, 0.8);
          backdrop-filter: blur(18px);
          overflow: hidden;
          min-width: ${MIN_W}px;
          min-height: ${MIN_H}px;
          border-radius: 0.35rem;
        }
        .win__bar {
          display: flex;
          align-items: stretch;
          justify-content: space-between;
          gap: 0.5rem;
          background: linear-gradient(180deg, rgba(121,223,255,0.1), transparent);
          border-bottom: 1px solid rgba(121, 223, 255, 0.12);
          user-select: none;
        }
        .win__drag {
          flex: 1;
          display: flex;
          align-items: center;
          padding: 0.45rem 0.35rem 0.45rem 0.85rem;
          cursor: grab;
          min-width: 0;
        }
        .win__drag:active { cursor: grabbing; }
        .win__title {
          font-family: var(--font-mono);
          font-size: 0.72rem;
          letter-spacing: 0.08em;
          text-transform: lowercase;
          color: var(--mist);
          pointer-events: none;
        }
        .win__actions {
          display: flex;
          align-items: center;
          gap: 0.25rem;
          padding: 0.35rem 0.45rem;
          flex-shrink: 0;
        }
        .win__actions button {
          width: 1.75rem;
          height: 1.55rem;
          border: 1px solid rgba(236,242,248,0.16);
          background: rgba(0,0,0,0.25);
          color: var(--mist);
          cursor: pointer;
          font-size: 1rem;
          line-height: 1;
          z-index: 2;
        }
        .win__actions button:hover {
          color: var(--ink);
          background: var(--filament);
          border-color: var(--filament);
        }
        .win__body {
          min-height: 0;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }
        .win__body > * {
          flex: 1;
          min-height: 0;
        }
        .win__resize {
          position: absolute;
          z-index: 5;
          touch-action: none;
        }
        .win__resize--n { top: 0; left: 8px; right: 8px; height: 6px; cursor: ns-resize; }
        .win__resize--s { bottom: 0; left: 8px; right: 8px; height: 6px; cursor: ns-resize; }
        .win__resize--e { right: 0; top: 8px; bottom: 8px; width: 6px; cursor: ew-resize; }
        .win__resize--w { left: 0; top: 8px; bottom: 8px; width: 6px; cursor: ew-resize; }
        .win__resize--ne { top: 0; right: 0; width: 12px; height: 12px; cursor: nesw-resize; }
        .win__resize--nw { top: 0; left: 0; width: 12px; height: 12px; cursor: nwse-resize; }
        .win__resize--se { bottom: 0; right: 0; width: 14px; height: 14px; cursor: nwse-resize; }
        .win__resize--sw { bottom: 0; left: 0; width: 12px; height: 12px; cursor: nesw-resize; }
        .win__resize--se::after {
          content: "";
          position: absolute;
          right: 3px;
          bottom: 3px;
          width: 8px;
          height: 8px;
          border-right: 1.5px solid rgba(232,194,122,0.45);
          border-bottom: 1.5px solid rgba(232,194,122,0.45);
          pointer-events: none;
        }
      `}</style>
    </div>
  );
}

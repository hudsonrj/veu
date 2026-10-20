import { useEffect, useMemo, useState } from "react";
import { APP_TITLES, DESKTOP_ICONS } from "./catalog";
import type { WinApp } from "./types";
import { apiFetch, KERNEL } from "../lib/kernel";

type Props = {
  open: boolean;
  onClose: () => void;
  onOpenApp: (app: WinApp) => void;
  onIntent: (intent: string) => void;
};

type Row =
  | { kind: "app"; app: WinApp; label: string }
  | { kind: "action"; id: string; label: string; run: () => void };

export function CommandBar({ open, onClose, onOpenApp, onIntent }: Props) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setIdx(0);
  }, [open]);

  const rows = useMemo<Row[]>(() => {
    const query = q.trim().toLowerCase();
    const apps: Row[] = DESKTOP_ICONS.filter((i) => {
      if (!query) return true;
      return (
        i.label.toLowerCase().includes(query) ||
        i.app.includes(query) ||
        (APP_TITLES[i.app] || "").toLowerCase().includes(query)
      );
    }).map((i) => ({ kind: "app", app: i.app, label: `abrir ${i.label}` }));

    const actions: Row[] = [];
    if (query.length > 2) {
      actions.push({
        kind: "action",
        id: "intent",
        label: `pedir ao Véu: “${q.trim()}”`,
        run: () => {
          onIntent(q.trim());
          onClose();
        },
      });
      actions.push({
        kind: "action",
        id: "job",
        label: `enfileirar job: “${q.trim()}”`,
        run: () => {
          void apiFetch(`${KERNEL}/jobs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ intent: q.trim(), breath: "guided" }),
          });
          onClose();
        },
      });
      actions.push({
        kind: "action",
        id: "life",
        label: `pergunte à minha vida: “${q.trim()}”`,
        run: () => {
          onOpenApp("asklife");
          onIntent(`life:${q.trim()}`);
          onClose();
        },
      });
    }
    return [...actions, ...apps].slice(0, 14);
  }, [q, onClose, onIntent, onOpenApp]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setIdx((i) => Math.min(i + 1, Math.max(0, rows.length - 1)));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setIdx((i) => Math.max(0, i - 1));
      }
      if (e.key === "Enter" && rows[idx]) {
        e.preventDefault();
        const row = rows[idx];
        if (row.kind === "app") {
          onOpenApp(row.app);
          onClose();
        } else row.run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, rows, idx, onClose, onOpenApp]);

  if (!open) return null;

  return (
    <div className="cmdk" role="dialog" aria-label="barra de comando">
      <div className="cmdk__panel">
        <input
          autoFocus
          className="cmdk__input"
          placeholder="Abrir app, pedir ao Véu, enfileirar job…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setIdx(0);
          }}
        />
        <ul className="cmdk__list">
          {rows.map((row, i) => (
            <li key={row.kind === "app" ? row.app : row.id}>
              <button
                type="button"
                className={i === idx ? "is-active" : ""}
                onMouseEnter={() => setIdx(i)}
                onClick={() => {
                  if (row.kind === "app") {
                    onOpenApp(row.app);
                    onClose();
                  } else row.run();
                }}
              >
                {row.label}
              </button>
            </li>
          ))}
          {!rows.length ? <li className="cmdk__empty">nada encontrado</li> : null}
        </ul>
        <p className="cmdk__hint">↑↓ navegar · Enter abrir · Esc fechar · ⌘K</p>
      </div>
      <button type="button" className="cmdk__backdrop" aria-label="fechar" onClick={onClose} />
      <style>{`
        .cmdk {
          position: fixed; inset: 0; z-index: 80;
          display: grid; place-items: start center;
          padding: max(0.75rem, env(safe-area-inset-top)) 0.75rem 0;
          padding-top: max(8vh, env(safe-area-inset-top));
        }
        .cmdk__backdrop { position: absolute; inset: 0; border: 0; background: rgba(5,8,12,0.55); }
        .cmdk__panel {
          position: relative; z-index: 1;
          width: min(36rem, 100%);
          max-height: min(78dvh, 36rem);
          display: flex; flex-direction: column;
          background: rgba(12,16,22,0.94);
          border: 1px solid rgba(232,238,244,0.16);
          backdrop-filter: blur(14px);
        }
        .cmdk__input {
          width: 100%; box-sizing: border-box;
          padding: 0.95rem 1rem;
          border: 0; border-bottom: 1px solid rgba(232,238,244,0.12);
          background: transparent; color: #e8eef4;
          font: 500 1.02rem Syne, sans-serif; outline: none;
          font-size: max(16px, 1.02rem); /* evita zoom iOS */
        }
        .cmdk__list { list-style: none; margin: 0; padding: 0.35rem; overflow: auto; flex: 1; -webkit-overflow-scrolling: touch; }
        .cmdk__list button {
          width: 100%; text-align: left; border: 0; background: transparent;
          color: #dce6f0; padding: 0.75rem 0.75rem; min-height: 2.75rem;
          font: 400 0.92rem "IBM Plex Sans", sans-serif; cursor: pointer;
        }
        .cmdk__list button.is-active, .cmdk__list button:hover { background: rgba(232,194,122,0.12); }
        .cmdk__empty { padding: 0.85rem; color: rgba(232,238,244,0.45); }
        .cmdk__hint { margin: 0; padding: 0.55rem 0.9rem 0.75rem; color: rgba(232,238,244,0.4); font-size: 0.72rem; letter-spacing: 0.04em; }
        @media (min-width: 744px) {
          .cmdk { padding-top: 12vh; }
          .cmdk__panel { width: min(36rem, 92vw); }
        }
      `}</style>
    </div>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { apiFetch, KERNEL } from "../lib/kernel";
import {
  AGENT_FEEDS,
  DESKTOP_ICONS,
  DESKTOP_SURFACE,
  DESKTOP_WEB_LINKS,
  ICON_ZONES,
  ZONE_HUB,
  ZONE_HUE,
  type AgentFeed,
  type DesktopWebLink,
  type IconZoneId,
} from "./catalog";
import type { DesktopIcon, WinApp } from "./types";

/** connector id → app do desktop */
const NERVE_APP: Record<string, WinApp> = {
  teams: "teams",
  outlook: "outlook",
  gmail: "gmail",
  slack: "slack",
  "google-chat": "gchat",
  whatsapp: "whatsapp",
  google: "google",
};

type Props = {
  onOpen: (app: WinApp) => void;
  /** Abre URL como aba no Browser do SO (apps compatíveis ruOS). */
  onOpenUrl?: (url: string, title?: string) => void;
  /**
   * Só desenha zonas + arcos (fundo). Ícones clicáveis ficam nas pastas
   * do AppsShelf — evita nós “fora” das caixas véu/mente/canais/workspace.
   */
  chromeOnly?: boolean;
};

type Pos = { x: number; y: number };

type ZoneLayout = {
  id: IconZoneId;
  x0: number;
  y0: number;
  w: number;
  h: number;
};

const ICON = 56;
const GAP_X = 96;

function neighborsOf(app: WinApp): Set<WinApp> {
  const out = new Set<WinApp>();
  for (const f of AGENT_FEEDS) {
    if (f.from === app) out.add(f.to);
    if (f.to === app) out.add(f.from);
  }
  return out;
}

/**
 * Layout tipo ruOS: uma faixa clara no topo (a linha) + 3 colunas embaixo.
 *   [======== Véu → Missão → Chat → Console ========]
 *   [ canais ]     [ mente ]     [ workspace ]
 */
function zoneBoxes(w: number, h: number): ZoneLayout[] {
  const padX = 28;
  const padY = 44;
  const gap = 20;
  const usableW = Math.max(420, w - padX * 2);
  const usableH = Math.max(320, h - padY * 2 - 16);
  // espinha: altura p/ glyph+label; corpo ganha o resto pro anel
  const spineH = Math.min(118, Math.max(104, usableH * 0.24));
  const bodyY = padY + spineH + gap;
  const bodyH = usableH - spineH - gap;
  const colW = (usableW - gap * 2) / 3;
  return [
    { id: "espinha", x0: padX, y0: padY, w: usableW, h: spineH },
    { id: "canais", x0: padX, y0: bodyY, w: colW, h: bodyH },
    {
      id: "mente",
      x0: padX + colW + gap,
      y0: bodyY,
      w: colW,
      h: bodyH,
    },
    {
      id: "workspace",
      x0: padX + (colW + gap) * 2,
      y0: bodyY,
      w: colW,
      h: bodyH,
    },
  ];
}

/**
 * Espinha = fila horizontal (a linha Véu→…→Console).
 * canais / mente / workspace = hub no centro + satélites em anel
 * (raios clampados para o glyph+label caberem dentro da caixa).
 */
function placeZone(
  zone: ZoneLayout,
  apps: WinApp[],
  hub: WinApp,
  links: DesktopWebLink[],
): Record<string, Pos> {
  const out: Record<string, Pos> = {};
  if (apps.length === 0 && links.length === 0) return out;

  if (zone.id === "espinha") {
    const n = apps.length;
    if (n === 0) return out;
    const pad = ICON / 2 + 12;
    const span = Math.min(
      zone.w - pad * 2,
      (n - 1) * Math.max(72, Math.min(GAP_X, zone.w / Math.max(n, 1))),
    );
    const startX = zone.x0 + (zone.w - span) / 2;
    // centro vertical deixando espaço pro label abaixo do glyph
    const y = zone.y0 + Math.min(zone.h * 0.48, zone.h - 42);
    apps.forEach((app, i) => {
      const t = n === 1 ? 0.5 : i / (n - 1);
      out[app] = { x: startX + t * span, y };
    });
    return out;
  }

  const cx = zone.x0 + zone.w / 2;
  const cy = zone.y0 + zone.h * 0.54;
  out[hub] = { x: cx, y: cy };

  const sats = [
    ...apps.filter((a) => a !== hub).map((a) => a as string),
    ...links.map((l) => l.id),
  ];
  const n = sats.length;
  if (n === 0) return out;

  // margem: meia-ícone + label embaixo + respiro do rótulo da zona
  const half = ICON / 2;
  const labelBelow = 30;
  const zoneTitle = 22;
  const maxRx = Math.max(24, zone.w / 2 - half - 10);
  const maxRyUp = Math.max(24, cy - (zone.y0 + zoneTitle) - half);
  const maxRyDown = Math.max(24, zone.y0 + zone.h - cy - half - labelBelow);
  const rx = Math.min(maxRx, zone.w * 0.3);
  const ry = Math.min(maxRyUp, maxRyDown, zone.h * 0.28);

  const start = -Math.PI / 2;
  sats.forEach((key, i) => {
    const ang = start + (i / n) * Math.PI * 2;
    out[key] = {
      x: cx + Math.cos(ang) * rx,
      y: cy + Math.sin(ang) * ry,
    };
  });
  return out;
}

function buildLayout(w: number, h: number): Record<string, Pos> {
  const zones = zoneBoxes(w, h);
  const out: Record<string, Pos> = {};
  for (const z of zones) {
    const def = ICON_ZONES.find((x) => x.id === z.id);
    if (!def) continue;
    const links = DESKTOP_WEB_LINKS.filter((l) => l.zone === z.id);
    Object.assign(out, placeZone(z, def.apps, ZONE_HUB[z.id], links));
  }
  return out;
}

function feedStroke(kind: AgentFeed["kind"]): string {
  if (kind === "feed") return "rgba(127, 231, 212, 0.32)";
  if (kind === "talk") return "rgba(232, 194, 122, 0.38)";
  return "rgba(155, 183, 255, 0.3)";
}

/** Constelação — linha Véu→Missão→Chat→Console + apps/links compatíveis. */
export function DesktopIcons({ onOpen, onOpenUrl, chromeOnly = false }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 960, h: 640 });
  const [statusMap, setStatusMap] = useState<
    Partial<Record<WinApp, DesktopIcon["status"]>>
  >({});
  const [hover, setHover] = useState<WinApp | null>(null);
  const [pulse, setPulse] = useState(0);
  const [focusGroup, setFocusGroup] = useState<IconZoneId | null>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (!r) return;
      setSize({ w: Math.max(320, r.width), h: Math.max(280, r.height) });
    });
    ro.observe(el);
    setSize({
      w: Math.max(320, el.clientWidth),
      h: Math.max(280, el.clientHeight),
    });
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setPulse((p) => p + 1), 48);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const sync = async () => {
      try {
        const r = await apiFetch(`${KERNEL}/connectors`);
        const j = await r.json();
        const next: Partial<Record<WinApp, DesktopIcon["status"]>> = {};
        for (const c of j.connectors || []) {
          const app = NERVE_APP[c.id as string];
          if (!app) continue;
          const st = c.status as DesktopIcon["status"];
          if (st === "live" || st === "ready" || st === "planned") next[app] = st;
        }
        setStatusMap(next);
      } catch {
        /* offline */
      }
    };
    void sync();
    const id = window.setInterval(sync, 30_000);
    return () => window.clearInterval(id);
  }, []);

  const layout = useMemo(
    () => buildLayout(size.w, size.h),
    [size.w, size.h],
  );

  const zones = useMemo(() => zoneBoxes(size.w, size.h), [size.w, size.h]);

  const appZone = useMemo(() => {
    const m = new Map<WinApp, IconZoneId>();
    for (const z of ICON_ZONES) {
      for (const a of z.apps) m.set(a, z.id);
    }
    return m;
  }, []);

  const surfaceSet = useMemo(() => new Set(DESKTOP_SURFACE), []);

  const icons = useMemo(
    () =>
      DESKTOP_ICONS.filter((icon) => surfaceSet.has(icon.app)).map((icon) => ({
        ...icon,
        status: statusMap[icon.app] || icon.status,
        pos: layout[icon.app] || { x: 40, y: 40 },
        zone: appZone.get(icon.app) || ("espinha" as IconZoneId),
      })),
    [layout, statusMap, appZone, surfaceSet],
  );

  const linkIcons = useMemo(
    () =>
      DESKTOP_WEB_LINKS.map((link) => ({
        ...link,
        pos: layout[link.id] || { x: 40, y: 40 },
      })),
    [layout],
  );

  const byApp = useMemo(
    () => Object.fromEntries(icons.map((i) => [i.app, i])),
    [icons],
  );

  const hot = useMemo(() => {
    if (!hover) return new Set<WinApp>();
    const s = neighborsOf(hover);
    s.add(hover);
    return s;
  }, [hover]);

  const open = useCallback(
    (app: WinApp) => {
      onOpen(app);
    },
    [onOpen],
  );

  const openLink = useCallback(
    (link: DesktopWebLink) => {
      onOpenUrl?.(link.url, link.label);
    },
    [onOpenUrl],
  );

  const dimmed = (app: WinApp) => {
    if (hover && !hot.has(app)) return true;
    if (focusGroup && appZone.get(app) !== focusGroup) return true;
    return false;
  };

  return (
    <div
      className={`desk-net${chromeOnly ? " desk-net--chrome" : ""}`}
      ref={rootRef}
      role="navigation"
      aria-label="Linha Véu — SO, mente, canais, workspace"
      aria-hidden={chromeOnly || undefined}
    >
      {!chromeOnly ? (
        <div className="desk-net__legend" aria-hidden>
          <span className="desk-net__line">
            Véu → Missão → Chat → Console · apps web no SO
          </span>
          <button
            type="button"
            className={!focusGroup ? "is-on" : ""}
            onClick={() => setFocusGroup(null)}
          >
            todos
          </button>
          {ICON_ZONES.map((z) => (
            <button
              key={z.id}
              type="button"
              className={focusGroup === z.id ? "is-on" : ""}
              style={{ ["--zhue" as string]: ZONE_HUE[z.id] }}
              onClick={() =>
                setFocusGroup((cur) => (cur === z.id ? null : z.id))
              }
            >
              {z.label}
            </button>
          ))}
        </div>
      ) : null}

      <svg
        className="desk-net__svg"
        width={size.w}
        height={size.h}
        aria-hidden
      >
        <defs>
          {ICON_ZONES.map((z) => (
            <linearGradient
              key={z.id}
              id={`zg-${z.id}`}
              x1="0%"
              y1="0%"
              x2="100%"
              y2="100%"
            >
              <stop
                offset="0%"
                stopColor={ZONE_HUE[z.id]}
                stopOpacity="0.1"
              />
              <stop offset="100%" stopColor="transparent" stopOpacity="0" />
            </linearGradient>
          ))}
          <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {zones.map((z) => {
          const faded =
            focusGroup != null && focusGroup !== z.id ? 0.18 : 1;
          const label = ICON_ZONES.find((x) => x.id === z.id)?.label;
          const cx = z.x0 + z.w / 2;
          const cy = z.y0 + z.h * 0.54;
          const half = ICON / 2;
          const maxRx = Math.max(24, z.w / 2 - half - 10);
          const maxRyUp = Math.max(24, cy - (z.y0 + 22) - half);
          const maxRyDown = Math.max(
            24,
            z.y0 + z.h - cy - half - 30,
          );
          const rx = Math.min(maxRx, z.w * 0.3);
          const ry = Math.min(maxRyUp, maxRyDown, z.h * 0.28);
          return (
            <g key={z.id} opacity={faded}>
              <rect
                x={z.x0}
                y={z.y0}
                width={z.w}
                height={z.h}
                rx={14}
                fill={`url(#zg-${z.id})`}
                stroke={ZONE_HUE[z.id]}
                strokeOpacity={0.14}
                strokeWidth={1}
              />
              {z.id !== "espinha" ? (
                <ellipse
                  cx={cx}
                  cy={cy}
                  rx={rx}
                  ry={ry}
                  fill="none"
                  stroke={ZONE_HUE[z.id]}
                  strokeOpacity={0.14}
                  strokeWidth={1}
                  strokeDasharray="3 5"
                />
              ) : null}
              <text
                x={z.x0 + 14}
                y={z.y0 + 18}
                className="desk-net__zone-label"
                fill={ZONE_HUE[z.id]}
              >
                {label}
              </text>
            </g>
          );
        })}

        {(() => {
          const spine = ["ruos", "mission", "chat", "console"] as WinApp[];
          const pts = spine.map((a) => byApp[a]?.pos).filter(Boolean) as Pos[];
          if (pts.length < 2) return null;
          const d = pts
            .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
            .join(" ");
          return (
            <path
              d={d}
              fill="none"
              stroke="rgba(232, 194, 122, 0.22)"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          );
        })()}

        {AGENT_FEEDS.map((link, i) => {
          const a = byApp[link.from];
          const b = byApp[link.to];
          if (!a || !b) return null;
          const active =
            !hover || hot.has(link.from) || hot.has(link.to);
          const groupOk =
            !focusGroup ||
            appZone.get(link.from) === focusGroup ||
            appZone.get(link.to) === focusGroup;
          if (!groupOk) return null;

          const spinePair =
            (link.from === "ruos" && link.to === "mission") ||
            (link.from === "mission" && link.to === "chat") ||
            (link.from === "chat" && link.to === "console");
          if (spinePair && !hover) return null;

          const x1 = a.pos.x;
          const y1 = a.pos.y;
          const x2 = b.pos.x;
          const y2 = b.pos.y;
          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;
          const dx = x2 - x1;
          const dy = y2 - y1;
          const len = Math.hypot(dx, dy) || 1;
          const bend = (i % 2 === 0 ? 1 : -1) * Math.min(18, len * 0.08);
          const cx = mx - (dy / len) * bend;
          const cy = my + (dx / len) * bend;
          const t = (pulse * 0.028 + i * 0.13) % 1;
          const omt = 1 - t;
          const px = omt * omt * x1 + 2 * omt * t * cx + t * t * x2;
          const py = omt * omt * y1 + 2 * omt * t * cy + t * t * y2;

          return (
            <g
              key={`${link.from}-${link.to}-${link.kind}`}
              opacity={active ? 1 : 0.1}
            >
              <path
                d={`M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`}
                fill="none"
                stroke={feedStroke(link.kind)}
                strokeWidth={active && hover ? 1.5 : 1}
                strokeLinecap="round"
              />
              {active ? (
                <circle
                  cx={px}
                  cy={py}
                  r={2.2}
                  fill={
                    link.kind === "feed"
                      ? "#7fe7d4"
                      : link.kind === "talk"
                        ? "#e8c27a"
                        : "#9bb7ff"
                  }
                  filter="url(#softGlow)"
                  opacity={0.9}
                />
              ) : null}
            </g>
          );
        })}
      </svg>

      {!chromeOnly
        ? icons.map((icon, idx) => {
            const isHub = ZONE_HUB[icon.zone] === icon.app;
            const lit = !dimmed(icon.app);
            const linked =
              hover != null && hot.has(icon.app) && icon.app !== hover;
            const onSpine =
              icon.app === "ruos" ||
              icon.app === "mission" ||
              icon.app === "chat" ||
              icon.app === "console";
            return (
              <motion.button
                key={icon.app}
                type="button"
                className={`desk-net__node is-${icon.status || "planned"}${
                  isHub || onSpine ? " is-hub" : ""
                }${hover === icon.app ? " is-hover" : ""}${
                  linked ? " is-linked" : ""
                }${lit ? "" : " is-dim"}`}
                style={{
                  ["--hue" as string]: icon.hue,
                  left: icon.pos.x,
                  top: icon.pos.y,
                }}
                initial={{ opacity: 0, scale: 0.7 }}
                animate={{
                  opacity: lit ? 1 : 0.22,
                  scale: hover === icon.app ? 1.1 : linked ? 1.04 : 1,
                }}
                transition={{
                  delay: Math.min(0.35, idx * 0.025),
                  type: "spring",
                  stiffness: 380,
                  damping: 28,
                }}
                onMouseEnter={() => setHover(icon.app)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(icon.app)}
                onBlur={() => setHover(null)}
                onClick={() => open(icon.app)}
                title={`${icon.label} · ${ICON_ZONES.find((z) => z.id === icon.zone)?.hint || ""}`}
              >
                <span className="desk-net__glyph" aria-hidden>
                  {icon.glyph}
                </span>
                <span className="desk-net__label">{icon.label}</span>
                <span
                  className={`desk-net__pip is-${icon.status || "planned"}`}
                />
              </motion.button>
            );
          })
        : null}

      {!chromeOnly
        ? linkIcons.map((link, idx) => {
            const zoneDim =
              focusGroup != null && focusGroup !== link.zone ? true : false;
            return (
              <motion.button
                key={link.id}
                type="button"
                className={`desk-net__node desk-net__node--web is-${link.status || "live"}${
                  zoneDim ? " is-dim" : ""
                }`}
                style={{
                  ["--hue" as string]: link.hue,
                  left: link.pos.x,
                  top: link.pos.y,
                }}
                initial={{ opacity: 0, scale: 0.7 }}
                animate={{
                  opacity: zoneDim ? 0.22 : 1,
                  scale: 1,
                }}
                transition={{
                  delay: Math.min(0.4, 0.2 + idx * 0.03),
                  type: "spring",
                  stiffness: 380,
                  damping: 28,
                }}
                onClick={() => openLink(link)}
                title={`${link.label} · abre aba no Browser do Véu`}
              >
                <span className="desk-net__glyph" aria-hidden>
                  {link.glyph}
                </span>
                <span className="desk-net__label">{link.label}</span>
                <span className="desk-net__pip is-live" />
              </motion.button>
            );
          })
        : null}

      {!chromeOnly ? (
        <div className="desk-net__hint" aria-hidden>
          links web abrem no Browser · ⌘K busca tudo
        </div>
      ) : null}

      <style>{`
        .desk-net {
          position: absolute;
          top: 0.35rem;
          left: 0.35rem;
          /* não entrar por baixo do DayRail (direita) */
          right: calc(var(--veu-rail-w, 0px) + 0.75rem);
          bottom: 4.5rem;
          z-index: 5;
          pointer-events: none;
          overflow: hidden;
        }
        .desk-net--chrome {
          opacity: 0.45;
        }
        .desk-net__svg {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
        }
        .desk-net__zone-label {
          font-family: var(--font-mono);
          font-size: 10px;
          letter-spacing: 0.2em;
          text-transform: lowercase;
          opacity: 0.8;
        }
        .desk-net__legend {
          pointer-events: auto;
          position: absolute;
          top: 0.15rem;
          left: 0.2rem;
          right: 0.2rem;
          z-index: 8;
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.35rem;
        }
        .desk-net__line {
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.06em;
          color: #e8c27a;
          margin-right: 0.4rem;
          text-shadow: 0 1px 8px rgba(0,0,0,0.8);
        }
        .desk-net__legend button {
          pointer-events: auto;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          padding: 0.28rem 0.55rem !important;
          border-radius: 999px;
          border: 1px solid rgba(232, 194, 122, 0.22) !important;
          background: rgba(7, 9, 12, 0.55) !important;
          color: var(--mist-dim) !important;
          cursor: pointer;
        }
        .desk-net__legend button.is-on {
          color: #0a0c10 !important;
          background: color-mix(in srgb, var(--zhue, #e8c27a) 82%, #fff) !important;
          border-color: transparent !important;
        }
        .desk-net__node {
          pointer-events: auto;
          position: absolute;
          width: ${ICON}px;
          margin-left: -${ICON / 2}px;
          margin-top: -${ICON / 2}px;
          display: grid;
          justify-items: center;
          gap: 0.28rem;
          padding: 0.2rem !important;
          border: 0 !important;
          background: transparent !important;
          color: var(--mist) !important;
          cursor: pointer;
          border-radius: 0.45rem;
          z-index: 2;
          transform-origin: center center;
        }
        .desk-net__node.is-hub { z-index: 4; }
        .desk-net__node.is-hover,
        .desk-net__node.is-linked { z-index: 6; }
        .desk-net__node--web .desk-net__glyph {
          outline: 1px dashed rgba(155, 183, 255, 0.45);
          outline-offset: 1px;
        }
        .desk-net__glyph {
          width: 2.5rem;
          height: 2.5rem;
          display: grid;
          place-items: center;
          border-radius: 0.5rem;
          background: color-mix(in srgb, var(--hue) 88%, #0a0c10);
          color: #0a0c10;
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 0.95rem;
          box-shadow: 0 8px 22px rgba(0, 0, 0, 0.45);
          transition: box-shadow 180ms ease, transform 180ms ease;
        }
        .desk-net__node.is-hub .desk-net__glyph {
          width: 2.85rem;
          height: 2.85rem;
          font-size: 1.08rem;
          box-shadow:
            0 10px 28px rgba(0, 0, 0, 0.5),
            0 0 0 1px rgba(232, 194, 122, 0.4);
        }
        .desk-net__node.is-live .desk-net__glyph {
          box-shadow:
            0 8px 22px rgba(0, 0, 0, 0.45),
            0 0 0 1px rgba(232, 194, 122, 0.28);
        }
        .desk-net__node.is-planned .desk-net__glyph {
          opacity: 0.6;
          filter: saturate(0.65);
        }
        .desk-net__node.is-hover .desk-net__glyph,
        .desk-net__node.is-linked .desk-net__glyph {
          box-shadow:
            0 0 0 1px color-mix(in srgb, var(--hue) 70%, #fff),
            0 0 22px color-mix(in srgb, var(--hue) 45%, transparent);
        }
        .desk-net__label {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.02em;
          text-align: center;
          text-shadow: 0 1px 10px rgba(0, 0, 0, 0.95);
          max-width: 5rem;
          line-height: 1.15;
          pointer-events: none;
        }
        .desk-net__pip {
          position: absolute;
          top: 0.15rem;
          right: 0.35rem;
          width: 0.3rem;
          height: 0.3rem;
          border-radius: 50%;
          pointer-events: none;
        }
        .desk-net__pip.is-live {
          background: var(--filament);
          box-shadow: 0 0 6px var(--filament);
        }
        .desk-net__pip.is-ready { background: var(--signal); }
        .desk-net__pip.is-planned { background: rgba(236, 242, 248, 0.28); }
        .desk-net__hint {
          pointer-events: none;
          position: absolute;
          right: 0.45rem;
          bottom: 0.25rem;
          font-family: var(--font-mono);
          font-size: 0.55rem;
          letter-spacing: 0.08em;
          text-transform: lowercase;
          color: var(--mist-dim);
          opacity: 0.65;
        }

        @media (max-width: 767px) {
          .desk-net { display: none; }
        }
      `}</style>
    </div>
  );
}

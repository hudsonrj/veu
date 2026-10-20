import { useState } from "react";
import { AutonomyOrbit, type AutonomyBreath } from "../components/AutonomyOrbit";
import { GearButton } from "../components/GearButton";
import type { BridgeInfo } from "../bridge/hostBridge";
import { apiFetch, KERNEL, type KernelPulse } from "../lib/kernel";

type Props = {
  breath: AutonomyBreath;
  onBreath: (b: AutonomyBreath) => void;
  ecoOpen: boolean;
  onToggleEco: () => void;
  bridge: BridgeInfo;
  kernel: KernelPulse;
  clock: string;
  compact?: boolean;
  onOpenControl?: () => void;
};

export function TopBar({
  breath,
  onBreath,
  ecoOpen,
  onToggleEco,
  bridge,
  kernel,
  clock,
  compact,
  onOpenControl,
}: Props) {
  const [stopping, setStopping] = useState(false);
  const kernelLabel = kernel.ok ? "on" : "off";
  const hostLabel =
    bridge.status === "connected"
      ? bridge.platform || "ok"
      : "off";

  const stopAll = async () => {
    setStopping(true);
    try {
      await apiFetch(`${KERNEL}/control/stop-all`, { method: "POST" });
      onBreath("guided");
      onOpenControl?.();
    } finally {
      setStopping(false);
    }
  };

  return (
    <header className={`top${compact ? " top--compact" : ""}`}>
      <div className="top__left">
        <span className="top__brand">véu <em>os</em></span>
        <button
          type="button"
          className="top__stop"
          title="Parar tudo — cancela jobs, pausa executor, guiado"
          disabled={stopping}
          onClick={() => void stopAll()}
        >
          {stopping ? "…" : "parar tudo"}
        </button>
        {!compact ? <AutonomyOrbit value={breath} onChange={onBreath} /> : null}
        {!compact ? <GearButton open={ecoOpen} onClick={onToggleEco} /> : null}
      </div>
      <div className="top__right">
        <span
          className={`top__pill is-${kernel.ok ? "connected" : "error"}`}
          title={
            kernel.ok
              ? "API do Véu respondendo (/healthz)"
              : kernel.error || "kernel inacessível — chat e nervos offline"
          }
        >
          {compact ? `k · ${kernelLabel}` : `kernel · ${kernelLabel === "on" ? "on" : "off"}`}
        </span>
        {!compact ? (
          <span
            className={`top__pill is-${bridge.status}`}
            title={
              bridge.status === "connected"
                ? bridge.message
                : `${bridge.message} (extensão — não derruba o chat web)`
            }
          >
            host · {hostLabel}
          </span>
        ) : null}
        <span className="top__clock">{clock}</span>
      </div>
      {compact ? (
        <div className="top__breath">
          <AutonomyOrbit value={breath} onChange={onBreath} />
        </div>
      ) : null}
      <style>{`
        .top {
          position: relative;
          z-index: 50;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.65rem;
          padding: 0.55rem var(--veu-pad-x, 0.75rem);
          background: rgba(7, 9, 12, 0.55);
          border-bottom: 1px solid rgba(236,242,248,0.06);
          backdrop-filter: blur(14px);
          min-width: 0;
        }
        .top--compact {
          flex-wrap: wrap;
          row-gap: 0.35rem;
        }
        .top__left, .top__right {
          display: flex;
          align-items: center;
          gap: 0.55rem;
          min-width: 0;
        }
        .top__breath {
          flex: 1 1 100%;
          display: flex;
          justify-content: flex-start;
        }
        .top__brand {
          font-family: var(--font-display);
          font-weight: 800;
          letter-spacing: 0.14em;
          text-transform: lowercase;
          color: var(--mist);
          font-size: clamp(0.92rem, 3.2vw, 1rem);
          white-space: nowrap;
        }
        .top__brand em {
          font-style: normal;
          color: var(--filament);
          letter-spacing: 0.12em;
          margin-left: 0.15rem;
        }
        .top__pill, .top__clock {
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.06em;
          text-transform: lowercase;
          color: var(--mist-dim);
          white-space: nowrap;
        }
        .top__stop {
          border: 1px solid rgba(240, 120, 100, 0.45);
          background: rgba(240, 120, 100, 0.12);
          color: #f0a090;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.06em;
          text-transform: lowercase;
          padding: 0.28rem 0.55rem;
          cursor: pointer;
          white-space: nowrap;
        }
        .top__stop:disabled { opacity: 0.5; cursor: wait; }
        .top__pill.is-connected { color: var(--signal); }
        .top__pill.is-missing { color: var(--mist-dim); }
        .top__pill.is-error { color: var(--danger); }
        @media (min-width: 744px) {
          .top { padding: 0.6rem 1rem; gap: 0.85rem; }
          .top__pill, .top__clock { font-size: 0.68rem; }
        }
        @media (min-width: 768px) {
          .top--compact { flex-wrap: nowrap; }
          /* desktop usa orbit no top__left; compact real (phone) mantém top__breath */
          .top:not(.top--compact) .top__breath { display: none; }
        }
      `}</style>
    </header>
  );
}

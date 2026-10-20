/**
 * Véu Placa — companion ESP32 CYD (placa amarela 2.8" / 61115).
 * Emparelha token, mostra ficha do hardware e guia de flash.
 */
import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type BoardInfo = {
  board?: {
    name?: string;
    model?: string;
    sku?: string;
    mcu?: string;
    memory?: string;
    display?: { size?: string; resolution?: string; driver?: string };
    touch?: { driver?: string };
    extras?: {
      wifi?: boolean;
      bluetooth?: boolean;
      rgb_led?: Record<string, unknown>;
      ldr?: number;
      microsd?: Record<string, number>;
      gpio_free?: number[];
    };
  };
  potential?: string[];
  firmware_path?: string;
};

type Enroll = {
  ok?: boolean;
  token?: string;
  device?: { id?: string; label?: string; model?: string };
  portal?: { ssid?: string; password?: string; url?: string; hint?: string };
};

type DeviceRow = {
  id?: string;
  label?: string;
  model?: string;
  last_seen?: number;
  created?: number;
};

export function Esp32App() {
  const [board, setBoard] = useState<BoardInfo | null>(null);
  const [devices, setDevices] = useState<DeviceRow[]>([]);
  const [enroll, setEnroll] = useState<Enroll | null>(null);
  const [events, setEvents] = useState<
    { ts?: number; type?: string; payload?: string; device_id?: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [b, d, e] = await Promise.all([
      apiFetch(`${KERNEL}/device/esp32/board`),
      apiFetch(`${KERNEL}/device/esp32/devices`),
      apiFetch(`${KERNEL}/device/esp32/events?limit=16`),
    ]);
    setBoard(await b.json());
    const dj = await d.json();
    setDevices(dj.devices || []);
    const ej = await e.json();
    setEvents(ej.events || []);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const doEnroll = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await apiFetch(`${KERNEL}/device/esp32/enroll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: "placa amarela",
          model: "ESP32-2432S028R",
        }),
      });
      const j = (await r.json()) as Enroll;
      if (!j.ok) {
        setNote("enroll falhou");
      } else {
        setEnroll(j);
        setNote("token gerado — cole no portal veu-placa");
        await refresh();
      }
    } catch (e) {
      setNote(e instanceof Error ? e.message : "erro");
    } finally {
      setBusy(false);
    }
  };

  const b = board?.board;

  return (
    <div className="panel-app placa">
      <header className="placa__head">
        <div>
          <p className="placa__eyebrow">device · esp32-cyd</p>
          <h2>Véu Placa · amarela 2.8"</h2>
          <p className="placa__lede">
            CYD ESP32-2432S028R (SKU 61115) — TFT touch + WiFi/BT como nervo
            físico do SO. Não cabe o React inteiro: a placa é o painel táctil
            do kernel.
          </p>
        </div>
        <button type="button" className="placa__cta" disabled={busy} onClick={() => void doEnroll()}>
          {busy ? "…" : "gerar token"}
        </button>
      </header>

      {note ? <p className="placa__note">{note}</p> : null}

      {enroll?.token ? (
        <section className="placa__token">
          <h3>emparelhar</h3>
          <ol>
            <li>
              Flash: <code>cd device/esp32-cyd && pio run -t upload</code>
            </li>
            <li>
              WiFi da placa sobe AP <strong>{enroll.portal?.ssid}</strong> /{" "}
              <code>{enroll.portal?.password}</code>
            </li>
            <li>
              Abra <code>{enroll.portal?.url}</code>
            </li>
            <li>
              URL do Véu: <code>https://veu.ch8ai.com.br</code>
            </li>
            <li>
              Token:
              <pre>{enroll.token}</pre>
            </li>
          </ol>
          <p className="placa__hint">
            device id: <code>{enroll.device?.id}</code>
          </p>
        </section>
      ) : null}

      <section className="placa__grid">
        <article>
          <h3>hardware</h3>
          <ul>
            <li>{b?.name}</li>
            <li>
              {b?.model} · SKU {b?.sku}
            </li>
            <li>{b?.mcu}</li>
            <li>{b?.memory}</li>
            <li>
              TFT {b?.display?.size} {b?.display?.resolution} ·{" "}
              {b?.display?.driver}
            </li>
            <li>Touch {b?.touch?.driver}</li>
            <li>
              WiFi/BT · RGB · LDR · microSD · GPIO{" "}
              {(b?.extras?.gpio_free || []).join(", ")}
            </li>
          </ul>
        </article>
        <article>
          <h3>potencial no Véu</h3>
          <ul>
            {(board?.potential || []).map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
          <p className="placa__hint">
            firmware: <code>{board?.firmware_path || "device/esp32-cyd"}</code>
          </p>
        </article>
      </section>

      <section className="placa__devices">
        <h3>placas cadastradas</h3>
        {devices.length === 0 ? (
          <p className="placa__hint">nenhuma ainda — gere um token</p>
        ) : (
          <ul>
            {devices.map((d) => (
              <li key={d.id}>
                <strong>{d.label || d.id}</strong>
                <span>
                  {d.model} · last seen{" "}
                  {d.last_seen
                    ? new Date(d.last_seen * 1000).toLocaleString("pt-BR")
                    : "nunca"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="placa__events">
        <h3>eventos recentes</h3>
        {events.length === 0 ? (
          <p className="placa__hint">aguardando toques da placa…</p>
        ) : (
          <ul>
            {events.map((ev, i) => (
              <li key={`${ev.ts}-${i}`}>
                <code>{ev.type}</code> {ev.payload}
                <span>
                  {ev.ts
                    ? new Date(ev.ts * 1000).toLocaleTimeString("pt-BR")
                    : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <style>{`
        .placa {
          height: 100%;
          overflow: auto;
          padding: 1rem 1.1rem 1.5rem;
          color: var(--mist, #ecf2f8);
        }
        .placa__head {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          align-items: flex-start;
          margin-bottom: 0.85rem;
        }
        .placa__eyebrow {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          letter-spacing: 0.12em;
          color: #e8c27a;
        }
        .placa h2 {
          margin: 0.2rem 0 0.35rem;
          font-family: var(--font-display);
          font-size: 1.35rem;
        }
        .placa__lede {
          margin: 0;
          max-width: 38rem;
          color: #a8b4c0;
          font-size: 0.88rem;
          line-height: 1.4;
        }
        .placa__cta {
          appearance: none;
          cursor: pointer;
          border: 0;
          background: #e8c27a;
          color: #0a0c10;
          font-family: var(--font-mono);
          font-size: 0.72rem;
          font-weight: 700;
          padding: 0.65rem 0.95rem;
          border-radius: 0.4rem;
        }
        .placa__cta:disabled { opacity: 0.55; }
        .placa__note {
          color: #7fe7d4;
          font-family: var(--font-mono);
          font-size: 0.72rem;
        }
        .placa__token {
          border: 1px solid rgba(232, 194, 122, 0.35);
          background: rgba(7, 9, 12, 0.55);
          padding: 0.85rem 1rem;
          border-radius: 0.45rem;
          margin-bottom: 1rem;
        }
        .placa__token h3, .placa__grid h3, .placa__devices h3, .placa__events h3 {
          margin: 0 0 0.45rem;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
          color: #e8c27a;
        }
        .placa__token ol {
          margin: 0;
          padding-left: 1.2rem;
          font-size: 0.85rem;
          line-height: 1.5;
        }
        .placa__token pre {
          margin: 0.35rem 0 0;
          padding: 0.55rem 0.65rem;
          background: #0a0c10;
          border-radius: 0.35rem;
          overflow: auto;
          font-size: 0.78rem;
          color: #7fe7d4;
        }
        .placa__grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.75rem;
          margin-bottom: 1rem;
        }
        @media (max-width: 720px) {
          .placa__grid { grid-template-columns: 1fr; }
        }
        .placa__grid article {
          border: 1px solid rgba(155, 183, 255, 0.18);
          background: rgba(7, 9, 12, 0.4);
          padding: 0.75rem 0.85rem;
          border-radius: 0.45rem;
        }
        .placa__grid ul, .placa__devices ul, .placa__events ul {
          margin: 0;
          padding-left: 1.1rem;
          font-size: 0.82rem;
          color: #c8d0dc;
          line-height: 1.45;
        }
        .placa__hint {
          font-family: var(--font-mono);
          font-size: 0.68rem;
          color: #8a939c;
        }
        .placa__devices li, .placa__events li {
          display: flex;
          flex-wrap: wrap;
          gap: 0.45rem 0.75rem;
          margin-bottom: 0.35rem;
        }
        .placa__devices span, .placa__events span {
          color: #8a939c;
          font-size: 0.72rem;
        }
        .placa code {
          font-family: var(--font-mono);
          font-size: 0.78em;
          color: #9bb7ff;
        }
      `}</style>
    </div>
  );
}

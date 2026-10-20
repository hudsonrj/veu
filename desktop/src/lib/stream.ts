import { KERNEL } from "./kernel";

export type StreamHandlers = {
  onEvent?: (type: string, data: unknown) => void;
  onStatus?: (status: "connecting" | "live" | "fallback" | "closed") => void;
};

/**
 * SSE único com backoff. Após 3 falhas, chama onStatus('fallback')
 * para o caller voltar ao polling.
 */
export function connectKernelStream(handlers: StreamHandlers = {}) {
  let es: EventSource | null = null;
  let fails = 0;
  let closed = false;
  let timer: number | null = null;
  const events = ["hello", "mission", "pulse", "sideboard", "job", "credentials", "approval"];

  const open = () => {
    if (closed) return;
    handlers.onStatus?.("connecting");
    // same-origin → cookie de sessão vai junto
    es = new EventSource(`${KERNEL}/stream`, { withCredentials: true });
    es.onopen = () => {
      fails = 0;
      handlers.onStatus?.("live");
    };
    es.onerror = () => {
      es?.close();
      es = null;
      fails += 1;
      if (fails >= 3) {
        handlers.onStatus?.("fallback");
        return;
      }
      const wait = Math.min(15_000, 1000 * 2 ** fails);
      timer = window.setTimeout(open, wait);
    };
    for (const name of events) {
      es.addEventListener(name, (ev) => {
        try {
          const data = JSON.parse((ev as MessageEvent).data);
          handlers.onEvent?.(name, data);
        } catch {
          /* ignore */
        }
      });
    }
  };

  open();

  return () => {
    closed = true;
    if (timer) window.clearTimeout(timer);
    es?.close();
    handlers.onStatus?.("closed");
  };
}

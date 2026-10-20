/** Abre URL na máquina do usuário — gesto síncrono + extensão. */

const URL_RE =
  /(?:https?:\/\/[^\s<>"']+)|(?:www\.[^\s<>"']+)|(?:(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?:\/[^\s<>"']*)?)/i;

export function peekUrl(text: string): string | null {
  const m = (text || "").match(URL_RE);
  if (!m) return null;
  let raw = m[0].replace(/[.,;:!?)】」]+$/, "");
  if (/^www\./i.test(raw)) raw = `https://${raw}`;
  else if (!/^https?:\/\//i.test(raw)) raw = `https://${raw}`;
  return raw;
}

export function looksLikeOpen(text: string): boolean {
  const t = (text || "").toLowerCase();
  // Só se o usuário pediu abrir um site de verdade (não "abra o agente…")
  if (peekUrl(text)) return true;
  return /\b(acesse|acessar|navegue|navegar)\b/.test(t) && !!peekUrl(text);
}

/** URLs de assinatura IA — NUNCA abrir sozinho a partir do Chat Véu. */
export function isAiSubscriptionUrl(url: string): boolean {
  return /chatgpt\.com|claude\.ai|grok\.x\.ai|grok\.com|chat\.openai\.com/i.test(
    url || "",
  );
}

/** Dispara extensão sem esperar (não bloqueia gesto). */
export function askExtensionOpen(url: string) {
  window.postMessage(
    {
      source: "veu-os",
      id: `open-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      type: "veu.host.openUrl",
      url,
    },
    "*",
  );
}

/**
 * Abre no clique do usuário.
 * - preopened: janela about:blank aberta no mesmo gesto
 * - fallback: window.open(url) + extensão
 */
export function openUrlNow(url: string, preopened?: Window | null): "ok" | "blocked" {
  askExtensionOpen(url);
  try {
    if (preopened && !preopened.closed) {
      preopened.location.href = url;
      return "ok";
    }
  } catch {
    /* cross-origin / closed */
  }
  const w = window.open(url, "_blank", "noopener,noreferrer");
  return w ? "ok" : "blocked";
}

/** Reserva aba no gesto do submit (antes do await). */
export function reserveTab(): Window | null {
  try {
    return window.open("about:blank", "_blank");
  } catch {
    return null;
  }
}

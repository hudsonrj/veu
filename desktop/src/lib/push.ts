import { apiFetch, KERNEL } from "./kernel";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

export async function enablePush(): Promise<{ ok: boolean; error?: string }> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return { ok: false, error: "este browser não suporte Web Push" };
  }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") {
    return { ok: false, error: "permissão de notificação negada" };
  }
  const reg = await navigator.serviceWorker.ready;
  const vapid = await apiFetch(`${KERNEL}/push/vapid-public`).then((r) => r.json());
  const publicKey = String(vapid.publicKey || "");
  if (!publicKey) return { ok: false, error: "VAPID público ausente" };

  const sub =
    (await reg.pushManager.getSubscription()) ||
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
    }));

  const json = sub.toJSON();
  const res = await apiFetch(`${KERNEL}/push/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: json.endpoint,
      keys: json.keys,
      ua: navigator.userAgent.slice(0, 120),
    }),
  });
  const body = await res.json();
  return body.ok ? { ok: true } : { ok: false, error: body.error || "falha ao gravar subscription" };
}

/* Véu service worker — app-shell + SWR para /mission e /pulse */
const SHELL = "veu-shell-v1";
const API = "veu-api-v1";
const SHELL_URLS = ["/", "/index.html", "/veu.svg", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => ![SHELL, API].includes(k)).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const path = url.pathname;

  const swr = path === "/mission" || path === "/pulse" || path === "/ready" || path === "/auth/status";
  if (swr) {
    event.respondWith(
      caches.open(API).then(async (cache) => {
        try {
          const fresh = await fetch(req);
          if (fresh.ok) cache.put(req, fresh.clone());
          return fresh;
        } catch {
          const hit = await cache.match(req);
          if (hit) return hit;
          throw new Error("offline");
        }
      }),
    );
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        const copy = res.clone();
        if (res.ok && (path.endsWith(".js") || path.endsWith(".css") || path.endsWith(".svg"))) {
          caches.open(SHELL).then((c) => c.put(req, copy));
        }
        return res;
      }).catch(() => caches.match("/index.html"))),
    );
  }
});

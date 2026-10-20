/**
 * Véu Host — ponte página ↔ extensão.
 * ping local; host.info e o resto vão ao service worker (Native Messaging).
 */
(() => {
  const EXT = "veu-extension";
  const OS = "veu-os";
  const VERSION = "0.3.7";

  const platform = (() => {
    try {
      const p = navigator.userAgentData && navigator.userAgentData.platform;
      if (p) {
        const s = String(p).toLowerCase();
        if (s.includes("win")) return "win32";
        if (s.includes("mac")) return "darwin";
        if (s.includes("linux")) return "linux";
        return String(p);
      }
    } catch (_) {
      /* ignore */
    }
    const ua = navigator.userAgent || "";
    if (/Windows/i.test(ua)) return "win32";
    if (/Linux/i.test(ua)) return "linux";
    if (/Mac/i.test(ua)) return "darwin";
    return "unknown";
  })();

  const caps = [
    "ping",
    "openApp",
    "focusApp",
    "listTabs",
    "readSurface",
    "shell",
    "fs",
    "runPreset",
  ];

  const post = (payload) => {
    window.postMessage(
      { source: EXT, version: VERSION, platform, capabilities: caps, ...payload },
      "*",
    );
  };

  const announce = () => {
    post({ type: "veu.ready", ok: true });
  };

  const forward = (msg) => {
    const replyTo = msg.id;
    const resultType = msg.type === "veu.host.info" ? "veu.host.info.result" : `${msg.type}.result`;
    try {
      if (!chrome || !chrome.runtime || !chrome.runtime.sendMessage) {
        post({
          type: resultType,
          ok: false,
          replyTo,
          error: "runtime indisponível",
        });
        return;
      }
      chrome.runtime.sendMessage(msg, (res) => {
        const err = chrome.runtime.lastError;
        if (err) {
          post({
            type: resultType,
            ok: false,
            replyTo,
            error: err.message || String(err),
          });
          return;
        }
        post({
          type: resultType,
          ok: !!(res && res.ok),
          replyTo,
          data: res && res.data,
          error: res && res.error,
        });
      });
    } catch (e) {
      post({
        type: resultType,
        ok: false,
        replyTo,
        error: String(e && e.message ? e.message : e),
      });
    }
  };

  window.addEventListener("message", (ev) => {
    if (ev.source !== window) return;
    const msg = ev.data;
    if (!msg || msg.source !== OS || typeof msg.type !== "string") return;

    // ping fica no content script (rápido)
    if (msg.type === "veu.ping") {
      post({ type: "veu.pong", ok: true, replyTo: msg.id });
      return;
    }

    // info + openApp + listDir + shell → background (native)
    forward(msg);
  });

  announce();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", announce, { once: true });
  } else {
    setTimeout(announce, 0);
  }
  window.addEventListener("load", announce, { once: true });
  setInterval(announce, 8000);
})();

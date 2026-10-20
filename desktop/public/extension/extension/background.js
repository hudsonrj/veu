/**
 * Véu Host 0.3.5 — service worker + Native Messaging (com.veu.host).
 * Abre apps, foca abas, lê inbox/mensagens em programas abertos no browser.
 */

const VERSION = "0.3.7";
const NATIVE_HOST = "com.veu.host";

const WEB_APPS = {
  whatsapp: "https://web.whatsapp.com/",
  gmail: "https://mail.google.com/",
  calendar: "https://calendar.google.com/",
  agenda: "https://calendar.google.com/",
  notion: "https://www.notion.so/",
  teams: "https://teams.microsoft.com/",
  outlook: "https://outlook.office.com/",
  slack: "https://app.slack.com/",
  grok: "https://grok.com/",
  chatgpt: "https://chatgpt.com/",
  claude: "https://claude.ai/new",
  calendar: "https://calendar.google.com/",
  agenda: "https://calendar.google.com/",
  outlook: "https://outlook.office.com/calendar/",
};

const APP_HOST_MATCH = {
  gmail: ["mail.google.com"],
  calendar: ["calendar.google.com"],
  agenda: ["calendar.google.com"],
  notion: ["notion.so", "www.notion.so"],
  slack: ["app.slack.com"],
  outlook: ["outlook.office.com", "outlook.live.com"],
  teams: ["teams.microsoft.com", "teams.live.com"],
  whatsapp: ["web.whatsapp.com"],
  grok: ["grok.com", "grok.x.ai"],
  chatgpt: ["chatgpt.com", "chat.openai.com"],
  claude: ["claude.ai"],
};

function sendNative(msg, timeoutMs = 6000) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => {
      finish({ ok: false, error: "timeout native host", native: false });
    }, timeoutMs);

    try {
      chrome.runtime.sendNativeMessage(NATIVE_HOST, msg, (response) => {
        const err = chrome.runtime.lastError;
        if (err) {
          finish({
            ok: false,
            error: err.message || String(err),
            native: false,
          });
          return;
        }
        finish({ ...(response || { ok: false, error: "sem resposta" }), native: true });
      });
    } catch (e) {
      finish({ ok: false, error: String(e), native: false });
    }
  });
}

function matchAppFromUrl(url) {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    for (const [app, hosts] of Object.entries(APP_HOST_MATCH)) {
      if (hosts.some((h) => host === h || host.endsWith("." + h))) return app;
    }
  } catch (_) {
    /* ignore */
  }
  return null;
}

async function listAppTabs() {
  const tabs = await chrome.tabs.query({});
  const rows = [];
  for (const t of tabs) {
    if (!t.url || t.url.startsWith("chrome")) continue;
    const app = matchAppFromUrl(t.url);
    rows.push({
      id: t.id,
      title: (t.title || "").slice(0, 120),
      url: t.url,
      active: !!t.active,
      windowId: t.windowId,
      app: app || null,
    });
  }
  return rows;
}

async function findAppTab(app) {
  const hosts = APP_HOST_MATCH[app];
  if (!hosts) return null;
  const tabs = await chrome.tabs.query({});
  for (const t of tabs) {
    if (!t.url) continue;
    try {
      const host = new URL(t.url).hostname.replace(/^www\./, "");
      if (hosts.some((h) => host === h || host.endsWith("." + h))) return t;
    } catch (_) {
      /* ignore */
    }
  }
  return null;
}

async function focusOrOpenApp(app) {
  const existing = await findAppTab(app);
  if (existing && existing.id != null) {
    await chrome.tabs.update(existing.id, { active: true });
    if (existing.windowId != null) {
      try {
        await chrome.windows.update(existing.windowId, { focused: true });
      } catch (_) {
        /* ignore */
      }
    }
    return {
      ok: true,
      data: {
        app,
        mode: "focus",
        tabId: existing.id,
        url: existing.url,
        title: existing.title,
      },
    };
  }

  const native = await sendNative({ type: "veu.host.openApp", app });
  if (native && native.ok) {
    return native;
  }

  const url = WEB_APPS[app];
  if (url) {
    const tab = await chrome.tabs.create({ url });
    return {
      ok: true,
      data: {
        opened: url,
        mode: "web-fallback",
        tabId: tab && tab.id,
        nativeError: native && native.error,
      },
    };
  }

  return {
    ok: false,
    error:
      (native && native.error ? `Native: ${native.error}. ` : "") +
      `App "${app}" precisa do host nativo.`,
  };
}

/** Scrapers rodam no contexto da aba (DOM). Heurísticos e tolerantes. */
function scrapeSurfaceFn(app) {
  const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
  const items = [];
  const maxLen = ["chatgpt", "claude", "grok"].includes(app) ? 8000 : 220;
  const push = (line) => {
    const t = clean(line);
    if (t && t.length > 2 && !items.includes(t)) items.push(t.slice(0, maxLen));
  };

  if (app === "chatgpt") {
    const nodes = document.querySelectorAll(
      "[data-message-author-role='assistant']",
    );
    if (nodes.length) {
      nodes.forEach((node) => {
        const text = clean(node.innerText || node.textContent);
        if (text && text.length > 12) push(text);
      });
    } else {
      // fallback: blocos markdown do assistente
      document
        .querySelectorAll("main .markdown, main [class*='assistant'], main article")
        .forEach((node) => {
          if (items.length >= 10) return;
          const text = clean(node.innerText || node.textContent);
          if (text && text.length > 40) push(text);
        });
    }
  } else if (app === "claude") {
    const nodes = document.querySelectorAll(
      "[data-is-streaming], .font-claude-message, div[data-test-render-count]",
    );
    nodes.forEach((node) => {
      if (items.length >= 10) return;
      const text = clean(node.innerText || node.textContent);
      if (text && text.length > 20 && !/^(Claude|Human|You)$/i.test(text)) {
        push(text);
      }
    });
  } else if (app === "grok") {
    const nodes = document.querySelectorAll(
      "[data-testid*='message'], .message-bubble, .response-content, main article, main [class*='message']",
    );
    nodes.forEach((node) => {
      if (items.length >= 10) return;
      const text = clean(node.innerText || node.textContent);
      if (text && text.length > 20) push(text);
    });
  } else if (app === "calendar" || app === "agenda") {
    const rows = document.querySelectorAll(
      "[data-eventid], [data-eventchip], [role='button'][data-opens-details], div[class*='event']",
    );
    rows.forEach((row) => {
      if (items.length >= 24) return;
      const text = clean(row.getAttribute("aria-label") || row.innerText || row.textContent);
      if (text && text.length > 3 && text.length < 300) push(text.slice(0, 220));
    });
  } else if (app === "gmail") {
    const rows = document.querySelectorAll("tr.zA, div[role='row']");
    rows.forEach((row) => {
      if (items.length >= 12) return;
      const text = clean(row.innerText || row.textContent);
      if (text && text.length > 8 && text.length < 400) push(text.slice(0, 200));
    });
  } else if (app === "outlook") {
    // mail + calendar chips in Outlook web
    const rows = document.querySelectorAll(
      "[role='option'], [role='row'], div[class*='mailList'], div[class*='listItem'], [aria-label*='event'], button[aria-label], div[class*='calendar'] [role='button']",
    );
    rows.forEach((row) => {
      if (items.length >= 20) return;
      const text = clean(
        row.getAttribute("aria-label") || row.innerText || row.textContent,
      );
      if (text && text.length > 8 && text.length < 400) push(text.slice(0, 220));
    });
  } else if (app === "whatsapp") {
    const rows = document.querySelectorAll(
      "[data-testid='cell-frame-container'], div[role='listitem'], div[role='row']",
    );
    rows.forEach((row) => {
      if (items.length >= 12) return;
      const text = clean(row.innerText || row.textContent);
      if (text && text.length > 3 && text.length < 300) push(text.slice(0, 180));
    });
  } else if (app === "slack") {
    const rows = document.querySelectorAll(
      "[data-qa='message_content'], .c-message_kit__text, [role='listitem']",
    );
    rows.forEach((row) => {
      if (items.length >= 12) return;
      const text = clean(row.innerText || row.textContent);
      if (text && text.length > 3 && text.length < 400) push(text.slice(0, 200));
    });
  } else if (app === "teams") {
    const rows = document.querySelectorAll(
      "[data-tid='chat-pane-message'], [role='listitem'], [role='article']",
    );
    rows.forEach((row) => {
      if (items.length >= 12) return;
      const text = clean(row.innerText || row.textContent);
      if (text && text.length > 3 && text.length < 400) push(text.slice(0, 200));
    });
  } else {
    const main =
      document.querySelector("main, [role='main'], #app, body") || document.body;
    const text = clean(main && (main.innerText || main.textContent));
    if (text) {
      text
        .split("\n")
        .map(clean)
        .filter((l) => l.length > 12 && l.length < 200)
        .slice(0, 10)
        .forEach(push);
    }
  }

  return {
    app,
    url: location.href,
    title: document.title || "",
    count: items.length,
    items,
    note:
      items.length === 0
        ? "Nada legível na aba — faça login ou espere a página carregar e peça de novo."
        : undefined,
  };
}

async function readSurface(app) {
  let tab = await findAppTab(app);
  if (!tab) {
    const opened = await focusOrOpenApp(app);
    if (!opened.ok) return opened;
    // espera curta pra aba carregar
    await new Promise((r) => setTimeout(r, 1800));
    tab = await findAppTab(app);
  } else {
    await chrome.tabs.update(tab.id, { active: true });
  }
  if (!tab || tab.id == null) {
    return {
      ok: false,
      error: `Não achei aba do ${app}. Abra o app e peça de novo.`,
    };
  }

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: scrapeSurfaceFn,
      args: [app],
    });
    const data = results && results[0] && results[0].result;
    if (!data) {
      return { ok: false, error: "Sem retorno do scrape na aba." };
    }
    return { ok: true, data };
  } catch (e) {
    return {
      ok: false,
      error:
        String(e && e.message ? e.message : e) +
        " — confira permissões da extensão nas abas do app.",
    };
  }
}

function formatSurfaceText(data) {
  if (!data) return "";
  const lines = [`${data.app || "app"} · ${data.title || data.url || ""}`];
  if (data.items && data.items.length) {
    data.items.forEach((it, i) => lines.push(`${i + 1}. ${it}`));
  } else if (data.note) {
    lines.push(data.note);
  }
  return lines.join("\n");
}

/** Tenta clicar Enviar / Enter no composer da IA. */
function trySubmitFn() {
  const btn =
    document.querySelector('[data-testid="send-button"]') ||
    document.querySelector('button[aria-label*="Send" i]') ||
    document.querySelector('button[aria-label*="Enviar" i]') ||
    document.querySelector('button[data-testid="composer-send"]') ||
    document.querySelector('form button[type="submit"]');
  if (btn && !btn.disabled) {
    btn.click();
    return { clicked: true };
  }
  const ta =
    document.querySelector("#prompt-textarea") ||
    document.querySelector("textarea") ||
    document.querySelector('[contenteditable="true"]');
  if (ta) {
    ta.focus();
    ta.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        which: 13,
        bubbles: true,
      }),
    );
    return { entered: true };
  }
  return { ok: false };
}

/**
 * Fluxo assinatura → resposta na própria janela do Véu:
 * abre/reusa aba, tenta submit, espera, scrape da última resposta.
 */
async function askSubscriptionTurn(app, url, prompt) {
  // 1) abrir / reusar
  let tabId = null;
  try {
    const targetHost = new URL(url).hostname.replace(/^www\./, "");
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) {
      if (!t.url || t.id == null) continue;
      try {
        const h = new URL(t.url).hostname.replace(/^www\./, "");
        if (h === targetHost || h.endsWith("." + targetHost)) {
          await chrome.tabs.update(t.id, { url, active: true });
          tabId = t.id;
          break;
        }
      } catch (_) {
        /* ignore */
      }
    }
  } catch (_) {
    /* ignore */
  }
  if (tabId == null) {
    const tab = await chrome.tabs.create({ url });
    tabId = tab && tab.id;
  }
  if (tabId == null) {
    return { ok: false, error: "não abri a aba da assinatura" };
  }

  await new Promise((r) => setTimeout(r, 2500));

  // 2) tentar enviar (se o ?q= só preencheu)
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: trySubmitFn,
    });
  } catch (_) {
    /* ignore */
  }

  // 3) polling da resposta
  const promptHead = String(prompt || "")
    .slice(0, 40)
    .toLowerCase();
  let best = "";
  for (let i = 0; i < 14; i++) {
    await new Promise((r) => setTimeout(r, i === 0 ? 3000 : 2200));
    try {
      // re-submit leve nas primeiras rodadas se ainda não saiu nada
      if (i === 1 || i === 3) {
        try {
          await chrome.scripting.executeScript({
            target: { tabId },
            func: trySubmitFn,
          });
        } catch (_) {
          /* ignore */
        }
      }
      const results = await chrome.scripting.executeScript({
        target: { tabId },
        func: scrapeSurfaceFn,
        args: [app],
      });
      const data = results && results[0] && results[0].result;
      const list = (data && data.items) || [];
      const candidates = list
        .map((t) => String(t || "").trim())
        .filter((t) => t.length > 24)
        .filter(
          (t) => !promptHead || !t.toLowerCase().includes(promptHead),
        );
      if (candidates.length) {
        const last = candidates[candidates.length - 1];
        // evita pegar resposta ainda streaming curta demais demais cedo
        if (last.length > best.length) best = last;
        if (best.length > 80 && i >= 2) {
          return {
            ok: true,
            data: {
              app,
              reply: best.slice(0, 8000),
              items: candidates.slice(-3),
              polled: i + 1,
            },
          };
        }
      }
    } catch (e) {
      if (i === 13) {
        return {
          ok: false,
          error: String(e && e.message ? e.message : e),
          data: best ? { reply: best } : undefined,
        };
      }
    }
  }
  if (best) {
    return {
      ok: true,
      data: { app, reply: best.slice(0, 8000), polled: 14 },
    };
  }
  return {
    ok: false,
    error:
      "Ainda sem resposta legível na aba — confirme o login da assinatura e tente de novo.",
  };
}

chrome.runtime.onInstalled.addListener(() => {
  console.info(`[Véu Host ${VERSION}] instalada · native=${NATIVE_HOST}`);
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || !msg.type) {
    sendResponse({ ok: false, error: "mensagem inválida" });
    return false;
  }

  (async () => {
    if (msg.type === "veu.host.info" || msg.type === "veu.ping") {
      const native = await sendNative({ type: "veu.host.info" }, 2500);
      sendResponse({
        ok: true,
        data: {
          version: VERSION,
          extensionId: chrome.runtime.id,
          nativeHost: NATIVE_HOST,
          nativeConnected: !!(native && native.ok && native.native),
          nativeError: native && !native.ok ? native.error : undefined,
          nativeData: native && native.ok ? native.data : undefined,
          capabilities: [
            "ping",
            "openApp",
            "focusApp",
            "listTabs",
            "readSurface",
            "askSubscription",
            "shell",
            "fs",
            "runPreset",
          ],
          note:
            native && native.ok
              ? "extensão + Native Messaging ok"
              : "extensão ok — instale o host nativo para terminal/shell",
        },
      });
      return;
    }

    if (msg.type === "veu.host.openUrl") {
      const url = String(msg.url || "").trim();
      if (!url || !/^https?:\/\//i.test(url)) {
        sendResponse({ ok: false, error: "URL inválida" });
        return;
      }
      // Reusa aba do mesmo host (ChatGPT/Claude/Grok) pra manter a sessão
      let reused = null;
      try {
        const targetHost = new URL(url).hostname.replace(/^www\./, "");
        const tabs = await chrome.tabs.query({});
        for (const t of tabs) {
          if (!t.url || t.id == null) continue;
          try {
            const h = new URL(t.url).hostname.replace(/^www\./, "");
            if (h === targetHost || h.endsWith("." + targetHost)) {
              await chrome.tabs.update(t.id, { url, active: true });
              if (t.windowId != null) {
                try {
                  await chrome.windows.update(t.windowId, { focused: true });
                } catch (_) {
                  /* ignore */
                }
              }
              reused = t.id;
              break;
            }
          } catch (_) {
            /* ignore */
          }
        }
      } catch (_) {
        /* ignore */
      }
      if (reused == null) {
        const tab = await chrome.tabs.create({ url });
        sendResponse({
          ok: true,
          data: { opened: url, mode: "tab", tabId: tab && tab.id },
        });
      } else {
        sendResponse({
          ok: true,
          data: { opened: url, mode: "reuse", tabId: reused },
        });
      }
      return;
    }

    // Pedido completo: abre URL da assinatura, tenta enviar, lê a resposta na aba
    if (msg.type === "veu.host.askSubscription") {
      const app = String(msg.app || "").trim().toLowerCase();
      const url = String(msg.url || "").trim();
      const prompt = String(msg.prompt || "").trim();
      if (!app || !url) {
        sendResponse({ ok: false, error: "app/url obrigatórios" });
        return;
      }
      sendResponse(await askSubscriptionTurn(app, url, prompt));
      return;
    }

    if (msg.type === "veu.host.openApp" || msg.type === "veu.host.focusApp") {
      const app = String(msg.app || "").trim().toLowerCase();
      if (!app) {
        sendResponse({ ok: false, error: "app vazio" });
        return;
      }
      // web apps: foca aba existente; nativos (terminal) via native
      if (WEB_APPS[app] || APP_HOST_MATCH[app]) {
        sendResponse(await focusOrOpenApp(app));
        return;
      }
      const native = await sendNative({ type: "veu.host.openApp", app });
      if (native && native.ok) {
        sendResponse(native);
        return;
      }
      sendResponse({
        ok: false,
        error:
          (native && native.error ? `Native: ${native.error}. ` : "") +
          `App "${app}" precisa do host nativo. ` +
          `Instale: /extension/native/ (ID ${chrome.runtime.id})`,
        data: {
          extensionId: chrome.runtime.id,
          nativeHost: NATIVE_HOST,
          install: "https://veu.ch8ai.com.br/extension/#native",
        },
      });
      return;
    }

    if (msg.type === "veu.host.listTabs") {
      const tabs = await listAppTabs();
      const known = tabs.filter((t) => t.app);
      sendResponse({
        ok: true,
        data: {
          total: tabs.length,
          known: known.length,
          tabs: known.length ? known : tabs.slice(0, 40),
          text:
            (known.length ? known : tabs.slice(0, 20))
              .map(
                (t, i) =>
                  `${i + 1}. ${t.app ? `[${t.app}] ` : ""}${(t.title || t.url || "").slice(0, 100)}`,
              )
              .join("\n") || "Nenhuma aba encontrada.",
        },
      });
      return;
    }

    if (msg.type === "veu.host.readSurface") {
      const app = String(msg.app || "").trim().toLowerCase();
      if (!app) {
        sendResponse({ ok: false, error: "app vazio" });
        return;
      }
      const result = await readSurface(app);
      if (result.ok && result.data) {
        result.data.text = formatSurfaceText(result.data);
      }
      sendResponse(result);
      return;
    }

    if (msg.type === "veu.host.runPreset") {
      const preset = String(msg.preset || "").trim();
      const native = await sendNative({ type: "veu.host.runPreset", preset });
      if (native && native.ok) {
        sendResponse(native);
        return;
      }
      const url = WEB_APPS[preset];
      if (url) {
        await chrome.tabs.create({ url });
        sendResponse({
          ok: true,
          data: { opened: url, mode: "web-fallback", preset },
        });
        return;
      }
      sendResponse({
        ok: false,
        error:
          (native && native.error) ||
          "Host nativo ausente para este preset. Instale /extension/native/",
        data: { extensionId: chrome.runtime.id },
      });
      return;
    }

    if (
      msg.type === "veu.host.shell" ||
      msg.type === "veu.host.readPath" ||
      msg.type === "veu.host.listDir"
    ) {
      const native = await sendNative(msg);
      sendResponse(
        native && native.ok
          ? native
          : {
              ok: false,
              error:
                (native && native.error) ||
                "Host nativo ausente. Rode install.sh / install.ps1 em /extension/native/",
              data: { extensionId: chrome.runtime.id },
            },
      );
      return;
    }

    sendResponse({ ok: false, error: `tipo não suportado: ${msg.type}` });
  })();

  return true;
});

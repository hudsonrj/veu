import { useCallback, useEffect, useState } from "react";
import { ruosPost } from "../../lib/ruos";

const LITE_APPS = [
  { id: "welcome", label: "Welcome", url: "https://ruos.cognitum.one" },
  { id: "chatgpt", label: "ChatGPT", url: "https://chatgpt.com" },
  { id: "claude", label: "Claude", url: "https://claude.ai" },
  { id: "vscode", label: "VS Code", url: "https://vscode.dev" },
  { id: "github", label: "GitHub", url: "https://github.com" },
  { id: "search", label: "Search", url: "https://duckduckgo.com" },
];

type Props = { seedUrl?: string | null };

/** ruOS Lite — desktop leve no browser, web apps only (sem terminal/arquivos). */
export function BrowserApp({ seedUrl }: Props) {
  const [url, setUrl] = useState(seedUrl || "https://ruos.cognitum.one");
  const [bar, setBar] = useState(seedUrl || "https://ruos.cognitum.one");
  const [ai, setAi] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    void ruosPost("/ruos/lite/resume");
  }, []);

  const go = useCallback((next: string) => {
    let u = next.trim();
    if (!u) return;
    if (!/^https?:\/\//i.test(u)) {
      if (u.includes(" ") || !u.includes(".")) {
        u = `https://duckduckgo.com/?q=${encodeURIComponent(u)}`;
      } else {
        u = `https://${u}`;
      }
    }
    setBar(u);
    setUrl(u);
  }, []);

  return (
    <div className="lite">
      <header className="lite__bar">
        <span className="lite__mark">ruOS Lite · browser-based</span>
        <form
          className="lite__addr"
          onSubmit={(e) => {
            e.preventDefault();
            go(bar);
          }}
        >
          <input
            value={bar}
            onChange={(e) => setBar(e.target.value)}
            placeholder="Search or URL"
            aria-label="Address"
          />
          <button type="submit">Go</button>
        </form>
        <button
          type="button"
          className={ai ? "is-on" : ""}
          onClick={() => {
            const next = !ai;
            setAi(next);
            void ruosPost("/ruos/lite/ai", { enabled: next });
            setNote(next ? "AI is using this browser" : "AI stopped");
          }}
        >
          {ai ? "Stop AI" : "Allow AI"}
        </button>
      </header>

      <nav className="lite__dock" aria-label="Lite apps">
        {LITE_APPS.map((a) => (
          <button key={a.id} type="button" onClick={() => go(a.url)}>
            {a.label}
          </button>
        ))}
      </nav>

      <p className="lite__hint">
        Browser only: no terminal, no files. Sign-ins, site data and open tabs
        are saved encrypted between sessions (30 days); caches are not kept.
        {note ? ` · ${note}` : ""}
      </p>

      <div className="lite__frame">
        <iframe title="ruOS Lite" src={url} sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox" />
      </div>

      <style>{`
        .lite {
          height: 100%;
          display: grid;
          grid-template-rows: auto auto auto 1fr;
          background: #08080c;
          color: #e0e4f2;
          min-height: 0;
        }
        .lite__bar {
          display: flex; gap: 0.45rem; align-items: center; flex-wrap: wrap;
          padding: 0.45rem 0.6rem;
          border-bottom: 1px solid rgba(121,223,255,0.2);
          background: #0b121a;
        }
        .lite__mark {
          font-family: var(--font-mono); font-size: 0.62rem;
          letter-spacing: 0.12em; color: #79dfff; text-transform: lowercase;
        }
        .lite__addr { display: flex; flex: 1; gap: 0.35rem; min-width: 12rem; }
        .lite__addr input {
          flex: 1; background: #05070a; border: 1px solid rgba(121,223,255,0.25);
          color: #e0e4f2; padding: 0.4rem 0.55rem; font: inherit; font-size: 0.8rem;
        }
        .lite__bar button, .lite__dock button {
          appearance: none; border: 1px solid rgba(121,223,255,0.28);
          background: rgba(8,19,31,0.9); color: #d6e9f2;
          padding: 0.35rem 0.55rem; font-size: 0.72rem; cursor: pointer;
        }
        .lite__bar button.is-on {
          background: rgba(240,100,73,0.25); border-color: #f06449; color: #ffcf73;
        }
        .lite__dock {
          display: flex; gap: 0.35rem; overflow-x: auto; padding: 0.4rem 0.6rem;
          border-bottom: 1px solid rgba(121,223,255,0.12);
        }
        .lite__hint {
          margin: 0; padding: 0.35rem 0.65rem; font-size: 0.68rem; color: #8a939c;
        }
        .lite__frame { min-height: 0; background: #000; }
        .lite__frame iframe {
          width: 100%; height: 100%; border: 0; background: #111;
        }
      `}</style>
    </div>
  );
}

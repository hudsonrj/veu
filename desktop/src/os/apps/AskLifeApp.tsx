import { useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Source = { title?: string; url?: string; excerpt?: string; kind?: string };

export function AskLifeApp({ seed }: { seed?: string | null }) {
  const [q, setQ] = useState(seed?.replace(/^life:/, "") || "");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [brief, setBrief] = useState<string>("");

  useEffect(() => {
    if (seed?.startsWith("life:")) setQ(seed.slice(5));
  }, [seed]);

  useEffect(() => {
    void apiFetch(`${KERNEL}/briefing?kind=morning`)
      .then((r) => r.json())
      .then((j) => setBrief(String(j.text || "")));
  }, []);

  const ask = async () => {
    setBusy(true);
    setErr(null);
    setAnswer("");
    setSources([]);
    try {
      const r = await apiFetch(`${KERNEL}/life/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const j = await r.json();
      if (!j.ok) {
        setErr(j.message || j.error || "sem resposta");
      } else {
        setAnswer(j.answer || "");
        setSources(j.sources || []);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel-app">
      <header className="panel-app__head">
        <h2>Pergunte à minha vida</h2>
      </header>
      <form
        className="panel-app__form"
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="O que ficou pendente da Vale?"
        />
        <button type="submit" disabled={busy || !q.trim()}>
          {busy ? "…" : "perguntar"}
        </button>
      </form>
      {err ? <p className="panel-app__warn">{err}</p> : null}
      {answer ? <p className="panel-app__answer">{answer}</p> : null}
      {sources.length ? (
        <>
          <h3>Fontes</h3>
          <ul className="panel-app__list">
            {sources.map((s, i) => (
              <li key={i}>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.title || s.url}
                  </a>
                ) : (
                  <span>{s.title || s.excerpt || s.kind || "fonte"}</span>
                )}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {brief ? (
        <>
          <h3>Briefing</h3>
          <pre className="panel-app__brief">{brief}</pre>
          <button
            type="button"
            onClick={() =>
              void apiFetch(`${KERNEL}/briefing/build?kind=morning`, { method: "POST" })
                .then((r) => r.json())
                .then((j) => setBrief(String(j.text || "")))
            }
          >
            regenerar manhã
          </button>
        </>
      ) : null}
    </div>
  );
}

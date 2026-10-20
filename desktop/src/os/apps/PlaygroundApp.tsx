import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";

type SurfaceId = "openai" | "claude" | "xai" | "ollama" | "huggingface";

type SurfaceMeta = {
  id: SurfaceId;
  label: string;
  kind: "llm" | "mcp";
  ready: boolean;
  model?: string;
  models?: string[];
  tools?: { name?: string; description?: string }[];
  hint?: string;
};

const LABELS: Record<SurfaceId, string> = {
  openai: "OpenAI",
  claude: "Claude",
  xai: "Grok",
  ollama: "Ollama",
  huggingface: "Hugging Face",
};

const HUES: Record<SurfaceId, string> = {
  openai: "#10A37F",
  claude: "#D4A27F",
  xai: "#E8C27A",
  ollama: "#7FE7D4",
  huggingface: "#FFD21E",
};

const DEFAULT_PROMPTS: Record<SurfaceId, string> = {
  openai: "Explique em 3 frases o que é um SO agentic.",
  claude: "Revise este raciocínio: o Véu deve responder dentro do SO, não em outra aba.",
  xai: "Resposta direta: o que priorizar hoje num desktop de IA?",
  ollama: "Diga oi em uma frase curta.",
  huggingface: "whisper",
};

/** Playground unificado — testa IAs e HF dentro do Véu. */
export function PlaygroundApp() {
  const [surfaces, setSurfaces] = useState<SurfaceMeta[]>([]);
  const [surface, setSurface] = useState<SurfaceId>("openai");
  const [prompt, setPrompt] = useState(DEFAULT_PROMPTS.openai);
  const [system, setSystem] = useState("");
  const [model, setModel] = useState("");
  const [hfTool, setHfTool] = useState("hub_repo_search");
  const [out, setOut] = useState("");
  const [meta, setMeta] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const res = await apiFetch(`${KERNEL}/llm/playground`);
      const data = (await res.json()) as { surfaces?: SurfaceMeta[] };
      const list = data.surfaces || [];
      setSurfaces(list);
      const cur = list.find((s) => s.id === surface);
      if (cur?.model && !model) setModel(cur.model);
      if (cur?.tools?.length && !cur.tools.some((t) => t.name === hfTool)) {
        setHfTool(cur.tools[0]?.name || "hf_whoami");
      }
    } catch {
      setErr("kernel offline");
    }
  }, [surface, model, hfTool]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const pick = (id: SurfaceId) => {
    setSurface(id);
    setPrompt(DEFAULT_PROMPTS[id]);
    setOut("");
    setErr(null);
    const cur = surfaces.find((s) => s.id === id);
    setModel(cur?.model || "");
    if (id === "huggingface" && cur?.tools?.[0]?.name) {
      setHfTool(cur.tools[0].name || "hf_whoami");
    }
  };

  const run = async () => {
    setBusy(true);
    setErr(null);
    setOut("");
    setMeta("rodando…");
    try {
      const body: Record<string, unknown> = {
        surface,
        prompt,
        system: system.trim() || null,
        model: model.trim() || null,
      };
      if (surface === "huggingface") {
        body.tool = hfTool;
        if (hfTool === "hf_whoami") body.prompt = "";
      }
      const res = await apiFetch(`${KERNEL}/llm/playground`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const raw = await res.text();
      if (!raw.trim()) {
        throw new Error(
          `kernel respondeu vazio (HTTP ${res.status}) — tente de novo`,
        );
      }
      let data: {
        ok?: boolean;
        text?: string;
        error?: string;
        model?: string;
        provider?: string;
        tool?: string;
        kind?: string;
      };
      try {
        data = JSON.parse(raw) as typeof data;
      } catch {
        throw new Error(
          `resposta inválida do kernel (HTTP ${res.status}): ${raw.slice(0, 120)}`,
        );
      }
      setOut(data.text || data.error || "sem saída");
      setMeta(
        [
          data.kind || surface,
          data.provider || surface,
          data.model,
          data.tool,
          data.ok === false ? "falhou" : "ok",
        ]
          .filter(Boolean)
          .join(" · "),
      );
      if (!data.ok && data.error) setErr(data.error);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
      setMeta("erro");
    } finally {
      setBusy(false);
    }
  };

  const cur = surfaces.find((s) => s.id === surface);
  const hue = HUES[surface];

  return (
    <div className="pg" style={{ ["--hue" as string]: hue }}>
      <header className="pg__head">
        <div>
          <h2>Playground</h2>
          <p>OpenAI · Claude · Grok · Ollama · Hugging Face — tudo dentro do Véu.</p>
        </div>
        <button type="button" className="pg__refresh" onClick={() => void reload()}>
          atualizar
        </button>
      </header>

      <div className="pg__tabs">
        {(Object.keys(LABELS) as SurfaceId[]).map((id) => {
          const s = surfaces.find((x) => x.id === id);
          return (
            <button
              key={id}
              type="button"
              className={surface === id ? "is-on" : undefined}
              onClick={() => pick(id)}
              style={{ ["--tab" as string]: HUES[id] }}
            >
              {LABELS[id]}
              <i className={s?.ready ? "is-live" : ""}>{s?.ready ? "live" : "off"}</i>
            </button>
          );
        })}
      </div>

      <p className="pg__hint">
        {cur?.hint || "Cole API key em Ajustes → assinaturas · HF já via MCP"}
        {cur?.ready ? "" : " · superfície offline até conectar"}
      </p>

      <div className="pg__grid">
        <div className="pg__in">
          {surface === "huggingface" ? (
            <label>
              <span>tool MCP</span>
              <select value={hfTool} onChange={(e) => setHfTool(e.target.value)}>
                {(cur?.tools || [{ name: "hf_whoami" }, { name: "hub_repo_search" }, { name: "hub_repo_details" }]).map(
                  (t) => (
                    <option key={t.name || "x"} value={t.name || ""}>
                      {t.name}
                    </option>
                  ),
                )}
              </select>
            </label>
          ) : (
            <label>
              <span>modelo</span>
              {surface === "ollama" && (cur?.models?.length || 0) > 0 ? (
                <select value={model} onChange={(e) => setModel(e.target.value)}>
                  {(cur?.models || []).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={cur?.model || "modelo"}
                />
              )}
            </label>
          )}

          {surface !== "huggingface" ? (
            <label>
              <span>system (opcional)</span>
              <textarea
                rows={2}
                value={system}
                onChange={(e) => setSystem(e.target.value)}
                placeholder="instrução de sistema…"
              />
            </label>
          ) : null}

          <label>
            <span>
              {surface === "huggingface"
                ? hfTool === "hf_whoami"
                  ? "prompt (não precisa)"
                  : hfTool === "hub_repo_details"
                    ? "repo (ex.: openai/whisper-large-v3)"
                    : "busca (ex.: whisper, qwen)"
                : "prompt"}
            </span>
            <textarea
              rows={6}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="escreva aqui…"
              disabled={surface === "huggingface" && hfTool === "hf_whoami"}
            />
          </label>

          <button type="button" className="pg__run" disabled={busy} onClick={() => void run()}>
            {busy ? "…" : "rodar"}
          </button>
        </div>

        <div className="pg__out">
          <div className="pg__outhead">
            <span>saída</span>
            <em>{meta || "—"}</em>
          </div>
          <pre>{out || "resultado aparece aqui"}</pre>
          {err ? <p className="pg__err">{err}</p> : null}
        </div>
      </div>

      <style>{`
        .pg {
          height: 100%;
          display: flex;
          flex-direction: column;
          gap: 0.55rem;
          padding: 0.85rem 1rem;
          color: #e8ebe6;
          background:
            radial-gradient(ellipse at 0% 0%, color-mix(in srgb, var(--hue) 18%, transparent), transparent 50%),
            linear-gradient(165deg, #121418, #0c0e12 60%);
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .pg__head {
          display: flex;
          justify-content: space-between;
          gap: 0.75rem;
          align-items: flex-start;
        }
        .pg__head h2 {
          margin: 0;
          font-family: "IBM Plex Serif", Georgia, serif;
          font-weight: 500;
          font-size: 1.4rem;
          color: color-mix(in srgb, var(--hue) 65%, #fff);
        }
        .pg__head p {
          margin: 0.2rem 0 0;
          font-size: 0.82rem;
          color: #9aa3ad;
        }
        .pg__refresh {
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(255,255,255,0.04);
          color: #c8d0d8;
          border-radius: 5px;
          padding: 0.35rem 0.65rem;
          font-size: 0.75rem;
          cursor: pointer;
        }
        .pg__tabs {
          display: flex;
          flex-wrap: wrap;
          gap: 0.35rem;
        }
        .pg__tabs button {
          border: 1px solid color-mix(in srgb, var(--tab, #888) 35%, transparent);
          background: color-mix(in srgb, var(--tab, #888) 8%, transparent);
          color: #d8dde2;
          border-radius: 5px;
          padding: 0.4rem 0.7rem;
          font-size: 0.78rem;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
        }
        .pg__tabs button.is-on {
          background: color-mix(in srgb, var(--tab, #888) 22%, transparent);
          border-color: color-mix(in srgb, var(--tab, #888) 55%, transparent);
        }
        .pg__tabs i {
          font-style: normal;
          font-size: 0.62rem;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: #6b7480;
        }
        .pg__tabs i.is-live { color: #8fbf9f; }
        .pg__hint {
          margin: 0;
          font-size: 0.75rem;
          color: #7a8490;
        }
        .pg__grid {
          flex: 1;
          min-height: 0;
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
          gap: 0.75rem;
        }
        .pg__in, .pg__out {
          min-height: 0;
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }
        .pg__in label {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
          font-size: 0.72rem;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          color: #7a8490;
        }
        .pg__in textarea, .pg__in input, .pg__in select {
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(0,0,0,0.3);
          color: #e8ebe6;
          border-radius: 6px;
          padding: 0.5rem 0.65rem;
          font: inherit;
          font-size: 0.88rem;
          text-transform: none;
          letter-spacing: normal;
        }
        .pg__in textarea { resize: vertical; }
        .pg__run {
          align-self: flex-start;
          border: 1px solid color-mix(in srgb, var(--hue) 50%, transparent);
          background: color-mix(in srgb, var(--hue) 18%, transparent);
          color: #fff;
          border-radius: 6px;
          padding: 0.5rem 1.1rem;
          font-size: 0.88rem;
          cursor: pointer;
        }
        .pg__run:disabled { opacity: 0.55; cursor: default; }
        .pg__out {
          border: 1px solid rgba(255,255,255,0.1);
          border-radius: 8px;
          background: rgba(0,0,0,0.22);
          padding: 0.65rem 0.75rem;
        }
        .pg__outhead {
          display: flex;
          justify-content: space-between;
          font-size: 0.7rem;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: #7a8490;
        }
        .pg__out pre {
          margin: 0.4rem 0 0;
          flex: 1;
          overflow: auto;
          white-space: pre-wrap;
          word-break: break-word;
          font-family: "IBM Plex Mono", ui-monospace, monospace;
          font-size: 0.8rem;
          line-height: 1.45;
          color: #dce3ea;
        }
        .pg__err { margin: 0.35rem 0 0; color: #e8a0a0; font-size: 0.78rem; }
        @media (max-width: 800px) {
          .pg__grid { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL  } from "../../lib/kernel";

type Tool = {
  name?: string;
  description?: string;
};

type Server = {
  id: string;
  name?: string;
  status?: string;
  tools?: Tool[];
  note?: string;
};

/** MCP — escolher servidor, tool e executar de verdade. */
export function McpApp() {
  const [servers, setServers] = useState<Server[]>([]);
  const [serverId, setServerId] = useState("");
  const [tool, setTool] = useState("");
  const [argsJson, setArgsJson] = useState("{}");
  const [prompt, setPrompt] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const res = await apiFetch(`${KERNEL}/mcp`);
      const data = (await res.json()) as { servers?: Server[] };
      const list = data.servers || [];
      setServers(list);
      if (!serverId && list[0]?.id) {
        setServerId(list[0].id);
        const t0 = list[0].tools?.[0]?.name || "";
        if (t0) setTool(t0);
      }
    } catch {
      setErr("kernel offline");
    }
  }, [serverId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const current = servers.find((s) => s.id === serverId);
  const tools = current?.tools || [];

  useEffect(() => {
    if (!tools.some((t) => t.name === tool) && tools[0]?.name) {
      setTool(tools[0].name || "");
    }
  }, [serverId, tools, tool]);

  const call = async () => {
    if (!serverId || !tool) return;
    setBusy(true);
    setErr(null);
    setOut("executando…");
    try {
      let arguments_: Record<string, unknown> = {};
      try {
        arguments_ = JSON.parse(argsJson || "{}") as Record<string, unknown>;
      } catch {
        throw new Error("JSON de argumentos inválido");
      }
      // atalhos HF comuns
      if (tool === "hub_repo_search" && prompt.trim() && !arguments_.query) {
        arguments_.query = prompt.trim();
        arguments_.limit = arguments_.limit ?? 5;
        arguments_.repo_types = arguments_.repo_types ?? ["model"];
      }
      if (tool === "hub_repo_details" && prompt.trim() && !arguments_.repo_ids) {
        arguments_.repo_ids = [prompt.trim().split(/\s+/)[0]];
      }
      if (tool === "hf_whoami") {
        arguments_ = {};
      }

      const res = await fetch(
        `${KERNEL}/mcp/${encodeURIComponent(serverId)}/call`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tool, arguments: arguments_ }),
        },
      );
      const raw = await res.text();
      const data = raw
        ? (JSON.parse(raw) as {
            ok?: boolean;
            result?: unknown;
            error?: string;
            message?: string;
          })
        : {};
      if (!data.ok) {
        setErr(data.error || data.message || "falha");
        setOut(data.error || JSON.stringify(data, null, 2));
      } else {
        const result = data.result;
        let text = "";
        if (result && typeof result === "object" && "content" in (result as object)) {
          const content = (result as { content?: { type?: string; text?: string }[] })
            .content;
          text = (content || [])
            .filter((c) => c.type === "text")
            .map((c) => c.text || "")
            .join("\n");
        }
        setOut(text || JSON.stringify(result ?? data, null, 2));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha");
      setOut("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mcp">
      <div className="mcp__row">
        <label>
          <span>servidor</span>
          <select
            value={serverId}
            disabled={busy || servers.length === 0}
            onChange={(e) => setServerId(e.target.value)}
          >
            {servers.length === 0 ? (
              <option value="">nenhum MCP</option>
            ) : (
              servers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name || s.id} · {s.status || "?"}
                </option>
              ))
            )}
          </select>
        </label>
        <label>
          <span>tool</span>
          <select
            value={tool}
            disabled={busy || tools.length === 0}
            onChange={(e) => setTool(e.target.value)}
          >
            {tools.length === 0 ? (
              <option value="">sem tools</option>
            ) : (
              tools.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))
            )}
          </select>
        </label>
        <button type="button" className="mcp__refresh" disabled={busy} onClick={() => void reload()}>
          atualizar
        </button>
      </div>

      {tools.find((t) => t.name === tool)?.description ? (
        <p className="mcp__hint">{tools.find((t) => t.name === tool)?.description}</p>
      ) : null}

      <label className="mcp__block">
        <span>atalho / query</span>
        <input
          value={prompt}
          disabled={busy}
          placeholder="ex.: whisper · openai/gpt-oss · (vazio = whoami)"
          onChange={(e) => setPrompt(e.target.value)}
        />
      </label>

      <label className="mcp__block">
        <span>arguments (JSON)</span>
        <textarea
          rows={4}
          value={argsJson}
          disabled={busy}
          onChange={(e) => setArgsJson(e.target.value)}
        />
      </label>

      <button
        type="button"
        className="mcp__go"
        disabled={busy || !serverId || !tool}
        onClick={() => void call()}
      >
        {busy ? "executando…" : "executar tool"}
      </button>

      <pre className="mcp__out">{out || "resultado aparece aqui"}</pre>
      {err ? <p className="mcp__err">{err}</p> : null}

      <style>{`
        .mcp {
          height: 100%;
          display: grid;
          grid-template-rows: auto auto auto auto auto 1fr auto;
          gap: 0.5rem;
          padding: 0.75rem 0.85rem;
          background: linear-gradient(165deg, #111418, #0c0e12 70%);
          color: #e4e8ec;
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .mcp__row {
          display: grid;
          grid-template-columns: 1fr 1fr auto;
          gap: 0.45rem;
          align-items: end;
        }
        .mcp label span, .mcp__block span {
          display: block;
          font-size: 0.62rem;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: #8a96a0;
          margin-bottom: 0.25rem;
        }
        .mcp select, .mcp input, .mcp textarea {
          width: 100%;
          border: 1px solid rgba(255,255,255,0.12);
          background: rgba(0,0,0,0.35);
          color: #e4e8ec;
          padding: 0.45rem 0.55rem;
          font: inherit;
        }
        .mcp textarea { font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; }
        .mcp__refresh, .mcp__go {
          border: 1px solid rgba(168,180,192,0.4);
          background: rgba(168,180,192,0.1);
          color: #d4dce4;
          padding: 0.45rem 0.7rem;
          cursor: pointer;
          font-size: 0.78rem;
        }
        .mcp__go {
          justify-self: start;
          border-color: rgba(127,231,212,0.4);
          background: rgba(127,231,212,0.1);
          color: #c8f0e6;
        }
        .mcp__go:disabled, .mcp__refresh:disabled { opacity: 0.4; cursor: default; }
        .mcp__hint {
          margin: 0;
          font-size: 0.78rem;
          color: #8a96a0;
        }
        .mcp__out {
          margin: 0;
          min-height: 0;
          overflow: auto;
          padding: 0.6rem;
          background: rgba(0,0,0,0.4);
          font-family: "IBM Plex Mono", monospace;
          font-size: 0.72rem;
          white-space: pre-wrap;
          color: #b8c4ce;
        }
        .mcp__err { margin: 0; color: #e8a0a0; font-size: 0.78rem; }
        @media (max-width: 640px) {
          .mcp__row { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}

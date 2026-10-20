import { useCallback, useEffect, useMemo, useState } from "react";
import type { AutonomyBreath } from "../../components/AutonomyOrbit";
import { NERVE_GROUPS } from "../catalog";
import { apiFetch,
  KERNEL,
  confirmSubscriptionAccount,
  connectSubscription,
  deleteServer,
  disconnectSubscription,
  fetchServerMaintenance,
  fetchServerSites,
  deleteMcpServer,
  fetchMcpServers,
  fetchServers,
  fetchSubscriptions,
  importMcpJson,
  linkSubscriptionAccount,
  subscriptionLoginUrl,
  probeMcpServer,
  testServer,
  upsertServer,
  type McpServer,
  type ServerSlot,
  type SubscriptionSlot,
 } from "../../lib/kernel";
import { openUrlNow } from "../../lib/openUrl";

type Section =
  | "mapa"
  | "nervos"
  | "assinaturas"
  | "servidores"
  | "mcp"
  | "modelos"
  | "musculo"
  | "politicas";

type Connector = {
  id: string;
  name: string;
  kind: string;
  surface: string;
  status: string;
  capabilities: string[];
  notes?: string;
};

type Pulse = {
  connectors?: number;
  ecc_agents?: number;
  ecc_skills?: number;
  notion?: string;
  openrag?: { status?: string; base_url?: string | null };
  llm?: {
    openai?: boolean;
    openai_model?: string;
    deepseek?: boolean;
    deepseek_model?: string;
    huggingface?: boolean;
    huggingface_model?: string;
    claude?: boolean;
    claude_model?: string;
    xai?: boolean;
    xai_model?: string;
    ollama?: boolean;
    ollama_model?: string;
  };
  jev?: { status?: string; model?: string };
  bridges?: {
    grokbot?: { status?: string; webhook_configured?: boolean; routine?: string };
    openclaw?: { status?: string };
    hermes?: { status?: string };
  };
  harness?: { active?: boolean; recent?: { id: string; route: string; tools: string[] }[] };
};

type Props = {
  breath: AutonomyBreath;
  onBreath: (b: AutonomyBreath) => void;
};

const NAV: { id: Section; label: string; glyph: string }[] = [
  { id: "mapa", label: "mapa", glyph: "◎" },
  { id: "nervos", label: "nervos", glyph: "⚡" },
  { id: "assinaturas", label: "assinaturas", glyph: "◇" },
  { id: "servidores", label: "servidores", glyph: "⌘" },
  { id: "mcp", label: "MCP", glyph: "M" },
  { id: "modelos", label: "modelos", glyph: "✦" },
  { id: "musculo", label: "músculo", glyph: "◈" },
  { id: "politicas", label: "políticas", glyph: "◌" },
];

function tone(status?: string | boolean | null) {
  if (typeof status === "boolean") return status ? "live" : "dim";
  const s = (status || "").toLowerCase();
  if (s === "live") return "live";
  if (s === "ready") return "ready";
  if (!s || s === "off" || s === "planned") return "dim";
  return "ready";
}

function StatusPip({ status }: { status?: string | boolean | null }) {
  return <i className={`ctl__pip is-${tone(status)}`} aria-hidden />;
}

/** Control center do SO — cabe na janela, sem lista infinita. */
export function SettingsApp({ breath, onBreath }: Props) {
  const [section, setSection] = useState<Section>("mapa");
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [harness, setHarness] = useState<Pulse["harness"]>(undefined);
  const [picked, setPicked] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [subs, setSubs] = useState<SubscriptionSlot[]>([]);
  const [subBusy, setSubBusy] = useState<string | null>(null);
  const [subMsg, setSubMsg] = useState<string | null>(null);
  const [draftKeys, setDraftKeys] = useState<Record<string, string>>({});
  const [draftModels, setDraftModels] = useState<Record<string, string>>({});
  const [servers, setServers] = useState<ServerSlot[]>([]);
  const [srvBusy, setSrvBusy] = useState<string | null>(null);
  const [srvMsg, setSrvMsg] = useState<string | null>(null);
  const [srvDetail, setSrvDetail] = useState<string | null>(null);
  const [draftSrv, setDraftSrv] = useState({
    name: "",
    host: "",
    port: "22",
    username: "root",
    password: "",
    notes: "",
  });
  const [draftSrvPass, setDraftSrvPass] = useState<Record<string, string>>({});
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [mcpJson, setMcpJson] = useState(
    '{\n  "mcpServers": {\n    "exemplo": {\n      "url": "https://mcp.exemplo.com/sse"\n    }\n  }\n}',
  );
  const [mcpBusy, setMcpBusy] = useState<string | null>(null);
  const [mcpMsg, setMcpMsg] = useState<string | null>(null);
  const [hfToken, setHfToken] = useState("");
  const [hfModel, setHfModel] = useState("");
  const [hfBusy, setHfBusy] = useState(false);
  const [hfLive, setHfLive] = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushMsg, setPushMsg] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [p, c, h, s, srv, mcp] = await Promise.all([
        apiFetch(`${KERNEL}/pulse`).then((r) => r.json()),
        apiFetch(`${KERNEL}/connectors`).then((r) => r.json()),
        apiFetch(`${KERNEL}/harness`).then((r) => r.json()),
        fetchSubscriptions(),
        fetchServers(),
        fetchMcpServers(),
      ]);
      const pulseObj = p as Pulse;
      setPulse(pulseObj);
      setConnectors(((c as { connectors?: Connector[] }).connectors || []) as Connector[]);
      setHarness(h as Pulse["harness"]);
      setSubs(s);
      setServers(srv);
      setMcpServers(mcp);
      setHfLive(Boolean(pulseObj.llm?.huggingface));
      if (pulseObj.llm?.huggingface_model) setHfModel(pulseObj.llm.huggingface_model);
      setErr(null);
    } catch {
      setErr("kernel offline");
    }
  }, []);

  useEffect(() => {
    void reload();
    const id = window.setInterval(reload, 14_000);
    return () => window.clearInterval(id);
  }, [reload]);

  const grouped = useMemo(() => {
    const used = new Set<string>();
    const groups = NERVE_GROUPS.map((g) => {
      const items = connectors.filter((c) => {
        if (used.has(c.id)) return false;
        if (g.match(c.id, c.kind)) {
          used.add(c.id);
          return true;
        }
        return false;
      });
      return { ...g, items };
    });
    const rest = connectors.filter((c) => !used.has(c.id));
    if (rest.length) groups.push({ id: "outros", label: "outros", match: () => false, items: rest });
    return groups.filter((g) => g.items.length > 0);
  }, [connectors]);

  const selected = connectors.find((c) => c.id === picked) || null;
  const liveCount = connectors.filter((c) => c.status === "live" || c.status === "ready").length;
  const recent = harness?.recent || pulse?.harness?.recent || [];

  return (
    <div className="ctl">
      <aside className="ctl__rail">
        <p className="ctl__brand">ajustes</p>
        {NAV.map((n) => (
          <button
            key={n.id}
            type="button"
            className={`ctl__nav${section === n.id ? " is-on" : ""}`}
            onClick={() => setSection(n.id)}
          >
            <span aria-hidden>{n.glyph}</span>
            {n.label}
          </button>
        ))}
        <button type="button" className="ctl__sync" onClick={() => void reload()}>
          sync
        </button>
      </aside>

      <div className="ctl__stage">
        {err ? <p className="ctl__err">{err}</p> : null}

        {section === "mapa" && (
          <section className="ctl__panel">
            <header className="ctl__hero">
              <h2>mapa do SO</h2>
              <p>Um olhar — o que está vivo agora.</p>
            </header>
            <div className="ctl__meters">
              <Meter label="nervos" value={`${liveCount}/${connectors.length || "—"}`} tip="live+ready" />
              <Meter label="agentes" value={String(pulse?.ecc_agents ?? "—")} tip="ECC" />
              <Meter label="skills" value={String(pulse?.ecc_skills ?? "—")} tip="ECC" />
              <Meter
                label="harness"
                value={harness?.active || pulse?.harness?.active ? "on" : "off"}
                tip="agentic"
                hot={!!(harness?.active || pulse?.harness?.active)}
              />
            </div>
            <div className="ctl__constellation">
              <Node name="Jev" status={pulse?.jev?.status} detail={pulse?.jev?.model} />
              <Node name="OpenAI" status={pulse?.llm?.openai ? "live" : "off"} detail={pulse?.llm?.openai_model} />
              <Node name="Claude" status={pulse?.llm?.claude ? "live" : "off"} detail={pulse?.llm?.claude_model} />
              <Node name="Grok" status={pulse?.llm?.xai ? "live" : "off"} detail={pulse?.llm?.xai_model} />
              <Node name="Ollama" status={pulse?.llm?.ollama ? "live" : "off"} detail={pulse?.llm?.ollama_model} />
              <Node name="Notion" status={pulse?.notion} />
              <Node name="OpenRAG" status={pulse?.openrag?.status} detail={pulse?.openrag?.base_url || undefined} />
              <Node
                name="Grok Bot"
                status={pulse?.bridges?.grokbot?.status}
                detail={pulse?.bridges?.grokbot?.webhook_configured ? "webhook" : undefined}
              />
            </div>
            <p className="ctl__foot">
              Assinaturas em <code>ajustes → assinaturas</code> · secrets em <code>/root/veu/engine/.env</code>
            </p>
          </section>
        )}

        {section === "assinaturas" && (
          <section className="ctl__panel">
            <header className="ctl__hero">
              <h2>assinaturas</h2>
              <p>
                Cada IA aceita <strong>API key</strong> e/ou <strong>assinatura de conta</strong>
                {" "}(ChatGPT, Claude.ai, Grok). Os dois caminhos podem ficar ligados ao mesmo tempo.
              </p>
            </header>
            <div className="ctl__subs">
              {(subs.length
                ? subs
                : ([
                    {
                      id: "openai",
                      name: "OpenAI",
                      product: "ChatGPT",
                      status: "ready",
                      configured: false,
                      key_env: "OPENAI_API_KEY",
                      model_env: "VEU_OPENAI_MODEL",
                      model: "gpt-5.4-nano",
                      key_masked: "",
                      hint: "",
                      modes: {
                        api_key: {
                          available: true,
                          configured: false,
                          key_env: "OPENAI_API_KEY",
                          key_masked: "",
                          hint: "platform.openai.com → API keys",
                        },
                        subscription: {
                          available: true,
                          status: "off",
                          configured: false,
                          login_url: "https://chatgpt.com/auth/login",
                          hint: "ChatGPT Plus / Team — login no browser",
                        },
                      },
                    },
                    {
                      id: "claude",
                      name: "Claude",
                      product: "Claude.ai",
                      status: "ready",
                      configured: false,
                      key_env: "ANTHROPIC_API_KEY",
                      model_env: "VEU_CLAUDE_MODEL",
                      model: "claude-sonnet-4-5",
                      key_masked: "",
                      hint: "",
                      modes: {
                        api_key: {
                          available: true,
                          configured: false,
                          key_env: "ANTHROPIC_API_KEY",
                          key_masked: "",
                          hint: "console.anthropic.com → API keys",
                        },
                        subscription: {
                          available: true,
                          status: "off",
                          configured: false,
                          login_url: "https://claude.ai/login",
                          hint: "Claude Pro / Max — login no browser",
                        },
                      },
                    },
                    {
                      id: "xai",
                      name: "Grok",
                      product: "Grok",
                      status: "ready",
                      configured: false,
                      key_env: "XAI_API_KEY",
                      model_env: "VEU_XAI_MODEL",
                      model: "grok-3-mini",
                      key_masked: "",
                      hint: "",
                      modes: {
                        api_key: {
                          available: true,
                          configured: false,
                          key_env: "XAI_API_KEY",
                          key_masked: "",
                          hint: "console.x.ai → API keys · chat em grok.com",
                        },
                        subscription: {
                          available: true,
                          status: "off",
                          configured: false,
                          login_url: "https://accounts.x.ai/sign-in",
                          hint: "Grok / X Premium — login no browser",
                        },
                      },
                    },
                  ] as SubscriptionSlot[])
              ).map((slot) => {
                const api = slot.modes?.api_key;
                const sub = slot.modes?.subscription;
                const busy = subBusy === slot.id;
                return (
                  <article key={slot.id} className="ctl__sub">
                    <header>
                      <StatusPip status={slot.configured ? "live" : slot.status === "pending" ? "ready" : "dim"} />
                      <strong>{slot.name}</strong>
                      <em>
                        {slot.auth_mode === "both"
                          ? "key + conta"
                          : slot.auth_mode === "subscription"
                            ? "conta"
                            : api?.configured
                              ? "api key"
                              : "pronta"}
                      </em>
                    </header>

                    <div className="ctl__subpath">
                      <p className="ctl__subpath-title">1 · api key</p>
                      <p className="ctl__subhint">{api?.hint || slot.hint}</p>
                      <label>
                        <span>api key</span>
                        <input
                          type="password"
                          autoComplete="off"
                          placeholder={
                            api?.key_masked
                              ? `atual · ${api.key_masked}`
                              : api?.key_env || slot.key_env
                          }
                          value={draftKeys[slot.id] || ""}
                          onChange={(e) =>
                            setDraftKeys((prev) => ({ ...prev, [slot.id]: e.target.value }))
                          }
                          disabled={busy}
                        />
                      </label>
                      <label>
                        <span>modelo</span>
                        <input
                          type="text"
                          autoComplete="off"
                          placeholder={slot.model}
                          value={draftModels[slot.id] ?? ""}
                          onChange={(e) =>
                            setDraftModels((prev) => ({ ...prev, [slot.id]: e.target.value }))
                          }
                          disabled={busy}
                        />
                      </label>
                      <div className="ctl__subactions">
                        <button
                          type="button"
                          className="ctl__subgo"
                          disabled={busy || !(draftKeys[slot.id] || "").trim()}
                          onClick={() => {
                            const key = (draftKeys[slot.id] || "").trim();
                            if (!key) return;
                            setSubBusy(slot.id);
                            setSubMsg(null);
                            void connectSubscription(
                              slot.id,
                              key,
                              (draftModels[slot.id] || "").trim() || undefined,
                            ).then((r) => {
                              setSubBusy(null);
                              if (r.ok) {
                                setDraftKeys((prev) => ({ ...prev, [slot.id]: "" }));
                                setSubMsg(`${slot.name} · API key conectada`);
                                void reload();
                              } else {
                                setSubMsg(r.error || "falha ao conectar key");
                              }
                            });
                          }}
                        >
                          {busy ? "…" : "salvar key"}
                        </button>
                        {api?.configured ? (
                          <button
                            type="button"
                            className="ctl__suboff"
                            disabled={busy}
                            onClick={() => {
                              setSubBusy(slot.id);
                              void disconnectSubscription(slot.id, "api_key").then((ok) => {
                                setSubBusy(null);
                                setSubMsg(ok ? `${slot.name} · key removida` : "falha");
                                void reload();
                              });
                            }}
                          >
                            tirar key
                          </button>
                        ) : null}
                      </div>
                    </div>

                    <div className="ctl__subpath ctl__subpath--sub">
                      <p className="ctl__subpath-title">
                        2 · assinatura · {slot.product || slot.name}
                      </p>
                      <p className="ctl__subhint">{sub?.hint}</p>
                      <p className="ctl__substatus">
                        conta ·{" "}
                        {sub?.status === "linked"
                          ? "ligada"
                          : sub?.status === "pending"
                            ? "aguardando login"
                            : "não ligada"}
                      </p>
                      <div className="ctl__subactions">
                        <button
                          type="button"
                          className="ctl__subgo"
                          disabled={busy}
                          onClick={() => {
                            setSubBusy(slot.id);
                            setSubMsg(null);
                            void linkSubscriptionAccount(
                              slot.id as "openai" | "claude" | "xai",
                            ).then((r) => {
                              setSubBusy(null);
                              if (r.ok) {
                                const login = subscriptionLoginUrl(
                                  slot.id as "openai" | "claude" | "xai",
                                  r.url,
                                );
                                openUrlNow(login);
                                setSubMsg(
                                  r.message ||
                                    `Login da assinatura · ${login}`,
                                );
                                void reload();
                              } else {
                                setSubMsg(r.error || "falha ao iniciar login");
                              }
                            });
                          }}
                        >
                          {busy ? "…" : "abrir login da assinatura"}
                        </button>
                        <button
                          type="button"
                          className="ctl__subgo"
                          disabled={busy || sub?.status === "linked"}
                          onClick={() => {
                            setSubBusy(slot.id);
                            void confirmSubscriptionAccount(slot.id).then((r) => {
                              setSubBusy(null);
                              setSubMsg(
                                r.ok
                                  ? r.message || `${slot.name} · assinatura ligada`
                                  : r.error || "falha",
                              );
                              void reload();
                            });
                          }}
                        >
                          confirmei a conta
                        </button>
                        {sub?.configured ? (
                          <button
                            type="button"
                            className="ctl__suboff"
                            disabled={busy}
                            onClick={() => {
                              setSubBusy(slot.id);
                              void disconnectSubscription(slot.id, "subscription").then((ok) => {
                                setSubBusy(null);
                                setSubMsg(ok ? `${slot.name} · conta desligada` : "falha");
                                void reload();
                              });
                            }}
                          >
                            desligar conta
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
            {subMsg ? <p className="ctl__foot">{subMsg}</p> : null}

            <article className="ctl__sub" style={{ marginTop: "1rem" }}>
              <header>
                <StatusPip status={hfLive ? "live" : "ready"} />
                <strong>Hugging Face</strong>
                <em>{hfLive ? "chat ligado" : "token hf_…"}</em>
              </header>
              <div className="ctl__subpath">
                <p className="ctl__subhint">
                  Token <code>hf_…</code> liga o chat no Véu (router.huggingface.co) e o MCP.
                </p>
                <label>
                  <span>HF_TOKEN</span>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="hf_…"
                    value={hfToken}
                    onChange={(e) => setHfToken(e.target.value)}
                    disabled={hfBusy}
                  />
                </label>
                <label>
                  <span>modelo</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder={hfModel || "Qwen/Qwen2.5-7B-Instruct"}
                    value={hfModel}
                    onChange={(e) => setHfModel(e.target.value)}
                    disabled={hfBusy}
                  />
                </label>
                <div className="ctl__subactions">
                  <button
                    type="button"
                    className="ctl__subgo"
                    disabled={hfBusy || !hfToken.trim()}
                    onClick={() => {
                      setHfBusy(true);
                      setSubMsg(null);
                      void apiFetch(`${KERNEL}/llm/keys/huggingface`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          token: hfToken.trim(),
                          model: hfModel.trim() || undefined,
                        }),
                      })
                        .then(async (r) => {
                          const j = await r.json();
                          setHfBusy(false);
                          if (j.ok) {
                            setHfToken("");
                            setHfLive(true);
                            setSubMsg(`Hugging Face · ${j.model || "ok"}`);
                            void reload();
                          } else {
                            setSubMsg(j.error || "falha HF");
                          }
                        })
                        .catch(() => {
                          setHfBusy(false);
                          setSubMsg("falha HF");
                        });
                    }}
                  >
                    {hfBusy ? "…" : "ligar Hugging Face"}
                  </button>
                </div>
              </div>
            </article>

            <article className="ctl__sub" style={{ marginTop: "1rem" }}>
              <header>
                <StatusPip status="ready" />
                <strong>Notificações push</strong>
                <em>PWA</em>
              </header>
              <div className="ctl__subpath">
                <p className="ctl__subhint">
                  Ative push neste dispositivo (aprovação, inbox, jobs).
                </p>
                <div className="ctl__subactions">
                  <button
                    type="button"
                    className="ctl__subgo"
                    disabled={pushBusy}
                    onClick={() => {
                      setPushBusy(true);
                      setPushMsg(null);
                      void (async () => {
                        try {
                          const { enablePush } = await import("../../lib/push");
                          const r = await enablePush();
                          setPushMsg(r.ok ? "push ligado neste browser" : r.error || "falha");
                          if (r.ok) {
                            await apiFetch(`${KERNEL}/push/test`, { method: "POST" });
                          }
                        } catch (e) {
                          setPushMsg(e instanceof Error ? e.message : "falha push");
                        } finally {
                          setPushBusy(false);
                        }
                      })();
                    }}
                  >
                    {pushBusy ? "…" : "ativar push neste aparelho"}
                  </button>
                </div>
                {pushMsg ? <p className="ctl__foot">{pushMsg}</p> : null}
              </div>
            </article>
          </section>
        )}

        {section === "servidores" && (
          <section className="ctl__panel">
            <header className="ctl__hero">
              <h2>servidores</h2>
              <p>
                Só hosts que <strong>você</strong> cadastrar — o Véu não varre a rede.
                Senha vai pro <code>.env</code> do kernel e aparece mascarada (como assinaturas).
              </p>
            </header>

            <article className="ctl__sub">
              <header>
                <StatusPip status="ready" />
                <strong>novo servidor</strong>
                <em>cadastro</em>
              </header>
              <div className="ctl__subpath">
                <label>
                  <span>nome</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="produção · ch8"
                    value={draftSrv.name}
                    onChange={(e) => setDraftSrv((d) => ({ ...d, name: e.target.value }))}
                  />
                </label>
                <label>
                  <span>host</span>
                  <input
                    type="text"
                    autoComplete="off"
                    placeholder="IP ou hostname que você informa"
                    value={draftSrv.host}
                    onChange={(e) => setDraftSrv((d) => ({ ...d, host: e.target.value }))}
                  />
                </label>
                <div className="ctl__srvrow">
                  <label>
                    <span>porta</span>
                    <input
                      type="text"
                      autoComplete="off"
                      value={draftSrv.port}
                      onChange={(e) => setDraftSrv((d) => ({ ...d, port: e.target.value }))}
                    />
                  </label>
                  <label>
                    <span>usuário</span>
                    <input
                      type="text"
                      autoComplete="off"
                      value={draftSrv.username}
                      onChange={(e) => setDraftSrv((d) => ({ ...d, username: e.target.value }))}
                    />
                  </label>
                </div>
                <label>
                  <span>senha ssh</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    placeholder="grava no .env · nunca volta em claro"
                    value={draftSrv.password}
                    onChange={(e) => setDraftSrv((d) => ({ ...d, password: e.target.value }))}
                  />
                </label>
                <div className="ctl__subactions">
                  <button
                    type="button"
                    className="ctl__subgo"
                    disabled={srvBusy === "new" || !draftSrv.host.trim()}
                    onClick={() => {
                      const host = draftSrv.host.trim();
                      if (!host) {
                        setSrvMsg("informe o host do seu servidor");
                        return;
                      }
                      setSrvBusy("new");
                      setSrvMsg(null);
                      setSrvDetail(null);
                      void upsertServer({
                        name: draftSrv.name.trim() || host,
                        host,
                        port: Number(draftSrv.port) || 22,
                        username: draftSrv.username.trim() || "root",
                        password: draftSrv.password.trim() || undefined,
                      }).then((r) => {
                        setSrvBusy(null);
                        if (r.ok) {
                          setDraftSrv({
                            name: "",
                            host: "",
                            port: "22",
                            username: "root",
                            password: "",
                            notes: "",
                          });
                          setSrvMsg(
                            r.server?.has_secret
                              ? `${r.server.name} · cadastrado · senha em ${r.server.secret_env}`
                              : `${r.server?.name || host} · cadastrado · falta senha para testar`,
                          );
                          void reload();
                        } else {
                          setSrvMsg(r.error || "falha ao cadastrar");
                        }
                      });
                    }}
                  >
                    {srvBusy === "new" ? "…" : "salvar"}
                  </button>
                </div>
              </div>
            </article>

            <div className="ctl__subs">
              {servers.length === 0 ? (
                <p className="ctl__placeholder">nenhum servidor ainda — cadastre o host acima</p>
              ) : (
                servers.map((slot) => {
                  const busy = srvBusy === slot.id;
                  return (
                    <article key={slot.id} className="ctl__sub">
                      <header>
                        <StatusPip
                          status={
                            slot.last_status === "ok"
                              ? "live"
                              : slot.last_status === "error"
                                ? "ready"
                                : slot.has_secret
                                  ? "ready"
                                  : "dim"
                          }
                        />
                        <strong>{slot.name}</strong>
                        <em>
                          {slot.host}:{slot.port} · {slot.username}
                        </em>
                      </header>
                      <p className="ctl__subhint">
                        env · <code>{slot.secret_env}</code>
                        {slot.secret_masked
                          ? ` · atual · ${slot.secret_masked}`
                          : " · sem senha"}
                        {slot.last_status && slot.last_status !== "unknown"
                          ? ` · último teste · ${slot.last_status}`
                          : ""}
                      </p>
                      <div className="ctl__subpath">
                        <label>
                          <span>nova senha</span>
                          <input
                            type="password"
                            autoComplete="new-password"
                            placeholder={
                              slot.secret_masked
                                ? `atual · ${slot.secret_masked}`
                                : "informe a senha ssh"
                            }
                            value={draftSrvPass[slot.id] || ""}
                            onChange={(e) =>
                              setDraftSrvPass((prev) => ({
                                ...prev,
                                [slot.id]: e.target.value,
                              }))
                            }
                            disabled={busy}
                          />
                        </label>
                        <div className="ctl__subactions">
                          <button
                            type="button"
                            className="ctl__subgo"
                            disabled={busy || !(draftSrvPass[slot.id] || "").trim()}
                            onClick={() => {
                              const password = (draftSrvPass[slot.id] || "").trim();
                              if (!password) return;
                              setSrvBusy(slot.id);
                              void upsertServer({
                                id: slot.id,
                                name: slot.name,
                                host: slot.host,
                                port: slot.port,
                                username: slot.username,
                                password,
                              }).then((r) => {
                                setSrvBusy(null);
                                if (r.ok) {
                                  setDraftSrvPass((prev) => ({ ...prev, [slot.id]: "" }));
                                  setSrvMsg(`${slot.name} · senha atualizada no .env`);
                                  void reload();
                                } else {
                                  setSrvMsg(r.error || "falha");
                                }
                              });
                            }}
                          >
                            salvar senha
                          </button>
                          <button
                            type="button"
                            className="ctl__subgo"
                            disabled={busy}
                            onClick={() => {
                              if (!slot.has_secret) {
                                setSrvMsg("senha em falta — grave acima antes de testar");
                                return;
                              }
                              setSrvBusy(slot.id);
                              setSrvDetail(null);
                              void testServer(slot.id).then((r) => {
                                setSrvBusy(null);
                                if (r.ok && r.probe) {
                                  const p = r.probe;
                                  setSrvMsg(`${slot.name} · conexão ok`);
                                  setSrvDetail(
                                    [
                                      p.hostname && `host ${p.hostname}`,
                                      p.uname,
                                      p.uptime,
                                      p.mem && `mem ${p.mem}`,
                                      p.disk && `disco ${p.disk}`,
                                      p.ip && `ip ${p.ip}`,
                                    ]
                                      .filter(Boolean)
                                      .join("\n"),
                                  );
                                  void reload();
                                } else {
                                  setSrvMsg(r.error || "teste falhou");
                                }
                              });
                            }}
                          >
                            {busy ? "…" : "testar"}
                          </button>
                          <button
                            type="button"
                            className="ctl__subgo"
                            disabled={busy}
                            onClick={() => {
                              if (!slot.has_secret) {
                                setSrvMsg("senha em falta — grave acima");
                                return;
                              }
                              setSrvBusy(slot.id);
                              void fetchServerSites(slot.id).then((r) => {
                                setSrvBusy(null);
                                if (!r.ok) {
                                  setSrvMsg(r.error || "falha ao listar sites");
                                  return;
                                }
                                const lines = [
                                  ...(r.sites || []).map(
                                    (s) =>
                                      `${s.source} · ${s.name}${s.status ? ` · ${s.status}` : ""}`,
                                  ),
                                  ...Object.entries(r.services || {}).map(
                                    ([k, v]) => `svc · ${k}=${v}`,
                                  ),
                                ];
                                setSrvMsg(
                                  `${slot.name} · ${r.sites?.length || 0} site(s)`,
                                );
                                setSrvDetail(lines.join("\n") || "nenhum site detectado");
                              });
                            }}
                          >
                            sites
                          </button>
                          <button
                            type="button"
                            className="ctl__subgo"
                            disabled={busy}
                            onClick={() => {
                              if (!slot.has_secret) {
                                setSrvMsg("senha em falta — grave acima");
                                return;
                              }
                              setSrvBusy(slot.id);
                              void fetchServerMaintenance(slot.id).then((r) => {
                                setSrvBusy(null);
                                if (!r.ok) {
                                  setSrvMsg(r.error || "falha na manutenção");
                                  return;
                                }
                                setSrvMsg(`${slot.name} · status de manutenção`);
                                setSrvDetail(
                                  [
                                    r.uptime && `uptime · ${r.uptime}`,
                                    r.disk && `disco · ${r.disk}`,
                                    r.mem && `mem · ${r.mem}`,
                                    r.updates && `updates · ${r.updates}`,
                                    r.veu_units?.length
                                      ? `veu · ${r.veu_units.join(" ")}`
                                      : "",
                                    r.health_raw && `health · ${r.health_raw}`,
                                  ]
                                    .filter(Boolean)
                                    .join("\n"),
                                );
                              });
                            }}
                          >
                            manutenção
                          </button>
                          <button
                            type="button"
                            className="ctl__suboff"
                            disabled={busy}
                            onClick={() => {
                              setSrvBusy(slot.id);
                              void deleteServer(slot.id).then((ok) => {
                                setSrvBusy(null);
                                setSrvMsg(ok ? `${slot.name} · removido` : "falha");
                                setSrvDetail(null);
                                void reload();
                              });
                            }}
                          >
                            remover
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })
              )}
            </div>
            {srvMsg ? <p className="ctl__foot">{srvMsg}</p> : null}
            {srvDetail ? <pre className="ctl__srvout">{srvDetail}</pre> : null}
          </section>
        )}

        {section === "mcp" && (
          <section className="ctl__panel">
            <header className="ctl__hero">
              <h2>MCP</h2>
              <p>
                Cole o JSON (Cursor/Claude) — o Véu configura sozinho: secrets no{" "}
                <code>.env</code>, probe das tools e nervo live.
              </p>
            </header>
            <label className="ctl__mcplabel">
              <span>JSON</span>
              <textarea
                className="ctl__mcpjson"
                rows={10}
                spellCheck={false}
                value={mcpJson}
                onChange={(e) => setMcpJson(e.target.value)}
              />
            </label>
            <div className="ctl__subactions">
              <button
                type="button"
                className="ctl__subgo"
                disabled={mcpBusy === "import"}
                onClick={() => {
                  let parsed: unknown;
                  try {
                    parsed = JSON.parse(mcpJson);
                  } catch {
                    setMcpMsg("JSON inválido");
                    return;
                  }
                  setMcpBusy("import");
                  setMcpMsg(null);
                  void importMcpJson(parsed, true).then((r) => {
                    setMcpBusy(null);
                    setMcpMsg(r.ok ? r.message || "MCP ligado" : r.error || "falha");
                    if (r.ok) void reload();
                  });
                }}
              >
                {mcpBusy === "import" ? "…" : "importar e ligar"}
              </button>
            </div>
            {mcpMsg ? <p className="ctl__foot">{mcpMsg}</p> : null}
            <div className="ctl__subs" style={{ marginTop: "0.75rem" }}>
              {mcpServers.length === 0 ? (
                <p className="ctl__placeholder">nenhum MCP ainda — cole o JSON acima</p>
              ) : (
                mcpServers.map((s) => (
                  <article key={s.id} className="ctl__sub">
                    <header>
                      <StatusPip status={s.status === "live" ? "live" : s.status === "error" ? "ready" : "dim"} />
                      <strong>{s.name}</strong>
                      <em>
                        {s.transport}
                        {s.url ? ` · ${s.url}` : s.command ? ` · ${s.command}` : ""}
                        {` · ${s.tool_count ?? 0} tools`}
                      </em>
                    </header>
                    {s.last_error ? (
                      <p className="ctl__subhint">{s.last_error}</p>
                    ) : s.tools?.length ? (
                      <p className="ctl__subhint">
                        {(s.tools || [])
                          .slice(0, 8)
                          .map((t) => t.name)
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    ) : null}
                    <div className="ctl__subactions">
                      <button
                        type="button"
                        className="ctl__subgo"
                        disabled={mcpBusy === s.id}
                        onClick={() => {
                          setMcpBusy(s.id);
                          void probeMcpServer(s.id).then((r) => {
                            setMcpBusy(null);
                            setMcpMsg(r.ok ? `${s.name} · live` : r.error || "probe falhou");
                            void reload();
                          });
                        }}
                      >
                        probe
                      </button>
                      <button
                        type="button"
                        className="ctl__subgo"
                        disabled={mcpBusy === s.id}
                        onClick={() => {
                          setMcpBusy(s.id);
                          void deleteMcpServer(s.id).then((ok) => {
                            setMcpBusy(null);
                            setMcpMsg(ok ? `${s.name} removido` : "falha ao remover");
                            void reload();
                          });
                        }}
                      >
                        remover
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
            <style>{`
              .ctl__mcplabel { display: flex; flex-direction: column; gap: 0.35rem; }
              .ctl__mcplabel span { font-size: 0.75rem; color: #9aa; }
              .ctl__mcpjson {
                width: 100%;
                font-family: ui-monospace, monospace;
                font-size: 0.78rem;
                border-radius: 6px;
                border: 1px solid rgba(255,255,255,0.12);
                background: rgba(0,0,0,0.35);
                color: #e8ebe6;
                padding: 0.65rem;
                resize: vertical;
              }
            `}</style>
          </section>
        )}

        {section === "nervos" && (
          <section className="ctl__panel ctl__panel--split">
            <div className="ctl__nerves">
              <header className="ctl__hero">
                <h2>nervos</h2>
                <p>Toque um pra detalhe — agrupados por papel.</p>
              </header>
              <div className="ctl__groups">
                {grouped.map((g) => (
                  <div key={g.id} className="ctl__group">
                    <h3>{g.label}</h3>
                    <div className="ctl__tiles">
                      {g.items.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          className={`ctl__tile${picked === c.id ? " is-on" : ""}`}
                          onClick={() => setPicked(c.id)}
                        >
                          <StatusPip status={c.status} />
                          <strong>{c.name}</strong>
                          <span>{c.status}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <aside className="ctl__inspect">
              {selected ? (
                <>
                  <h3>{selected.name}</h3>
                  <dl>
                    <div>
                      <dt>status</dt>
                      <dd>
                        <StatusPip status={selected.status} /> {selected.status}
                      </dd>
                    </div>
                    <div>
                      <dt>kind</dt>
                      <dd>{selected.kind}</dd>
                    </div>
                    <div>
                      <dt>surface</dt>
                      <dd>{selected.surface}</dd>
                    </div>
                  </dl>
                  {selected.capabilities?.length ? (
                    <p className="ctl__caps">{selected.capabilities.slice(0, 8).join(" · ")}</p>
                  ) : null}
                  {selected.notes ? <p className="ctl__caps">{selected.notes}</p> : null}
                </>
              ) : (
                <p className="ctl__placeholder">escolha um nervo</p>
              )}
            </aside>
          </section>
        )}

        {section === "modelos" && (
          <section className="ctl__panel">
            <header className="ctl__hero">
              <h2>modelos</h2>
              <p>Jev decide o caminho; assinaturas falam; Ollama fica no host.</p>
            </header>
            <div className="ctl__modelgrid">
              <ModelCard title="Jev" status={pulse?.jev?.status} body={pulse?.jev?.model || "jev-1.13.0"} role="roteador" />
              <ModelCard
                title="OpenAI"
                status={pulse?.llm?.openai ? "live" : "off"}
                body={pulse?.llm?.openai_model || "—"}
                role="assinatura"
              />
              <ModelCard
                title="Claude"
                status={pulse?.llm?.claude ? "live" : "off"}
                body={pulse?.llm?.claude_model || "—"}
                role="assinatura"
              />
              <ModelCard
                title="Grok"
                status={pulse?.llm?.xai ? "live" : "off"}
                body={pulse?.llm?.xai_model || "—"}
                role="assinatura"
              />
              <ModelCard
                title="Ollama"
                status={pulse?.llm?.ollama ? "live" : "off"}
                body={pulse?.llm?.ollama_model || "—"}
                role="local"
              />
              <ModelCard
                title="OpenRAG"
                status={pulse?.openrag?.status}
                body={pulse?.openrag?.base_url || "—"}
                role="retrieval"
              />
            </div>
          </section>
        )}

        {section === "musculo" && (
          <section className="ctl__panel">
            <header className="ctl__hero">
              <h2>músculo</h2>
              <p>ECC + harness — o chat ativa sozinho quando a intenção é agentic.</p>
            </header>
            <div className="ctl__meters">
              <Meter label="agentes" value={String(pulse?.ecc_agents ?? "—")} tip="vendor ECC" />
              <Meter label="skills" value={String(pulse?.ecc_skills ?? "—")} tip="vendor ECC" />
              <Meter
                label="sessão"
                value={harness?.active || pulse?.harness?.active ? "ativa" : "quieta"}
                tip="harness"
                hot={!!(harness?.active || pulse?.harness?.active)}
              />
            </div>
            <div className="ctl__recent">
              {recent.length === 0 ? (
                <p className="ctl__placeholder">nenhuma sessão recente — peça algo agentic no chat</p>
              ) : (
                recent.slice(0, 4).map((r) => (
                  <div key={r.id} className="ctl__session">
                    <StatusPip status="ready" />
                    <div>
                      <strong>{r.route}</strong>
                      <span>{(r.tools || []).slice(0, 5).join(" · ") || r.id}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        )}

        {section === "politicas" && (
          <section className="ctl__panel">
            <header className="ctl__hero">
              <h2>políticas</h2>
              <p>Respiração de autonomia — a mesma da barra superior.</p>
            </header>
            <div className="ctl__breath">
              {(
                [
                  { id: "guided" as const, label: "guiado", blurb: "plano interno; ações delicadas pedem OK" },
                  { id: "semi" as const, label: "semi", blurb: "executa o comum; só pede o de alto risco" },
                  { id: "free" as const, label: "livre", blurb: "autonomia até o teto; sem gastar/apagar produção sozinho" },
                  {
                    id: "autonomous" as const,
                    label: "autônomo",
                    blurb: "percorre apps e agentes, prepara respostas/ações e você escolhe o que marcar como feito",
                  },
                ] as const
              ).map((b) => (
                <button
                  key={b.id}
                  type="button"
                  className={`ctl__breathcard${breath === b.id ? " is-on" : ""}`}
                  onClick={() => onBreath(b.id)}
                >
                  <strong>{b.label}</strong>
                  <span>{b.blurb}</span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      <style>{`
        .ctl {
          height: 100%;
          display: grid;
          grid-template-columns: 7.2rem 1fr;
          min-height: 0;
          overflow: hidden;
          color: var(--mist);
          background:
            radial-gradient(70% 50% at 100% 0%, rgba(127,231,212,0.05), transparent 50%),
            radial-gradient(60% 40% at 0% 100%, rgba(232,194,122,0.05), transparent 45%);
        }
        .ctl__rail {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
          padding: 0.75rem 0.45rem;
          border-right: 1px solid rgba(232,194,122,0.12);
          background: rgba(7,9,12,0.4);
          min-height: 0;
        }
        .ctl__brand {
          margin: 0 0.35rem 0.55rem;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.22em;
          color: var(--signal);
        }
        .ctl__nav, .ctl__sync {
          border: 0;
          background: transparent;
          color: var(--mist-dim);
          display: flex;
          align-items: center;
          gap: 0.4rem;
          text-align: left;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.06em;
          padding: 0.45rem 0.4rem;
          cursor: pointer;
          border-radius: 0.25rem;
        }
        .ctl__nav span { color: var(--filament); opacity: 0.55; width: 0.9rem; }
        .ctl__nav.is-on {
          color: var(--filament);
          background: rgba(232,194,122,0.1);
        }
        .ctl__nav.is-on span { opacity: 1; }
        .ctl__sync {
          margin-top: auto;
          color: var(--signal);
          border-top: 1px solid rgba(232,194,122,0.1);
          padding-top: 0.65rem;
        }
        .ctl__stage {
          min-height: 0;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }
        .ctl__panel {
          flex: 1;
          min-height: 0;
          padding: 0.85rem 1rem 0.9rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          overflow: hidden;
        }
        .ctl__panel--split {
          display: grid;
          grid-template-columns: 1fr 11.5rem;
          gap: 0.75rem;
          padding-right: 0.75rem;
        }
        .ctl__hero h2 {
          margin: 0;
          font-family: var(--font-display);
          font-size: 1.25rem;
          color: var(--filament);
          font-weight: 700;
        }
        .ctl__hero p {
          margin: 0.2rem 0 0;
          font-weight: 300;
          font-size: 0.82rem;
          color: var(--mist-dim);
        }
        .ctl__meters {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 0.45rem;
        }
        .ctl__meter {
          padding: 0.55rem 0.6rem;
          border: 1px solid rgba(232,194,122,0.12);
          background: rgba(7,9,12,0.35);
        }
        .ctl__meter.is-hot {
          border-color: rgba(127,231,212,0.35);
        }
        .ctl__meter span {
          display: block;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.12em;
          color: var(--mist-dim);
        }
        .ctl__meter strong {
          display: block;
          margin-top: 0.2rem;
          font-family: var(--font-display);
          font-size: 1.15rem;
          color: var(--mist);
          font-weight: 700;
        }
        .ctl__meter em {
          display: block;
          margin-top: 0.1rem;
          font-style: normal;
          font-size: 0.62rem;
          color: var(--mist-dim);
        }
        .ctl__constellation {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 0.4rem;
          flex: 1;
          min-height: 0;
          align-content: start;
        }
        .ctl__node {
          display: grid;
          gap: 0.15rem;
          padding: 0.55rem 0.55rem 0.5rem;
          border: 1px solid rgba(232,194,122,0.1);
          background: rgba(13,18,24,0.55);
          min-width: 0;
        }
        .ctl__node header {
          display: flex;
          align-items: center;
          gap: 0.35rem;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.04em;
        }
        .ctl__node p {
          margin: 0;
          font-size: 0.65rem;
          color: var(--mist-dim);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ctl__pip {
          width: 0.38rem;
          height: 0.38rem;
          border-radius: 50%;
          display: inline-block;
          background: rgba(236,242,248,0.25);
          flex-shrink: 0;
        }
        .ctl__pip.is-live { background: var(--filament); box-shadow: 0 0 7px var(--filament); }
        .ctl__pip.is-ready { background: var(--signal); }
        .ctl__pip.is-dim { background: rgba(236,242,248,0.22); }
        .ctl__foot {
          margin: 0;
          font-size: 0.68rem;
          color: var(--mist-dim);
        }
        .ctl__foot code {
          font-family: var(--font-mono);
          font-size: 0.62rem;
          color: var(--signal);
        }
        .ctl__subs {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 0.65rem;
          min-height: 0;
          overflow: auto;
          align-content: start;
        }
        @media (max-width: 900px) {
          .ctl__subs { grid-template-columns: 1fr; }
        }
        .ctl__sub {
          display: grid;
          gap: 0.45rem;
          padding: 0.75rem 0.8rem;
          border: 1px solid rgba(232,194,122,0.18);
          background: linear-gradient(180deg, rgba(232,194,122,0.06), rgba(7,9,12,0.25));
          min-width: 0;
        }
        .ctl__sub header {
          display: flex;
          align-items: center;
          gap: 0.4rem;
        }
        .ctl__sub header strong {
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 1.05rem;
          color: var(--filament);
        }
        .ctl__sub header em {
          margin-left: auto;
          font-style: normal;
          font-family: var(--font-mono);
          font-size: 0.6rem;
          letter-spacing: 0.1em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .ctl__subhint {
          margin: 0;
          font-size: 0.7rem;
          color: var(--mist-dim);
          line-height: 1.35;
        }
        .ctl__subpath {
          display: grid;
          gap: 0.4rem;
          padding-top: 0.45rem;
          border-top: 1px solid rgba(236,242,248,0.08);
        }
        .ctl__subpath--sub {
          margin-top: 0.15rem;
          border-top-color: rgba(127,231,212,0.18);
        }
        .ctl__subpath-title {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.6rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .ctl__substatus {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.06em;
          color: var(--filament);
          text-transform: lowercase;
        }
        .ctl__hero strong { color: var(--filament); font-weight: 500; }
        .ctl__sub label {
          display: grid;
          gap: 0.2rem;
        }
        .ctl__sub label span {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.12em;
          color: var(--signal);
          text-transform: lowercase;
        }
        .ctl__sub input {
          border: 1px solid rgba(127,231,212,0.2);
          background: rgba(7,9,12,0.55);
          color: var(--mist);
          padding: 0.45rem 0.55rem;
          font-family: var(--font-mono);
          font-size: 0.72rem;
          outline: none;
        }
        .ctl__sub input:focus {
          border-color: rgba(232,194,122,0.55);
        }
        .ctl__subactions {
          display: flex;
          gap: 0.45rem;
          margin-top: 0.15rem;
        }
        .ctl__subgo, .ctl__suboff {
          border: 1px solid rgba(232,194,122,0.4);
          background: transparent;
          color: var(--filament);
          font-family: var(--font-mono);
          font-size: 0.68rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          padding: 0.45rem 0.7rem;
          cursor: pointer;
        }
        .ctl__subgo:hover:not(:disabled) {
          background: var(--filament);
          color: var(--ink);
        }
        .ctl__subgo:disabled { opacity: 0.35; cursor: default; }
        .ctl__suboff {
          border-color: rgba(236,242,248,0.18);
          color: var(--mist-dim);
        }
        .ctl__srvrow {
          display: grid;
          grid-template-columns: 5rem 1fr;
          gap: 0.45rem;
        }
        .ctl__srvout {
          margin: 0;
          padding: 0.55rem 0.65rem;
          max-height: 9rem;
          overflow: auto;
          font-family: var(--font-mono);
          font-size: 0.68rem;
          line-height: 1.45;
          color: var(--mist);
          background: rgba(7,9,12,0.55);
          border: 1px solid rgba(232,194,122,0.12);
          white-space: pre-wrap;
          word-break: break-word;
        }
        .ctl__nerves {
          min-height: 0;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          gap: 0.55rem;
        }
        .ctl__groups {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.55rem 0.7rem;
          flex: 1;
          min-height: 0;
          overflow: auto;
          scrollbar-width: thin;
          scrollbar-color: rgba(232,194,122,0.25) transparent;
        }
        .ctl__group h3 {
          margin: 0 0 0.35rem;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.16em;
          color: var(--signal);
          font-weight: 500;
        }
        .ctl__tiles {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.3rem;
        }
        .ctl__tile {
          border: 1px solid rgba(232,194,122,0.12);
          background: rgba(7,9,12,0.35);
          color: var(--mist);
          display: grid;
          grid-template-columns: 0.4rem 1fr;
          grid-template-rows: auto auto;
          column-gap: 0.4rem;
          padding: 0.4rem 0.45rem;
          text-align: left;
          cursor: pointer;
          min-width: 0;
        }
        .ctl__tile .ctl__pip { grid-row: 1 / span 2; align-self: center; }
        .ctl__tile strong {
          font-family: var(--font-mono);
          font-size: 0.68rem;
          font-weight: 500;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ctl__tile span {
          font-size: 0.58rem;
          color: var(--mist-dim);
        }
        .ctl__tile.is-on {
          border-color: rgba(232,194,122,0.45);
          background: rgba(232,194,122,0.08);
        }
        .ctl__inspect {
          border-left: 1px solid rgba(232,194,122,0.12);
          padding: 0.75rem 0.65rem;
          min-height: 0;
          overflow: hidden;
          background: rgba(7,9,12,0.28);
        }
        .ctl__inspect h3 {
          margin: 0 0 0.65rem;
          font-family: var(--font-display);
          font-size: 1rem;
          color: var(--filament);
        }
        .ctl__inspect dl {
          margin: 0;
          display: grid;
          gap: 0.45rem;
        }
        .ctl__inspect dt {
          font-family: var(--font-mono);
          font-size: 0.55rem;
          letter-spacing: 0.12em;
          color: var(--mist-dim);
        }
        .ctl__inspect dd {
          margin: 0.1rem 0 0;
          font-size: 0.78rem;
          display: flex;
          align-items: center;
          gap: 0.35rem;
        }
        .ctl__caps {
          margin: 0.7rem 0 0;
          font-size: 0.68rem;
          color: var(--mist-dim);
          line-height: 1.4;
        }
        .ctl__placeholder {
          margin: 1.2rem 0 0;
          font-size: 0.75rem;
          color: var(--mist-dim);
          font-weight: 300;
        }
        .ctl__modelgrid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.5rem;
          flex: 1;
          align-content: start;
        }
        .ctl__mcard {
          padding: 0.7rem 0.75rem;
          border: 1px solid rgba(232,194,122,0.12);
          background: rgba(7,9,12,0.35);
          display: grid;
          gap: 0.25rem;
          min-width: 0;
        }
        .ctl__mcard header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.5rem;
        }
        .ctl__mcard strong {
          font-family: var(--font-display);
          font-size: 0.95rem;
          color: var(--filament);
        }
        .ctl__mcard em {
          font-style: normal;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.1em;
          color: var(--mist-dim);
        }
        .ctl__mcard p {
          margin: 0;
          font-size: 0.78rem;
          color: var(--mist);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ctl__recent {
          display: grid;
          gap: 0.4rem;
          flex: 1;
          align-content: start;
          min-height: 0;
        }
        .ctl__session {
          display: grid;
          grid-template-columns: 0.4rem 1fr;
          gap: 0.5rem;
          align-items: start;
          padding: 0.45rem 0;
          border-bottom: 1px solid rgba(232,194,122,0.08);
        }
        .ctl__session strong {
          display: block;
          font-family: var(--font-mono);
          font-size: 0.72rem;
          font-weight: 500;
        }
        .ctl__session span {
          display: block;
          margin-top: 0.15rem;
          font-size: 0.68rem;
          color: var(--mist-dim);
        }
        .ctl__breath {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr;
          gap: 0.5rem;
          flex: 1;
          align-content: start;
        }
        .ctl__breathcard {
          border: 1px solid rgba(232,194,122,0.16);
          background: rgba(7,9,12,0.35);
          color: var(--mist);
          text-align: left;
          padding: 0.85rem 0.75rem;
          cursor: pointer;
          display: grid;
          gap: 0.4rem;
          min-height: 7.5rem;
          transition: border-color 160ms ease, background 160ms ease;
        }
        .ctl__breathcard strong {
          font-family: var(--font-display);
          font-size: 1.05rem;
          color: var(--mist-dim);
        }
        .ctl__breathcard span {
          font-size: 0.75rem;
          font-weight: 300;
          color: var(--mist-dim);
          line-height: 1.4;
        }
        .ctl__breathcard.is-on {
          border-color: rgba(232,194,122,0.55);
          background: rgba(232,194,122,0.08);
        }
        .ctl__breathcard.is-on strong { color: var(--filament); }
        .ctl__err {
          margin: 0.5rem 1rem 0;
          color: #e8a07a;
          font-size: 0.78rem;
        }
        @media (max-width: 700px) {
          .ctl { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
          .ctl__rail {
            flex-direction: row;
            flex-wrap: wrap;
            border-right: 0;
            border-bottom: 1px solid rgba(232,194,122,0.12);
          }
          .ctl__sync { margin-top: 0; border-top: 0; }
          .ctl__panel--split { grid-template-columns: 1fr; }
          .ctl__inspect { border-left: 0; border-top: 1px solid rgba(232,194,122,0.12); }
          .ctl__meters, .ctl__constellation { grid-template-columns: 1fr 1fr; }
          .ctl__breath { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}

function Meter({
  label,
  value,
  tip,
  hot,
}: {
  label: string;
  value: string;
  tip: string;
  hot?: boolean;
}) {
  return (
    <div className={`ctl__meter${hot ? " is-hot" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{tip}</em>
    </div>
  );
}

function Node({
  name,
  status,
  detail,
}: {
  name: string;
  status?: string | boolean | null;
  detail?: string | null;
}) {
  return (
    <div className="ctl__node">
      <header>
        <StatusPip status={status} />
        {name}
      </header>
      <p>{detail || (typeof status === "string" ? status : status ? "live" : "off")}</p>
    </div>
  );
}

function ModelCard({
  title,
  status,
  body,
  role,
}: {
  title: string;
  status?: string | boolean | null;
  body: string;
  role: string;
}) {
  return (
    <div className="ctl__mcard">
      <header>
        <strong>{title}</strong>
        <StatusPip status={status} />
      </header>
      <em>{role}</em>
      <p title={body}>{body}</p>
    </div>
  );
}

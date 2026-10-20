import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { apiFetch, KERNEL } from "../../lib/kernel";
import {
  CONSOLE_ACTIONS,
  CONSOLE_APPS,
  fetchRuflo,
  fetchRuosBoard,
  fetchRuosKeys,
  rufloPost,
  ruosPost,
  type RuosBoard,
  type RuosDesktop,
  type RuosKeys,
  type RufloSnapshot,
} from "../../lib/ruos";

type Tab = "desktops" | "keys" | "terminal" | "swarms" | "ruflo";
type SwarmPane = "overview" | "deploy" | "operate" | "activity";
type AddMode = null | "cloud" | "mac" | "linux" | "rustdesk" | "snapshots";
type DeployStep = 1 | 2 | 3 | 4 | 5;

type SwarmTemplate = {
  id: string;
  icon: string;
  title: string;
  blurb: string;
  topology: string;
  agents: number;
  consensus: string;
  team: Record<string, number>;
  caps: string[];
  objective: string;
};

const TEMPLATES: SwarmTemplate[] = [
  {
    id: "full-stack",
    icon: "🏗",
    title: "Full-Stack Feature",
    blurb: "Build a feature end-to-end — design, code, tests, review.",
    topology: "hierarchical",
    agents: 6,
    consensus: "raft",
    team: { coder: 2, researcher: 1, reviewer: 1, tester: 1, planner: 1 },
    caps: ["hooks", "memory", "hive"],
    objective: "Build the feature end-to-end with design, code, tests and review.",
  },
  {
    id: "code-review",
    icon: "🔍",
    title: "Code Review Swarm",
    blurb: "Multi-agent review of a PR or codebase, findings verified.",
    topology: "hierarchical",
    agents: 5,
    consensus: "raft",
    team: { reviewer: 2, researcher: 1, tester: 1, planner: 1 },
    caps: ["hooks", "security"],
    objective: "Review the PR/codebase; verify findings with evidence.",
  },
  {
    id: "deep-research",
    icon: "🔬",
    title: "Deep Research",
    blurb: "Parallel research + synthesis with cited findings.",
    topology: "mesh",
    agents: 5,
    consensus: "gossip",
    team: { researcher: 3, reviewer: 1, planner: 1 },
    caps: ["hooks", "memory", "neural"],
    objective:
      "Research the topic across sources, cross-reference findings, resolve contradictions, cite sources.",
  },
  {
    id: "security-audit",
    icon: "🛡",
    title: "Security Audit",
    blurb: "CVE scan, threat model, red/blue eval (byzantine).",
    topology: "hierarchical",
    agents: 5,
    consensus: "byzantine",
    team: { researcher: 1, reviewer: 2, tester: 1, planner: 1 },
    caps: ["security", "hooks", "memory"],
    objective: "CVE scan, threat model, red/blue evaluation with byzantine consensus.",
  },
  {
    id: "test-coverage",
    icon: "🧪",
    title: "Test Coverage Sprint",
    blurb: "Find gaps, raise coverage with TDD.",
    topology: "hierarchical",
    agents: 5,
    consensus: "raft",
    team: { tester: 2, coder: 1, reviewer: 1, planner: 1 },
    caps: ["hooks", "memory"],
    objective: "Find coverage gaps and raise them with TDD London School.",
  },
];

const TOPOLOGIES = [
  { id: "hierarchical", label: "Hierarchical", hint: "Queen-led. Best anti-drift." },
  { id: "mesh", label: "Mesh", hint: "Peer-to-peer, fault-tolerant." },
  { id: "star", label: "Star", hint: "One coordinator, many workers." },
  { id: "ring", label: "Ring", hint: "Pipeline hand-off." },
  { id: "adaptive", label: "Adaptive", hint: "Switches as the task evolves." },
];

const CAPS = [
  { id: "hive", label: "Hive-mind consensus" },
  { id: "hooks", label: "Self-learning hooks" },
  { id: "memory", label: "Vector memory" },
  { id: "neural", label: "Neural patterns" },
  { id: "metaharness", label: "MetaHarness" },
  { id: "security", label: "Security scanning" },
  { id: "autoscale", label: "Auto-scaling" },
  { id: "federation", label: "Fleet federation" },
];

type Props = { onOpenBrowser?: () => void; onOpenApp?: (app: string) => void };

export function RuosDesktopApp({ onOpenBrowser, onOpenApp }: Props) {
  const [tab, setTab] = useState<Tab>("desktops");
  const [board, setBoard] = useState<RuosBoard | null>(null);
  const [keys, setKeys] = useState<RuosKeys | null>(null);
  const [ruflo, setRuflo] = useState<RufloSnapshot | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<string>("ruos-desktop");
  const [addMode, setAddMode] = useState<AddMode>(null);
  const [enrollCmd, setEnrollCmd] = useState<string>("");
  const [enrollNotes, setEnrollNotes] = useState("");
  const [rustdeskId, setRustdeskId] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // Keys
  const [keySlot, setKeySlot] = useState("llm");
  const [keyVal, setKeyVal] = useState("");
  const [routeMode, setRouteMode] = useState("shared");
  const [keysTab, setKeysTab] = useState<
    "model" | "custom" | "website" | "mcp" | "slack" | "tailscale"
  >("model");
  const [onceToken, setOnceToken] = useState<string | null>(null);

  // Terminal / AI Console
  const [consoleIn, setConsoleIn] = useState("");
  const [consoleLog, setConsoleLog] = useState<
    { ts: number; role: "user" | "sys"; text: string }[]
  >([]);

  // Swarms
  const [swarmPane, setSwarmPane] = useState<SwarmPane>("deploy");
  const [tpl, setTpl] = useState<SwarmTemplate | null>(TEMPLATES[2]);
  const [step, setStep] = useState<DeployStep>(5);
  const [objective, setObjective] = useState(TEMPLATES[2].objective);
  const [topology, setTopology] = useState(TEMPLATES[2].topology);
  const [team, setTeam] = useState(TEMPLATES[2].team);
  const [caps, setCaps] = useState<string[]>(TEMPLATES[2].caps);
  const [maxAgents, setMaxAgents] = useState(6);
  const [deployLog, setDeployLog] = useState<string[]>([]);
  const [snaps, setSnaps] = useState<{ id: string; label: string; desktop_name?: string }[]>([]);

  const refresh = useCallback(async () => {
    const [b, k, r] = await Promise.all([
      fetchRuosBoard(q),
      fetchRuosKeys(),
      fetchRuflo(),
    ]);
    if (b) {
      setBoard(b);
      if (!b.desktops.find((d) => d.id === selected) && b.desktops[0]) {
        setSelected(b.desktops[0].id);
      }
    }
    if (k) {
      setKeys(k);
      setRouteMode(k.routing?.current || "shared");
    }
    if (r) setRuflo(r);
  }, [q, selected]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 12_000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const desk = useMemo(
    () => board?.desktops.find((d) => d.id === selected) || board?.desktops[0],
    [board, selected],
  );

  const flash = (t: string) => {
    setMsg(t);
    window.setTimeout(() => setMsg(null), 3200);
  };

  const act = async (fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(true);
    try {
      const r = (await fn()) as { ok?: boolean; error?: string; detail?: string };
      if (r && r.ok === false) flash(r.error || r.detail || "falhou");
      else flash(okMsg);
      await refresh();
      return r;
    } catch {
      flash("erro de rede");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const generateEnroll = async (platform: "linux" | "mac") => {
    setBusy(true);
    try {
      const r = await ruosPost("/ruos/enroll", { platform });
      if (r.ok) {
        setEnrollCmd(String(r.command || ""));
        setEnrollNotes(String(r.notes || ""));
        setAddMode(platform);
      } else flash(r.error || "enroll falhou");
    } finally {
      setBusy(false);
    }
  };

  const applyTemplate = (t: SwarmTemplate) => {
    setTpl(t);
    setObjective(t.objective);
    setTopology(t.topology);
    setTeam({ ...t.team });
    setCaps([...t.caps]);
    setMaxAgents(t.agents);
    setStep(5);
    setSwarmPane("deploy");
  };

  const deployPlan = useMemo(() => {
    const name = tpl?.id || "swarm";
    const teamLine = Object.entries(team)
      .filter(([, n]) => n > 0)
      .map(([role, n]) => `${n}× ${role}`)
      .join(", ");
    return [
      `swarm: ${name}`,
      `target: ${desk?.name || "desktop"}`,
      `1. ruflo init --force`,
      `2. ruflo swarm init --topology ${topology} --max-agents ${maxAgents} --strategy balanced`,
      `3. spawn team: ${teamLine || "—"}  · provider anthropic`,
      caps.includes("hooks") ? `4. ruflo hooks — self-learning enabled` : null,
      caps.includes("memory") ? `5. ruflo memory — vector store active` : null,
      `6. ruflo swarm start -o "${objective.slice(0, 72)}…" -s balanced`,
      `caps: ${caps.join(" · ") || "—"}`,
    ].filter(Boolean) as string[];
  }, [tpl, desk, topology, maxAgents, team, caps, objective]);

  const deploySwarm = async () => {
    setDeployLog(["→ authorizing Claude control…"]);
    await rufloPost("/ruflo/control", {
      level: "manage",
      approval: "auto",
      active: true,
    });
    setDeployLog((l) => [...l, "→ ruflo swarm init…"]);
    const init = await rufloPost("/ruflo/swarm/init", { topology });
    setDeployLog((l) => [
      ...l,
      init?.ok
        ? `✓ swarm active · ${topology} · ${(init.swarm?.agents || []).length} agents`
        : `✗ ${init?.error || init?.detail || "refused"}`,
    ]);
    const mission = await rufloPost("/ruflo/missions", {
      goal: objective,
      confirm: true,
    });
    setDeployLog((l) => [
      ...l,
      mission?.ok
        ? `✓ mission ${mission.mission?.id}`
        : `· mission: ${mission?.error || "skipped"}`,
      "── deployment complete (local spine) ──",
    ]);
    await refresh();
  };

  const runConsole = async () => {
    const line = consoleIn.trim();
    if (!line) return;
    setConsoleLog((l) => [...l, { ts: Date.now(), role: "user", text: line }]);
    setConsoleIn("");
    let reply = "";
    if (line.startsWith("/fleet") || line === "/status") {
      const n = board?.counts?.total ?? 0;
      reply = `fleet · ${n} desktops · selected: ${desk?.name || "—"} (${desk?.state})\n${(board?.desktops || [])
        .map((d) => `· ${d.name} · ${d.state} · ${d.kind}`)
        .join("\n")}`;
    } else if (line.startsWith("/swarm")) {
      const s = ruflo?.pulse?.swarm;
      reply = s?.active
        ? `swarm live · ${s.topology || "?"} · ${(s.agents || []).map((a) => a.role).join(", ")}`
        : "swarm idle — use Swarms → Deploy or /swarm init";
      if (line.includes("init")) {
        await rufloPost("/ruflo/control", { level: "manage", approval: "auto", active: true });
        const r = await rufloPost("/ruflo/swarm/init", { topology: "hierarchical" });
        reply = r?.ok ? `swarm init ok · ${r.swarm?.topology}` : `refused: ${r?.error}`;
        await refresh();
      }
    } else if (line.startsWith("/open")) {
      const target = line.split(/\s+/)[1] || "browser";
      if (target.includes("browser") || target === "@browser") onOpenBrowser?.();
      else onOpenApp?.(target.replace(/^@/, ""));
      reply = `opened ${target} in Véu window`;
    } else if (line.startsWith("/run ")) {
      reply = `queued on ${desk?.name || "desktop"} (JWT control):\n$ ${line.slice(5)}\n(stub local — wire RUOS_MCP for live exec)`;
    } else if (line.startsWith("@")) {
      onOpenApp?.(line.slice(1));
      reply = `app ${line}`;
    } else {
      await rufloPost("/ruflo/missions", { goal: line, confirm: true });
      reply = `ruflo · mission queued on ${desk?.name || "desktop"} · LLM: ${keys?.routing?.current || "shared"}`;
      await refresh();
    }
    setConsoleLog((l) => [...l, { ts: Date.now(), role: "sys", text: reply }]);
  };

  const stateTone = (s: string) => {
    if (s === "running" || s === "ready") return "ok";
    if (s === "asleep" || s === "stopped") return "sleep";
    if (s === "starting") return "run";
    return "bad";
  };

  return (
    <div className="ruos">
      <header className="ruos__top">
        <div className="ruos__brand">
          <img src="/ruflo/ruos-animated.svg" alt="" className="ruos__logo" />
          <div>
            <p className="ruos__kicker">ruOS · agentic desktop</p>
            <h1>a desktop that runs itself</h1>
          </div>
        </div>
        <div className="ruos__status">
          <span className="is-on">signed in</span>
          <span>MCP</span>
          <span>LLM: {keys?.routing?.current || "shared"}</span>
        </div>
      </header>

      <nav className="ruos__tabs">
        {(
          [
            ["desktops", "Desktops"],
            ["swarms", "Swarms"],
            ["terminal", "Terminal"],
            ["keys", "Keys"],
            ["ruflo", "Ruflo"],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? "is-on" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {msg ? <p className="ruos__toast">{msg}</p> : null}

      {tab === "desktops" ? (
        <div className="ruos__pane">
          <div className="ruos__toolbar">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search desktops"
              aria-label="Search desktops"
            />
            <span>
              {board?.counts?.total ?? "…"} desktops in your fleet
            </span>
          </div>

          <div className="ruos__actions">
            {(
              [
                ["cloud", "Add desktop"],
                ["snapshots", "Snapshots"],
                ["cloud", "Provision cloud desktop"],
                ["mac", "Add your Mac"],
                ["linux", "Add your Linux machine"],
                ["rustdesk", "Add via RustDesk ID"],
              ] as [AddMode, string][]
            ).map(([mode, label], i) => (
              <button
                key={`${mode}-${i}`}
                type="button"
                disabled={busy}
                onClick={() => {
                  if (mode === "mac" || mode === "linux") void generateEnroll(mode);
                  else if (mode === "snapshots") {
                    void (async () => {
                      const r = await apiFetch(`${KERNEL}/ruos/snapshots`);
                      const j = await r.json();
                      setSnaps(j.snapshots || []);
                      setAddMode("snapshots");
                    })();
                  } else setAddMode(mode);
                }}
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              disabled={busy || !desk}
              onClick={() =>
                desk && act(() => ruosPost(`/ruos/desktops/${desk.id}/reconnect`), "reconnect")
              }
            >
              Reconnect
            </button>
            <button
              type="button"
              onClick={() => {
                document.documentElement.requestFullscreen?.();
                flash("full screen");
              }}
            >
              Full screen
            </button>
          </div>

          <div className="ruos__fleet">
            {(board?.desktops || []).map((d: RuosDesktop) => (
              <motion.button
                key={d.id}
                type="button"
                className={`ruos__card is-${stateTone(d.state)}${
                  selected === d.id ? " is-sel" : ""
                }`}
                onClick={() => setSelected(d.id)}
                layout
              >
                <div className="ruos__card-h">
                  <strong>{d.name}</strong>
                  <em className={`st st-${stateTone(d.state)}`}>{d.state}</em>
                </div>
                <p>
                  {d.kind === "lite"
                    ? "ruOS Lite · browser-based"
                    : d.host || d.kind}
                </p>
                <div className="ruos__card-a">
                  {d.kind === "lite" ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void act(async () => {
                          const r = await ruosPost("/ruos/lite/resume");
                          onOpenBrowser?.();
                          return r;
                        }, "Resume ruOS Lite");
                      }}
                    >
                      Resume ruOS Lite
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void act(
                            () => ruosPost(`/ruos/desktops/${d.id}/start`),
                            "started",
                          );
                        }}
                      >
                        Start
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void act(
                            () => ruosPost(`/ruos/desktops/${d.id}/stop`),
                            "asleep",
                          );
                        }}
                      >
                        Stop
                      </button>
                    </>
                  )}
                </div>
              </motion.button>
            ))}
          </div>

          <AnimatePresence>
            {addMode ? (
              <motion.div
                className="ruos__sheet"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <button
                  type="button"
                  className="ruos__x"
                  onClick={() => {
                    setAddMode(null);
                    setEnrollCmd("");
                  }}
                >
                  ✕
                </button>
                {addMode === "cloud" ? (
                  <>
                    <h3>Provision cloud desktop</h3>
                    <p>{board?.copy?.cloud}</p>
                    <div className="ruos__row">
                      {(["desktop", "phone", "gpu"] as const).map((p) => (
                        <button
                          key={p}
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            void act(
                              () => ruosPost("/ruos/provision", { profile: p }),
                              `cloud ${p} ready`,
                            ).then(() => setAddMode(null))
                          }
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
                {addMode === "linux" || addMode === "mac" ? (
                  <>
                    <h3>
                      Add your {addMode === "linux" ? "Linux machine" : "Mac"}
                    </h3>
                    <p>
                      {addMode === "linux"
                        ? board?.copy?.linux
                        : board?.copy?.mac}
                    </p>
                    <pre className="ruos__cmd">
                      {enrollCmd ||
                        'Click "Generate installer command" to get a one-time enrollment command…'}
                    </pre>
                    <div className="ruos__row">
                      <button
                        type="button"
                        onClick={() => {
                          if (enrollCmd) void navigator.clipboard.writeText(enrollCmd);
                          flash("copied");
                        }}
                      >
                        copy
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void generateEnroll(addMode)}
                      >
                        Generate installer command
                      </button>
                    </div>
                    <p className="ruos__notes">{enrollNotes}</p>
                  </>
                ) : null}
                {addMode === "rustdesk" ? (
                  <>
                    <h3>Add via RustDesk ID</h3>
                    <p>{board?.copy?.rustdesk}</p>
                    <input
                      value={rustdeskId}
                      onChange={(e) => setRustdeskId(e.target.value)}
                      placeholder="RustDesk ID"
                    />
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void act(
                          () =>
                            ruosPost("/ruos/rustdesk", { id: rustdeskId }),
                          "added",
                        ).then(() => setAddMode(null))
                      }
                    >
                      Add
                    </button>
                  </>
                ) : null}
                {addMode === "snapshots" ? (
                  <>
                    <h3>Desktop snapshots</h3>
                    <p>{board?.copy?.snapshot}</p>
                    <button
                      type="button"
                      disabled={busy || !desk}
                      onClick={() =>
                        desk &&
                        void act(
                          () =>
                            ruosPost("/ruos/snapshots", {
                              desktop_id: desk.id,
                            }),
                          "snapshot taken",
                        )
                      }
                    >
                      Take snapshot
                    </button>
                    <ul className="ruos__list">
                      {snaps.map((s) => (
                        <li key={s.id}>
                          {s.label}
                          <button
                            type="button"
                            onClick={() =>
                              void act(
                                () =>
                                  ruosPost(
                                    `/ruos/snapshots/${s.id}/duplicate`,
                                  ),
                                "duplicated",
                              )
                            }
                          >
                            duplicate
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </motion.div>
            ) : null}
          </AnimatePresence>

          <section className="ruos__lite">
            <h3>ruOS Lite browser</h3>
            <p>{board?.copy?.lite}</p>
            <button
              type="button"
              onClick={() =>
                void act(async () => {
                  const r = await ruosPost("/ruos/lite/resume");
                  onOpenBrowser?.();
                  return r;
                }, "Lite resumed")
              }
            >
              Resume ruOS Lite
            </button>
          </section>
        </div>
      ) : null}

      {tab === "keys" && keys ? (
        <div className="ruos__pane">
          <p className="ruos__lead">
            Your own API keys, stored write-only in the vault. · vault{" "}
            {keys.vault}
          </p>
          <nav className="ruos__sub">
            {(
              [
                ["model", "Model keys"],
                ["custom", "Custom keys"],
                ["website", "Website sign-ins"],
                ["mcp", "MCP tokens"],
                ["slack", "Slack"],
                ["tailscale", "Tailscale"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={keysTab === id ? "is-on" : ""}
                onClick={() => setKeysTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>
          {keysTab === "model" ? (
            <>
              <p className="ruos__notes">{keys.model_keys.copy}</p>
              <p>
                {keys.model_keys.any
                  ? "keys present"
                  : keys.model_keys.empty_hint}
              </p>
              <p>
                Meta-LLM: {keys.model_keys.meta_llm} · keys present (llm):{" "}
                {keys.routing.keys_present_llm ? "yes" : "no"}
              </p>
              <div className="ruos__form">
                <select
                  value={keySlot}
                  onChange={(e) => setKeySlot(e.target.value)}
                >
                  {keys.model_keys.slots.map((s) => (
                    <option key={s} value={s}>
                      {s}
                      {keys.model_keys.present[s] ? " · set" : ""}
                    </option>
                  ))}
                </select>
                <input
                  type="password"
                  placeholder="Paste the key value"
                  value={keyVal}
                  onChange={(e) => setKeyVal(e.target.value)}
                />
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      () =>
                        ruosPost("/ruos/keys/model", {
                          slot: keySlot,
                          value: keyVal,
                        }),
                      "key saved",
                    ).then(() => setKeyVal(""))
                  }
                >
                  Save key
                </button>
              </div>
              <h3>LLM routing</h3>
              <p className="ruos__notes">{keys.routing.copy}</p>
              <p>current: {keys.routing.current}</p>
              <div className="ruos__row">
                {keys.routing.options.map((o) => (
                  <button
                    key={o.id}
                    type="button"
                    className={routeMode === o.id ? "is-on" : ""}
                    onClick={() => setRouteMode(o.id)}
                  >
                    {o.label}
                  </button>
                ))}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void act(
                      () =>
                        ruosPost("/ruos/keys/routing", { mode: routeMode }),
                      "routing saved",
                    )
                  }
                >
                  Save routing
                </button>
              </div>
            </>
          ) : null}
          {keysTab === "mcp" ? (
            <>
              <button
                type="button"
                onClick={() =>
                  void act(async () => {
                    const r = await ruosPost("/ruos/keys/mcp", {
                      scope: "full",
                      days: 30,
                    });
                    if (r.token) setOnceToken(String(r.token));
                    return r;
                  }, "token created")
                }
              >
                Create token
              </button>
              {onceToken ? (
                <pre className="ruos__cmd">
                  Copy it now — it will not be shown again{"\n"}
                  {onceToken}
                </pre>
              ) : null}
              <ul className="ruos__list">
                {keys.mcp_tokens.map((t) => (
                  <li key={t.id}>
                    {t.label} · {t.scope} · {t.fp}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {keysTab === "custom" ||
          keysTab === "website" ||
          keysTab === "slack" ||
          keysTab === "tailscale" ? (
            <p className="ruos__notes">
              Write-only vault entries — use the forms above patterns on Model /
              MCP. Slack webhook and Tailscale tskey-auth- via API{" "}
              <code>/ruos/keys/{keysTab}</code>.
            </p>
          ) : null}
        </div>
      ) : null}

      {tab === "terminal" ? (
        <div className="ruos__pane ruos__term">
          <header className="ruos__term-h">
            <div>
              <p className="ruos__kicker">AI Console</p>
              <h2>powered by ruflo · / actions · @ apps · natural language</h2>
            </div>
            <div className="ruos__term-meta">
              <label>
                controls:
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  {(board?.desktops || []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
              <span>LLM: {keys?.routing?.current || "shared"}</span>
              <button type="button" onClick={() => setConsoleLog([])}>
                Clear
              </button>
            </div>
          </header>
          <p className="ruos__notes">
            AI Console — powered by ruflo. Ask in plain English, run shell
            commands, or use / actions (
            {CONSOLE_ACTIONS.map((a) => a.id).join(", ")}) and @ apps. Use the
            selector above to choose which desktop it controls — everything
            executes on the selected desktop.
          </p>
          <div className="ruos__term-log">
            {consoleLog.map((l, i) => (
              <pre key={i} className={l.role === "user" ? "is-user" : ""}>
                {l.role === "user" ? "› " : ""}
                {l.text}
              </pre>
            ))}
          </div>
          <div className="ruos__suggest">
            {CONSOLE_ACTIONS.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => setConsoleIn(`${a.id} `)}
                title={a.hint}
              >
                {a.id}
              </button>
            ))}
            {CONSOLE_APPS.map((a) => (
              <button key={a} type="button" onClick={() => setConsoleIn(`${a}`)}>
                {a}
              </button>
            ))}
          </div>
          <form
            className="ruos__term-in"
            onSubmit={(e) => {
              e.preventDefault();
              void runConsole();
            }}
          >
            <span>›</span>
            <input
              value={consoleIn}
              onChange={(e) => setConsoleIn(e.target.value)}
              placeholder="Ask, run a command, or type / for actions, @ for apps…"
            />
            <button type="submit">Run</button>
          </form>
        </div>
      ) : null}

      {tab === "swarms" ? (
        <div className="ruos__pane">
          <nav className="ruos__sub">
            {(
              [
                ["overview", "Overview"],
                ["deploy", "Deploy"],
                ["operate", "Operate"],
                ["activity", "Activity"],
              ] as [SwarmPane, string][]
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={swarmPane === id ? "is-on" : ""}
                onClick={() => setSwarmPane(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          {swarmPane === "overview" ? (
            <div className="ruos__gauges">
              <div>
                <span>Runtime</span>
                <strong>
                  {ruflo?.pulse?.swarm?.active ? "swarm live" : "idle"}
                </strong>
              </div>
              <div>
                <span>Agents</span>
                <strong>{ruflo?.pulse?.swarm?.agents?.length ?? 0}</strong>
              </div>
              <div>
                <span>Topology</span>
                <strong>{ruflo?.pulse?.swarm?.topology || "—"}</strong>
              </div>
              <div>
                <span>Fleet</span>
                <strong>{board?.counts?.total ?? 0} desktops</strong>
              </div>
              <div>
                <span>Missions</span>
                <strong>{ruflo?.pulse?.missions?.open ?? 0} open</strong>
              </div>
              <div>
                <span>Plugins</span>
                <strong>
                  {ruflo?.pulse?.plugins?.enabled ?? 0}/
                  {ruflo?.pulse?.plugins?.total ?? 0}
                </strong>
              </div>
            </div>
          ) : null}

          {swarmPane === "deploy" ? (
            <>
              <h3>Quick-start templates</h3>
              <p className="ruos__notes">
                Pick a ready-made swarm — it fills the wizard below so you can
                review and deploy in one step. Everything stays editable.
              </p>
              <div className="ruos__tpls">
                {TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={tpl?.id === t.id ? "is-on" : ""}
                    onClick={() => applyTemplate(t)}
                  >
                    <span className="ruos__tpl-ico">{t.icon}</span>
                    <strong>{t.title}</strong>
                    <em>{t.blurb}</em>
                    <small>
                      {t.topology} · {t.agents} agents · {t.consensus}
                    </small>
                  </button>
                ))}
              </div>

              <div className="ruos__wizard">
                <div className="ruos__wiz-h">
                  <h3>Deploy a swarm</h3>
                  <label>
                    target:
                    <select
                      value={selected}
                      onChange={(e) => setSelected(e.target.value)}
                    >
                      {(board?.desktops || []).map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="button" onClick={() => void refresh()}>
                    ⟳ Status
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void act(() => rufloPost("/ruflo/swarm/stop"), "stopped")
                    }
                  >
                    Stop swarm
                  </button>
                </div>
                <ol className="ruos__steps">
                  {(
                    [
                      [1, "Objective"],
                      [2, "Topology"],
                      [3, "Team"],
                      [4, "Capabilities"],
                      [5, "Review & deploy"],
                    ] as [DeployStep, string][]
                  ).map(([n, label]) => (
                    <li key={n}>
                      <button
                        type="button"
                        className={step === n ? "is-on" : ""}
                        onClick={() => setStep(n)}
                      >
                        {n} {label}
                      </button>
                    </li>
                  ))}
                </ol>

                {step === 1 ? (
                  <textarea
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    rows={4}
                  />
                ) : null}
                {step === 2 ? (
                  <div className="ruos__tpls">
                    {TOPOLOGIES.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        className={topology === t.id ? "is-on" : ""}
                        onClick={() => setTopology(t.id)}
                      >
                        <strong>{t.label}</strong>
                        <em>{t.hint}</em>
                      </button>
                    ))}
                    <label>
                      Max agents
                      <input
                        type="number"
                        min={1}
                        max={12}
                        value={maxAgents}
                        onChange={(e) => setMaxAgents(Number(e.target.value))}
                      />
                    </label>
                  </div>
                ) : null}
                {step === 3 ? (
                  <div className="ruos__team">
                    {Object.keys({
                      coder: 0,
                      researcher: 0,
                      reviewer: 0,
                      tester: 0,
                      planner: 0,
                      architect: 0,
                      ...team,
                    }).map((role) => (
                      <label key={role}>
                        {role}
                        <input
                          type="number"
                          min={0}
                          max={8}
                          value={team[role] || 0}
                          onChange={(e) =>
                            setTeam((t) => ({
                              ...t,
                              [role]: Number(e.target.value),
                            }))
                          }
                        />
                      </label>
                    ))}
                  </div>
                ) : null}
                {step === 4 ? (
                  <div className="ruos__row wrap">
                    {CAPS.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className={caps.includes(c.id) ? "is-on" : ""}
                        onClick={() =>
                          setCaps((x) =>
                            x.includes(c.id)
                              ? x.filter((i) => i !== c.id)
                              : [...x, c.id],
                          )
                        }
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                ) : null}
                {step === 5 ? (
                  <>
                    <h3>Review & deploy</h3>
                    <p className="ruos__notes">
                      This runs on your desktop through the JWT-gated control
                      API. Here&apos;s the plan:
                    </p>
                    <pre className="ruos__cmd">{deployPlan.join("\n")}</pre>
                    <p className="ruos__notes">
                      Each command executes as your desktop user via ruflo;
                      output streams below.
                    </p>
                    <div className="ruos__row">
                      <button type="button" onClick={() => setStep(4)}>
                        ← Back
                      </button>
                      <button
                        type="button"
                        className="is-go"
                        disabled={busy}
                        onClick={() => void deploySwarm()}
                      >
                        🚀 Deploy swarm
                      </button>
                    </div>
                    <h3>Deployment log</h3>
                    <button type="button" onClick={() => setDeployLog([])}>
                      Clear
                    </button>
                    <pre className="ruos__cmd">
                      {deployLog.join("\n") ||
                        "Complete the wizard and deploy — live output appears here."}
                    </pre>
                  </>
                ) : null}
              </div>
            </>
          ) : null}

          {swarmPane === "operate" ? (
            <div>
              <h3>Claims board</h3>
              <p className="ruos__notes">
                ruflo issue claims on the selected desktop — claim work, hand it
                off, mark it stealable.
              </p>
              <p>desktop: {desk?.name || "—"}</p>
              <button
                type="button"
                onClick={() =>
                  void act(
                    () =>
                      rufloPost("/ruflo/missions", {
                        goal: `claim work on ${desk?.name}`,
                        confirm: true,
                      }),
                    "claimed",
                  )
                }
              >
                Claim
              </button>
              <h3>Cluster dispatch</h3>
              <p className="ruos__notes">
                Run one command across several desktops — fanned out over the
                fleet.
              </p>
            </div>
          ) : null}

          {swarmPane === "activity" ? (
            <ul className="ruos__list">
              {(ruflo?.events || []).map((e, i) => (
                <li key={i}>
                  {new Date(e.ts * 1000).toLocaleTimeString()} · {e.kind}
                </li>
              ))}
              {!ruflo?.events?.length ? (
                <li>No activity yet — deploy a swarm.</li>
              ) : null}
            </ul>
          ) : null}
        </div>
      ) : null}

      {tab === "ruflo" ? (
        <div className="ruos__pane">
          <img
            src="/ruflo/ruflo-neon-header.svg"
            alt="Ruflo"
            className="ruos__neon"
          />
          <p className="ruos__lead">
            Agent = Model + Harness · spine of Véu ·{" "}
            <a
              href="https://github.com/ruvnet/ruflo"
              target="_blank"
              rel="noreferrer"
            >
              ruvnet/ruflo
            </a>
          </p>
          <ol className="ruos__flow">
            {(ruflo?.architecture?.flow || ruflo?.pulse?.architecture || []).map(
              (s) => (
                <li key={s}>{s}</li>
              ),
            )}
          </ol>
          <div className="ruos__gauges">
            <div>
              <span>Theme</span>
              <strong>{ruflo?.pulse?.theme || "orbital"}</strong>
            </div>
            <div>
              <span>Control</span>
              <strong>
                {ruflo?.pulse?.control?.active
                  ? ruflo.pulse.control.level
                  : "off"}
              </strong>
            </div>
            <div>
              <span>CLI</span>
              <strong>
                {ruflo?.pulse?.cli?.available
                  ? ruflo.pulse.cli.version || "yes"
                  : "npx pending"}
              </strong>
            </div>
          </div>
          <h3>Plugins</h3>
          <div className="ruos__plugins">
            {(ruflo?.plugins || []).map((p) => (
              <button
                key={p.id}
                type="button"
                className={p.enabled ? "is-on" : ""}
                title={p.description}
                onClick={() =>
                  void act(
                    () =>
                      rufloPost(`/ruflo/plugins/${p.id}`, {
                        enabled: !p.enabled,
                      }),
                    p.enabled ? "disabled" : "enabled",
                  )
                }
              >
                <strong>{p.name}</strong>
                <em>{p.category}</em>
              </button>
            ))}
          </div>
          <div className="ruos__row">
            <button
              type="button"
              onClick={() =>
                void act(
                  () =>
                    rufloPost("/ruflo/control", {
                      active: true,
                      level: "write",
                      approval: "ask",
                    }),
                  "Claude control on",
                )
              }
            >
              Claude control · write+ask
            </button>
            <button
              type="button"
              onClick={() =>
                void act(
                  () => rufloPost("/ruflo/control", { active: false }),
                  "Take back control",
                )
              }
            >
              Take back control
            </button>
          </div>
          <img
            src="/ruflo/ruflo-tui-compact.svg"
            alt="Ruflo TUI"
            className="ruos__art"
          />
        </div>
      ) : null}

      <style>{`
        .ruos {
          height: 100%;
          overflow: auto;
          padding: 0.85rem 1rem 1.4rem;
          background:
            radial-gradient(80% 50% at 10% 0%, rgba(121,223,255,0.08), transparent 55%),
            radial-gradient(70% 40% at 90% 10%, rgba(237,153,255,0.06), transparent 50%),
            #08080c;
          color: #e0e4f2;
          font-family: var(--font-mono, ui-monospace, monospace);
        }
        .ruos__top {
          display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start;
          margin-bottom: 0.75rem;
        }
        .ruos__brand { display: flex; gap: 0.75rem; align-items: center; }
        .ruos__logo { width: 3.2rem; height: 3.2rem; object-fit: contain; }
        .ruos__kicker {
          margin: 0; font-size: 0.62rem; letter-spacing: 0.18em; text-transform: lowercase;
          color: #79dfff;
        }
        .ruos h1 {
          margin: 0.15rem 0 0; font-family: var(--font-display, Syne, sans-serif);
          font-size: 1.35rem; letter-spacing: -0.03em; color: #f4efe6;
        }
        .ruos h2, .ruos h3 { font-family: var(--font-display, Syne, sans-serif); color: #f4efe6; }
        .ruos__status { display: flex; gap: 0.5rem; flex-wrap: wrap; font-size: 0.65rem; }
        .ruos__status span {
          padding: 0.25rem 0.5rem; border: 1px solid rgba(121,223,255,0.25);
          color: #9bb7ff;
        }
        .ruos__status .is-on { color: #8ee6be; border-color: rgba(142,230,190,0.4); }
        .ruos__tabs, .ruos__sub, .ruos__actions, .ruos__row, .ruos__suggest {
          display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.75rem;
        }
        .ruos__tabs button, .ruos__sub button, .ruos__actions button,
        .ruos__row button, .ruos__suggest button, .ruos__card-a button,
        .ruos__form button, .ruos__term-in button, .ruos__wiz-h button {
          appearance: none; border: 1px solid rgba(121,223,255,0.28);
          background: rgba(8,19,31,0.85); color: #d6e9f2;
          padding: 0.4rem 0.65rem; font-size: 0.72rem; cursor: pointer;
        }
        .ruos__tabs button.is-on, .ruos__sub button.is-on,
        .ruos__row button.is-on, .ruos__tpls button.is-on,
        .ruos__plugins button.is-on, .ruos__steps button.is-on {
          background: rgba(121,223,255,0.18); border-color: #79dfff; color: #fff;
        }
        .ruos__row button.is-go {
          background: rgba(240,100,73,0.85); border-color: #f06449; color: #fff;
        }
        .ruos__toast {
          margin: 0 0 0.5rem; padding: 0.4rem 0.6rem;
          background: rgba(240,100,73,0.2); color: #ffcf73; font-size: 0.75rem;
        }
        .ruos__toolbar {
          display: flex; gap: 0.75rem; align-items: center; margin-bottom: 0.75rem;
        }
        .ruos__toolbar input, .ruos input, .ruos select, .ruos textarea {
          background: #0c121a; border: 1px solid rgba(121,223,255,0.22);
          color: #e0e4f2; padding: 0.45rem 0.6rem; font: inherit;
        }
        .ruos__toolbar input { flex: 1; min-width: 0; }
        .ruos__fleet {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
          gap: 0.65rem; margin-bottom: 1rem;
        }
        .ruos__card {
          text-align: left; padding: 0.75rem; border: 1px solid rgba(121,223,255,0.2);
          background: rgba(10,16,24,0.9); color: inherit; cursor: pointer;
        }
        .ruos__card.is-sel { box-shadow: 0 0 0 1px #79dfff; }
        .ruos__card-h { display: flex; justify-content: space-between; gap: 0.5rem; }
        .ruos__card p { margin: 0.35rem 0 0.55rem; font-size: 0.72rem; color: #8a939c; }
        .st { font-style: normal; font-size: 0.65rem; letter-spacing: 0.08em; text-transform: lowercase; }
        .st-ok { color: #8ee6be; } .st-sleep { color: #9bb7ff; } .st-run { color: #ffcf73; } .st-bad { color: #ff929d; }
        .ruos__sheet {
          position: relative; margin: 0.75rem 0; padding: 1rem;
          border: 1px solid rgba(237,153,255,0.28); background: rgba(23,13,38,0.92);
        }
        .ruos__x { position: absolute; top: 0.4rem; right: 0.4rem; }
        .ruos__cmd {
          overflow: auto; max-height: 12rem; padding: 0.75rem;
          background: #05070a; border: 1px solid rgba(121,223,255,0.18);
          font-size: 0.68rem; white-space: pre-wrap; word-break: break-all;
        }
        .ruos__notes, .ruos__lead { font-size: 0.78rem; color: #a8b4c0; line-height: 1.45; }
        .ruos__lite {
          margin-top: 1rem; padding-top: 0.75rem;
          border-top: 1px solid rgba(121,223,255,0.15);
        }
        .ruos__form { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 1rem; }
        .ruos__form input { flex: 1; min-width: 10rem; }
        .ruos__list { list-style: none; margin: 0; padding: 0; }
        .ruos__list li {
          display: flex; justify-content: space-between; gap: 0.5rem;
          padding: 0.45rem 0; border-bottom: 1px solid rgba(255,255,255,0.06);
          font-size: 0.75rem;
        }
        .ruos__term-h { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
        .ruos__term-meta { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; font-size: 0.7rem; }
        .ruos__term-log {
          min-height: 10rem; max-height: 40vh; overflow: auto;
          background: #05070a; padding: 0.75rem; margin: 0.5rem 0;
          border: 1px solid rgba(121,223,255,0.15);
        }
        .ruos__term-log pre { margin: 0 0 0.45rem; font-size: 0.72rem; white-space: pre-wrap; }
        .ruos__term-log .is-user { color: #79dfff; }
        .ruos__term-in { display: flex; gap: 0.4rem; align-items: center; }
        .ruos__term-in input { flex: 1; }
        .ruos__gauges {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
          gap: 0.5rem; margin-bottom: 1rem;
        }
        .ruos__gauges > div {
          padding: 0.65rem; background: rgba(8,19,31,0.8);
          border: 1px solid rgba(121,223,255,0.18);
        }
        .ruos__gauges span { display: block; font-size: 0.62rem; color: #8a939c; letter-spacing: 0.1em; text-transform: lowercase; }
        .ruos__gauges strong { font-size: 1.05rem; color: #79dfff; }
        .ruos__tpls {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
          gap: 0.5rem; margin-bottom: 1rem;
        }
        .ruos__tpls button {
          display: grid; gap: 0.25rem; text-align: left; padding: 0.7rem;
          border: 1px solid rgba(121,223,255,0.22); background: rgba(8,19,31,0.85);
          color: inherit; cursor: pointer;
        }
        .ruos__tpls strong { font-size: 0.85rem; }
        .ruos__tpls em, .ruos__tpls small { font-style: normal; font-size: 0.68rem; color: #8a939c; }
        .ruos__tpl-ico { font-size: 1.2rem; }
        .ruos__wiz-h { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-bottom: 0.75rem; }
        .ruos__steps { display: flex; flex-wrap: wrap; gap: 0.35rem; list-style: none; padding: 0; margin: 0 0 0.75rem; }
        .ruos__team { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 0.5rem; }
        .ruos__team label { display: grid; gap: 0.25rem; font-size: 0.72rem; }
        .ruos__plugins {
          display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
          gap: 0.4rem; margin-bottom: 1rem;
        }
        .ruos__plugins button {
          display: grid; gap: 0.15rem; text-align: left; padding: 0.55rem;
          border: 1px solid rgba(121,223,255,0.2); background: rgba(8,19,31,0.8);
          color: inherit; cursor: pointer;
        }
        .ruos__plugins em { font-style: normal; font-size: 0.62rem; color: #8a939c; }
        .ruos__neon { width: 100%; max-height: 4.5rem; object-fit: contain; margin-bottom: 0.75rem; }
        .ruos__art { width: 100%; margin-top: 1rem; border: 1px solid rgba(121,223,255,0.15); }
        .ruos__flow { font-size: 0.78rem; color: #a8b4c0; }
        .wrap { flex-wrap: wrap; }
        a { color: #79dfff; }
      `}</style>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { NativeChat, type ChatTurn } from "../../components/NativeChat";
import { IntentContinuum } from "../../components/IntentContinuum";
import { LiveExecution, type LiveStep } from "../../components/LiveExecution";
import type { AutonomyBreath } from "../../components/AutonomyOrbit";
import { streamChat, type FormationPayload } from "../../lib/kernel";
import {
  isAiSubscriptionUrl,
  looksLikeOpen,
  openUrlNow,
  peekUrl,
  reserveTab,
} from "../../lib/openUrl";
import { callBridge, runHostPreset } from "../../bridge/hostBridge";

type Props = {
  breath: AutonomyBreath;
  seedIntent?: string | null;
  onSeedConsumed?: () => void;
};

export function ChatApp({ breath, seedIntent, onSeedConsumed }: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>([
    {
      id: "boot",
      role: "veu",
      text: "Oi. Em que posso te ajudar?",
    },
  ]);
  const [weaving, setWeaving] = useState(false);
  const [waitText, setWaitText] = useState("…");
  const [harnessOn, setHarnessOn] = useState(false);
  const [toolCount, setToolCount] = useState(0);
  const [steps, setSteps] = useState<LiveStep[]>([]);
  const [formationTitle, setFormationTitle] = useState("");
  const [nerves, setNerves] = useState<string[]>([]);
  const [telemetry, setTelemetry] = useState("");

  const push = useCallback((role: ChatTurn["role"], text: string) => {
    setTurns((p) => [
      ...p,
      { id: `${Date.now()}-${Math.random().toString(36).slice(2, 5)}`, role, text },
    ]);
  }, []);

  const onIntent = useCallback(
    async (raw: string) => {
      const eagerUrl = peekUrl(raw);
      let reserved: Window | null = null;
      try {
        if (eagerUrl || looksLikeOpen(raw)) {
          reserved = reserveTab();
        }
        if (eagerUrl) {
          openUrlNow(eagerUrl, reserved);
          reserved = null;
        }
      } catch {
        reserved = null;
      }

      setWeaving(true);
      setWaitText(eagerUrl ? "abrindo site…" : "tecendo…");
      setHarnessOn(false);
      setToolCount(0);
      setSteps([]);
      setFormationTitle("");
      setNerves([]);
      setTelemetry("");
      push("user", raw);

      let replied = false;
      let opened = !!eagerUrl;
      let formation: FormationPayload | null = null;

      try {
        formation = await streamChat(raw, breath, (ev) => {
          if (ev.type === "status" && ev.text?.trim()) {
            setWaitText(ev.text.trim());
          }
          if (ev.type === "harness") {
            setHarnessOn(ev.active);
            setToolCount(ev.session?.tools?.length || 0);
            if (ev.active && ev.session?.tools?.length) {
              setTelemetry(`harness · ${ev.session.tools.join(" · ")}`);
            }
          }
          if (ev.type === "plan" && ev.formation) {
            const f = ev.formation;
            setFormationTitle(f.title || f.kind || "missão");
            setNerves((f.connectors || []).map((c) => c.name));
            const jev = (f as { jev?: { route?: string; kind?: string; source?: string } })
              .jev;
            if (jev?.route) {
              setTelemetry(
                `jev · ${jev.kind || "?"} → ${jev.route}${
                  jev.source ? ` · ${jev.source}` : ""
                }`,
              );
            }
            if (f.steps?.length) {
              setSteps(
                f.steps.map((s, index) => ({
                  index,
                  label: s.label,
                  actor: s.actor,
                  state: "pending" as const,
                })),
              );
            }
            if (f.agents?.length) {
              setNerves((prev) => [
                ...prev,
                ...f.agents.map((a) => a.title),
              ]);
            }
          }
          if (ev.type === "step") {
            const state =
              ev.state === "done" || ev.state === "running" || ev.state === "pending"
                ? ev.state
                : "pending";
            setSteps((prev) => {
              const next = [...prev];
              const row: LiveStep = {
                index: ev.index,
                label: ev.step.label,
                actor: ev.step.actor,
                state,
              };
              const at = next.findIndex((s) => s.index === ev.index);
              if (at >= 0) next[at] = row;
              else next.push(row);
              return next.sort((a, b) => a.index - b.index);
            });
          }
          if (ev.type === "action" && ev.action === "open_url" && ev.url) {
            // Nunca abrir ChatGPT/Claude/Grok a partir do chat do SO
            if (isAiSubscriptionUrl(ev.url)) {
              if (reserved && !reserved.closed) {
                try {
                  reserved.close();
                } catch {
                  /* ignore */
                }
                reserved = null;
              }
              return;
            }
            setWaitText("abrindo site…");
            if (!opened || ev.url !== eagerUrl) {
              const result = openUrlNow(ev.url, reserved);
              reserved = null;
              opened = result === "ok" || opened;
              if (result === "blocked") {
                push("veu", `O browser bloqueou a aba. Abra aqui: ${ev.url}`);
                replied = true;
              }
            } else if (reserved && !reserved.closed) {
              try {
                reserved.close();
              } catch {
                /* ignore */
              }
              reserved = null;
            }
          }
          if (
            ev.type === "action" &&
            (ev.action === "open_app" ||
              ev.action === "focus_app" ||
              ev.action === "run_preset" ||
              ev.action === "shell" ||
              ev.action === "list_tabs" ||
              ev.action === "read_surface")
          ) {
            const payload = (ev.payload || {}) as {
              app?: string;
              preset?: string;
              command?: string;
            };
            setWaitText("na máquina local…");
            void (async () => {
              try {
                if (ev.action === "open_app" || ev.action === "focus_app") {
                  const app = String(payload.app || ev.app || "").trim();
                  if (!app) return;
                  const res = await callBridge({
                    type:
                      ev.action === "focus_app"
                        ? "veu.host.focusApp"
                        : "veu.host.openApp",
                    app,
                  });
                  if (!res.ok) {
                    push(
                      "veu",
                      res.error ||
                        `Não abri ${app} — instale/ative a extensão Véu Host (host · ok).`,
                    );
                    replied = true;
                  }
                } else if (ev.action === "list_tabs") {
                  const res = await callBridge({ type: "veu.host.listTabs" });
                  if (!res.ok) {
                    push(
                      "veu",
                      res.error ||
                        "Não listei as abas — extensão Véu Host 0.3.5 precisa estar ativa.",
                    );
                    replied = true;
                  } else {
                    const data = (res.data || {}) as { text?: string };
                    if (data.text?.trim()) {
                      push("veu", `Abas abertas:\n${data.text.trim().slice(0, 1600)}`);
                      replied = true;
                    }
                  }
                } else if (ev.action === "read_surface") {
                  const app = String(payload.app || ev.app || "").trim();
                  if (!app) return;
                  const res = await callBridge(
                    { type: "veu.host.readSurface", app },
                    15000,
                  );
                  if (!res.ok) {
                    push(
                      "veu",
                      res.error ||
                        `Não li ${app} — abra o app logado e peça de novo (extensão 0.3.5).`,
                    );
                    replied = true;
                  } else {
                    const data = (res.data || {}) as {
                      text?: string;
                      items?: string[];
                      note?: string;
                    };
                    const body =
                      data.text?.trim() ||
                      (data.items?.length
                        ? data.items.map((it, i) => `${i + 1}. ${it}`).join("\n")
                        : data.note || "");
                    if (body) {
                      push("veu", body.slice(0, 2000));
                      replied = true;
                    }
                  }
                } else if (ev.action === "run_preset") {
                  const preset = String(payload.preset || payload.app || "").trim();
                  if (!preset) return;
                  const res = await runHostPreset(preset);
                  if (!res.ok) {
                    push(
                      "veu",
                      res.error ||
                        `Preset ${preset} falhou — confira a extensão / host nativo.`,
                    );
                    replied = true;
                  } else if (res.data && typeof res.data === "object") {
                    const data = res.data as { stdout?: string };
                    if (data.stdout?.trim()) {
                      push("veu", data.stdout.trim().slice(0, 1200));
                      replied = true;
                    }
                  }
                } else if (ev.action === "shell") {
                  const command = String(payload.command || "").trim();
                  if (!command) return;
                  const res = await callBridge({
                    type: "veu.host.shell",
                    command,
                  });
                  if (!res.ok) {
                    push(
                      "veu",
                      res.error ||
                        "Shell bloqueado — no host: VEU_HOST_ALLOW_SHELL=1 + extensão.",
                    );
                    replied = true;
                  } else if (res.data && typeof res.data === "object") {
                    const data = res.data as { stdout?: string; stderr?: string };
                    const out = [data.stdout, data.stderr].filter(Boolean).join("\n").trim();
                    if (out) {
                      push("veu", out.slice(0, 1200));
                      replied = true;
                    }
                  }
                }
              } catch (e) {
                push(
                  "veu",
                  e instanceof Error
                    ? e.message
                    : "Falha ao falar com a máquina local.",
                );
                replied = true;
              }
            })();
          }
          if (ev.type === "reply" && ev.text?.trim()) {
            let text = ev.text.trim();
            const url = peekUrl(raw) || peekUrl(text);
            if (url && !text.includes(url) && /abrindo/i.test(text)) {
              text = `${text}\n${url}`;
            }
            push("veu", text);
            replied = true;
          }
        });
      } catch (err) {
        const detail =
          err instanceof Error && err.message ? ` (${err.message})` : "";
        push(
          "veu",
          `Não consegui falar com o kernel agora${detail}. Confira se “kernel · on” está verde e tente de novo.`,
        );
        replied = true;
      }

      try {
        const exec = (
          formation as {
            execution?: { action?: { type?: string; url?: string }; url?: string };
          } | null
        )?.execution;
        const finalUrl = exec?.action?.url || exec?.url;
        if (finalUrl && !opened && !isAiSubscriptionUrl(finalUrl)) {
          const result = openUrlNow(finalUrl, reserved);
          reserved = null;
          if (result === "blocked" && !replied) {
            push("veu", `Não consegui abrir sozinho. Clique: ${finalUrl}`);
            replied = true;
          }
        } else if (reserved && !reserved.closed) {
          try {
            reserved.close();
          } catch {
            /* ignore */
          }
        }
      } finally {
        if (!formation && !replied) {
          push(
            "veu",
            "Estou com dificuldade pra falar agora. Tenta de novo em um instante.",
          );
        }
        setWeaving(false);
        setWaitText("…");
        setHarnessOn(false);
        setToolCount(0);
      }
    },
    [breath, push],
  );

  useEffect(() => {
    if (!seedIntent?.trim() || weaving) return;
    const msg = seedIntent.trim();
    onSeedConsumed?.();
    void onIntent(msg);
  }, [seedIntent, weaving, onIntent, onSeedConsumed]);

  return (
    <div className="chat-app">
      <div className="chat-app__stream">
        <NativeChat turns={turns} />
        {(weaving || steps.length > 0) && (
          <LiveExecution
            thinking={weaving ? waitText : undefined}
            steps={steps}
            title={formationTitle || undefined}
            nerves={nerves.length ? nerves : undefined}
          />
        )}
        {(telemetry || harnessOn) && (
          <p className="chat-app__telem">
            {telemetry}
            {harnessOn ? (
              <span className="chat-app__harness"> · agente · {toolCount} tools</span>
            ) : null}
          </p>
        )}
      </div>
      <IntentContinuum
        weaving={weaving}
        breath={breath}
        onSubmit={onIntent}
        placeholder="um pedido simples — o Véu constrói e executa ao vivo…"
      />
      <style>{`
        .chat-app {
          height: 100%;
          display: grid;
          grid-template-rows: 1fr auto;
          gap: 0.75rem;
          padding: 0.85rem;
        }
        .chat-app__stream {
          min-height: 0;
          overflow: auto;
          display: grid;
          align-content: start;
          gap: 0.75rem;
        }
        .chat-app__telem {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.7rem;
          letter-spacing: 0.06em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .chat-app__harness {
          color: var(--filament);
        }
      `}</style>
    </div>
  );
}

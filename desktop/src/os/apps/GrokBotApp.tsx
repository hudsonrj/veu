import { useCallback, useEffect, useState } from "react";
import {
  approveGrokJob,
  askGrokBot,
  fetchGrokBrief,
  fetchGrokSideboard,
  type GrokBrief,
  type GrokInboxItem,
  type GrokSideboard,
} from "../../lib/kernel";
import {
  callBridge,
  probeBridge,
  runHostPreset,
  type BridgeInfo,
} from "../../bridge/hostBridge";

const QUICK_ASKS = [
  "resuma o que importa hoje e o que precisa da minha OK",
  "triage meu e-mail e me diga as 3 urgências",
  "prepare um checklist do dia e avise se algo travar",
];

const FALLBACK_REMOTE: {
  id: string;
  label: string;
  hint: string;
  ask: string;
}[] = [
  {
    id: "plaud",
    label: "Plaud",
    hint: "transcrições e resumos",
    ask: "Use o Plaud que você já tem: liste reuniões recentes e resumos das 3 principais.",
  },
  {
    id: "day-brief",
    label: "briefing",
    hint: "status no cloud",
    ask: "Briefing do dia no seu lado (jobs, Plaud, aprovações). Resumo curto no callback.",
  },
];

const LOCAL_ACTIONS: { id: string; label: string; kind: "preset" | "app" }[] = [
  { id: "gmail", label: "gmail", kind: "app" },
  { id: "calendar", label: "agenda", kind: "app" },
  { id: "notion", label: "notion", kind: "app" },
  { id: "terminal", label: "terminal", kind: "preset" },
  { id: "explorer", label: "arquivos", kind: "preset" },
];

function ago(ts?: number) {
  if (!ts) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function fmtWhen(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Hub Grok Bot — esquerda pedidos; direita live.json do Control (já lido). */
export function GrokBotApp() {
  const [brief, setBrief] = useState<GrokBrief | null>(null);
  const [side, setSide] = useState<GrokSideboard | null>(null);
  const [host, setHost] = useState<BridgeInfo | null>(null);
  const [intent, setIntent] = useState("");
  const [agent, setAgent] = useState<string>("");
  const [viaAgent, setViaAgent] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [hostLog, setHostLog] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [b, s, h] = await Promise.all([
      fetchGrokBrief(),
      fetchGrokSideboard(),
      probeBridge(1200),
    ]);
    setBrief(b);
    setSide(s || b?.sideboard || null);
    setHost(h);
    setErr(b ? null : "kernel offline");
    const agents = b?.agents || s?.agents || [];
    if (!agent && agents[0]) {
      const first = agents[0] as { id?: string; name?: string; label?: string };
      setAgent(String(first.id || first.name || first.label || ""));
    }
  }, [agent]);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 20_000);
    return () => window.clearInterval(id);
  }, [reload]);

  const status = brief?.status || "planned";
  const agents =
    brief?.agents ||
    (side?.agents || []).map((a) => ({
      id: String(a.id || a.name || ""),
      label: String(a.label || a.name || ""),
      hint: String(a.hint || ""),
    })) ||
    [];

  const sendAsk = async (text: string) => {
    const intentText = text.trim();
    if (!intentText) {
      setMsg("diga o que o Grok Bot deve fazer");
      return;
    }
    setBusy("ask");
    setMsg(null);
    const r = await askGrokBot({
      intent: intentText,
      breath: "semi",
      agent: viaAgent ? agent || null : null,
      via: viaAgent ? "agent" : "os",
    });
    setBusy(null);
    setMsg(r.ok ? r.message || "enviado" : r.error || "falha");
    if (r.ok) setIntent("");
    void reload();
  };

  const runLocal = async (action: (typeof LOCAL_ACTIONS)[number]) => {
    setBusy(`host:${action.id}`);
    setHostLog(null);
    try {
      if (host?.status !== "connected") {
        setHostLog("extensão ausente — instale Véu Host e recarregue");
        return;
      }
      const res =
        action.kind === "app"
          ? await callBridge({ type: "veu.host.openApp", app: action.id })
          : await runHostPreset(action.id);
      setHostLog(
        res.ok
          ? JSON.stringify(res.data ?? { ok: true }, null, 2)
          : res.error || "falha no host",
      );
    } finally {
      setBusy(null);
      void probeBridge(800).then(setHost);
    }
  };

  const inbox = brief?.inbox || [];
  const decisions = brief?.decisions || inbox.filter((i) => i.priority === "decision");
  const running = brief?.running || [];
  const remotes = brief?.remote_capabilities?.length
    ? brief.remote_capabilities
    : FALLBACK_REMOTE;

  return (
    <div className="gbday">
      <header className="gbday__head">
        <div>
          <p className="gbday__kicker">grok bot · reuse live.json</p>
          <h2 className="gbday__title">teammate no SO</h2>
          <p className="gbday__sub">
            esquerda pede; direita mostra o que o Control/Grok Bot já leu
            (Outlook, Teams, Gmail, agenda, reuniões) — sem reler.
          </p>
        </div>
        <div className={`gbday__badge is-${status}`}>
          <span />
          {status}
          {side?.available ? " · live" : ""}
          {err ? ` · ${err}` : ""}
        </div>
      </header>

      <div className="gbday__split">
        <div className="gbday__left">
          <section className="gbday__ask">
            <label>
              <span>pedir ao grok bot</span>
              <textarea
                rows={2}
                placeholder="ex.: o que precisa de OK no Outlook/Teams hoje?"
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
                disabled={!!busy}
              />
            </label>
            <div className="gbday__askrow">
              <label className="gbday__check">
                <input
                  type="checkbox"
                  checked={viaAgent}
                  onChange={(e) => setViaAgent(e.target.checked)}
                />
                via agente
              </label>
              <select
                value={agent}
                onChange={(e) => setAgent(e.target.value)}
                disabled={!viaAgent || !!busy}
              >
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="gbday__go"
                disabled={!!busy || !intent.trim()}
                onClick={() => void sendAsk(intent)}
              >
                {busy === "ask" ? "…" : "enviar"}
              </button>
            </div>
            <div className="gbday__chips">
              {QUICK_ASKS.map((q) => (
                <button key={q} type="button" disabled={!!busy} onClick={() => void sendAsk(q)}>
                  {q}
                </button>
              ))}
            </div>
          </section>

          <section className="gbday__remote">
            <h3>
              no cloud · já no Grok Bot <em>pedir · não duplicar</em>
            </h3>
            <div className="gbday__remote-grid">
              {remotes.map((cap) => (
                <button
                  key={cap.id}
                  type="button"
                  disabled={!!busy}
                  title={cap.hint}
                  onClick={() => void sendAsk(cap.ask)}
                >
                  <strong>{cap.label}</strong>
                  <span>{cap.hint}</span>
                </button>
              ))}
            </div>
          </section>

          <div className="gbday__grid">
            <section className="gbday__panel">
              <h3>decisões · precisa de OK</h3>
              {decisions.length === 0 ? (
                <p className="gbday__empty">nada pendente na ponte</p>
              ) : (
                <ul className="gbday__list">
                  {decisions.map((item) => (
                    <InboxRow
                      key={item.id || item.job_id || item.title}
                      item={item}
                      busy={busy}
                      onApprove={(id) => {
                        setBusy(`ok:${id}`);
                        void approveGrokJob(id).then((r) => {
                          setBusy(null);
                          setMsg(r.ok ? r.message || "aprovado" : r.error || "falha");
                          void reload();
                        });
                      }}
                    />
                  ))}
                </ul>
              )}
            </section>

            <section className="gbday__panel">
              <h3>em curso</h3>
              {running.length === 0 ? (
                <p className="gbday__empty">nenhum job ativo</p>
              ) : (
                <ul className="gbday__list">
                  {running.map((j) => (
                    <li key={j.job_id}>
                      <header>
                        <em>{j.state}</em>
                        <span>{ago(j.ts)}</span>
                      </header>
                      <strong>{j.intent}</strong>
                      {j.agent ? <p>agente · {j.agent}</p> : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="gbday__panel gbday__panel--wide">
              <h3>
                máquina local{" "}
                <em className={host?.status === "connected" ? "is-on" : ""}>
                  {host?.status === "connected" ? "host · ok" : "host · off"}
                </em>
              </h3>
              <div className="gbday__local">
                {LOCAL_ACTIONS.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    disabled={!!busy}
                    onClick={() => void runLocal(a)}
                  >
                    {busy === `host:${a.id}` ? "…" : a.label}
                  </button>
                ))}
              </div>
              {hostLog ? <pre className="gbday__log">{hostLog}</pre> : null}
            </section>
          </div>
        </div>

        <aside className="gbday__right">
          <Sideboard board={side} />
        </aside>
      </div>

      {msg ? <p className="gbday__foot">{msg}</p> : null}
      {brief?.tip ? <p className="gbday__tip">{brief.tip}</p> : null}

      <style>{`
        .gbday {
          height: 100%;
          min-height: 0;
          overflow: auto;
          display: grid;
          gap: 0.55rem;
          padding: 0.7rem 0.75rem 0.75rem;
          color: var(--mist);
          scrollbar-width: thin;
        }
        .gbday__head {
          display: flex;
          justify-content: space-between;
          gap: 0.75rem;
          align-items: flex-start;
        }
        .gbday__kicker {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.14em;
          color: var(--signal);
          text-transform: lowercase;
        }
        .gbday__title {
          margin: 0.1rem 0 0;
          font-family: var(--font-display);
          font-size: 1.2rem;
          color: var(--filament);
          font-weight: 700;
        }
        .gbday__sub {
          margin: 0.18rem 0 0;
          font-size: 0.76rem;
          font-weight: 300;
          color: var(--mist-dim);
          max-width: 36rem;
          line-height: 1.35;
        }
        .gbday__badge {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.08em;
          text-transform: lowercase;
          padding: 0.32rem 0.48rem;
          border: 1px solid rgba(232,194,122,0.22);
          color: var(--mist-dim);
          white-space: nowrap;
        }
        .gbday__badge.is-live { color: var(--filament); border-color: rgba(232,194,122,0.5); }
        .gbday__badge span {
          width: 0.35rem; height: 0.35rem; border-radius: 50%;
          background: currentColor; box-shadow: 0 0 8px currentColor;
        }
        .gbday__split {
          display: grid;
          grid-template-columns: minmax(0, 1.05fr) minmax(280px, 0.95fr);
          gap: 0.55rem;
          align-items: start;
          min-height: 0;
        }
        .gbday__left, .gbday__right {
          display: grid;
          gap: 0.5rem;
          min-width: 0;
        }
        .gbday__ask, .gbday__remote, .gbday__panel, .gbday__side {
          padding: 0.55rem 0.6rem;
          border: 1px solid rgba(232,194,122,0.12);
          background: rgba(7,9,12,0.36);
        }
        .gbday__remote { border-color: rgba(127,231,212,0.16); }
        .gbday__ask label span,
        .gbday__remote h3,
        .gbday__panel h3,
        .gbday__side h3 {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.56rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
          color: var(--signal);
          font-weight: 500;
        }
        .gbday__remote h3, .gbday__panel h3, .gbday__side h3 {
          display: flex;
          justify-content: space-between;
          gap: 0.4rem;
        }
        .gbday__remote h3 em, .gbday__panel h3 em, .gbday__side h3 em {
          font-style: normal;
          color: var(--mist-dim);
        }
        .gbday__panel h3 em.is-on { color: var(--signal); }
        .gbday__ask textarea {
          width: 100%;
          margin-top: 0.25rem;
          border: 1px solid rgba(127,231,212,0.2);
          background: rgba(7,9,12,0.55);
          color: var(--mist);
          padding: 0.45rem 0.5rem;
          font-family: var(--font-mono);
          font-size: 0.72rem;
          resize: vertical;
          outline: none;
        }
        .gbday__askrow {
          display: flex;
          flex-wrap: wrap;
          gap: 0.4rem;
          align-items: center;
          margin-top: 0.35rem;
        }
        .gbday__check {
          display: inline-flex;
          align-items: center;
          gap: 0.3rem;
          font-family: var(--font-mono);
          font-size: 0.62rem;
          color: var(--mist-dim);
        }
        .gbday__ask select {
          border: 1px solid rgba(232,194,122,0.25);
          background: rgba(7,9,12,0.55);
          color: var(--mist);
          font-family: var(--font-mono);
          font-size: 0.65rem;
          padding: 0.32rem 0.4rem;
          max-width: 10rem;
        }
        .gbday__go {
          margin-left: auto;
          border: 1px solid rgba(232,194,122,0.45);
          background: transparent;
          color: var(--filament);
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          padding: 0.35rem 0.7rem;
          cursor: pointer;
        }
        .gbday__go:hover:not(:disabled) { background: var(--filament); color: var(--ink); }
        .gbday__go:disabled { opacity: 0.35; cursor: default; }
        .gbday__chips, .gbday__local {
          display: flex;
          flex-wrap: wrap;
          gap: 0.28rem;
          margin-top: 0.35rem;
        }
        .gbday__chips button, .gbday__local button {
          border: 1px solid rgba(236,242,248,0.12);
          background: transparent;
          color: var(--mist-dim);
          font-family: var(--font-mono);
          font-size: 0.58rem;
          padding: 0.28rem 0.4rem;
          cursor: pointer;
          text-align: left;
        }
        .gbday__chips button:hover:not(:disabled),
        .gbday__local button:hover:not(:disabled) {
          border-color: rgba(232,194,122,0.4);
          color: var(--filament);
        }
        .gbday__remote-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.3rem;
          margin-top: 0.35rem;
        }
        .gbday__remote-grid button {
          display: grid;
          gap: 0.12rem;
          text-align: left;
          border: 1px solid rgba(127,231,212,0.18);
          background: transparent;
          color: var(--mist);
          padding: 0.35rem 0.4rem;
          cursor: pointer;
        }
        .gbday__remote-grid button:hover:not(:disabled) {
          border-color: rgba(232,194,122,0.45);
          color: var(--filament);
        }
        .gbday__remote-grid strong {
          font-family: var(--font-mono);
          font-size: 0.64rem;
          font-weight: 500;
        }
        .gbday__remote-grid span {
          font-size: 0.56rem;
          color: var(--mist-dim);
          line-height: 1.25;
        }
        .gbday__grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0.45rem;
        }
        .gbday__panel--wide { grid-column: 1 / -1; }
        .gbday__empty {
          margin: 0.35rem 0 0;
          font-size: 0.7rem;
          color: var(--mist-dim);
          font-weight: 300;
        }
        .gbday__list {
          list-style: none;
          margin: 0.3rem 0 0;
          padding: 0;
          display: grid;
          gap: 0.4rem;
          max-height: 11rem;
          overflow: auto;
          scrollbar-width: thin;
        }
        .gbday__list li {
          display: grid;
          gap: 0.12rem;
          padding-bottom: 0.35rem;
          border-bottom: 1px solid rgba(232,194,122,0.08);
        }
        .gbday__list header {
          display: flex;
          justify-content: space-between;
          gap: 0.35rem;
          font-family: var(--font-mono);
          font-size: 0.54rem;
          letter-spacing: 0.08em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .gbday__list header em.is-decision { color: #e8a07a; }
        .gbday__list header em.is-important { color: var(--filament); }
        .gbday__list strong {
          font-size: 0.74rem;
          font-weight: 500;
          color: var(--mist);
          line-height: 1.3;
        }
        .gbday__list p {
          margin: 0;
          font-size: 0.64rem;
          color: var(--mist-dim);
          line-height: 1.35;
        }
        .gbday__list button {
          justify-self: start;
          margin-top: 0.15rem;
          border: 1px solid rgba(232,194,122,0.4);
          background: transparent;
          color: var(--filament);
          font-family: var(--font-mono);
          font-size: 0.58rem;
          padding: 0.25rem 0.45rem;
          cursor: pointer;
        }
        .gbday__log {
          margin: 0.35rem 0 0;
          padding: 0.35rem 0.45rem;
          max-height: 4.5rem;
          overflow: auto;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          background: rgba(0,0,0,0.35);
        }
        .gbday__side {
          display: grid;
          gap: 0.55rem;
          border-color: rgba(127,231,212,0.14);
          background: rgba(6,10,12,0.5);
        }
        .gbday__side-kicker {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.54rem;
          letter-spacing: 0.12em;
          color: var(--signal);
          text-transform: lowercase;
        }
        .gbday__metrics {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 0.3rem;
        }
        .gbday__metric {
          display: grid;
          gap: 0.08rem;
          padding: 0.35rem 0.4rem;
          border: 1px solid rgba(232,194,122,0.12);
          background: rgba(0,0,0,0.22);
        }
        .gbday__metric b {
          font-family: var(--font-mono);
          font-size: 0.95rem;
          color: var(--filament);
          font-weight: 600;
        }
        .gbday__metric span {
          font-size: 0.54rem;
          color: var(--mist-dim);
          letter-spacing: 0.06em;
          text-transform: lowercase;
        }
        .gbday__note {
          margin: 0;
          font-size: 0.68rem;
          color: var(--mist-dim);
          line-height: 1.35;
        }
        .gbday__warn {
          margin: 0;
          font-size: 0.64rem;
          color: #e8a07a;
          line-height: 1.35;
        }
        .gbday__block { display: grid; gap: 0.28rem; }
        .gbday__tag {
          display: inline-block;
          margin-right: 0.25rem;
          font-family: var(--font-mono);
          font-size: 0.52rem;
          letter-spacing: 0.06em;
          color: var(--signal);
          text-transform: lowercase;
        }
        .gbday__foot, .gbday__tip {
          margin: 0;
          font-size: 0.7rem;
          color: var(--mist-dim);
        }
        .gbday__foot { color: var(--filament); }
        @media (max-width: 980px) {
          .gbday__split { grid-template-columns: 1fr; }
        }
        @media (max-width: 720px) {
          .gbday__grid, .gbday__remote-grid, .gbday__metrics { grid-template-columns: 1fr 1fr; }
        }
      `}</style>
    </div>
  );
}

function Sideboard({ board }: { board: GrokSideboard | null }) {
  if (!board?.available) {
    return (
      <section className="gbday__side">
        <p className="gbday__side-kicker">control · live.json</p>
        <h3>produtividade · saúde</h3>
        <p className="gbday__empty">
          {board?.error ||
            "live.json ainda não visível neste host — o Grok Bot já grava em /var/www/control-kiosk/live.json"}
        </p>
      </section>
    );
  }

  const h = board.health || {};
  const p = board.productivity || {};
  const channels = h.channels || {};

  return (
    <section className="gbday__side">
      <p className="gbday__side-kicker">
        control · live.json · {board.updatedAt ? fmtWhen(board.updatedAt) : "—"}
      </p>

      <div className="gbday__block">
        <h3>
          saúde <em>{h.fleet || "—"}</em>
        </h3>
        <div className="gbday__metrics">
          <div className="gbday__metric">
            <b>{h.inbox_total ?? 0}</b>
            <span>msgs</span>
          </div>
          <div className="gbday__metric">
            <b>{h.unread ?? 0}</b>
            <span>não lidas</span>
          </div>
          <div className="gbday__metric">
            <b>{h.needs_approval ?? 0}</b>
            <span>aprovação</span>
          </div>
          <div className="gbday__metric">
            <b>{channels.outlook || 0}</b>
            <span>outlook</span>
          </div>
          <div className="gbday__metric">
            <b>{channels.teams || 0}</b>
            <span>teams</span>
          </div>
          <div className="gbday__metric">
            <b>{(channels.mail || 0) + (channels.gmail || 0) + (channels.email || 0)}</b>
            <span>e-mail</span>
          </div>
        </div>
        {h.source_note ? <p className="gbday__note">{h.source_note}</p> : null}
        {(h.needs_login_count || 0) > 0 ? (
          <p className="gbday__warn">
            {h.needs_login_count} login(s) pendente(s)
            {h.needs_login?.[0] ? ` · ${h.needs_login[0].slice(0, 120)}` : ""}
          </p>
        ) : null}
      </div>

      <div className="gbday__block">
        <h3>
          produtividade <em>{p.focus || "foco"}</em>
        </h3>
        <div className="gbday__metrics">
          <div className="gbday__metric">
            <b>{p.doing ?? 0}</b>
            <span>doing</span>
          </div>
          <div className="gbday__metric">
            <b>{p.blocked ?? 0}</b>
            <span>blocked</span>
          </div>
          <div className="gbday__metric">
            <b>{p.todo ?? 0}</b>
            <span>todo</span>
          </div>
        </div>
        {p.counsel_headline ? <p className="gbday__note">{p.counsel_headline}</p> : null}
        {(board.insights || []).slice(0, 3).map((i) => (
          <div key={i.id || i.title}>
            <strong style={{ fontSize: "0.72rem", color: "var(--mist)" }}>
              {i.company ? <span className="gbday__tag">{i.company}</span> : null}
              {i.title}
            </strong>
            <p className="gbday__note">{i.body}</p>
          </div>
        ))}
      </div>

      <div className="gbday__block">
        <h3>
          agenda do dia <em>{h.agenda_open ?? 0} abertos</em>
        </h3>
        {(board.agenda || []).length === 0 ? (
          <p className="gbday__empty">sem compromissos no live</p>
        ) : (
          <ul className="gbday__list">
            {(board.agenda || []).slice(0, 7).map((a) => (
              <li key={a.id || a.title}>
                <header>
                  <em>{a.cancelled ? "cancelado" : a.company || a.source || "agenda"}</em>
                  <span>{fmtWhen(a.start)}</span>
                </header>
                <strong style={{ opacity: a.cancelled ? 0.45 : 1 }}>{a.title}</strong>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="gbday__block">
        <h3>
          reuniões · comportamento <em>{h.meetings ?? 0}</em>
        </h3>
        {(board.meetings || []).length === 0 ? (
          <p className="gbday__empty">sem atas no live</p>
        ) : (
          <ul className="gbday__list">
            {(board.meetings || []).slice(0, 5).map((m) => (
              <li key={m.id || m.title}>
                <header>
                  <em>{m.empresa || "reunião"}</em>
                  <span>{m.when}</span>
                </header>
                <strong>{m.title}</strong>
                {m.behavior ? <p>{m.behavior}</p> : null}
                {(m.bullets || []).slice(0, 2).map((b) => (
                  <p key={b}>· {b}</p>
                ))}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="gbday__block">
        <h3>
          inbox · já lido <em>
            {(board.inbox || []).length} / {h.inbox_total ?? 0}
          </em>
        </h3>
        <ul className="gbday__list">
          {(board.inbox || []).slice(0, 8).map((m) => (
            <li key={m.id || m.subject}>
              <header>
                <em className={m.needsApproval ? "is-decision" : m.unread ? "is-important" : ""}>
                  {m.channel}
                  {m.company ? ` · ${m.company}` : ""}
                </em>
                <span>{fmtWhen(m.at)}</span>
              </header>
              <strong>{m.subject || "(sem assunto)"}</strong>
              {m.why ? <p>{m.why}</p> : m.preview ? <p>{m.preview}</p> : null}
            </li>
          ))}
        </ul>
      </div>

      {(board.tasks || []).length > 0 ? (
        <div className="gbday__block">
          <h3>tarefas quentes</h3>
          <ul className="gbday__list">
            {(board.tasks || []).slice(0, 6).map((t) => (
              <li key={t.id || t.title}>
                <header>
                  <em>{t.status}</em>
                  <span>{t.owner || t.company || ""}</span>
                </header>
                <strong>{t.title}</strong>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function InboxRow({
  item,
  busy,
  onApprove,
}: {
  item: GrokInboxItem;
  busy: string | null;
  onApprove?: (jobId: string) => void;
}) {
  const pri = item.priority || "update";
  return (
    <li>
      <header>
        <em className={`is-${pri}`}>{pri}</em>
        <span>{ago(item.ts)}</span>
      </header>
      <strong>{item.title || item.message || "mensagem"}</strong>
      {item.message && item.message !== item.title ? <p>{item.message}</p> : null}
      {item.agent ? <p>agente · {item.agent}</p> : null}
      {item.needs_action && item.job_id && onApprove ? (
        <button
          type="button"
          disabled={!!busy}
          onClick={() => onApprove(item.job_id!)}
        >
          {busy === `ok:${item.job_id}` ? "…" : "aprovar no SO"}
        </button>
      ) : null}
    </li>
  );
}

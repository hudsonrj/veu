import { useCallback, useEffect, useState } from "react";
import {
  askGrokBot,
  fetchGrokSideboard,
  fetchMeetingDetail,
  type GrokSideboard,
} from "../lib/kernel";

type Props = {
  onOpenGrok?: () => void;
  onOpenCompanies?: () => void;
  onOpenServers?: () => void;
};

type RailDetail = {
  kind: string;
  title: string;
  subtitle?: string;
  body: string[];
  ask?: string;
  shallow?: boolean;
};

function fmtWhen(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtHour(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** Painel direito do desktop — live.json do Control, organizado. */
export function DayRail({ onOpenGrok, onOpenCompanies, onOpenServers }: Props) {
  const [board, setBoard] = useState<GrokSideboard | null>(null);
  const [tab, setTab] = useState<"dia" | "inbox" | "reunioes" | "tarefas">("dia");
  const [detail, setDetail] = useState<RailDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const s = await fetchGrokSideboard();
    setBoard(s);
  }, []);

  useEffect(() => {
    let alive = true;
    let pollId: number | null = null;
    void reload();

    const startPoll = () => {
      if (pollId != null) return;
      pollId = window.setInterval(() => void reload(), 30_000);
    };

    let stopStream: (() => void) | null = null;
    void import("../lib/stream").then(({ connectKernelStream }) => {
      if (!alive) return;
      stopStream = connectKernelStream({
        onEvent: (type) => {
          if (type === "sideboard" || type === "credentials" || type === "hello") {
            void reload();
          }
        },
        onStatus: (status) => {
          if (status === "live" && pollId != null) {
            window.clearInterval(pollId);
            pollId = null;
          }
          if (status === "fallback") startPoll();
        },
      });
    });

    const boot = window.setTimeout(() => {
      if (alive && pollId == null) startPoll();
    }, 12_000);

    return () => {
      alive = false;
      window.clearTimeout(boot);
      if (pollId != null) window.clearInterval(pollId);
      stopStream?.();
    };
  }, [reload]);

  const askDepth = async (ask: string) => {
    setBusy("ask");
    setNote(null);
    const r = await askGrokBot({ intent: ask, breath: "semi", via: "os" });
    setBusy(null);
    setNote(r.ok ? r.message || "pedido ao Grok Bot enviado" : r.error || "falha");
  };

  const openMeeting = async (m: NonNullable<GrokSideboard["meetings"]>[number]) => {
    setBusy("meeting");
    const d = m.id ? await fetchMeetingDetail(m.id) : null;
    setBusy(null);
    const mt = d?.meeting || m;
    const bullets = mt.bullets || [];
    const body = [
      mt.behavior ? `comportamento · ${mt.behavior}` : "",
      ...bullets.map((b) => `· ${b}`),
    ].filter(Boolean);
    const shallow = Boolean(d?.shallow || body.length < 2);
    setDetail({
      kind: "reunião",
      title: String(mt.title || "reunião"),
      subtitle: [mt.empresa, mt.when].filter(Boolean).join(" · "),
      body: body.length ? body : ["sem resumo no live"],
      shallow,
      ask:
        d?.ask ||
        `Aprofunde a reunião «${mt.title}» (${mt.when || ""}): resumo, decisões, ações e comportamento. Use Plaud.`,
    });
  };

  const h = board?.health || {};
  const p = board?.productivity || {};
  const channels = h.channels || {};
  const available = Boolean(board?.available);

  return (
    <aside className="dayrail" aria-label="Dia · Control live">
      <header className="dayrail__head">
        <div>
          <p className="dayrail__kicker">control · live</p>
          <h2 className="dayrail__title">hoje</h2>
        </div>
        <div className="dayrail__head-meta">
          <span className={`dayrail__fleet is-${h.fleet || "off"}`}>
            {available ? h.fleet || "—" : "off"}
          </span>
          <button type="button" className="dayrail__refresh" onClick={() => void reload()}>
            atualizar
          </button>
        </div>
      </header>

      {!available ? (
        <p className="dayrail__empty">
          {board?.error || "live.json ainda não visível — o Grok Bot grava no Control."}
        </p>
      ) : (
        <>
          <section className="dayrail__metrics" aria-label="Saúde e produtividade">
            <Metric n={h.inbox_total ?? 0} label="msgs" />
            <Metric n={h.unread ?? 0} label="não lidas" />
            <Metric n={h.needs_approval ?? 0} label="OK?" />
            <Metric n={channels.outlook || 0} label="outlook" />
            <Metric n={channels.teams || 0} label="teams" />
            <Metric n={(channels.mail || 0) + (channels.gmail || 0) + (channels.email || 0)} label="e-mail" />
            <Metric n={p.doing ?? 0} label="doing" />
            <Metric n={p.blocked ?? 0} label="blocked" />
            <Metric n={h.agenda_open ?? 0} label="agenda" />
          </section>

          {(h.needs_login_count || 0) > 0 ? (
            <p className="dayrail__warn">
              {h.needs_login_count} login(s) · {(h.needs_login || [])[0]?.slice(0, 90) || "Outlook/Teams"}
            </p>
          ) : null}

          {p.counsel_headline || p.focus ? (
            <p className="dayrail__focus">
              <em>foco</em> {p.focus || p.counsel_headline}
            </p>
          ) : null}

          {(board?.insights || []).slice(0, 2).map((i) => (
            <button
              key={i.id || i.title}
              type="button"
              className="dayrail__insight"
              onClick={() =>
                setDetail({
                  kind: "insight",
                  title: String(i.title || "insight"),
                  subtitle: i.company,
                  body: [i.body || "sem texto"].filter(Boolean),
                  shallow: !i.body || String(i.body).length < 80,
                  ask: `Aprofunde o insight «${i.title}» (${i.company || ""}): contexto, evidências e próxima ação. Callback com result.summary.`,
                })
              }
            >
              {i.company ? <span className="dayrail__tag">{i.company}</span> : null}
              <strong>{i.title}</strong>
              <p>{i.body}</p>
            </button>
          ))}

          <nav className="dayrail__tabs" aria-label="Seções">
            {(
              [
                ["dia", "agenda"],
                ["inbox", "inbox"],
                ["reunioes", "reuniões"],
                ["tarefas", "tarefas"],
              ] as const
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

          {detail ? (
            <div className="dayrail__detail">
              <header>
                <em>{detail.kind}</em>
                <button type="button" onClick={() => setDetail(null)}>
                  fechar
                </button>
              </header>
              <strong>{detail.title}</strong>
              {detail.subtitle ? <p className="dayrail__sub">{detail.subtitle}</p> : null}
              {detail.body.map((line) => (
                <p key={line}>{line}</p>
              ))}
              {(detail.shallow || detail.ask) && detail.ask ? (
                <button
                  type="button"
                  className="dayrail__ask"
                  disabled={!!busy}
                  onClick={() => void askDepth(detail.ask!)}
                >
                  {busy === "ask" ? "…" : "pedir profundidade ao Grok Bot"}
                </button>
              ) : null}
              {note ? <p className="dayrail__note">{note}</p> : null}
            </div>
          ) : (
            <div className="dayrail__body">
              {tab === "dia" ? (
                <ul className="dayrail__list">
                  {(board?.agenda || []).length === 0 ? (
                    <li className="dayrail__empty-row">sem compromissos no live</li>
                  ) : (
                    (board?.agenda || []).map((a) => (
                      <li key={a.id || a.title} className={a.cancelled ? "is-dim" : ""}>
                        <button
                          type="button"
                          className="dayrail__row"
                          onClick={() =>
                            setDetail({
                              kind: "compromisso",
                              title: String(a.title || "compromisso"),
                              subtitle: [a.company, a.source, fmtWhen(a.start)]
                                .filter(Boolean)
                                .join(" · "),
                              body: [
                                a.status ? `status · ${a.status}` : "",
                                a.cancelled ? "cancelado" : "",
                                a.source || "",
                              ].filter(Boolean),
                              shallow: true,
                              ask: `Aprofunde o compromisso «${a.title}» (${fmtWhen(a.start)} · ${a.company || ""}): contexto, participantes e preparação.`,
                            })
                          }
                        >
                          <header>
                            <em>{a.company || "agenda"}</em>
                            <span>{fmtHour(a.start)}</span>
                          </header>
                          <strong>{a.title}</strong>
                          <p>{a.source}</p>
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              ) : null}

              {tab === "inbox" ? (
                <ul className="dayrail__list">
                  {(board?.inbox || []).map((m) => (
                    <li key={m.id || m.subject}>
                      <button
                        type="button"
                        className="dayrail__row"
                        onClick={() =>
                          setDetail({
                            kind: "mensagem",
                            title: String(m.subject || "(sem assunto)"),
                            subtitle: [m.channel, m.company, fmtWhen(m.at)]
                              .filter(Boolean)
                              .join(" · "),
                            body: [
                              m.sender ? `de · ${m.sender}` : "",
                              m.why || "",
                              m.preview || "",
                            ].filter(Boolean),
                            shallow: !(m.preview || m.why) || String(m.preview || "").length < 40,
                            ask: `Resumo e ação da mensagem «${m.subject}» (${m.channel} · ${m.company || ""}).`,
                          })
                        }
                      >
                        <header>
                          <em className={m.needsApproval ? "is-hot" : m.unread ? "is-new" : ""}>
                            {m.channel}
                            {m.company ? ` · ${m.company}` : ""}
                          </em>
                          <span>{fmtWhen(m.at)}</span>
                        </header>
                        <strong>{m.subject || "(sem assunto)"}</strong>
                        {m.why || m.preview ? <p>{m.why || m.preview}</p> : null}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              {tab === "reunioes" ? (
                <ul className="dayrail__list">
                  {(board?.meetings || []).map((m) => (
                    <li key={m.id || m.title}>
                      <button
                        type="button"
                        className="dayrail__row"
                        onClick={() => void openMeeting(m)}
                      >
                        <header>
                          <em>{m.empresa || "reunião"}</em>
                          <span>{m.when}</span>
                        </header>
                        <strong>{m.title}</strong>
                        {m.behavior ? <p className="dayrail__behavior">{m.behavior}</p> : null}
                        {(m.bullets || []).slice(0, 2).map((b) => (
                          <p key={b}>· {b}</p>
                        ))}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              {tab === "tarefas" ? (
                <ul className="dayrail__list">
                  {(board?.tasks || []).map((t) => (
                    <li key={t.id || t.title}>
                      <button
                        type="button"
                        className="dayrail__row"
                        onClick={() =>
                          setDetail({
                            kind: "tarefa",
                            title: String(t.title || "tarefa"),
                            subtitle: [t.status, t.owner, t.company].filter(Boolean).join(" · "),
                            body: [t.status ? `status · ${t.status}` : "", t.owner ? `dono · ${t.owner}` : ""].filter(Boolean),
                            shallow: true,
                            ask: `Aprofunde a tarefa «${t.title}» (${t.company || ""}): bloqueios, próximo passo e evidências.`,
                          })
                        }
                      >
                        <header>
                          <em>{t.status}</em>
                          <span>{t.owner || t.company || ""}</span>
                        </header>
                        <strong>{t.title}</strong>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}

          <footer className="dayrail__foot">
            <span>{board?.updatedAt ? `atualizado ${fmtWhen(board.updatedAt)}` : "live.json"}</span>
            <span className="dayrail__foot-actions">
              {onOpenCompanies ? (
                <button type="button" onClick={onOpenCompanies}>
                  empresas
                </button>
              ) : null}
              {onOpenServers ? (
                <button type="button" onClick={onOpenServers}>
                  servidores
                </button>
              ) : null}
              {onOpenGrok ? (
                <button type="button" onClick={onOpenGrok}>
                  grok bot
                </button>
              ) : null}
            </span>
          </footer>
        </>
      )}

      <style>{`
        .dayrail {
          position: absolute;
          top: 0.55rem;
          right: 0.55rem;
          bottom: 4.8rem;
          width: min(22.5rem, 34vw);
          z-index: 40;
          display: grid;
          grid-template-rows: auto auto auto auto auto 1fr auto;
          gap: 0.45rem;
          padding: 0.65rem 0.7rem 0.6rem;
          overflow: hidden;
          color: var(--mist);
          background:
            linear-gradient(165deg, rgba(10,14,18,0.88), rgba(7,9,12,0.78));
          border: 1px solid rgba(127,231,212,0.16);
          border-left-color: rgba(232,194,122,0.22);
          backdrop-filter: blur(16px);
          box-shadow: -12px 0 40px rgba(0,0,0,0.28);
        }
        .dayrail__head {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
          align-items: flex-start;
        }
        .dayrail__kicker {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.54rem;
          letter-spacing: 0.16em;
          color: var(--signal);
          text-transform: lowercase;
        }
        .dayrail__title {
          margin: 0.08rem 0 0;
          font-family: var(--font-display);
          font-size: 1.35rem;
          font-weight: 700;
          color: var(--filament);
          letter-spacing: 0.02em;
        }
        .dayrail__head-meta {
          display: grid;
          gap: 0.25rem;
          justify-items: end;
        }
        .dayrail__fleet {
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--mist-dim);
        }
        .dayrail__fleet.is-ok { color: var(--signal); }
        .dayrail__refresh, .dayrail__foot button, .dayrail__tabs button {
          border: 1px solid rgba(236,242,248,0.14);
          background: transparent;
          color: var(--mist-dim);
          font-family: var(--font-mono);
          font-size: 0.56rem;
          letter-spacing: 0.08em;
          text-transform: lowercase;
          padding: 0.22rem 0.4rem;
          cursor: pointer;
        }
        .dayrail__refresh:hover,
        .dayrail__foot button:hover,
        .dayrail__tabs button:hover {
          border-color: rgba(232,194,122,0.4);
          color: var(--filament);
        }
        .dayrail__metrics {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 0.28rem;
        }
        .dayrail__metric {
          display: grid;
          gap: 0.05rem;
          padding: 0.32rem 0.35rem;
          border: 1px solid rgba(232,194,122,0.12);
          background: rgba(0,0,0,0.22);
        }
        .dayrail__metric b {
          font-family: var(--font-mono);
          font-size: 0.92rem;
          color: var(--filament);
          font-weight: 600;
        }
        .dayrail__metric span {
          font-size: 0.5rem;
          letter-spacing: 0.08em;
          text-transform: lowercase;
          color: var(--mist-dim);
        }
        .dayrail__warn {
          margin: 0;
          font-size: 0.62rem;
          line-height: 1.35;
          color: #e8a07a;
        }
        .dayrail__focus {
          margin: 0;
          font-size: 0.72rem;
          line-height: 1.35;
          color: var(--mist);
        }
        .dayrail__focus em {
          font-style: normal;
          font-family: var(--font-mono);
          font-size: 0.54rem;
          letter-spacing: 0.12em;
          color: var(--signal);
          margin-right: 0.35rem;
          text-transform: lowercase;
        }
        .dayrail__insight {
          display: grid;
          gap: 0.12rem;
          padding: 0.2rem 0 0.35rem;
          border: 0;
          border-bottom: 1px solid rgba(232,194,122,0.08);
          background: transparent;
          color: inherit;
          text-align: left;
          cursor: pointer;
          width: 100%;
        }
        .dayrail__insight:hover strong { color: var(--filament); }
        .dayrail__row {
          display: grid;
          gap: 0.1rem;
          width: 100%;
          text-align: left;
          border: 0;
          background: transparent;
          color: inherit;
          cursor: pointer;
          padding: 0;
        }
        .dayrail__row:hover strong { color: var(--filament); }
        .dayrail__detail {
          min-height: 0;
          overflow: auto;
          display: grid;
          gap: 0.28rem;
          align-content: start;
          padding: 0.35rem 0.2rem;
          scrollbar-width: thin;
        }
        .dayrail__detail header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-family: var(--font-mono);
          font-size: 0.52rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .dayrail__detail header button,
        .dayrail__ask {
          border: 1px solid rgba(232,194,122,0.35);
          background: transparent;
          color: var(--filament);
          font-family: var(--font-mono);
          font-size: 0.56rem;
          letter-spacing: 0.06em;
          text-transform: lowercase;
          padding: 0.28rem 0.4rem;
          cursor: pointer;
        }
        .dayrail__detail strong {
          font-size: 0.82rem;
          color: var(--filament);
          line-height: 1.3;
        }
        .dayrail__detail p, .dayrail__sub {
          margin: 0;
          font-size: 0.66rem;
          line-height: 1.35;
          color: var(--mist-dim);
        }
        .dayrail__ask { justify-self: start; margin-top: 0.25rem; }
        .dayrail__note { color: var(--filament) !important; }
        .dayrail__foot-actions { display: inline-flex; gap: 0.25rem; }
        .dayrail__insight strong {
          font-size: 0.72rem;
          font-weight: 500;
          color: var(--mist);
        }
        .dayrail__insight p {
          margin: 0;
          font-size: 0.64rem;
          line-height: 1.35;
          color: var(--mist-dim);
        }
        .dayrail__tag {
          font-family: var(--font-mono);
          font-size: 0.5rem;
          letter-spacing: 0.1em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .dayrail__tabs {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 0.2rem;
        }
        .dayrail__tabs button.is-on {
          border-color: rgba(232,194,122,0.45);
          color: var(--filament);
        }
        .dayrail__body {
          min-height: 0;
          overflow: auto;
          scrollbar-width: thin;
        }
        .dayrail__list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 0.4rem;
        }
        .dayrail__list li {
          display: grid;
          gap: 0.1rem;
          padding-bottom: 0.35rem;
          border-bottom: 1px solid rgba(232,194,122,0.08);
        }
        .dayrail__list li.is-dim { opacity: 0.45; }
        .dayrail__list header {
          display: flex;
          justify-content: space-between;
          gap: 0.35rem;
          font-family: var(--font-mono);
          font-size: 0.52rem;
          letter-spacing: 0.08em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .dayrail__list header em.is-hot { color: #e8a07a; }
        .dayrail__list header em.is-new { color: var(--filament); }
        .dayrail__list strong {
          font-size: 0.72rem;
          font-weight: 500;
          line-height: 1.3;
          color: var(--mist);
        }
        .dayrail__list p {
          margin: 0;
          font-size: 0.62rem;
          line-height: 1.35;
          color: var(--mist-dim);
        }
        .dayrail__behavior { color: var(--signal) !important; }
        .dayrail__empty, .dayrail__empty-row {
          margin: 0.4rem 0;
          font-size: 0.7rem;
          color: var(--mist-dim);
          font-weight: 300;
        }
        .dayrail__foot {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 0.4rem;
          font-family: var(--font-mono);
          font-size: 0.52rem;
          letter-spacing: 0.06em;
          color: var(--mist-dim);
          text-transform: lowercase;
          border-top: 1px solid rgba(232,194,122,0.1);
          padding-top: 0.4rem;
        }
        /* mobile-first: no drawer compacto o DayRail vira fluxo estático */
        .os--compact .dayrail,
        .os__rail-drawer .dayrail {
          position: relative;
          top: auto;
          right: auto;
          bottom: auto;
          width: auto;
          max-height: none;
          margin: 0;
          padding: 0.75rem 1rem 1rem;
        }
        @media (min-width: 1024px) {
          .dayrail {
            width: min(22rem, 32vw);
          }
        }
        @media (min-width: 1280px) {
          .dayrail {
            width: min(23rem, 30vw);
          }
        }
      `}</style>
    </aside>
  );
}

function Metric({ n, label }: { n: number; label: string }) {
  return (
    <div className="dayrail__metric">
      <b>{n}</b>
      <span>{label}</span>
    </div>
  );
}

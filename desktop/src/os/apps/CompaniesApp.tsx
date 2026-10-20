import { useCallback, useEffect, useMemo, useState } from "react";
import {
  askGrokBot,
  fetchCompaniesTree,
  fetchMeetingDetail,
  type CompanyFolder,
  type CompanyProject,
  type GrokSideboard,
} from "../../lib/kernel";

type Level =
  | { kind: "root" }
  | { kind: "company"; company: CompanyFolder }
  | { kind: "project"; company: CompanyFolder; project: CompanyProject };

type DetailKind = "meeting" | "task" | "message" | "agenda" | "insight" | "project";

type Detail = {
  kind: DetailKind;
  title: string;
  subtitle?: string;
  body?: string[];
  meta?: string[];
  rawAsk?: string;
  shallow?: boolean;
};

type Msg = NonNullable<GrokSideboard["inbox"]>[number];
type Task = NonNullable<GrokSideboard["tasks"]>[number];
type Meeting = NonNullable<GrokSideboard["meetings"]>[number];
type Agenda = NonNullable<GrokSideboard["agenda"]>[number];

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

/** Pastas Empresa → projetos → conteúdo, com detalhe profundo + ask Grok. */
export function CompaniesApp() {
  const [tree, setTree] = useState<CompanyFolder[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [level, setLevel] = useState<Level>({ kind: "root" });
  const [tab, setTab] = useState<"tarefas" | "mensagens" | "reunioes" | "agenda">("tarefas");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const t = await fetchCompaniesTree();
    if (!t?.ok) {
      setErr(t?.error || "live.json indisponível");
      return;
    }
    setTree(t.companies || []);
    setUpdatedAt(t.updatedAt || "");
    setErr(null);
  }, []);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 45_000);
    return () => window.clearInterval(id);
  }, [reload]);

  const crumbs = useMemo(() => {
    if (level.kind === "root") return ["empresas"];
    if (level.kind === "company") return ["empresas", level.company.name];
    return ["empresas", level.company.name, level.project.name];
  }, [level]);

  const askDepth = async (ask: string, label: string) => {
    setBusy(label);
    setNote(null);
    const r = await askGrokBot({ intent: ask, breath: "semi", via: "os" });
    setBusy(null);
    setNote(
      r.ok
        ? r.message || "pedido enviado ao Grok Bot — o retorno cai na inbox"
        : r.error || "falha ao pedir ao Grok Bot",
    );
  };

  const openMeeting = async (m: Meeting) => {
    setBusy("meeting");
    const d = m.id ? await fetchMeetingDetail(m.id) : null;
    setBusy(null);
    const mt = d?.meeting || m;
    const bullets = (mt.bullets || []) as string[];
    const body = [
      mt.behavior ? `comportamento · ${mt.behavior}` : "",
      ...bullets.map((b) => `· ${b}`),
    ].filter(Boolean);
    const shallow = Boolean(d?.shallow || d?.needs_grok || body.length < 2);
    const ask =
      d?.ask ||
      `Aprofunde a reunião «${mt.title}» (${mt.when || ""})` +
        `${mt.empresa ? ` · ${mt.empresa}` : ""}: resumo completo, decisões, ações e humor/sobrecarga. Use Plaud. Callback com result.summary.`;
    setDetail({
      kind: "meeting",
      title: String(mt.title || "reunião"),
      subtitle: [mt.empresa, mt.when, mt.source].filter(Boolean).join(" · "),
      body: body.length ? body : ["sem resumo no live.json ainda"],
      meta: [mt.id ? `id · ${mt.id}` : ""].filter(Boolean),
      shallow,
      rawAsk: ask,
    });
  };

  const openTask = (t: Task) => {
    const body = [
      t.note || "",
      t.due ? `prazo · ${t.due}` : "",
      t.priority ? `prioridade · ${t.priority}` : "",
      t.owner ? `dono · ${t.owner}` : "",
      t.status ? `status · ${t.status}` : "",
    ].filter(Boolean);
    const shallow = body.length < 2 || !t.note;
    setDetail({
      kind: "task",
      title: String(t.title || "tarefa"),
      subtitle: [t.company, t.projectId].filter(Boolean).join(" · "),
      body: body.length ? body : ["sem detalhe no live — peça ao Grok Bot"],
      shallow,
      rawAsk: `Aprofunde a tarefa «${t.title}» (${t.company || ""} / ${t.projectId || ""}): status real, bloqueios, próximo passo e se já houve update em e-mail/Teams. Callback com result.summary.`,
    });
  };

  const openMessage = (m: Msg) => {
    const body = [
      m.sender ? `de · ${m.sender}` : "",
      m.why || "",
      m.preview || "",
      m.needsApproval ? "precisa de aprovação" : "",
      m.unread ? "não lida" : "",
    ].filter(Boolean);
    const shallow = !(m.preview || m.why) || String(m.preview || "").length < 40;
    setDetail({
      kind: "message",
      title: String(m.subject || "(sem assunto)"),
      subtitle: [m.channel, m.company, fmtWhen(m.at)].filter(Boolean).join(" · "),
      body: body.length ? body : ["prévia vazia no live"],
      shallow,
      rawAsk: `Traga o conteúdo / resumo da mensagem «${m.subject}» (${m.channel} · ${m.company || ""}) e diga se precisa de ação. Callback com result.summary.`,
    });
  };

  const openAgenda = (a: Agenda) => {
    const body = [
      a.source || "",
      a.location ? `local · ${a.location}` : "",
      a.status ? `status · ${a.status}` : "",
      a.cancelled ? "cancelado" : "",
      a.start ? `início · ${fmtWhen(a.start)}` : "",
      a.end ? `fim · ${fmtWhen(a.end)}` : "",
    ].filter(Boolean);
    const shallow = body.length < 3;
    setDetail({
      kind: "agenda",
      title: String(a.title || "compromisso"),
      subtitle: [a.company, a.source].filter(Boolean).join(" · "),
      body,
      shallow,
      rawAsk: `Aprofunde o compromisso «${a.title}» (${fmtWhen(a.start)} · ${a.company || ""}): contexto, participantes, preparação e o que saiu/sairá. Callback com result.summary.`,
    });
  };

  const openProject = (company: CompanyFolder, project: CompanyProject) => {
    setLevel({ kind: "project", company, project });
    setTab("tarefas");
    setDetail({
      kind: "project",
      title: project.name,
      subtitle: `${company.name} · ${project.status || "projeto"}`,
      body: [
        project.summary || "sem resumo no live",
        `tarefas · ${project.counts?.tasks ?? project.tasks?.length ?? 0}`,
        `mensagens · ${project.counts?.messages ?? project.messages?.length ?? 0}`,
        `reuniões · ${project.counts?.meetings ?? project.meetings?.length ?? 0}`,
      ],
      shallow: !project.summary || project.summary.length < 40,
      rawAsk: `Resumo profundo do projeto «${project.name}» (${company.name}): status, riscos, próximas ações, reuniões recentes e mensagens quentes. Use live/Plaud/Outlook. Callback com result.summary.`,
    });
  };

  const projectBag = level.kind === "project" ? level.project : null;
  const companyLoose =
    level.kind === "company" ? level.company.loose : null;

  const listTasks =
    projectBag?.tasks ||
    companyLoose?.tasks ||
    [];
  const listMsgs =
    projectBag?.messages ||
    companyLoose?.messages ||
    [];
  const listMeetings =
    projectBag?.meetings ||
    companyLoose?.meetings ||
    [];
  const listAgenda =
    projectBag?.agenda ||
    companyLoose?.agenda ||
    [];

  return (
    <div className="co">
      <header className="co__head">
        <div>
          <p className="co__kicker">empresas · live.json</p>
          <nav className="co__crumbs" aria-label="caminho">
            {crumbs.map((c, i) => (
              <button
                key={`${c}-${i}`}
                type="button"
                onClick={() => {
                  if (i === 0) setLevel({ kind: "root" });
                  else if (i === 1 && level.kind !== "root")
                    setLevel({ kind: "company", company: level.company });
                }}
              >
                {c}
              </button>
            ))}
          </nav>
        </div>
        <button type="button" className="co__refresh" onClick={() => void reload()}>
          atualizar
        </button>
      </header>

      {err ? <p className="co__err">{err}</p> : null}
      {note ? <p className="co__note">{note}</p> : null}

      <div className={`co__split${detail ? " has-detail" : ""}`}>
        <div className="co__main">
          {level.kind === "root" ? (
            <section>
              <h3 className="co__section">pastas · empresas</h3>
              <div className="co__icons">
                {tree.map((co) => (
                  <button
                    key={co.id}
                    type="button"
                    className="co__icon"
                    style={{ ["--hue" as string]: co.hue || "#E8C27A" }}
                    onClick={() => {
                      setLevel({ kind: "company", company: co });
                      setDetail(null);
                    }}
                    onDoubleClick={() => {
                      setLevel({ kind: "company", company: co });
                    }}
                  >
                    <span className="co__glyph" aria-hidden>
                      {co.glyph || co.name[0]}
                    </span>
                    <strong>{co.name}</strong>
                    <em>
                      {co.counts?.projects ?? 0} proj · {co.counts?.tasks ?? 0} tar ·{" "}
                      {co.counts?.messages ?? 0} msg
                    </em>
                  </button>
                ))}
              </div>
              {!tree.length ? (
                <p className="co__empty">nenhuma empresa no live ainda</p>
              ) : null}
            </section>
          ) : null}

          {level.kind === "company" ? (
            <section>
              <h3 className="co__section">
                projetos · {level.company.name}{" "}
                <em>
                  {level.company.counts?.doing ?? 0} doing ·{" "}
                  {level.company.counts?.blocked ?? 0} blocked ·{" "}
                  {level.company.counts?.unread ?? 0} unread
                </em>
              </h3>
              <div className="co__icons">
                {(level.company.projects || []).map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className="co__icon is-project"
                    style={{ ["--hue" as string]: p.hue || level.company.hue || "#7FE7D4" }}
                    onClick={() => openProject(level.company, p)}
                  >
                    <span className="co__glyph" aria-hidden>
                      {p.glyph || "◇"}
                    </span>
                    <strong>{p.name}</strong>
                    <em>
                      {p.counts?.tasks ?? 0} tar · {p.counts?.meetings ?? 0} reu ·{" "}
                      {p.status || "—"}
                    </em>
                  </button>
                ))}
                <button
                  type="button"
                  className="co__icon is-loose"
                  onClick={() => {
                    setLevel({
                      kind: "project",
                      company: level.company,
                      project: {
                        id: "_loose",
                        name: "Geral · sem projeto",
                        company: level.company.name,
                        summary: "Itens da empresa ainda não ligados a um projeto.",
                        tasks: level.company.loose?.tasks || [],
                        messages: level.company.loose?.messages || [],
                        meetings: level.company.loose?.meetings || [],
                        agenda: level.company.loose?.agenda || [],
                        counts: {
                          tasks: level.company.loose?.tasks?.length || 0,
                          messages: level.company.loose?.messages?.length || 0,
                          meetings: level.company.loose?.meetings?.length || 0,
                          agenda: level.company.loose?.agenda?.length || 0,
                        },
                      },
                    });
                    setTab("mensagens");
                    setDetail(null);
                  }}
                >
                  <span className="co__glyph">⊕</span>
                  <strong>Geral</strong>
                  <em>msgs / reuniões soltas</em>
                </button>
              </div>
            </section>
          ) : null}

          {level.kind === "project" ? (
            <section>
              <h3 className="co__section">
                {level.project.name} <em>{level.company.name}</em>
              </h3>
              {level.project.summary ? (
                <p className="co__summary">{level.project.summary}</p>
              ) : null}
              <nav className="co__tabs">
                {(
                  [
                    ["tarefas", listTasks.length],
                    ["mensagens", listMsgs.length],
                    ["reunioes", listMeetings.length],
                    ["agenda", listAgenda.length],
                  ] as const
                ).map(([id, n]) => (
                  <button
                    key={id}
                    type="button"
                    className={tab === id ? "is-on" : ""}
                    onClick={() => setTab(id)}
                  >
                    {id} · {n}
                  </button>
                ))}
              </nav>

              {tab === "tarefas" ? (
                <ul className="co__list">
                  {listTasks.map((t) => (
                    <li key={t?.id || t?.title}>
                      <button type="button" onClick={() => t && openTask(t)}>
                        <header>
                          <em>{t?.status}</em>
                          <span>{t?.owner || t?.priority || ""}</span>
                        </header>
                        <strong>{t?.title}</strong>
                      </button>
                    </li>
                  ))}
                  {!listTasks.length ? <li className="co__empty">sem tarefas</li> : null}
                </ul>
              ) : null}

              {tab === "mensagens" ? (
                <ul className="co__list">
                  {listMsgs.map((m) => (
                    <li key={m?.id || m?.subject}>
                      <button type="button" onClick={() => m && openMessage(m)}>
                        <header>
                          <em>{m?.channel}</em>
                          <span>{fmtWhen(m?.at)}</span>
                        </header>
                        <strong>{m?.subject}</strong>
                        {m?.why ? <p>{m.why}</p> : null}
                      </button>
                    </li>
                  ))}
                  {!listMsgs.length ? <li className="co__empty">sem mensagens</li> : null}
                </ul>
              ) : null}

              {tab === "reunioes" ? (
                <ul className="co__list">
                  {listMeetings.map((m) => (
                    <li key={m?.id || m?.title}>
                      <button type="button" onClick={() => m && void openMeeting(m)}>
                        <header>
                          <em>{m?.empresa}</em>
                          <span>{m?.when}</span>
                        </header>
                        <strong>{m?.title}</strong>
                        {m?.behavior ? <p>{m.behavior}</p> : null}
                      </button>
                    </li>
                  ))}
                  {!listMeetings.length ? <li className="co__empty">sem reuniões</li> : null}
                </ul>
              ) : null}

              {tab === "agenda" ? (
                <ul className="co__list">
                  {listAgenda.map((a) => (
                    <li key={a?.id || a?.title}>
                      <button type="button" onClick={() => a && openAgenda(a)}>
                        <header>
                          <em>{a?.cancelled ? "cancelado" : a?.company}</em>
                          <span>{fmtWhen(a?.start)}</span>
                        </header>
                        <strong>{a?.title}</strong>
                      </button>
                    </li>
                  ))}
                  {!listAgenda.length ? <li className="co__empty">sem compromissos</li> : null}
                </ul>
              ) : null}
            </section>
          ) : null}
        </div>

        {detail ? (
          <aside className="co__detail">
            <header>
              <p className="co__kicker">{detail.kind}</p>
              <button type="button" onClick={() => setDetail(null)}>
                fechar
              </button>
            </header>
            <h3>{detail.title}</h3>
            {detail.subtitle ? <p className="co__sub">{detail.subtitle}</p> : null}
            <div className="co__detail-body">
              {(detail.body || []).map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
            {(detail.meta || []).map((m) => (
              <p key={m} className="co__meta">
                {m}
              </p>
            ))}
            {detail.shallow || detail.rawAsk ? (
              <div className="co__ask">
                <p>
                  {detail.shallow
                    ? "pouca profundidade no live — peça ao Grok Bot"
                    : "quer mais profundidade?"}
                </p>
                <button
                  type="button"
                  disabled={!!busy || !detail.rawAsk}
                  onClick={() =>
                    detail.rawAsk && void askDepth(detail.rawAsk, `ask:${detail.kind}`)
                  }
                >
                  {busy?.startsWith("ask") ? "…" : "pedir ao Grok Bot"}
                </button>
              </div>
            ) : null}
          </aside>
        ) : null}
      </div>

      <footer className="co__foot">
        {updatedAt ? `live · ${fmtWhen(updatedAt)}` : "live.json"}
        {busy === "meeting" ? " · carregando reunião…" : ""}
      </footer>

      <style>{`
        .co {
          height: 100%;
          min-height: 0;
          display: grid;
          grid-template-rows: auto auto 1fr auto;
          gap: 0.45rem;
          padding: 0.65rem 0.75rem 0.6rem;
          color: var(--mist);
          overflow: hidden;
        }
        .co__head {
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
          align-items: flex-start;
        }
        .co__kicker {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.54rem;
          letter-spacing: 0.14em;
          color: var(--signal);
          text-transform: lowercase;
        }
        .co__crumbs {
          display: flex;
          flex-wrap: wrap;
          gap: 0.25rem;
          margin-top: 0.2rem;
        }
        .co__crumbs button, .co__refresh, .co__tabs button, .co__detail header button, .co__ask button {
          border: 1px solid rgba(236,242,248,0.14);
          background: transparent;
          color: var(--mist-dim);
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.06em;
          text-transform: lowercase;
          padding: 0.22rem 0.4rem;
          cursor: pointer;
        }
        .co__crumbs button:hover, .co__refresh:hover, .co__tabs button:hover,
        .co__detail header button:hover, .co__ask button:hover {
          border-color: rgba(232,194,122,0.45);
          color: var(--filament);
        }
        .co__err { margin: 0; color: #e8a07a; font-size: 0.72rem; }
        .co__note { margin: 0; color: var(--filament); font-size: 0.7rem; }
        .co__split {
          min-height: 0;
          display: grid;
          grid-template-columns: 1fr;
          gap: 0.5rem;
          overflow: hidden;
        }
        .co__split.has-detail {
          grid-template-columns: minmax(0, 1.1fr) minmax(240px, 0.9fr);
        }
        .co__main, .co__detail {
          min-height: 0;
          overflow: auto;
          scrollbar-width: thin;
        }
        .co__section {
          margin: 0 0 0.45rem;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          letter-spacing: 0.12em;
          text-transform: lowercase;
          color: var(--signal);
          display: flex;
          justify-content: space-between;
          gap: 0.5rem;
        }
        .co__section em { font-style: normal; color: var(--mist-dim); }
        .co__icons {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(7.2rem, 1fr));
          gap: 0.45rem;
        }
        .co__icon {
          display: grid;
          justify-items: center;
          gap: 0.25rem;
          text-align: center;
          padding: 0.55rem 0.4rem 0.5rem;
          border: 1px solid color-mix(in srgb, var(--hue) 35%, transparent);
          background: rgba(7,9,12,0.4);
          color: var(--mist);
          cursor: pointer;
        }
        .co__icon:hover {
          border-color: var(--hue);
          color: var(--filament);
        }
        .co__glyph {
          width: 2.4rem;
          height: 2.4rem;
          display: grid;
          place-items: center;
          border: 1px solid color-mix(in srgb, var(--hue) 55%, transparent);
          color: var(--hue);
          font-family: var(--font-display);
          font-size: 1rem;
          font-weight: 700;
          background: color-mix(in srgb, var(--hue) 12%, transparent);
        }
        .co__icon strong {
          font-size: 0.7rem;
          font-weight: 500;
          line-height: 1.25;
        }
        .co__icon em {
          font-style: normal;
          font-size: 0.54rem;
          color: var(--mist-dim);
          line-height: 1.3;
        }
        .co__summary {
          margin: 0 0 0.45rem;
          font-size: 0.74rem;
          line-height: 1.4;
          color: var(--mist-dim);
        }
        .co__tabs {
          display: flex;
          flex-wrap: wrap;
          gap: 0.25rem;
          margin-bottom: 0.45rem;
        }
        .co__tabs button.is-on {
          border-color: rgba(232,194,122,0.5);
          color: var(--filament);
        }
        .co__list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 0.35rem;
        }
        .co__list button {
          width: 100%;
          text-align: left;
          display: grid;
          gap: 0.1rem;
          padding: 0.4rem 0.45rem;
          border: 1px solid rgba(232,194,122,0.1);
          background: rgba(0,0,0,0.2);
          color: var(--mist);
          cursor: pointer;
        }
        .co__list button:hover { border-color: rgba(232,194,122,0.35); }
        .co__list header {
          display: flex;
          justify-content: space-between;
          font-family: var(--font-mono);
          font-size: 0.52rem;
          letter-spacing: 0.08em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        .co__list strong { font-size: 0.74rem; font-weight: 500; }
        .co__list p { margin: 0; font-size: 0.64rem; color: var(--mist-dim); line-height: 1.35; }
        .co__empty { margin: 0.4rem 0; font-size: 0.7rem; color: var(--mist-dim); }
        .co__detail {
          padding: 0.55rem 0.6rem;
          border: 1px solid rgba(127,231,212,0.16);
          background: rgba(6,10,12,0.55);
          display: grid;
          align-content: start;
          gap: 0.35rem;
        }
        .co__detail header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .co__detail h3 {
          margin: 0;
          font-family: var(--font-display);
          font-size: 1rem;
          color: var(--filament);
          font-weight: 700;
          line-height: 1.25;
        }
        .co__sub { margin: 0; font-size: 0.68rem; color: var(--mist-dim); }
        .co__detail-body p {
          margin: 0 0 0.25rem;
          font-size: 0.72rem;
          line-height: 1.4;
          color: var(--mist);
        }
        .co__meta {
          margin: 0;
          font-family: var(--font-mono);
          font-size: 0.52rem;
          color: var(--mist-dim);
        }
        .co__ask {
          margin-top: 0.35rem;
          padding-top: 0.4rem;
          border-top: 1px solid rgba(232,194,122,0.12);
          display: grid;
          gap: 0.3rem;
        }
        .co__ask p { margin: 0; font-size: 0.66rem; color: #e8a07a; }
        .co__foot {
          font-family: var(--font-mono);
          font-size: 0.52rem;
          letter-spacing: 0.06em;
          color: var(--mist-dim);
          text-transform: lowercase;
        }
        @media (max-width: 720px) {
          .co__split.has-detail { grid-template-columns: 1fr; }
        }
      `}</style>
    </div>
  );
}

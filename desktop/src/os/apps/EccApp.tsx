import { useEffect, useMemo, useState } from "react";
import {
  fetchEccCatalog,
  type EccAgent,
  type EccCatalog,
  type EccSkill,
} from "../../lib/kernel";

type Tab = "overview" | "agents" | "skills";

type Props = {
  onUse?: (intent: string) => void;
};

type Picked =
  | { kind: "agent"; item: EccAgent }
  | { kind: "skill"; item: EccSkill }
  | null;

const STARTER_AGENTS = [
  "chief-of-staff",
  "planner",
  "architect",
  "doc-updater",
  "code-reviewer",
];

const STARTER_SKILLS = [
  "agentic-os",
  "continuous-agent-loop",
  "browser-qa",
  "connector-builder",
];

/** Músculo ECC — um clique aciona no Chat Véu. */
export function EccApp({ onUse }: Props) {
  const [cat, setCat] = useState<EccCatalog | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Picked>(null);

  useEffect(() => {
    void fetchEccCatalog().then((c) => {
      if (!c) {
        setErr("kernel offline — /ecc");
        return;
      }
      setCat(c);
      setErr(null);
    });
  }, []);

  const query = q.trim().toLowerCase();

  const agents = useMemo(() => {
    const list = cat?.agents || [];
    if (!query) return list;
    return list.filter((a) =>
      [a.id, a.title, a.role, a.description, ...(a.triggers || []), ...(a.can_do || [])]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [cat, query]);

  const skills = useMemo(() => {
    const list = cat?.skills || [];
    if (!query) return list;
    return list.filter((s) =>
      [s.id, s.title, s.description, ...(s.triggers || []), ...(s.can_do || [])]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [cat, query]);

  const launchAgent = (a: EccAgent) => {
    onUse?.(`ative o agente ECC ${a.id} (${a.title}) e assume a próxima tarefa no SO`);
  };

  const launchSkill = (s: EccSkill) => {
    onUse?.(`use a skill ECC ${s.id} (${s.title}) no que eu precisar agora`);
  };

  const launchLine = (line: string) => {
    onUse?.(`${line}. Faça isso agora no Véu e me diga o resultado.`);
  };

  const starters = useMemo(() => {
    const byIdA = Object.fromEntries((cat?.agents || []).map((a) => [a.id, a]));
    const byIdS = Object.fromEntries((cat?.skills || []).map((s) => [s.id, s]));
    const a = STARTER_AGENTS.map((id) => byIdA[id]).filter(Boolean) as EccAgent[];
    const s = STARTER_SKILLS.map((id) => byIdS[id]).filter(Boolean) as EccSkill[];
    // se vendor não tiver ids core, pega os primeiros
    if (a.length < 3) a.push(...(cat?.agents || []).slice(0, 5));
    if (s.length < 2) s.push(...(cat?.skills || []).slice(0, 4));
    const seenA = new Set<string>();
    const seenS = new Set<string>();
    return {
      agents: a.filter((x) => (seenA.has(x.id) ? false : (seenA.add(x.id), true))).slice(0, 5),
      skills: s.filter((x) => (seenS.has(x.id) ? false : (seenS.add(x.id), true))).slice(0, 4),
    };
  }, [cat]);

  return (
    <div className="ecc">
      <header className="ecc__hero">
        <div>
          <h2>ECC</h2>
          <p>
            Musculatura do SO. <strong>Clique = roda no Chat Véu</strong> — sem
            configurar nada. Catálogo só pra achar o especialista certo.
          </p>
        </div>
        <div className="ecc__meters">
          <span>
            <strong>{cat?.counts?.agents ?? "—"}</strong> agentes
          </span>
          <span>
            <strong>{cat?.counts?.skills ?? "—"}</strong> skills
          </span>
        </div>
      </header>

      {err ? <p className="ecc__err">{err}</p> : null}

      <div className="ecc__toolbar">
        <div className="ecc__tabs">
          {(
            [
              ["overview", "usar agora"],
              ["agents", "agentes"],
              ["skills", "skills"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={tab === id ? "is-on" : undefined}
              onClick={() => {
                setTab(id);
                if (id === "overview") setPicked(null);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {tab !== "overview" ? (
          <input
            className="ecc__search"
            placeholder={tab === "agents" ? "buscar agente…" : "buscar skill…"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        ) : null}
      </div>

      <div className="ecc__body">
        <div className="ecc__list">
          {tab === "overview" && (
            <>
              <p className="ecc__section">agentes — um clique</p>
              <div className="ecc__quick">
                {starters.agents.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className="ecc__launch"
                    disabled={!onUse}
                    onClick={() => launchAgent(a)}
                  >
                    <strong>{a.title}</strong>
                    <em>{a.role || a.description || a.id}</em>
                    <span>rodar no chat →</span>
                  </button>
                ))}
              </div>

              <p className="ecc__section">skills — um clique</p>
              <div className="ecc__quick">
                {starters.skills.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="ecc__launch is-skill"
                    disabled={!onUse}
                    onClick={() => launchSkill(s)}
                  >
                    <strong>{s.title}</strong>
                    <em>{s.description || s.id}</em>
                    <span>rodar no chat →</span>
                  </button>
                ))}
              </div>

              <p className="ecc__section">pedidos prontos</p>
              <ul className="ecc__cans ecc__cans--click">
                {(cat?.what_we_can_do || []).map((line) => (
                  <li key={line}>
                    <button
                      type="button"
                      disabled={!onUse}
                      onClick={() => launchLine(line)}
                    >
                      {line}
                    </button>
                  </li>
                ))}
                {!cat ? <li className="ecc__dim">carregando…</li> : null}
              </ul>
            </>
          )}

          {tab === "agents" &&
            agents.map((a) => (
              <div
                key={a.id}
                className={`ecc__row${picked?.kind === "agent" && picked.item.id === a.id ? " is-on" : ""}`}
              >
                <button
                  type="button"
                  className="ecc__rowmain"
                  onClick={() => setPicked({ kind: "agent", item: a })}
                >
                  <strong>{a.title}</strong>
                  <em>{a.role || a.description || a.id}</em>
                </button>
                <button
                  type="button"
                  className="ecc__rowgo"
                  disabled={!onUse}
                  onClick={() => launchAgent(a)}
                  title="Acionar no Chat Véu"
                >
                  usar
                </button>
              </div>
            ))}

          {tab === "skills" &&
            skills.map((s) => (
              <div
                key={s.id}
                className={`ecc__row${picked?.kind === "skill" && picked.item.id === s.id ? " is-on" : ""}`}
              >
                <button
                  type="button"
                  className="ecc__rowmain"
                  onClick={() => setPicked({ kind: "skill", item: s })}
                >
                  <strong>{s.title}</strong>
                  <em>{s.description || s.id}</em>
                </button>
                <button
                  type="button"
                  className="ecc__rowgo"
                  disabled={!onUse}
                  onClick={() => launchSkill(s)}
                  title="Usar no Chat Véu"
                >
                  usar
                </button>
              </div>
            ))}

          {tab === "agents" && agents.length === 0 ? (
            <p className="ecc__dim">nenhum agente com esse filtro</p>
          ) : null}
          {tab === "skills" && skills.length === 0 ? (
            <p className="ecc__dim">nenhuma skill com esse filtro</p>
          ) : null}
        </div>

        <aside className="ecc__detail">
          {tab === "overview" && !picked ? (
            <div className="ecc__empty">
              <p>
                <strong>Como usar</strong>
              </p>
              <p>
                Clique num agente/skill à esquerda → abre o <em>Chat Véu</em> e
                já manda o pedido. Não precisa selecionar e confirmar.
              </p>
              <p className="ecc__dim">
                Também funciona digitando no chat: “ative o planejador e monte o
                plano da semana”.
              </p>
              <p className="ecc__dim">
                root · <code>{cat?.root || "—"}</code>
              </p>
            </div>
          ) : !picked ? (
            <div className="ecc__empty">
              <p>Detalhes à direita · botão <strong>usar</strong> aciona na hora.</p>
            </div>
          ) : (
            <>
              <p className="ecc__kind">
                {picked.kind === "agent" ? "agente" : "skill"}
              </p>
              <h3>{picked.item.title}</h3>
              <p className="ecc__id">{picked.item.id}</p>
              <p className="ecc__desc">
                {picked.kind === "agent"
                  ? picked.item.description || picked.item.role || "—"
                  : picked.item.description || "—"}
              </p>

              {picked.kind === "agent" && picked.item.tools?.length ? (
                <section>
                  <h4>tools</h4>
                  <div className="ecc__chips">
                    {picked.item.tools.map((t) => (
                      <span key={t}>{t}</span>
                    ))}
                  </div>
                </section>
              ) : null}

              {picked.item.triggers?.length ? (
                <section>
                  <h4>quando aciona</h4>
                  <div className="ecc__chips">
                    {picked.item.triggers.slice(0, 10).map((t) => (
                      <span key={t}>{t}</span>
                    ))}
                  </div>
                </section>
              ) : null}

              <section>
                <h4>o que dá pra fazer</h4>
                <ul className="ecc__cans">
                  {(picked.item.can_do || []).length ? (
                    picked.item.can_do!.map((c) => <li key={c}>{c}</li>)
                  ) : (
                    <li className="ecc__dim">Roda no chat com o botão abaixo.</li>
                  )}
                </ul>
              </section>

              <button
                type="button"
                className="ecc__go"
                disabled={!onUse}
                onClick={() =>
                  picked.kind === "agent"
                    ? launchAgent(picked.item)
                    : launchSkill(picked.item)
                }
              >
                usar no chat agora →
              </button>
            </>
          )}
        </aside>
      </div>

      <style>{`
        .ecc {
          height: 100%;
          display: flex;
          flex-direction: column;
          gap: 0.65rem;
          padding: 0.85rem 1rem 1rem;
          color: #e8ebe6;
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
          background:
            radial-gradient(ellipse at 10% 0%, rgba(158,201,176,0.12), transparent 45%),
            linear-gradient(165deg, #121816 0%, #0c100e 55%, #101612 100%);
        }
        .ecc__hero {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          align-items: flex-start;
        }
        .ecc__hero h2 {
          margin: 0;
          font-family: "IBM Plex Serif", Georgia, serif;
          font-weight: 500;
          font-size: 1.55rem;
          letter-spacing: 0.02em;
          color: #d7ebe0;
        }
        .ecc__hero p {
          margin: 0.25rem 0 0;
          max-width: 38rem;
          font-size: 0.88rem;
          line-height: 1.4;
          color: #a8b8ae;
        }
        .ecc__hero strong { color: #d7ebe0; font-weight: 560; }
        .ecc__meters {
          display: flex;
          gap: 0.75rem;
          font-size: 0.78rem;
          color: #9aafa3;
        }
        .ecc__meters strong {
          color: #cfe8d8;
          font-size: 1.05rem;
          margin-right: 0.2rem;
        }
        .ecc__err { color: #e8a0a0; font-size: 0.85rem; margin: 0; }
        .ecc__toolbar {
          display: flex;
          gap: 0.75rem;
          align-items: center;
          flex-wrap: wrap;
        }
        .ecc__tabs { display: flex; gap: 0.35rem; }
        .ecc__tabs button {
          border: 1px solid rgba(200,220,208,0.14);
          background: rgba(255,255,255,0.03);
          color: #b7c8bc;
          border-radius: 4px;
          padding: 0.35rem 0.7rem;
          font-size: 0.78rem;
          cursor: pointer;
        }
        .ecc__tabs button.is-on {
          border-color: rgba(158,201,176,0.45);
          color: #e7f5ec;
          background: rgba(158,201,176,0.12);
        }
        .ecc__search {
          flex: 1;
          min-width: 10rem;
          border: 1px solid rgba(200,220,208,0.16);
          background: rgba(0,0,0,0.25);
          color: #e8ebe6;
          border-radius: 4px;
          padding: 0.4rem 0.65rem;
          font-size: 0.85rem;
        }
        .ecc__body {
          flex: 1;
          min-height: 0;
          display: grid;
          grid-template-columns: minmax(0, 1.2fr) minmax(13rem, 0.85fr);
          gap: 0.75rem;
        }
        .ecc__list {
          overflow: auto;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          padding-right: 0.2rem;
        }
        .ecc__section {
          margin: 0.55rem 0 0.2rem;
          font-size: 0.7rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: #7f9488;
        }
        .ecc__quick {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
          gap: 0.4rem;
        }
        .ecc__launch {
          text-align: left;
          border: 1px solid rgba(158,201,176,0.28);
          background: rgba(158,201,176,0.08);
          color: inherit;
          border-radius: 7px;
          padding: 0.65rem 0.7rem;
          cursor: pointer;
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
          min-height: 5.2rem;
        }
        .ecc__launch.is-skill {
          border-color: rgba(180,200,220,0.28);
          background: rgba(140,170,200,0.08);
        }
        .ecc__launch strong { font-size: 0.9rem; color: #eaf5ee; }
        .ecc__launch em {
          font-style: normal;
          font-size: 0.72rem;
          color: #8fa396;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          flex: 1;
        }
        .ecc__launch span {
          font-size: 0.7rem;
          color: #9ec9b0;
          margin-top: 0.15rem;
        }
        .ecc__launch:hover:not(:disabled) {
          background: rgba(158,201,176,0.18);
          border-color: rgba(158,201,176,0.5);
        }
        .ecc__launch:disabled { opacity: 0.5; cursor: default; }
        .ecc__row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.35rem;
          align-items: stretch;
        }
        .ecc__rowmain {
          text-align: left;
          border: 1px solid rgba(200,220,208,0.1);
          background: rgba(255,255,255,0.025);
          color: inherit;
          border-radius: 6px;
          padding: 0.55rem 0.7rem;
          cursor: pointer;
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }
        .ecc__row.is-on .ecc__rowmain {
          border-color: rgba(158,201,176,0.5);
          background: rgba(158,201,176,0.1);
        }
        .ecc__rowmain strong { font-size: 0.9rem; font-weight: 560; color: #e9f2ec; }
        .ecc__rowmain em {
          font-style: normal;
          font-size: 0.75rem;
          color: #8fa396;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .ecc__rowgo {
          border: 1px solid rgba(158,201,176,0.4);
          background: rgba(158,201,176,0.16);
          color: #eef8f1;
          border-radius: 6px;
          padding: 0 0.75rem;
          font-size: 0.78rem;
          cursor: pointer;
          min-width: 3.4rem;
        }
        .ecc__rowgo:hover:not(:disabled) { background: rgba(158,201,176,0.28); }
        .ecc__detail {
          border: 1px solid rgba(200,220,208,0.12);
          border-radius: 8px;
          padding: 0.85rem;
          overflow: auto;
          background: rgba(0,0,0,0.18);
        }
        .ecc__kind {
          margin: 0;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-size: 0.68rem;
          color: #8fbf9f;
        }
        .ecc__detail h3 {
          margin: 0.2rem 0 0;
          font-family: "IBM Plex Serif", Georgia, serif;
          font-weight: 500;
          font-size: 1.25rem;
          color: #eaf5ee;
        }
        .ecc__id {
          margin: 0.15rem 0 0.55rem;
          font-size: 0.75rem;
          color: #7f9488;
          font-family: ui-monospace, monospace;
        }
        .ecc__desc {
          margin: 0 0 0.75rem;
          font-size: 0.86rem;
          line-height: 1.45;
          color: #c2d2c8;
        }
        .ecc__detail h4 {
          margin: 0.7rem 0 0.35rem;
          font-size: 0.72rem;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: #8aa092;
          font-weight: 560;
        }
        .ecc__chips {
          display: flex;
          flex-wrap: wrap;
          gap: 0.3rem;
        }
        .ecc__chips span {
          font-size: 0.72rem;
          padding: 0.18rem 0.45rem;
          border-radius: 3px;
          background: rgba(158,201,176,0.1);
          color: #c5dfd0;
          border: 1px solid rgba(158,201,176,0.18);
        }
        .ecc__cans {
          margin: 0;
          padding-left: 1.1rem;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          font-size: 0.86rem;
          line-height: 1.4;
          color: #d0dfd6;
        }
        .ecc__cans--click {
          list-style: none;
          padding-left: 0;
        }
        .ecc__cans--click button {
          width: 100%;
          text-align: left;
          border: 1px solid rgba(200,220,208,0.1);
          background: rgba(255,255,255,0.03);
          color: #d0dfd6;
          border-radius: 5px;
          padding: 0.45rem 0.65rem;
          font-size: 0.82rem;
          cursor: pointer;
        }
        .ecc__cans--click button:hover:not(:disabled) {
          border-color: rgba(158,201,176,0.4);
          background: rgba(158,201,176,0.1);
        }
        .ecc__go {
          margin-top: 1rem;
          width: 100%;
          border: 1px solid rgba(158,201,176,0.45);
          background: rgba(158,201,176,0.16);
          color: #eef8f1;
          border-radius: 6px;
          padding: 0.55rem 0.75rem;
          font-size: 0.88rem;
          cursor: pointer;
        }
        .ecc__go:hover:not(:disabled) { background: rgba(158,201,176,0.24); }
        .ecc__empty p { margin: 0 0 0.5rem; color: #a8b8ae; font-size: 0.88rem; }
        .ecc__dim { color: #6f8578 !important; font-size: 0.8rem; }
        .ecc code { font-size: 0.75rem; color: #9ec9b0; }
        @media (max-width: 720px) {
          .ecc__body { grid-template-columns: 1fr; }
          .ecc__detail { min-height: 10rem; }
        }
      `}</style>
    </div>
  );
}

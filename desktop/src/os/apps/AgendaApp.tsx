import { useCallback, useEffect, useMemo, useState } from "react";
import { callBridge, probeBridge } from "../../bridge/hostBridge";
import { apiFetch, KERNEL, approveGrokJob, askGrokBot  } from "../../lib/kernel";

type Range = "day" | "week" | "month";

type Item = {
  id?: string;
  title?: string;
  kind?: string;
  source?: string;
  ts?: number;
  state?: string;
  agent?: string;
  message?: string;
  priority?: string;
  job_id?: string;
};

type DayBucket = { day: string; count: number; items: Item[] };
type Slot = { id: string; label: string; items: Item[] };
type Insight = { tone?: string; text?: string };

type AgendaSnap = {
  ok?: boolean;
  range?: Range;
  label?: string;
  items?: Item[];
  by_day?: DayBucket[];
  slots?: Slot[];
  insights?: Insight[];
  decisions?: Item[];
  running?: Item[];
  counts?: Record<string, number>;
  bridges?: { grokbot?: string; hermes?: string };
  tip?: string;
  source?: string;
};

function dayKey(ts: number) {
  const d = new Date(ts * 1000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fmtTime(ts?: number) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDay(day: string) {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1).toLocaleDateString("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

function sourceHue(source?: string) {
  switch (source) {
    case "grokbot":
      return "#E8C27A";
    case "hermes":
      return "#8FBF9F";
    case "studio":
      return "#7FE7D4";
    case "harness":
      return "#9EC9B0";
    default:
      return "#A8B4C0";
  }
}

/** Monta snap a partir de /os/day + /os/queue quando /os/agenda ainda não existe no kernel. */
function synthesizeFromLegacy(
  range: Range,
  day: Record<string, unknown>,
  queue: Record<string, unknown>,
): AgendaSnap {
  const now = Date.now() / 1000;
  const spans = { day: 86_400, week: 7 * 86_400, month: 31 * 86_400 };
  const span = spans[range];
  const start = now - span;

  const pushAll: Item[] = [];
  const take = (rows: unknown[], source: string, kind: string) => {
    for (const raw of rows) {
      const j = raw as Record<string, unknown>;
      const ts = Number(j.ts || now);
      if (ts < start) continue;
      pushAll.push({
        id: String(j.job_id || j.id || `${source}-${pushAll.length}`),
        title: String(j.intent || j.title || j.filename || j.job_id || kind),
        kind,
        source: String(j.source || source),
        ts,
        state: String(j.state || j.status || ""),
        agent: String(j.agent || ""),
        message: String(j.message || "").slice(0, 400),
        priority: String(j.priority || ""),
        job_id: j.job_id ? String(j.job_id) : undefined,
      });
    }
  };

  take((queue.running as unknown[]) || [], "grokbot", "job");
  take((queue.queued as unknown[]) || [], "grokbot", "job");
  take((queue.done as unknown[]) || [], "grokbot", "job");
  take((queue.decisions as unknown[]) || [], "grokbot", "inbox");
  take((day.studio_jobs as unknown[]) || [], "studio", "studio");

  const brief = (day.brief as Record<string, unknown>) || {};
  take((brief.inbox as unknown[]) || [], "grokbot", "inbox");
  take((brief.decisions as unknown[]) || [], "grokbot", "inbox");

  pushAll.sort((a, b) => (b.ts || 0) - (a.ts || 0));

  const byMap = new Map<string, Item[]>();
  for (const it of pushAll) {
    const k = dayKey(it.ts || now);
    if (!byMap.has(k)) byMap.set(k, []);
    byMap.get(k)!.push(it);
  }
  const by_day = [...byMap.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([day, items]) => ({ day, count: items.length, items: items.slice(0, 16) }));

  const slots: Slot[] =
    range === "day"
      ? (["manhã", "tarde", "noite"] as const).map((label, i) => {
          const h0 = [6, 12, 18][i];
          const h1 = [12, 18, 24][i];
          return {
            id: label,
            label,
            items: pushAll.filter((it) => {
              const h = new Date((it.ts || now) * 1000).getHours();
              return h >= h0 && h < h1;
            }),
          };
        })
      : [];

  const insights = ((day.insights as Insight[]) ||
    (queue.insights as Insight[]) ||
    []) as Insight[];

  return {
    ok: true,
    range,
    label: { day: "hoje", week: "esta semana", month: "este mês" }[range],
    items: pushAll.slice(0, 80),
    by_day,
    slots,
    insights: insights.length
      ? insights
      : [
          {
            tone: "calm",
            text: "Agenda em modo compatível · peça um briefing ao Grok Bot.",
          },
        ],
    decisions: ((brief.decisions as Item[]) || (queue.decisions as Item[]) || []).slice(
      0,
      12,
    ),
    running: pushAll.filter((i) =>
      ["running", "dispatched", "queued"].includes(String(i.state)),
    ),
    counts: {
      items: pushAll.length,
      days: by_day.length,
    },
    bridges: {
      grokbot: String(
        ((brief.status as Record<string, unknown>) || {}).status ||
          (queue.bridges as Record<string, string>)?.grokbot ||
          "—",
      ),
      hermes: (queue.bridges as Record<string, string>)?.hermes || "—",
    },
    tip: "Kernel ainda sem /os/agenda — usando fila + dia.",
    source: "legacy",
  };
}

function monthCells(items: Item[]) {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  const first = new Date(y, m, 1);
  const startPad = (first.getDay() + 6) % 7; // seg=0
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const counts = new Map<number, number>();
  for (const it of items) {
    if (!it.ts) continue;
    const d = new Date(it.ts * 1000);
    if (d.getMonth() === m && d.getFullYear() === y) {
      counts.set(d.getDate(), (counts.get(d.getDate()) || 0) + 1);
    }
  }
  const cells: { day: number | null; count: number; isToday: boolean }[] = [];
  for (let i = 0; i < startPad; i++) cells.push({ day: null, count: 0, isToday: false });
  const today = now.getDate();
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, count: counts.get(d) || 0, isToday: d === today });
  }
  return cells;
}

/** Agenda Dia · Semana · Mês — Grok Bot + Hermes + Studio + inbox. */
export function AgendaApp() {
  const [range, setRange] = useState<Range>("day");
  const [snap, setSnap] = useState<AgendaSnap | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [pickedDay, setPickedDay] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const res = await apiFetch(`${KERNEL}/os/agenda?range=${range}`);
      if (res.ok) {
        const raw = await res.text();
        if (!raw.trim()) throw new Error("agenda vazia");
        setSnap(JSON.parse(raw) as AgendaSnap);
        setErr(null);
        return;
      }
      // Fallback: kernel antigo sem /os/agenda
      const [dayRes, queueRes] = await Promise.all([
        apiFetch(`${KERNEL}/os/day`),
        apiFetch(`${KERNEL}/os/queue`),
      ]);
      if (!dayRes.ok && !queueRes.ok) throw new Error(`HTTP ${res.status}`);
      const day = dayRes.ok ? await dayRes.json() : {};
      const queue = queueRes.ok ? await queueRes.json() : {};
      setSnap(synthesizeFromLegacy(range, day, queue));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "offline");
    }
  }, [range]);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 8000);
    return () => window.clearInterval(id);
  }, [reload]);

  const askBrief = async () => {
    setBusy("brief");
    const q =
      range === "day"
        ? "resuma minha agenda de hoje e o que precisa da minha OK"
        : range === "week"
          ? "resuma a semana: o que importa, o que está atrasado e o que vem"
          : "visão do mês: prioridades, decisões pendentes e riscos";
    const r = await askGrokBot({ intent: q, breath: "semi", agent: "chief-of-staff" });
    setBusy(null);
    setNote(r.ok ? r.message || "briefing pedido ao Grok Bot" : r.error || "falha");
    void reload();
  };

  const approve = async (jobId: string) => {
    setBusy(jobId);
    const r = await approveGrokJob(jobId);
    setBusy(null);
    setNote(r.ok ? r.message || "aprovado" : r.error || "falha");
    void reload();
  };

  const pullCalendars = async () => {
    setBusy("cal");
    setNote(null);
    try {
      const bridge = await probeBridge(1200);
      if (bridge.status !== "connected") {
        setNote("Extensão Host off — instale Véu Host e abra Google Calendar ou Outlook.");
        return;
      }
      let total = 0;
      for (const app of ["calendar", "outlook"] as const) {
        try {
          const res = await callBridge({ type: "veu.host.readSurface", app }, 10000);
          const data = (res.data || {}) as {
            items?: string[];
            url?: string;
            data?: { items?: string[]; url?: string };
          };
          const items = data.items || data.data?.items || [];
          if (!res.ok || !items.length) continue;
          await apiFetch(`${KERNEL}/os/calendar/ingest`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              source: app === "calendar" ? "google" : "outlook",
              items,
              url: data.url || data.data?.url,
            }),
          });
          total += items.length;
        } catch {
          /* próximo */
        }
      }
      setNote(
        total
          ? `Calendário · ${total} evento(s) trazidos do Host`
          : "Nada lido — abra calendar.google.com ou Outlook no browser e tente de novo.",
      );
      void reload();
    } finally {
      setBusy(null);
    }
  };

  const items = snap?.items || [];
  const insights = snap?.insights || [];
  const decisions = snap?.decisions || [];
  const slots = snap?.slots || [];
  const byDay = snap?.by_day || [];
  const empty = items.length === 0;
  const cells = useMemo(() => monthCells(items), [items]);
  const pickedItems = pickedDay
    ? byDay.find((d) => d.day === pickedDay)?.items ||
      items.filter((it) => it.ts && dayKey(it.ts) === pickedDay)
    : [];

  return (
    <div className="ag">
      <header className="ag__head">
        <div>
          <p className="ag__kicker">agenda · so</p>
          <h2>{snap?.label || "agenda"}</h2>
        </div>
        <div className="ag__ranges" role="tablist">
          {(
            [
              ["day", "dia"],
              ["week", "semana"],
              ["month", "mês"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={range === id ? "is-on" : ""}
              onClick={() => {
                setRange(id);
                setPickedDay(null);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      <div className="ag__toolbar">
        <span className="ag__pulse">
          <i />
          grok · {snap?.bridges?.grokbot || "—"} · hermes · {snap?.bridges?.hermes || "—"}
        </span>
        <span>
          {snap?.counts?.items ?? 0} itens
          {snap?.counts?.days ? ` · ${snap.counts.days} dias` : ""}
          {snap?.source === "legacy" ? " · compat" : ""}
        </span>
        <button type="button" disabled={!!busy} onClick={() => void reload()}>
          atualizar
        </button>
        <button type="button" className="ag__primary" disabled={!!busy} onClick={() => void askBrief()}>
          {busy === "brief" ? "…" : "briefing Grok"}
        </button>
        <button
          type="button"
          disabled={!!busy}
          title="Lê Google Calendar / Outlook abertos no Host"
          onClick={() => void pullCalendars()}
        >
          {busy === "cal" ? "…" : "puxar Google/Outlook"}
        </button>
      </div>

      <section className="ag__insights" aria-label="insights">
        {insights.length === 0 ? (
          <p className="ag__empty">sem insights</p>
        ) : (
          <ul>
            {insights.map((i, idx) => (
              <li key={idx}>{i.text}</li>
            ))}
          </ul>
        )}
      </section>

      {empty ? (
        <div className="ag__vacant">
          <div className="ag__vacant-mark" aria-hidden>
            ◉
          </div>
          <p>Nada neste período ainda.</p>
          <p className="ag__tip">{snap?.tip || "Peça um briefing ou rode algo no Studio."}</p>
          <button type="button" className="ag__primary" disabled={!!busy} onClick={() => void askBrief()}>
            pedir briefing ao Grok Bot
          </button>
        </div>
      ) : null}

      {!empty && range === "day" ? (
        <div className="ag__slots">
          {(slots.length ? slots : [{ id: "tudo", label: "hoje", items }]).map((s) => (
            <section key={s.id} className="ag__panel">
              <h3>
                {s.label} <em>{s.items.length}</em>
              </h3>
              {s.items.length === 0 ? (
                <p className="ag__empty">livre</p>
              ) : (
                <ul>
                  {s.items.map((it) => (
                    <li key={it.id} style={{ ["--src" as string]: sourceHue(it.source) }}>
                      <header>
                        <em>{it.source}</em>
                        <span>{fmtTime(it.ts)}</span>
                      </header>
                      <strong>{it.title}</strong>
                      {it.message ? <p>{it.message}</p> : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      ) : null}

      {!empty && range === "week" ? (
        <div className="ag__days">
          {byDay.map((d) => (
            <section key={d.day} className="ag__panel">
              <h3>
                {fmtDay(d.day)} <em>{d.count}</em>
              </h3>
              <ul>
                {d.items.map((it) => (
                  <li key={it.id} style={{ ["--src" as string]: sourceHue(it.source) }}>
                    <header>
                      <em>{it.source}</em>
                      <span>{it.agent || it.state}</span>
                    </header>
                    <strong>{it.title}</strong>
                    {it.message ? <p>{it.message}</p> : null}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : null}

      {!empty && range === "month" ? (
        <div className="ag__month">
          <div className="ag__cal" role="grid" aria-label="mês">
            {["seg", "ter", "qua", "qui", "sex", "sáb", "dom"].map((w) => (
              <span key={w} className="ag__cal-w">
                {w}
              </span>
            ))}
            {cells.map((c, i) =>
              c.day == null ? (
                <span key={`e${i}`} className="ag__cal-cell is-pad" />
              ) : (
                <button
                  key={c.day}
                  type="button"
                  className={`ag__cal-cell${c.isToday ? " is-today" : ""}${c.count ? " has" : ""}${
                    pickedDay ===
                    `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, "0")}-${String(c.day).padStart(2, "0")}`
                      ? " is-pick"
                      : ""
                  }`}
                  onClick={() => {
                    const y = new Date().getFullYear();
                    const m = String(new Date().getMonth() + 1).padStart(2, "0");
                    const key = `${y}-${m}-${String(c.day).padStart(2, "0")}`;
                    setPickedDay((cur) => (cur === key ? null : key));
                  }}
                >
                  <b>{c.day}</b>
                  {c.count > 0 ? <i>{c.count}</i> : null}
                </button>
              ),
            )}
          </div>
          <section className="ag__panel ag__month-list">
            <h3>{pickedDay ? fmtDay(pickedDay) : "atividade do mês"}</h3>
            <ul>
              {(pickedDay ? pickedItems : items.slice(0, 12)).map((it) => (
                <li key={it.id} style={{ ["--src" as string]: sourceHue(it.source) }}>
                  <header>
                    <em>{it.source}</em>
                    <span>{fmtTime(it.ts)}</span>
                  </header>
                  <strong>{it.title}</strong>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}

      {decisions.length > 0 ? (
        <section className="ag__panel ag__ok">
          <h3>
            pedem OK <em>{decisions.length}</em>
          </h3>
          <ul>
            {decisions.map((d) => (
              <li key={d.job_id || d.id}>
                <strong>{d.title}</strong>
                {d.message ? <p>{d.message}</p> : null}
                {d.job_id ? (
                  <button
                    type="button"
                    disabled={busy === d.job_id}
                    onClick={() => void approve(String(d.job_id))}
                  >
                    {busy === d.job_id ? "…" : "aprovar"}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {note ? <p className="ag__foot">{note}</p> : null}
      {err ? <p className="ag__err">{err}</p> : null}

      <style>{`
        .ag {
          --ink: #e8ebe6;
          --muted: #8a939c;
          --dim: #5c6570;
          --line: rgba(232,194,122,0.28);
          --panel: rgba(0,0,0,0.28);
          height: 100%;
          overflow: auto;
          padding: 0.9rem 1rem 1.1rem;
          display: grid;
          gap: 0.7rem;
          align-content: start;
          color: var(--ink);
          background:
            radial-gradient(ellipse 80% 50% at 90% -10%, rgba(232,194,122,0.16), transparent 55%),
            radial-gradient(ellipse 60% 40% at 0% 100%, rgba(127,231,212,0.06), transparent 50%),
            linear-gradient(168deg, #14161c 0%, #0c0e12 55%, #0a0b0e 100%);
          font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        }
        .ag__head {
          display: flex;
          justify-content: space-between;
          align-items: end;
          gap: 0.75rem;
        }
        .ag__kicker {
          margin: 0;
          font-size: 0.62rem;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: #e8c27a;
        }
        .ag__head h2 {
          margin: 0.12rem 0 0;
          font-family: "IBM Plex Serif", Georgia, serif;
          font-weight: 500;
          font-size: clamp(1.35rem, 2.4vw, 1.7rem);
          text-transform: capitalize;
          letter-spacing: -0.02em;
        }
        .ag__ranges {
          display: flex;
          border: 1px solid var(--line);
          background: rgba(0,0,0,0.25);
        }
        .ag__ranges button {
          border: 0;
          background: transparent;
          color: var(--muted);
          padding: 0.4rem 0.75rem;
          font-size: 0.7rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          cursor: pointer;
          transition: background 0.15s ease, color 0.15s ease;
        }
        .ag__ranges button.is-on {
          background: rgba(232,194,122,0.2);
          color: #fff;
        }
        .ag__toolbar {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem 0.7rem;
          align-items: center;
          font-size: 0.68rem;
          letter-spacing: 0.05em;
          text-transform: uppercase;
          color: var(--dim);
        }
        .ag__pulse { display: inline-flex; align-items: center; gap: 0.35rem; }
        .ag__pulse i {
          width: 6px; height: 6px; border-radius: 50%;
          background: #8fbf9f;
          box-shadow: 0 0 0 3px rgba(143,191,159,0.15);
          animation: agPulse 2.4s ease-in-out infinite;
        }
        @keyframes agPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.45; }
        }
        .ag__toolbar button {
          border: 1px solid var(--line);
          background: transparent;
          color: #e8c27a;
          padding: 0.32rem 0.6rem;
          font-size: 0.66rem;
          cursor: pointer;
          letter-spacing: 0.05em;
          text-transform: uppercase;
        }
        .ag__primary {
          background: rgba(232,194,122,0.14) !important;
          border-color: rgba(232,194,122,0.45) !important;
        }
        .ag__insights {
          border: 1px solid var(--line);
          background:
            linear-gradient(90deg, rgba(232,194,122,0.1), transparent 60%),
            var(--panel);
          padding: 0.6rem 0.75rem;
        }
        .ag__insights ul {
          list-style: none; margin: 0; padding: 0;
          display: grid; gap: 0.35rem;
        }
        .ag__insights li {
          font-size: 0.88rem;
          line-height: 1.35;
          padding-left: 0.55rem;
          border-left: 2px solid rgba(232,194,122,0.45);
        }
        .ag__vacant {
          padding: 1.6rem 0.5rem 1rem;
          display: grid;
          gap: 0.4rem;
          justify-items: start;
        }
        .ag__vacant-mark {
          font-size: 1.6rem;
          color: rgba(232,194,122,0.55);
          animation: agPulse 3s ease-in-out infinite;
        }
        .ag__vacant p { margin: 0; color: var(--muted); }
        .ag__vacant .ag__primary {
          margin-top: 0.35rem;
          padding: 0.45rem 0.85rem;
          cursor: pointer;
          color: #e8c27a;
          border: 1px solid rgba(232,194,122,0.45);
          background: rgba(232,194,122,0.12);
          font-size: 0.8rem;
        }
        .ag__slots, .ag__days {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
          gap: 0.55rem;
        }
        .ag__month {
          display: grid;
          grid-template-columns: minmax(220px, 1.1fr) minmax(200px, 1fr);
          gap: 0.65rem;
        }
        @media (max-width: 640px) {
          .ag__month { grid-template-columns: 1fr; }
        }
        .ag__cal {
          display: grid;
          grid-template-columns: repeat(7, 1fr);
          gap: 0.25rem;
          padding: 0.55rem;
          border: 1px solid rgba(255,255,255,0.08);
          background: var(--panel);
        }
        .ag__cal-w {
          text-align: center;
          font-size: 0.58rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--dim);
          padding: 0.2rem 0;
        }
        .ag__cal-cell {
          aspect-ratio: 1;
          border: 1px solid transparent;
          background: transparent;
          color: var(--ink);
          display: grid;
          place-content: center;
          gap: 0.1rem;
          font-size: 0.78rem;
          cursor: pointer;
          position: relative;
        }
        .ag__cal-cell.is-pad { pointer-events: none; }
        .ag__cal-cell.has {
          border-color: rgba(232,194,122,0.25);
          background: rgba(232,194,122,0.08);
        }
        .ag__cal-cell.is-today b { color: #e8c27a; }
        .ag__cal-cell.is-pick {
          border-color: rgba(232,194,122,0.55);
          background: rgba(232,194,122,0.18);
        }
        .ag__cal-cell b { font-weight: 500; }
        .ag__cal-cell i {
          font-style: normal;
          font-size: 0.55rem;
          color: #e8c27a;
          position: absolute;
          bottom: 2px;
          right: 4px;
        }
        .ag__panel {
          border: 1px solid rgba(255,255,255,0.08);
          background: var(--panel);
          padding: 0.6rem 0.7rem;
          min-height: 5.5rem;
        }
        .ag__panel h3 {
          margin: 0 0 0.45rem;
          font-size: 0.66rem;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: #e8c27a;
          font-weight: 500;
        }
        .ag__panel h3 em {
          font-style: normal;
          color: var(--dim);
          margin-left: 0.3rem;
        }
        .ag__empty { margin: 0; font-size: 0.78rem; color: var(--dim); }
        .ag__panel ul {
          list-style: none; margin: 0; padding: 0;
          display: grid; gap: 0.5rem;
        }
        .ag__panel li {
          padding-left: 0.5rem;
          border-left: 2px solid var(--src, rgba(232,194,122,0.4));
        }
        .ag__panel li header {
          display: flex; gap: 0.4rem;
          font-size: 0.6rem;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          color: var(--dim);
        }
        .ag__panel li header em {
          color: var(--src, #e8c27a);
          font-style: normal;
        }
        .ag__panel strong {
          display: block;
          font-size: 0.84rem;
          font-weight: 500;
          margin-top: 0.08rem;
        }
        .ag__panel p {
          margin: 0.15rem 0 0;
          font-size: 0.74rem;
          color: var(--muted);
          line-height: 1.35;
        }
        .ag__ok button {
          margin-top: 0.35rem;
          border: 1px solid rgba(232,194,122,0.4);
          background: rgba(232,194,122,0.12);
          color: #e8c27a;
          padding: 0.22rem 0.55rem;
          font-size: 0.7rem;
          cursor: pointer;
        }
        .ag__foot { margin: 0; color: #8fbf9f; font-size: 0.8rem; }
        .ag__err { margin: 0; color: #e8a0a0; font-size: 0.8rem; }
        .ag__tip { font-size: 0.8rem !important; color: var(--dim) !important; }
      `}</style>
    </div>
  );
}

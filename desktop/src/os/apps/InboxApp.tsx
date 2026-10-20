import { useCallback, useEffect, useState } from "react";
import { apiFetch, KERNEL } from "../../lib/kernel";

type Item = {
  id: string;
  channel: string;
  sender?: string;
  subject?: string;
  preview?: string;
  unread?: boolean;
  needsApproval?: boolean;
  company?: string;
  draft?: string;
  why?: string;
};

type Draft = {
  id: string;
  channel: string;
  subject: string;
  body: string;
  status: string;
  to?: string;
};

export function InboxApp() {
  const [channel, setChannel] = useState<string>("");
  const [items, setItems] = useState<Item[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [channels, setChannels] = useState<Record<string, number>>({});
  const [selected, setSelected] = useState<Item | null>(null);
  const [draftBody, setDraftBody] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const q = channel ? `?channel=${encodeURIComponent(channel)}` : "";
    const r = await apiFetch(`${KERNEL}/inbox${q}`);
    const j = await r.json();
    setItems(j.items || []);
    setDrafts(j.pending_drafts || []);
    setChannels(j.channels || {});
  }, [channel]);

  useEffect(() => {
    void reload();
    const id = window.setInterval(() => void reload(), 20_000);
    return () => window.clearInterval(id);
  }, [reload]);

  const saveDraft = async () => {
    if (!selected || !draftBody.trim()) return;
    setBusy("draft");
    try {
      const r = await apiFetch(`${KERNEL}/inbox/drafts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          item_id: selected.id,
          channel: selected.channel,
          subject: `Re: ${selected.subject || ""}`,
          body: draftBody,
          to: selected.sender || "",
        }),
      });
      const j = await r.json();
      setNote(
        j.ok
          ? "rascunho na fila — aprove aqui ou em Aprovações pra enviar via Grok Bot"
          : j.error || "falha",
      );
      setDraftBody("");
      await reload();
    } finally {
      setBusy(null);
    }
  };

  const decide = async (id: string, approve: boolean) => {
    setBusy(id);
    try {
      const r = await apiFetch(`${KERNEL}/inbox/drafts/${encodeURIComponent(id)}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approve }),
      });
      const j = await r.json();
      setNote(j.note || (j.ok ? (approve ? "enviando…" : "recusado") : j.error || "falha"));
      await reload();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="panel-app inbox-app">
      <header className="panel-app__head">
        <h2>Inbox</h2>
        <div className="panel-app__tabs">
          <button type="button" className={!channel ? "is-on" : ""} onClick={() => setChannel("")}>
            todos
          </button>
          {Object.keys(channels).map((c) => (
            <button
              key={c}
              type="button"
              className={channel === c ? "is-on" : ""}
              onClick={() => setChannel(c)}
            >
              {c} · {channels[c]}
            </button>
          ))}
        </div>
      </header>
      <div className="inbox-app__grid">
        <ul className="panel-app__list">
          {items.map((it) => (
            <li key={it.id}>
              <button
                type="button"
                className="inbox-app__item"
                onClick={() => {
                  setSelected(it);
                  setDraftBody(it.draft || "");
                }}
              >
                <strong>{it.subject || "(sem assunto)"}</strong>
                <span>
                  {it.channel}
                  {it.unread ? " · não lida" : ""}
                  {it.needsApproval ? " · aprovação" : ""}
                </span>
                <em>{it.sender}</em>
              </button>
            </li>
          ))}
          {!items.length ? <li className="muted">inbox vazia neste recorte</li> : null}
        </ul>
        <div className="inbox-app__detail">
          {selected ? (
            <>
              <h3>{selected.subject}</h3>
              <p className="panel-app__meta">
                {selected.channel} · {selected.sender}
                {selected.company ? ` · ${selected.company}` : ""}
              </p>
              <p>{selected.preview}</p>
              {selected.why ? <p className="panel-app__warn">{selected.why}</p> : null}
              <textarea
                value={draftBody}
                onChange={(e) => setDraftBody(e.target.value)}
                placeholder="Rascunho de resposta (aprovação → envio via Grok Bot)"
                rows={5}
              />
              <button type="button" disabled={busy === "draft"} onClick={() => void saveDraft()}>
                {busy === "draft" ? "…" : "enviar rascunho à aprovação"}
              </button>
            </>
          ) : (
            <p className="muted">selecione uma mensagem</p>
          )}
          {note ? <p className="inbox-app__note">{note}</p> : null}
          {drafts.length ? (
            <>
              <h3>Rascunhos pendentes</h3>
              <ul className="panel-app__list inbox-app__drafts">
                {drafts.map((d) => (
                  <li key={d.id}>
                    <div>
                      <strong>
                        {d.channel} · {d.subject}
                      </strong>
                      <p>{(d.body || "").slice(0, 160)}</p>
                    </div>
                    <div className="inbox-app__actions">
                      <button
                        type="button"
                        disabled={busy === d.id}
                        onClick={() => void decide(d.id, true)}
                      >
                        {busy === d.id ? "…" : "aprovar · enviar"}
                      </button>
                      <button
                        type="button"
                        className="is-ghost"
                        disabled={busy === d.id}
                        onClick={() => void decide(d.id, false)}
                      >
                        recusar
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </div>
      <style>{`
        .inbox-app__grid { display: grid; grid-template-columns: 1fr; gap: 0.85rem; }
        .inbox-app__item { width: 100%; text-align: left; border: 0; background: transparent; color: inherit; cursor: pointer; display: grid; gap: 0.15rem; padding: 0; }
        .inbox-app__note { font-size: 0.78rem; color: var(--filament, #e8c27a); }
        .inbox-app__drafts li { display: grid; gap: 0.45rem; padding: 0.55rem 0; border-bottom: 1px solid rgba(232,238,244,0.08); }
        .inbox-app__drafts p { margin: 0.2rem 0 0; font-size: 0.75rem; opacity: 0.75; }
        .inbox-app__actions { display: flex; gap: 0.45rem; flex-wrap: wrap; }
        .inbox-app__actions button.is-ghost { background: transparent; border: 1px solid rgba(232,238,244,0.2); }
        @media (min-width: 744px) {
          .inbox-app__grid { grid-template-columns: minmax(0,1.1fr) minmax(0,1fr); }
        }
      `}</style>
    </div>
  );
}

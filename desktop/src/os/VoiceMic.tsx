import { useRef, useState } from "react";
import { KERNEL } from "../lib/kernel";

type Stage = "idle" | "listening" | "transcribing" | "routing" | "error";

type Props = {
  breath: "guided" | "semi" | "free" | "autonomous";
  onText?: (text: string) => void;
};

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
  "audio/ogg",
];

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "audio/webm";
  for (const m of MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "audio/webm";
}

function extFor(mime: string): string {
  if (mime.includes("mp4") || mime.includes("m4a")) return "m4a";
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("wav")) return "wav";
  return "webm";
}

/** Push-to-talk — o som da escuta. */
export function VoiceMic({ breath, onText }: Props) {
  const [stage, setStage] = useState<Stage>("idle");
  const [note, setNote] = useState("");
  const recRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const startedAt = useRef(0);
  const mimeRef = useRef("audio/webm");

  const stop = () => {
    const rec = recRef.current;
    if (!rec || rec.state === "inactive") return;
    try {
      rec.requestData?.();
    } catch {
      /* ignore */
    }
    rec.stop();
  };

  const start = async () => {
    if (stage === "listening" || stage === "transcribing" || stage === "routing") return;
    setNote("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
      });
      const mime = pickMime();
      mimeRef.current = mime;
      const rec = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 64_000 });
      chunks.current = [];
      startedAt.current = Date.now();
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.current.push(e.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        recRef.current = null;
        const elapsed = Date.now() - startedAt.current;
        const type = mimeRef.current.split(";")[0] || "audio/webm";
        const blob = new Blob(chunks.current, { type });
        if (elapsed < 350 || blob.size < 800) {
          setStage("error");
          setNote("fale um pouco mais · segure o botão");
          return;
        }
        setStage("transcribing");
        const ext = extFor(type);
        const fd = new FormData();
        fd.append("file", blob, `veu.${ext}`);
        fd.append("breath", breath);
        try {
          setStage("routing");
          const res = await fetch(`${KERNEL}/voice/ask`, {
            method: "POST",
            credentials: "include",
            headers: { "X-Veu-CSRF": "1" },
            body: fd,
          });
          const j = (await res.json()) as {
            ok?: boolean;
            error?: string;
            text?: string;
          };
          if (!j.ok) {
            setStage("error");
            const err = String(j.error || "falha na voz");
            if (/could not be decoded|format is not supported|invalid_request/i.test(err)) {
              setNote("áudio inválido — segure ~1s e fale de novo");
            } else if (/api key|401|invalid_api_key/i.test(err)) {
              setNote("key OpenAI pra voz inválida — Ajustes");
            } else {
              setNote(err.slice(0, 80));
            }
            return;
          }
          setNote(j.text || "ok");
          if (j.text) onText?.(j.text);
          setStage("idle");
        } catch (e) {
          setStage("error");
          setNote(e instanceof Error ? e.message : "erro");
        }
      };
      rec.onerror = () => {
        stream.getTracks().forEach((t) => t.stop());
        setStage("error");
        setNote("falha no gravador");
      };
      recRef.current = rec;
      // timeslice garante cabeçalho webm completo mesmo em gravações curtas
      rec.start(250);
      setStage("listening");
    } catch {
      setStage("error");
      setNote("microfone negado — digite no chat ou ⌘K");
    }
  };

  return (
    <div className="voice-mic">
      <button
        type="button"
        className={stage === "listening" ? "is-hot" : ""}
        onPointerDown={(e) => {
          e.preventDefault();
          void start();
        }}
        onPointerUp={(e) => {
          e.preventDefault();
          stop();
        }}
        onPointerCancel={() => stop()}
        onPointerLeave={() => {
          if (stage === "listening") stop();
        }}
        aria-label="segure para falar"
        title="segure ~1s e fale"
      >
        ◉
      </button>
      <span data-stage={stage}>
        {stage === "idle" && "segure · falar"}
        {stage === "listening" && "ouvindo…"}
        {stage === "transcribing" && "transcrevendo…"}
        {stage === "routing" && "roteando…"}
        {stage === "error" && (note || "erro")}
      </span>
      {stage !== "error" && note ? <em>{note}</em> : null}
      <style>{`
        .voice-mic { display: flex; align-items: center; gap: 0.55rem; }
        .voice-mic button {
          width: 2.4rem; height: 2.4rem; border-radius: 999px; border: 1px solid rgba(232,238,244,0.25);
          background: rgba(232,194,122,0.12); color: #e8c27a; font-size: 1rem; cursor: pointer;
          touch-action: none;
        }
        .voice-mic button.is-hot { background: #e8c27a; color: #0b0e12; transform: scale(1.06); }
        .voice-mic span { font-size: 0.75rem; color: rgba(232,238,244,0.55); }
        .voice-mic em { font-style: normal; font-size: 0.72rem; color: rgba(232,238,244,0.75); max-width: 12rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      `}</style>
    </div>
  );
}

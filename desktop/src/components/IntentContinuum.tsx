import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { motion } from "framer-motion";
import type { AutonomyBreath } from "./AutonomyOrbit";

type Props = {
  weaving: boolean;
  breath: AutonomyBreath;
  placeholder: string;
  onSubmit: (value: string) => void | Promise<void>;
};

/** Campo de intenção — multilinha: Enter envia · Ctrl/⌘+Enter ou Shift+Enter nova linha. */
export function IntentContinuum({ weaving, breath, placeholder, onSubmit }: Props) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = (value || inputRef.current?.value || "").trim();
    if (!trimmed || weaving) return;
    setValue("");
    if (inputRef.current) {
      inputRef.current.value = "";
      inputRef.current.style.height = "auto";
    }
    void onSubmit(trimmed);
  };

  const handle = (e: FormEvent) => {
    e.preventDefault();
    e.stopPropagation();
    submit();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter") return;
    // Ctrl/Cmd+Enter ou Shift+Enter → nova linha
    if (e.ctrlKey || e.metaKey || e.shiftKey) {
      return;
    }
    // Enter sozinho → enviar
    e.preventDefault();
    submit();
  };

  const autosize = (el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  };

  return (
    <form className="continuum" onSubmit={handle}>
      <motion.div
        className="continuum__ring"
        animate={{
          opacity: weaving ? [0.35, 0.9, 0.35] : 0.45,
          scale: weaving ? [1, 1.02, 1] : 1,
        }}
        transition={{
          duration: weaving ? 1.4 : 0.4,
          repeat: weaving ? Infinity : 0,
          ease: "easeInOut",
        }}
      />
      <label className="continuum__label" htmlFor="intent">
        intenção · {breath === "free" ? "livre" : breath === "semi" ? "semi" : "guiado"}
        <span className="continuum__hint"> · enter envia · ctrl+enter linha</span>
      </label>
      <textarea
        ref={inputRef}
        id="intent"
        className="continuum__input"
        value={value}
        rows={1}
        onChange={(e) => {
          setValue(e.target.value);
          autosize(e.target);
        }}
        onKeyDown={onKeyDown}
        onPaste={(e) => {
          // garante que paste multilinha entra no state (não bloqueia)
          const text = e.clipboardData?.getData("text");
          if (text && text.includes("\n")) {
            // deixa o paste padrão + autosize no próximo tick
            requestAnimationFrame(() => {
              if (inputRef.current) autosize(inputRef.current);
            });
          }
        }}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        disabled={weaving}
      />
      <button
        className="continuum__go"
        type="submit"
        disabled={weaving || !(value.trim() || inputRef.current?.value?.trim())}
        onClick={(e) => {
          if (weaving) return;
          const has = value.trim() || (inputRef.current?.value || "").trim();
          if (!has) return;
          e.preventDefault();
          submit();
        }}
      >
        {weaving ? "tecendo…" : "tecer"}
      </button>
      <style>{`
        .continuum {
          position: relative;
          width: min(720px, 100%);
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 0.65rem 0.85rem;
          padding: 1rem 1.1rem 1.1rem;
          background: rgba(10, 14, 18, 0.72);
          border: 1px solid rgba(127, 231, 212, 0.16);
          backdrop-filter: blur(18px);
        }
        .continuum__ring {
          pointer-events: none;
          position: absolute;
          inset: -1px;
          border: 1px solid var(--filament-soft);
          box-shadow: 0 0 40px rgba(232, 194, 122, 0.08);
        }
        .continuum__label {
          grid-column: 1 / -1;
          font-family: var(--font-mono);
          font-size: 0.65rem;
          letter-spacing: 0.16em;
          text-transform: lowercase;
          color: var(--signal);
        }
        .continuum__hint {
          letter-spacing: 0.08em;
          color: rgba(236, 242, 248, 0.35);
        }
        .continuum__input {
          border: 0;
          outline: none;
          background: transparent;
          font-size: clamp(1rem, 2.4vw, 1.2rem);
          font-weight: 300;
          padding: 0.35rem 0;
          resize: none;
          min-height: 1.6em;
          max-height: 180px;
          line-height: 1.35;
          font-family: inherit;
          color: inherit;
          overflow-y: auto;
        }
        .continuum__input::placeholder {
          color: rgba(236, 242, 248, 0.28);
        }
        .continuum__go {
          align-self: end;
          border: 1px solid rgba(232, 194, 122, 0.45);
          background: transparent;
          color: var(--filament);
          padding: 0.55rem 1rem;
          cursor: pointer;
          font-family: var(--font-mono);
          font-size: 0.75rem;
          letter-spacing: 0.14em;
          text-transform: lowercase;
          transition: background 0.2s ease, color 0.2s ease;
        }
        .continuum__go:hover:not(:disabled) {
          background: var(--filament);
          color: var(--ink);
        }
        .continuum__go:disabled {
          opacity: 0.4;
          cursor: default;
        }
      `}</style>
    </form>
  );
}

type Props = {
  open: boolean;
  onClick: () => void;
};

export function GearButton({ open, onClick }: Props) {
  return (
    <button
      type="button"
      className={`gear${open ? " is-open" : ""}`}
      onClick={onClick}
      aria-label={open ? "Fechar ecossistema" : "Abrir ecossistema de agentes"}
      aria-pressed={open}
      title="Ecossistema"
    >
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
        <path
          fill="currentColor"
          d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm9.4 3.1-1.7-.3a7.6 7.6 0 0 0-.6-1.5l1.1-1.3-1.4-1.4-1.3 1.1c-.5-.3-1-.5-1.5-.6l-.3-1.7h-2l-.3 1.7c-.5.1-1 .3-1.5.6L10.6 5.7 9.2 7.1l1.1 1.3c-.3.5-.5 1-.6 1.5l-1.7.3v2l1.7.3c.1.5.3 1 .6 1.5l-1.1 1.3 1.4 1.4 1.3-1.1c.5.3 1 .5 1.5.6l.3 1.7h2l.3-1.7c.5-.1 1-.3 1.5-.6l1.3 1.1 1.4-1.4-1.1-1.3c.3-.5.5-1 .6-1.5l1.7-.3v-2Z"
        />
      </svg>
      <style>{`
        .gear {
          display: inline-grid;
          place-items: center;
          width: 2.1rem;
          height: 2.1rem;
          border: 1px solid rgba(232, 194, 122, 0.28);
          background: rgba(7, 9, 12, 0.45);
          color: var(--filament);
          cursor: pointer;
          backdrop-filter: blur(10px);
          transition: transform 0.4s ease, border-color 0.2s ease, color 0.2s ease;
        }
        .gear:hover { border-color: rgba(232, 194, 122, 0.55); }
        .gear.is-open {
          color: var(--ink);
          background: linear-gradient(120deg, var(--filament), #f0d7a2);
          transform: rotate(45deg);
        }
      `}</style>
    </button>
  );
}

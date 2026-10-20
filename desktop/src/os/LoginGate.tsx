import { useCallback, useEffect, useState } from "react";
import {
  fetchAuthStatus,
  googleLoginUrl,
  loginWithPassword,
  type AuthStatus,
} from "../lib/kernel";

type Props = {
  children: React.ReactNode;
};

/**
 * Bloqueia o desktop até haver sessão Véu (Google OAuth ou senha).
 * Escuta `veu:auth-required` quando o kernel devolve 401.
 */
export function LoginGate({ children }: Props) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [checking, setChecking] = useState(true);
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const s = await fetchAuthStatus();
    setStatus(s);
    setChecking(false);
    return s;
  }, []);

  useEffect(() => {
    void refresh();
    const onNeed = () => {
      setStatus((prev) =>
        prev ? { ...prev, authenticated: false } : { ok: true, configured: true, authenticated: false },
      );
    };
    window.addEventListener("veu:auth-required", onNeed);
    return () => window.removeEventListener("veu:auth-required", onNeed);
  }, [refresh]);

  const onPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const ok = await loginWithPassword(password);
    setBusy(false);
    if (!ok) {
      setErr("Senha incorreta");
      return;
    }
    setPassword("");
    await refresh();
  };

  if (checking) {
    return (
      <div className="login-gate login-gate--boot">
        <p>véu · abrindo membrana…</p>
        <style>{gateCss}</style>
      </div>
    );
  }

  if (status?.authenticated) {
    return <>{children}</>;
  }

  const google = !!status?.methods?.google;
  const pwd = !!status?.methods?.password;

  return (
    <div className="login-gate">
      <div className="login-gate__panel">
        <p className="login-gate__brand">véu</p>
        <h1 className="login-gate__title">entrar no plano de controle</h1>
        <p className="login-gate__sub">
          Autentique para continuar. Com Google, o Véu já pede Drive, Docs, Sheets,
          Calendar e Gmail na mesma autorização.
        </p>

        {!status?.configured ? (
          <p className="login-gate__err">
            Auth não configurada no kernel — defina Google OAuth ou senha no .env.
          </p>
        ) : null}

        {google ? (
          <a className="login-gate__google" href={googleLoginUrl()}>
            <span className="login-gate__g">G</span>
            Continuar com Google
          </a>
        ) : null}

        {google && pwd ? <p className="login-gate__or">ou senha local</p> : null}

        {pwd ? (
          <form className="login-gate__form" onSubmit={onPassword}>
            <input
              type="password"
              autoComplete="current-password"
              placeholder="Senha Véu"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !password}>
              {busy ? "…" : "Entrar"}
            </button>
          </form>
        ) : null}

        {err ? <p className="login-gate__err">{err}</p> : null}
      </div>
      <style>{gateCss}</style>
    </div>
  );
}

const gateCss = `
  .login-gate {
    min-height: 100%;
    min-height: 100dvh;
    width: 100%;
    display: grid;
    place-items: center;
    padding:
      max(1rem, env(safe-area-inset-top))
      max(0.75rem, env(safe-area-inset-right))
      max(1rem, env(safe-area-inset-bottom))
      max(0.75rem, env(safe-area-inset-left));
    box-sizing: border-box;
    background:
      radial-gradient(80% 60% at 50% 0%, rgba(120, 150, 180, 0.18), transparent 55%),
      linear-gradient(165deg, #0b0e12 0%, #121820 45%, #0a0c10 100%);
    color: #e8eef4;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  }
  .login-gate--boot { opacity: 0.7; letter-spacing: 0.04em; }
  .login-gate__panel {
    width: min(26rem, 100%);
    padding: 1.5rem 1.15rem 1.35rem;
    border: 1px solid rgba(232,238,244,0.12);
    background: rgba(10,14,18,0.72);
    backdrop-filter: blur(16px);
  }
  @media (min-width: 480px) {
    .login-gate__panel { padding: 2rem 1.75rem 1.75rem; }
  }
  .login-gate__brand {
    margin: 0;
    font-family: Syne, "IBM Plex Sans", sans-serif;
    font-size: 1.65rem;
    font-weight: 700;
    letter-spacing: -0.03em;
  }
  .login-gate__title {
    margin: 0.85rem 0 0.35rem;
    font-family: Syne, sans-serif;
    font-size: 1.15rem;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  .login-gate__sub {
    margin: 0 0 1.4rem;
    color: rgba(232,238,244,0.62);
    font-size: 0.9rem;
    line-height: 1.45;
  }
  .login-gate__google {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.65rem;
    width: 100%;
    padding: 0.85rem 1rem;
    border: 1px solid rgba(232,238,244,0.2);
    background: rgba(255,255,255,0.04);
    color: inherit;
    text-decoration: none;
    font-size: 0.95rem;
    transition: background 0.15s ease, border-color 0.15s ease;
  }
  .login-gate__google:hover {
    background: rgba(255,255,255,0.09);
    border-color: rgba(232,238,244,0.35);
  }
  .login-gate__g {
    display: grid;
    place-items: center;
    width: 1.4rem;
    height: 1.4rem;
    border-radius: 2px;
    background: #fff;
    color: #4285f4;
    font-weight: 700;
    font-size: 0.85rem;
  }
  .login-gate__or {
    margin: 1rem 0 0.65rem;
    text-align: center;
    color: rgba(232,238,244,0.45);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .login-gate__form {
    display: grid;
    gap: 0.55rem;
  }
  .login-gate__form input {
    padding: 0.75rem 0.85rem;
    border: 1px solid rgba(232,238,244,0.18);
    background: rgba(0,0,0,0.35);
    color: inherit;
    font: inherit;
  }
  .login-gate__form button {
    padding: 0.75rem;
    border: 0;
    background: #dce6f0;
    color: #0b0e12;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  .login-gate__form button:disabled { opacity: 0.5; cursor: default; }
  .login-gate__err {
    margin: 0.85rem 0 0;
    color: #f0a8a0;
    font-size: 0.85rem;
  }
`;

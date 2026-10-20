import type { AutonomyBreath } from "../components/AutonomyOrbit";
import type { Formation } from "../components/FormationStage";

function detectKind(intent: string): Formation["kind"] {
  const t = intent.toLowerCase().trim();
  if (/^(oi|olá|ola|hey|hi|hello|bom dia|boa tarde|boa noite)\b/.test(t))
    return "hybrid"; // local fallback only; kernel uses greeting via Jev
  if (/(whatsapp|teams|outlook|gmail|slack|chat|mensagem|email|e-mail)/.test(t))
    return "comm";
  if (/(notion|workspace|drive|docs)/.test(t)) return "workspace";
  if (/(site|página|browser|naveg|web|url|http)/.test(t)) return "browser";
  if (/(arquivo|pasta|documento|pdf)/.test(t)) return "files";
  if (/(mcp|api|servidor|conectar)/.test(t)) return "mcp";
  if (/(sistema|janela|processo|terminal|shell|administr)/.test(t)) return "system";
  return "hybrid";
}

export async function weaveIntentLocal(
  intent: string,
  breath: AutonomyBreath,
): Promise<Formation> {
  await new Promise((r) => setTimeout(r, 400));
  const kind = detectKind(intent);
  const greet = /^(oi|olá|ola|hey|hi|hello|bom dia|boa tarde|boa noite)\b/i.test(
    intent.trim(),
  );
  const titles: Record<Formation["kind"], string> = {
    browser: "navegação",
    files: "arquivos",
    system: "sistema",
    mcp: "conexões",
    hybrid: greet ? "" : "tarefa",
    comm: "mensagens",
    workspace: "workspace",
  };
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    intent,
    title: titles[kind],
    kind,
    breath,
    threads: greet
      ? []
      : [
          "entender o pedido",
          "preparar ferramentas",
          breath === "free"
            ? "executar com autonomia"
            : breath === "semi"
              ? "avançar e só pedir o delicado"
              : "esperar confirmação",
        ],
    status: greet
      ? ""
      : breath === "guided"
        ? "quando quiser, confirmo e sigo"
        : breath === "semi"
          ? "avanço e só peço o delicado"
          : "seguindo com autonomia",
  };
}

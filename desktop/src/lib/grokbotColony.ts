/** Colônia Grok Bot — agentes/routines e ligações com o Véu. */

export type GrokNode = {
  id: string;
  label: string;
  kind: "veu" | "bot" | "routine" | "cloud" | "human" | "nerve";
  x: number;
  y: number;
  blurb: string;
};

export type GrokLink = {
  from: string;
  to: string;
  label?: string;
};

export const GROK_NODES: GrokNode[] = [
  {
    id: "veu",
    label: "véu",
    kind: "veu",
    x: 0.18,
    y: 0.5,
    blurb: "SO local — chat, Jev, ECC",
  },
  {
    id: "handoff",
    label: "handoff",
    kind: "routine",
    x: 0.42,
    y: 0.28,
    blurb: "Routine · webhook → executa job",
  },
  {
    id: "saude",
    label: "saúde",
    kind: "routine",
    x: 0.42,
    y: 0.72,
    blurb: "Routine · ping 9h/18h BRT",
  },
  {
    id: "cloud-bot",
    label: "véu cloud",
    kind: "bot",
    x: 0.68,
    y: 0.38,
    blurb: "Teammate always-on",
  },
  {
    id: "cloud-pc",
    label: "pc cloud",
    kind: "cloud",
    x: 0.88,
    y: 0.5,
    blurb: "Computador próprio 24/7",
  },
  {
    id: "callback",
    label: "callback",
    kind: "nerve",
    x: 0.42,
    y: 0.5,
    blurb: "/bridge/grokbot/inbound",
  },
  {
    id: "hudson",
    label: "você",
    kind: "human",
    x: 0.18,
    y: 0.18,
    blurb: "Aprovação · login",
  },
  {
    id: "plaud",
    label: "plaud",
    kind: "nerve",
    x: 0.88,
    y: 0.22,
    blurb: "Já no Grok Bot · não duplicar no Véu",
  },
];

export const GROK_LINKS: GrokLink[] = [
  { from: "veu", to: "handoff", label: "webhook" },
  { from: "handoff", to: "cloud-bot", label: "job" },
  { from: "cloud-bot", to: "cloud-pc", label: "executa" },
  { from: "cloud-bot", to: "callback", label: "resultado" },
  { from: "callback", to: "veu", label: "inbound" },
  { from: "saude", to: "callback", label: "ping" },
  { from: "saude", to: "veu", label: "health" },
  { from: "cloud-bot", to: "hudson", label: "aprovação" },
  { from: "hudson", to: "veu", label: "ok" },
  { from: "cloud-bot", to: "plaud", label: "usa" },
  { from: "plaud", to: "callback", label: "resumos" },
];

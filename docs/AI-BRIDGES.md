# Véu × OpenClaw × Hermes × Grok Bot — engenharia de IA

Como um engenheiro de IA: **não reimplementar esses sistemas dentro do Véu**. Extrair os padrões que cada um resolve melhor e plugá-los como *nervos / pontes*. O Véu continua sendo o **SO web administrado por IA**; OpenClaw, Hermes e Grok Bot são **runtimes externos** com papéis distintos.

---

## 1. Papéis (não competir — complementar)

| Sistema | O que é de verdade | Força | Papel no Véu |
|---------|--------------------|-------|--------------|
| **Véu** | Desktop web + kernel + respirações + ECC + host extension | Membrana viva, UI de SO, formações em tempo real, política `guided/semi/free` | **Control plane local** — onde o humano vê e respira |
| **OpenClaw** | Assistente self-hosted multi-canal (Slack/Discord/Teams/…) + skills + gateway | Presença nos canais onde o humano já está; harness de execução | **Gateway de canais** + padrões de skill/persona (já no ECC) |
| **Hermes** (Nous) | Agente self-improving: memória persistente, cria skills da experiência, importa OpenClaw | Loop de aprendizado + memória de operador | **Musculatura que cresce** — distilar sessões em skills ECC |
| **Grok Bot** (xAI/Cursor) | Teammates always-on com **computador cloud próprio**, 24/7, handoff de trabalho | Jobs longos que não param quando você fecha o browser | **Colônia cloud** — execução always-on fora do host |

Tese ECC (já documentada em `vendor/ecc/docs/HERMES-OPENCLAW-MIGRATION.md`):

> Hermes e OpenClaw são **sistemas-fonte**, não o runtime final. ECC é o substrato reutilizável (skills, agents, hooks).  
> No Véu: **ECC = músculo**, **OpenClaw/Hermes = harness opcionais**, **Grok Bot = mão cloud**.

---

## 2. O que implementar agora (priorizado)

### A. Padrões OpenClaw → Véu

1. **Channel Gateway** — nervo que despacha intenção para um canal (Slack/Teams/WhatsApp) com a mesma semântica do gateway OpenClaw (session → channel → tool).
2. **Persona / SOUL surface** — reusar skill `openclaw-persona-forge` do ECC para “personalidades” de formação no desktop (não copiar o runtime).
3. **Tool harness** — lista explícita de tools por formação (browser, shell via extension, MCP), com teto de risco = respiração.

### B. Padrões Hermes → Véu

1. **Learning loop** — após formações bem-sucedidas em `semi/free`, propor skill ECC sanitizada (`hermes-imports`).
2. **Memory Vault file-first** — alinhar `~/.veu/data/*.jsonl` com o modelo Hermes/ECC (sessions → decisions → skills).
3. **Cron / scheduler nervo** — jobs recorrentes (já previsto no ECC 2.0) como formações agendadas no kernel.

### C. Ponte Grok Bot ↔ Véu (sim, dá para juntar)

**Sim: juntamos os dois sem fundir os produtos.**  
Véu = membrana + política + ECC no host.  
Grok Bot = teammates com PC cloud.  
A ponte é um **nervo bidirecional**.

```text
┌──────────────┐   handoff    ┌──────────────┐
│  Véu Kernel  │ ───────────► │  Grok Bot    │
│  :8821       │ ◄─ webhook ─ │  (cloud PC)  │
│  formações   │              │  always-on   │
└──────┬───────┘              └──────────────┘
       │ host extension
       ▼
  apps físicos / browser
```

**Três modos da ponte:**

| Modo | Direção | Quando usar |
|------|---------|-------------|
| `handoff` | Véu → GrokBot | Job longo, 24/7, multi-app cloud, “termine enquanto eu saio” |
| `inbound` | GrokBot → Véu | Bot termina / precisa aprovação → evento no chat/formação |
| `mirror` | bidirecional | Status do teammate no Ecossistema (nó “Grok Bot”) |

**Superfícies técnicas (em ordem de realismo):**

1. **Fila local + API Véu** (`POST /bridge/grokbot/handoff`, `POST /bridge/grokbot/inbound`) — já no código.
2. **Webhook URL** configurável (`VEU_GROKBOT_WEBHOOK_URL`) quando o Bot/API expuser endpoint.
3. **xAI API** (`XAI_API_KEY`) como tier LLM “Grok” no `HybridLLM` (raciocínio forte sob demanda).
4. **Host bridge** — extension abre o app Grok Bot / deep-link quando existir.
5. **MCP** — se Grok Bot publicar MCP, entra no `mcp-bus` como qualquer outro nervo.

Não dependemos de fundir repos nem de “ser” o Grok Bot. Somos o **SO que o despacha e recebe o retorno**.

**Reuse, não rebuild:** o que o Grok Bot já tem (Plaud, pastas Empresa→projetos→assuntos, rotinas cloud, leitores Outlook/Teams/Gmail) **não** vira app/cliente duplicado no Véu. O hub Grok Bot no SO lista `remote_capabilities` e manda o pedido via handoff; o retorno cai na inbox. Política: `reuse-not-rebuild`.

**live.json do Control** (`/var/www/control-kiosk/live.json`): snapshot já pago pelos agentes cloud (agendas, Vale, CPQD…). Endpoints: `/bridge/control/live` e `/bridge/grokbot/sideboard`. Painel direito do hub = métricas + insights + agenda + reuniões + inbox — zero chamada nova a Outlook/Teams.

---

## 3. Arquitetura no código Véu

```text
engine/src/veu/bridges/
  __init__.py
  bus.py          # BridgeBus — status + handoff + inbound
  openclaw.py     # padrões gateway / canal
  hermes.py       # learning loop / skill proposal
  grokbot.py      # ponte always-on

connectors/registry.py  # nervos: openclaw, hermes, grokbot
api.py                  # /bridge/* endpoints
runtime.py              # weave detecta handoff → BridgeBus
```

Estados do nervo Grok Bot: `planned` → `ready` (env configurada) → `live` (handoff/inbound com ACK).

---

## 4. Política de autonomia na ponte

| Respiração | Handoff para Grok Bot |
|------------|------------------------|
| `guided` | Só enfileira após confirmação explícita |
| `semi` | Handoff automático se risco ≤ medium; high pede OK |
| `free` | Handoff automático até o teto; high ainda audita |

Tudo vai para `audit.jsonl` / `decisions.jsonl`.

---

## 5. O que *não* fazer

- Não embutir o runtime OpenClaw/Hermes/Grok dentro do Vite app.
- Não copiar secrets de `~/.hermes` / OpenClaw para o repo.
- Não tratar Grok Bot como “mais um chat” — ele é **executor cloud com PC próprio**.
- Não apagar o caminho ECC: skills/agents continuam a musculatura canônica.

---

## 6. Próximos commits concretos

1. ~~Scaffold `bridges/` + nervos no registry + `/bridge/*`~~ (este PR)
2. UI: nó “Grok Bot” no Ecossistema + botão “Enviar formação” no chat
3. `HybridLLM` + tier `xai` quando `XAI_API_KEY` existir
4. Learning loop Hermes → proposta de skill após N formações iguais
5. Webhook real assim que a superfície pública do Grok Bot estiver disponível

---

*Referências internas: ECC `docs/HERMES-SETUP.md`, `HERMES-OPENCLAW-MIGRATION.md`, skills `hermes-imports`, `openclaw-persona-forge`.*

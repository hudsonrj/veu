# Véu — Continuidade (handoff)

Documento para retomar o trabalho em **qualquer chat/agente** sem depender do histórico do GovGPT.

**Leia isto primeiro.** Depois: `MANIFESTO.md`, `README.md`.

---

## 1. O que é o Véu

Sistema operacional **administrado por IA**, rodando **sobre** Windows/Linux (não substitui o kernel).

- Chat nativo com o usuário (não é clone de ChatGPT)
- Construção e execução **em tempo real** (passos visíveis no campo)
- Três respirações de autonomia: `guided` · `semi` · `free`
- Nervos (conectores): WhatsApp, Teams, Outlook, Gmail, Google Chat, Google Workspace, Notion, Slack, MCP, APIs, apps do host
- Musculatura: [ECC](https://github.com/hudsonrj/ECC) — 71 agentes + 311 skills

Identidade de produto: membrana viva (“véu”), formações (não “abrir app”), campo animado, tipografia Syne + IBM Plex.

---

## 2. Onde está o código (NÃO misturar com GovGPT)

| Lugar | Caminho | Notas |
|-------|---------|--------|
| **Repo canônico (aqui)** | `/home/ubuntu/veu` | Fonte da verdade — ler `CONTINUIDADE.md` |
| Servidor de deploy | `/root/veu` | Mirror de runtime; **fora** de `/root/apps` |
| GitHub | https://github.com/hudsonrj/veu.git | Push do Cursor bot ainda pode precisar do GitHub App no repo `veu` |
| ECC (vendor) | `vendor/ecc` no repo / `/root/veu/vendor/ecc` no servidor | Clone de `hudsonrj/ECC` |

**Este é o projeto Véu.** GovGPT (`/workspace`, `hudsonrj/govgpt`) é outro repo — não misturar.

---

## 2.1 Auth (P0 — plano de controle fechado)

Desde o review `veuajustes.pdf` (Onda 1):

| Item | Detalhe |
|------|---------|
| Sessão | Cookie `veu_session` HttpOnly + Secure + SameSite=Strict |
| Login | Google OAuth (`/auth/google`) — e-mail allowlist `VEU_AUTH_GOOGLE_EMAILS` |
| Fallback | `VEU_AUTH_PASSWORD` (opcional) |
| Público | `/health`, `/ready`, `/auth/*` |
| Mutações | Origin/Referer allowlist + header `X-Veu-CSRF` |
| Segredos | `/servers` mascara host/IP/user; `secret_env` só com `?reveal=1` |
| Caddy | `@kernel` inclui `/auth*` |
| Google Console | Redirect URI obrigatória: `https://veu.ch8ai.com.br/auth/google/callback` |

Secrets no servidor: `/root/veu/engine/.env` (`VEU_GOOGLE_CLIENT_*`, `VEU_AUTH_*`). **Nunca** no git.

---

## 3. No ar agora

| Serviço | URL | systemd |
|---------|-----|---------|
| Desktop (shell) | https://veu.ch8ai.com.br | Caddy → `127.0.0.1:8820` |
| Kernel API | https://veu.ch8ai.com.br/pulse (etc.) | Caddy → `127.0.0.1:8821` |
| IP direto (fallback) | http://169.58.19.232:8820 / `:8821` | systemd `veu-desktop` / `veu-kernel` |

Host público: `169.58.19.232` · DNS A `veu.ch8ai.com.br` → esse IP · TLS Let's Encrypt via Caddy.  
IP Tailscale (inacessível do Cloud Agent sem Tailscale): `100.119.119.83`

### Comandos úteis no servidor

```bash
systemctl status veu-desktop veu-kernel
journalctl -u veu-desktop -u veu-kernel -f
curl -s http://127.0.0.1:8821/pulse
```

Working dirs nos units:

- Desktop: `/root/veu/desktop` → `node_modules/.bin/serve -s dist -l tcp://0.0.0.0:8820`
- Kernel: `/root/veu/engine/.venv/bin/uvicorn veu.api:app --host 0.0.0.0 --port 8821`
- Env: `VEU_ECC_ROOT=/root/veu/vendor/ecc`

---

## 4. Estrutura do projeto

```
veu/
├── CONTINUIDADE.md          ← este arquivo
├── MANIFESTO.md
├── README.md
├── desktop/                 # pele — Vite + React + framer-motion
│   ├── src/
│   │   ├── App.tsx          # SO acordado: chat + execução ao vivo
│   │   ├── components/
│   │   │   ├── LivingField.tsx
│   │   │   ├── BrandMark.tsx
│   │   │   ├── AutonomyOrbit.tsx
│   │   │   ├── IntentContinuum.tsx
│   │   │   ├── NativeChat.tsx
│   │   │   ├── LiveExecution.tsx
│   │   │   └── FormationStage.tsx
│   │   └── lib/
│   │       ├── kernel.ts    # SSE → VITE_VEU_KERNEL
│   │       └── weave.ts     # fallback local sem kernel
│   └── .env.production      # no servidor: VITE_VEU_KERNEL=http://169.58.19.232:8821
├── engine/                  # musculatura — Python
│   └── src/veu/
│       ├── api.py           # FastAPI: /pulse /connectors /bridge/* /weave /chat
│       ├── runtime.py       # kernel: weave + stream + bridges
│       ├── bridges/         # OpenClaw · Hermes · Grok Bot
│       ├── ecc.py           # catálogo ECC (+ hydrate do vendor)
│       ├── connectors/      # nervos
│       └── cli.py           # veu pulse | weave | serve
├── docs/AI-BRIDGES.md       # engenharia: o que puxar de cada runtime
└── vendor/ecc/              # no servidor (clone ECC)
```

---

## 5. APIs do kernel

- `GET /pulse` — saúde + contagens ECC/conectores + **bridges**  
- `GET /connectors` — catálogo de nervos  
- `GET /bridge` — pulse OpenClaw · Hermes · Grok Bot  
- `POST /bridge/grokbot/handoff` — Véu → Grok Bot (fila / webhook)  
- `POST /bridge/grokbot/ask` — pedido do SO / via agente ECC  
- `POST /bridge/grokbot/approve` — humano OK no SO → Grok segue  
- `GET /bridge/grokbot/brief` · `/inbox` — dia a dia (decisões, importantes)  
- `POST /bridge/grokbot/inbound` — Grok Bot → Véu (callback, persistido)  
- `GET /bridge/grokbot/queue` — fila outbound/inbound  
- `POST /weave` — `{ "message", "breath" }` → formação JSON  
- `POST /chat` — mesmo body, **SSE** eventos:
  - `thinking` → `plan` → `step` (running/done) → `reply` → `done`

Desktop fala com o kernel via `VITE_VEU_KERNEL` (default `http://127.0.0.1:8821`). Se o kernel cair, usa fallback local (`weave.ts`).

---

## 5b. Pontes de IA (Jev · OpenClaw · Hermes · Grok Bot)

Doc completo: [`docs/AI-BRIDGES.md`](docs/AI-BRIDGES.md).  
Prompt do bot cloud: [`docs/GROKBOT-SOUL.md`](docs/GROKBOT-SOUL.md).

| Runtime | Papel no Véu | Como juntar |
|---------|--------------|-------------|
| **Jev** | System One — decisões tipadas (Choice/Score/Noul) | `TYPESAFE_API_KEY` em `/root/veu/engine/.env` (não versionar); pin `jev-1.13.0` |
| OpenClaw | Gateway multi-canal + tool harness | nervo `openclaw`; `VEU_OPENCLAW_GATEWAY_URL` |
| Hermes | Learning loop → skills ECC | nervo `hermes`; observa formações; skill `hermes-imports` |
| **Grok Bot** | Teammates cloud always-on (PC próprio) | **ponte bidirecional** — handoff + inbound webhook |

Chat do usuário: **sem jargão interno** (híbrido/formação/barramento). Jev classifica; LLM responde.

**Sim, dá para juntar Véu + Grok Bot** sem fundir produtos. Env: `VEU_GROKBOT_WEBHOOK_URL`, `VEU_GROKBOT_API_BASE`, `XAI_API_KEY`.

Secrets do kernel: `EnvironmentFile=/root/veu/engine/.env` (chmod 600).

---

## 5c. Secrets no servidor (não versionar)

Arquivo: `/root/veu/engine/.env` (chmod 600), carregado pelo systemd `EnvironmentFile`.

| Var | Status |
|-----|--------|
| `TYPESAFE_API_KEY` | live (Jev) |
| `NOTION_TOKEN` | live |
| `OPENRAG_API_KEY` + `OPENRAG_URL` | live (hoje `https://rag.hatkg.com` — a key `orag_` não autentica em `ragpro.ch8ai.com.br`) |
| `OPENAI_API_KEY` | live (copiada do stack OpenRAG local) |

Modelo: `.env.example` no repo.

## 6. Conectores (nervos) — estado

| id | Status | Surface | Notas |
|----|--------|---------|--------|
| notion | ready | mcp | Primeiro workspace — autenticar MCP |
| slack | ready | mcp | MCP Slack |
| mcp-bus | ready | mcp | Host MCP genérico |
| api-bus | ready | api | HTTP/OAuth/webhooks |
| whatsapp | planned | hybrid | Web/Desktop + bridge |
| teams | planned | hybrid | Graph + app |
| outlook | planned | api | Microsoft Graph |
| gmail | planned | api | Gmail API |
| google-chat | planned | api | |
| google | planned | hybrid | Workspace |
| host-desktop | planned | desktop | UI Automation / AT-SPI |
| openclaw | planned→ready* | bridge | Gateway canais (*se env) |
| hermes | planned→ready* | bridge | Learning loop (*se `~/.hermes`) |
| grokbot | ready/live | bridge | Routine Handoff do Véu + Saúde do bridge; webhook Cursor Automations |

ECC já roteia comunicação → agente `chief-of-staff`; Notion/docs → `doc-updater` / `planner`.

---

## 7. Decisões de produto já tomadas

1. **Não** mapear mercado em docs — unir o melhor por baixo, pele própria.  
2. **Não** misturar com GovGPT / ChatGPT UI.  
3. Nome do produto: **Véu**.  
4. Pasta no servidor: **`/root/veu`** (não `/root/apps/veu`).  
5. ECC entra como vendor/musculatura, não como “plugin listado” na UI.  
6. Visual: campo vivo escuro, filament dourado + sinal ciano, Syne display — evitar clichês purple/cream-terracotta.  
7. Tudo com ajuda de IA: chat nativo + execução ao vivo + administração do SO.  
8. **Plaud e o que já vive no Grok Bot** — **não** criar cliente/app Plaud no Véu. Pedir via ponte (`/bridge/grokbot/ask` + inbound). Hub Grok Bot mostra `remote_capabilities` (Plaud, pastas Empresa→projetos→assuntos, briefing). Política: **reuse-not-rebuild**.  
9. **Control `live.json`** — o Grok Bot já consolida Outlook/Teams/Gmail/agenda/reuniões/tarefas em `/var/www/control-kiosk/live.json`. O Véu **só lê e transforma** (`GET /bridge/grokbot/sideboard`, `GET /bridge/control/live`, `GET /bridge/control/companies`). Painel direito (`DayRail`) + app **Empresas** (pastas → projetos → tarefas/msgs/reuniões). Clique abre detalhe; se raso, **pedir ao Grok Bot**. Sem reler caixas de e-mail.  
10. **Servidores** — app com ícones (Contabo/Hetzner/Pi do live + frota). Mostra apps/domínios/role; SSH via `POST /servers/{id}/ssh` + Véu Host (`veu.host.ssh`). Board: `GET /servers/board`.

---

## 7b. SO web + ponte física (atual)

Desktop é um **sistema operacional web**: wallpaper vivo, ícones, janelas arrastáveis, dock, chat como app, engrenagem → ecossistema de agentes.

Desktop: ícones em **zonas** (núcleo · mente · canais · ferramentas) — sem caixa com scroll. Dock só o núcleo + Notion/OpenRAG.

App **Ajustes** (control center): mapa · nervos · assinaturas · **servidores** · modelos · músculo · políticas — status via `/pulse`, `/connectors`, `/harness`, `/servers`. Secrets só no servidor (`/root/veu/engine/.env`).

### Servidores (frota do Hudson)

Só hosts que ele cadastra em **Ajustes → servidores**. Sem varredura de rede.

| Peça | Onde |
|------|------|
| Metadados (host, porta, user) | `$VEU_DATA_ROOT/servers.json` |
| Senha SSH | `.env` → `VEU_SRV_<HEX>_PASSWORD` (mascarada na UI) |
| API | `GET/POST/DELETE /servers` · `POST …/test` · `GET …/sites` · `GET …/maintenance` |
| Caddy | matcher `@kernel` precisa incluir `/servers*` — ver `docs/caddy-veu-kernel.snippet` |

Ações: testar conexão, listar sites/serviços, status de manutenção (leitura).

Extensão do browser em `extension/` liga o SO à máquina física (`host · ok` no topo).
Native Messaging (shell/fs/apps nativos) é o próximo degrau da ponte.

## 8. Próximos passos sugeridos (prioridade)

1. ~~**Memória do SO**~~ — `Memory` append-only (`~/.veu/data` ou `VEU_DATA_ROOT`) + `GET /memory`.  
2. ~~**Pontes OpenClaw/Hermes/GrokBot**~~ — scaffold + `/bridge/*` (ver `docs/AI-BRIDGES.md`).  
3. **UI Ecossistema** — nós OpenClaw / Hermes / Grok Bot + botão “Handoff” no chat.  
4. ~~**Auth Notion**~~ — `NOTION_TOKEN` no `.env` → nervo `live` (busca via chat). Mesmo padrão pros outros: token no `.env` hidrata status.  
5. **Webhook Grok Bot real** — `VEU_GROKBOT_WEBHOOK_URL` assim que a superfície pública existir; tier `XAI_API_KEY` no HybridLLM.  
6. **Chief-of-staff vivo** — triagem Gmail/Outlook (Graph) e WhatsApp (bridge/web).  
7. **Host apps** — abrir/focar WhatsApp Desktop, Teams, browser sob política de risco.  
8. ~~**DNS/Caddy**~~ — `https://veu.ch8ai.com.br` live (desktop + kernel no mesmo host).  
9. **Push GitHub** — liberar GitHub App do Cursor no repo `hudsonrj/veu` e `git push`.  
10. **Empacotar desktop** — Tauri/Electron para sensação de SO nativo no Windows/Linux.

### Prompt para o próximo chat

```text
Repo: /home/ubuntu/veu — leia CONTINUIDADE.md. Não use GovGPT.
Continue a partir daí.
```

---

## 9. Como continuar num chat novo

Prompt sugerido para colar:

```text
Continue o projeto Véu. Leia /home/ubuntu/veu/CONTINUIDADE.md (ou /root/veu/CONTINUIDADE.md no servidor)
e MANIFESTO.md. Código em /home/ubuntu/veu. Deploy em /root/veu no host 169.58.19.232
(portas 8820 desktop, 8821 kernel). Não misturar com GovGPT.
Próximo foco: [descreva o que quer — ex. Notion MCP auth, WhatsApp bridge, push no GitHub…]
```

Se o agente estiver no workspace GovGPT: trabalhar em `/home/ubuntu/veu` ou abrir o repo `hudsonrj/veu`.

---

## 10. Segurança / credenciais

- Senha de root do servidor foi usada neste chat para deploy via SSH — **não versionar senha** neste MD nem no git. Preferir chave SSH daqui pra frente e **rotacionar** a senha se foi exposta em chat.  
- Secrets futuros: tokens Notion/Slack/Google/Microsoft, `TAILSCALE_AUTHKEY` se o agente precisar da rede `100.x`.

---

## 11. Commits locais recentes (em `/home/ubuntu/veu`)

Histórico aproximado:

1. Nascimento do Véu (desktop + engine mínimo)  
2. SO administrado por IA — chat nativo, SSE, conectores, ECC  
3. Docs de pastas próprias  

Sincronizar servidor após mudanças:

```bash
# do ambiente de dev
cd /home/ubuntu/veu
tar -czf - --exclude=.git --exclude=node_modules --exclude=desktop/node_modules \
  --exclude=.venv --exclude=vendor --exclude=desktop/dist . \
| ssh root@169.58.19.232 'tar -xzf - -C /root/veu'

# no servidor: rebuild desktop + restart
cd /root/veu/desktop && npm install && npm run build
systemctl restart veu-desktop veu-kernel
```

(Ou rsync/scp equivalentes.)

---

*Última atualização deste handoff: 2026-10-16 — sessão Cloud Agent que separou Véu do GovGPT e subiu chat+kernel+ECC em `/root/veu`.*

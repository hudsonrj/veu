# API do kernel

O kernel (`engine/`) é uma aplicação FastAPI. Por padrão escuta em `:8821`; em produção, o Caddy encaminha as rotas do kernel no mesmo domínio do desktop.

- **OpenAPI interativo:** `GET /docs` (Swagger) e `GET /openapi.json`
- **Autenticação:** cookie de sessão `veu_session`. Rotas públicas: `/health`, `/healthz`, `/ready`, `/auth/*`.
- **Mutações** (`POST`/`PUT`/`DELETE`) exigem o header `X-Veu-CSRF: 1` e `Origin` permitido.
- **Ponte Grok Bot:** chamadas máquina-a-máquina usam `Authorization: Bearer <VEU_GROKBOT_WEBHOOK_SECRET>` ou `X-VEU-Webhook-Secret`.

## Essenciais

| Rota | Descrição |
|---|---|
| `GET /healthz` | Vida do kernel (público) |
| `GET /pulse` | Saúde completa: ECC, nervos, pontes, memória |
| `GET /auth/status` | Sessão atual e métodos de login disponíveis |
| `POST /auth/login` | `{ "password": "…" }` → cookie de sessão |
| `POST /weave` | `{ "message", "breath" }` → formação JSON (sem executar) |
| `POST /chat` | Mesmo corpo → **stream SSE** da execução |
| `GET /mission` | Snapshot do flight deck: projetos, jobs, agentes, go/no-go |
| `GET /connectors` | Catálogo de nervos e status (`live` · `ready` · `planned`) |
| `POST /control/stop-all` | Para tudo: cancela jobs, pausa o executor e volta para `guided` |

## Chat em tempo real (SSE)

```bash
curl -N https://SEU_HOST/chat \
  -H 'Content-Type: application/json' -H 'Accept: text/event-stream' \
  -H 'X-Veu-CSRF: 1' -b 'veu_session=…' \
  -d '{"message": "resuma minha inbox", "breath": "semi"}'
```

Cada evento é uma linha `data: {json}`:

| `type` | Payload | Quando |
|---|---|---|
| `status` / `thinking` | `text` | O kernel está lendo contexto |
| `harness` | `active`, `session { tools, risk_ceiling, route }` | Sessão de execução aberta |
| `plan` | `formation` | Plano pronto: nervos, agentes e passos |
| `step` | `index`, `step { id, label, actor }`, `state` (`running`/`done`) | Progresso de cada passo |
| `action` | `action`, `url`, `app`, `payload` | Pedido para o desktop abrir um app ou URL |
| `reply` | `text` | Resposta em linguagem natural |
| `done` | `formation` | Fim da formação |

Valores de `breath`: `guided` · `semi` · `free` · `autonomous`.

## Todas as rotas

Lista gerada a partir do código (`engine/src/veu`), agrupada por área.

<details>
<summary><b>Saúde</b> · 5 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/about` |
| `GET` | `/health` |
| `GET` | `/healthz` |
| `GET` | `/pulse` |
| `GET` | `/ready` |

</details>

<details>
<summary><b>Autenticação</b> · 6 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/auth/google` |
| `GET` | `/auth/google/callback` |
| `GET` | `/auth/google/workspace` |
| `POST` | `/auth/login` |
| `POST` | `/auth/logout` |
| `GET` | `/auth/status` |

</details>

<details>
<summary><b>Chat & formações</b> · 10 rotas</summary>

| Método | Rota |
|---|---|
| `POST` | `/chat` |
| `GET` | `/harness` |
| `GET` | `/jobs` |
| `GET` | `/jobs/{job_id}` |
| `POST` | `/jobs/{job_id}/cancel` |
| `GET` | `/jobs/{job_id}/report` |
| `GET` | `/mission` |
| `GET` | `/stream` |
| `GET` | `/stream/log` |
| `POST` | `/weave` |

</details>

<details>
<summary><b>Nervos (conectores)</b> · 22 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/connectors` |
| `POST` | `/connectors/audit-nerves` |
| `POST` | `/connectors/selftest` |
| `GET` | `/inbox` |
| `POST` | `/inbox/drafts` |
| `POST` | `/inbox/drafts/{draft_id}/decide` |
| `GET` | `/mcp` |
| `POST` | `/mcp/import` |
| `DELETE` | `/mcp/{server_id}` |
| `POST` | `/mcp/{server_id}/approve` |
| `POST` | `/mcp/{server_id}/call` |
| `POST` | `/mcp/{server_id}/probe` |
| `GET` | `/notion/pulse` |
| `POST` | `/notion/search` |
| `POST` | `/openrag/ask` |
| `GET` | `/openrag/pulse` |
| `GET` | `/workspace` |
| `GET` | `/workspace/calendar` |
| `POST` | `/workspace/disconnect` |
| `GET` | `/workspace/drive` |
| `GET` | `/workspace/gmail` |
| `GET` | `/workspace/status` |

</details>

<details>
<summary><b>Pontes de IA</b> · 18 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/bridge` |
| `GET` | `/bridge/control/companies` |
| `GET` | `/bridge/control/companies/{company_id}` |
| `GET` | `/bridge/control/live` |
| `GET` | `/bridge/control/meetings/{meeting_id}` |
| `POST` | `/bridge/grokbot/approve` |
| `POST` | `/bridge/grokbot/ask` |
| `GET` | `/bridge/grokbot/brief` |
| `POST` | `/bridge/grokbot/handoff` |
| `GET` | `/bridge/grokbot/health` |
| `POST` | `/bridge/grokbot/inbound` |
| `GET` | `/bridge/grokbot/inbox` |
| `GET` | `/bridge/grokbot/queue` |
| `GET` | `/bridge/grokbot/sideboard` |
| `POST` | `/bridge/hermes/ask` |
| `POST` | `/bridge/hermes/prefer` |
| `GET` | `/bridge/hermes/pulse` |
| `GET` | `/bridge/hermes/queue` |

</details>

<details>
<summary><b>Músculo ECC</b> · 3 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/agents` |
| `GET` | `/ecc` |
| `GET` | `/skills` |

</details>

<details>
<summary><b>Controle & segurança</b> · 21 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/approvals` |
| `POST` | `/approvals/{approval_id}/decide` |
| `GET` | `/autonomous` |
| `POST` | `/autonomous/actions/{action_id}/decide` |
| `GET` | `/autonomous/board` |
| `POST` | `/autonomous/clean-noise` |
| `POST` | `/autonomous/scan` |
| `GET` | `/control` |
| `GET` | `/control/audit` |
| `GET` | `/control/audit.csv` |
| `GET` | `/control/permissions` |
| `POST` | `/control/resume` |
| `POST` | `/control/stop-all` |
| `GET` | `/credentials` |
| `POST` | `/credentials/{account_id}/relogin-ok` |
| `GET` | `/decisions` |
| `GET` | `/integrity/verify` |
| `GET` | `/targets` |
| `POST` | `/targets/advanced` |
| `POST` | `/targets/authorize` |
| `POST` | `/targets/mark` |

</details>

<details>
<summary><b>Memória & dados</b> · 26 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/clone` |
| `POST` | `/clone/chat` |
| `POST` | `/clone/correct` |
| `POST` | `/clone/harvest` |
| `GET` | `/clone/history` |
| `GET` | `/clone/status` |
| `POST` | `/clone/teach` |
| `GET` | `/data` |
| `POST` | `/data/delete` |
| `GET` | `/data/delete/preview` |
| `POST` | `/data/export` |
| `POST` | `/import/chatgpt` |
| `POST` | `/import/claude` |
| `GET` | `/memory` |
| `GET` | `/projects` |
| `GET` | `/projects/folders` |
| `POST` | `/projects/folders/allow` |
| `POST` | `/projects/folders/deny` |
| `POST` | `/projects/sync/claude-code` |
| `POST` | `/projects/sync/cursor` |
| `GET` | `/projects/{project_id}` |
| `POST` | `/projects/{project_id}/ask` |
| `GET` | `/togo/export` |
| `POST` | `/togo/import/apply` |
| `POST` | `/togo/import/preview` |
| `POST` | `/togo/verify` |

</details>

<details>
<summary><b>Dia a dia</b> · 32 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/briefing` |
| `POST` | `/briefing/build` |
| `GET` | `/briefing/schedule` |
| `POST` | `/briefing/schedule/tick` |
| `POST` | `/capture` |
| `POST` | `/capture/preview` |
| `POST` | `/life/ask` |
| `GET` | `/mental` |
| `POST` | `/mental/alerts/{alert_id}/ack` |
| `GET` | `/mental/board` |
| `POST` | `/mental/checkin` |
| `POST` | `/mental/scan` |
| `POST` | `/mental/trigger` |
| `GET` | `/os/agenda` |
| `GET` | `/os/calendar` |
| `POST` | `/os/calendar/ingest` |
| `GET` | `/os/day` |
| `GET` | `/os/queue` |
| `GET` | `/os/voice` |
| `GET` | `/os/workspaces` |
| `GET` | `/os/workspaces/{ws_id}` |
| `POST` | `/os/workspaces/{ws_id}/activate` |
| `GET` | `/productivity` |
| `POST` | `/push/subscribe` |
| `POST` | `/push/test` |
| `POST` | `/push/unsubscribe` |
| `GET` | `/push/vapid-public` |
| `GET` | `/routines` |
| `POST` | `/routines/tick` |
| `DELETE` | `/routines/{routine_id}` |
| `POST` | `/voice/ask` |
| `POST` | `/voice/transcribe` |

</details>

<details>
<summary><b>Frota & desktops remotos</b> · 53 rotas</summary>

| Método | Rota |
|---|---|
| `POST` | `/browser/lite/sessions` |
| `DELETE` | `/browser/lite/sessions/{sid}` |
| `GET` | `/browser/lite/status` |
| `GET` | `/browser/lite/{sid}/frame.jpg` |
| `POST` | `/browser/lite/{sid}/input` |
| `GET` | `/browser/probe` |
| `GET` | `/browser/view` |
| `GET` | `/device/esp32/board` |
| `GET` | `/device/esp32/devices` |
| `POST` | `/device/esp32/enroll` |
| `POST` | `/device/esp32/event` |
| `GET` | `/device/esp32/events` |
| `GET` | `/device/esp32/state` |
| `GET` | `/ruflo` |
| `POST` | `/ruflo/control` |
| `POST` | `/ruflo/missions` |
| `GET` | `/ruflo/plugins` |
| `POST` | `/ruflo/plugins/{plugin_id}` |
| `GET` | `/ruflo/status` |
| `POST` | `/ruflo/swarm/init` |
| `POST` | `/ruflo/swarm/stop` |
| `POST` | `/ruflo/theme` |
| `GET` | `/ruos` |
| `GET` | `/ruos/desktops` |
| `POST` | `/ruos/desktops/{desktop_id}/reconnect` |
| `POST` | `/ruos/desktops/{desktop_id}/start` |
| `POST` | `/ruos/desktops/{desktop_id}/stop` |
| `POST` | `/ruos/enroll` |
| `GET` | `/ruos/enroll.sh` |
| `POST` | `/ruos/enroll/claim` |
| `GET` | `/ruos/keys` |
| `POST` | `/ruos/keys/custom` |
| `POST` | `/ruos/keys/mcp` |
| `DELETE` | `/ruos/keys/mcp/{token_id}` |
| `POST` | `/ruos/keys/model` |
| `DELETE` | `/ruos/keys/model/{slot}` |
| `POST` | `/ruos/keys/routing` |
| `POST` | `/ruos/keys/slack` |
| `POST` | `/ruos/keys/tailscale` |
| `POST` | `/ruos/keys/website` |
| `POST` | `/ruos/lite/ai` |
| `POST` | `/ruos/lite/resume` |
| `POST` | `/ruos/provision` |
| `POST` | `/ruos/rustdesk` |
| `GET` | `/ruos/snapshots` |
| `POST` | `/ruos/snapshots/{snap_id}/duplicate` |
| `GET` | `/servers` |
| `GET` | `/servers/board` |
| `DELETE` | `/servers/{server_id}` |
| `GET` | `/servers/{server_id}/maintenance` |
| `GET` | `/servers/{server_id}/sites` |
| `POST` | `/servers/{server_id}/ssh` |
| `POST` | `/servers/{server_id}/test` |

</details>

<details>
<summary><b>Custos & assinaturas</b> · 24 rotas</summary>

| Método | Rota |
|---|---|
| `POST` | `/billing/alerts/evaluate` |
| `GET` | `/billing/dashboard` |
| `GET` | `/billing/export.csv` |
| `POST` | `/billing/provider-costs/collect` |
| `GET` | `/billing/provider-costs/reconcile` |
| `POST` | `/billing/provider-costs/sample` |
| `GET` | `/billing/provider-costs/status` |
| `POST` | `/billing/receipts/ingest` |
| `POST` | `/billing/receipts/scan` |
| `GET` | `/billing/subscriptions` |
| `GET` | `/billing/subscriptions/{sub_id}` |
| `POST` | `/billing/subscriptions/{sub_id}/decision` |
| `GET` | `/billing/suggestions` |
| `POST` | `/billing/suggestions/{suggestion_id}/decide` |
| `POST` | `/llm/chat` |
| `GET` | `/llm/decide` |
| `POST` | `/llm/keys/huggingface` |
| `GET` | `/llm/playground` |
| `POST` | `/llm/subscription-compose` |
| `GET` | `/subscriptions` |
| `POST` | `/subscriptions/confirm` |
| `POST` | `/subscriptions/link` |
| `DELETE` | `/subscriptions/{provider}` |
| `GET` | `/usage` |

</details>

<details>
<summary><b>Estúdio & REA</b> · 14 rotas</summary>

| Método | Rota |
|---|---|
| `GET` | `/rea` |
| `POST` | `/rea/analyze` |
| `GET` | `/rea/jobs` |
| `GET` | `/rea/jobs/{job_id}` |
| `POST` | `/rea/jobs/{job_id}/publish` |
| `POST` | `/rea/mcp/register` |
| `GET` | `/rea/status` |
| `GET` | `/studio/actions` |
| `GET` | `/studio/assets` |
| `POST` | `/studio/from-text` |
| `GET` | `/studio/jobs` |
| `GET` | `/studio/pulse` |
| `POST` | `/studio/run` |
| `POST` | `/studio/upload` |

</details>

<details>
<summary><b>Sistema</b> · 2 rotas</summary>

| Método | Rota |
|---|---|
| `POST` | `/updates/check` |
| `GET` | `/updates/previous` |

</details>

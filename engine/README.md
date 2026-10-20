# Véu · engine (kernel)

O kernel do Véu: API **FastAPI** + CLI `veu`. Recebe intenções, tece *formações*, aplica a política de risco das respirações, aciona o músculo ECC e os nervos, e transmite tudo ao vivo por SSE.

## Rodar

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[llm,mcp]"
cp ../.env.example .env              # VEU_AUTH_PASSWORD, chaves de modelo…
.venv/bin/veu serve --host localhost --port 8821
```

## CLI

```bash
veu pulse                                   # saúde do kernel
veu weave "resuma minha inbox" -b semi      # tece uma formação (guided|semi|free)
veu serve --host 0.0.0.0 --port 8821        # sobe a API
```

## Mapa do código

| Módulo | Papel |
|---|---|
| `api.py` | Todas as rotas REST/SSE (veja [docs/API.md](../docs/API.md)) |
| `runtime.py` | `weave` → formação, `stream_weave` → eventos SSE |
| `auth.py` | Sessão, Google OAuth, senha, CSRF |
| `jev.py`, `llm.py` | Decisões tipadas (Jev) e LLM híbrido |
| `ecc.py`, `harness.py` | Catálogo ECC e sessões de execução com teto de risco |
| `bridges/` | Grok Bot, Hermes, OpenClaw, Control live |
| `connectors/` | Nervos: registry, Notion, OpenRAG, selftest |
| `memory.py`, `logbook.py`, `integrity.py` | Memória append-only, auditoria e verificação |
| `control.py`, `approvals.py`, `autonomous.py` | Parar tudo, aprovações humanas, modo autônomo |
| `fleet/`, `ruos_*.py`, `esp32_device.py` | Servidores, desktops remotos e a placa ESP32 |

## Testes

```bash
.venv/bin/pip install pytest && .venv/bin/pytest
```

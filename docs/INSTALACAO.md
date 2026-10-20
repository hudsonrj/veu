# Instalação

- [Desenvolvimento local](#desenvolvimento-local)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Produção (systemd + Caddy)](#produção-systemd--caddy)
- [Véu Host (extensão + native host)](#véu-host)
- [Placa ESP32](#placa-esp32)

---

## Desenvolvimento local

**Requisitos:** Node 20+, Python 3.10+, git.

```bash
git clone --recurse-submodules https://github.com/hudsonrj/veu.git
cd veu
```

> Se você clonou sem `--recurse-submodules`: `git submodule update --init`.

### Kernel

```bash
cd engine
python3 -m venv .venv
.venv/bin/pip install -e ".[llm,mcp]"        # extras opcionais: llm, mcp, browser
cp ../.env.example .env
```

No `.env`, defina pelo menos:

```ini
VEU_AUTH_PASSWORD=uma-senha-forte
VEU_AUTH_COOKIE_SECURE=0          # só em http local
VEU_ECC_ROOT=/caminho/para/veu/vendor/ecc
OPENAI_API_KEY=...                # ou OPENROUTER_API_KEY / OLLAMA_BASE_URL
```

Suba o kernel:

```bash
.venv/bin/veu serve --host localhost --port 8821
```

Confira se está vivo: `curl http://localhost:8821/healthz`. O Swagger fica em http://localhost:8821/docs.

### Desktop

```bash
cd desktop
npm install
VITE_VEU_KERNEL=http://localhost:8821 npm run dev
```

Abra http://localhost:5173.

> Use `localhost` (e não `127.0.0.1`) nos dois lados: o cookie é `SameSite=Strict` e os dois nomes contam como sites diferentes.

### Testes

```bash
cd engine && .venv/bin/pip install pytest && .venv/bin/pytest
cd desktop && npm run lint && npm run build
```

---

## Variáveis de ambiente

Modelo completo em [`.env.example`](../.env.example). Os segredos ficam **só** em `engine/.env` (chmod 600) e nunca entram no git.

| Grupo | Variáveis |
|---|---|
| Auth | `VEU_AUTH_PASSWORD`, `VEU_AUTH_SECRET`, `VEU_AUTH_COOKIE_SECURE`, `VEU_AUTH_ORIGINS`, `VEU_PUBLIC_URL` |
| Google OAuth | `VEU_GOOGLE_CLIENT_ID`, `VEU_GOOGLE_CLIENT_SECRET`, `VEU_AUTH_GOOGLE_EMAILS` |
| Modelos | `OPENAI_API_KEY`, `VEU_OPENAI_MODEL`, `OPENROUTER_API_KEY`, `VEU_OPENROUTER_MODEL`, `OLLAMA_BASE_URL`, `VEU_OLLAMA_MODEL` |
| Jev | `TYPESAFE_API_KEY`, `VEU_JEV_MODEL` |
| Nervos | `NOTION_TOKEN`, `OPENRAG_API_KEY`, `OPENRAG_URL` |
| Grok Bot | `VEU_GROKBOT_WEBHOOK_URL`, `VEU_GROKBOT_WEBHOOK_SECRET`, `VEU_GROKBOT_API_BASE`, `XAI_API_KEY` |
| Kernel | `VEU_ECC_ROOT`, `VEU_DATA_ROOT`, `VEU_CONTROL_LIVE_PATH` |
| Servidores | `VEU_SRV_<ID>_PASSWORD` (uma por servidor cadastrado em Ajustes) |
| Desktop (build) | `VITE_VEU_KERNEL`: URL do kernel. Vazio = mesma origem. |

---

## Produção (systemd + Caddy)

O layout usado em produção:

| Serviço | Porta | Unit |
|---|---|---|
| Desktop (estático) | `8820` | `veu-desktop` |
| Kernel | `8821` | `veu-kernel` |
| Caddy (TLS) | `443` | `caddy` |

### Build do desktop

```bash
cd desktop
echo "VITE_VEU_KERNEL=https://seu-dominio" > .env.production
npm ci && npm run build
```

### `/etc/systemd/system/veu-kernel.service`

```ini
[Unit]
Description=Véu kernel API (chat SSE)
After=network.target

[Service]
WorkingDirectory=/root/veu/engine
EnvironmentFile=-/root/veu/engine/.env
Environment=VEU_ECC_ROOT=/root/veu/vendor/ecc
ExecStart=/root/veu/engine/.venv/bin/uvicorn veu.api:app --host 127.0.0.1 --port 8821
Restart=always
MemoryMax=1G

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/veu-desktop.service`

```ini
[Unit]
Description=Véu desktop (AI OS shell)
After=network.target

[Service]
WorkingDirectory=/root/veu/desktop
ExecStart=/root/veu/desktop/node_modules/.bin/serve -s dist -l tcp://127.0.0.1:8820
Restart=always
MemoryMax=512M

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now veu-kernel veu-desktop
journalctl -u veu-kernel -u veu-desktop -f
```

### Caddy

O bloco de referência está em [`caddy-veu-kernel.snippet`](caddy-veu-kernel.snippet). As rotas do kernel vão para `:8821`, e o resto vai para o desktop em `:8820`. Toda área nova da API precisa entrar no matcher `@kernel`.

### Google OAuth

No Google Cloud Console, cadastre a redirect URI `https://seu-dominio/auth/google/callback` e preencha `VEU_GOOGLE_CLIENT_ID`, `VEU_GOOGLE_CLIENT_SECRET` e `VEU_AUTH_GOOGLE_EMAILS`.

---

## Véu Host

A extensão liga o SO web à máquina física: shell, arquivos, SSH e apps nativos via Native Messaging.

1. Em `chrome://extensions`, ative o modo desenvolvedor e use **Carregar sem compactação** na pasta `extension/`.
2. Copie o **ID** da extensão.
3. Instale o native host:
   - Windows: `extension\native\install.ps1 -ExtensionId <ID>`
   - Linux/macOS: `extension/native/install.sh <ID>`
4. Recarregue o Véu. A barra do topo deve mostrar `host · ok`.

Mais em [`extension/README.md`](../extension/README.md).

---

## Placa ESP32

Painel físico touch para a placa **ESP32-2432S028R** ("Cheap Yellow Display").

```bash
cd device/esp32-cyd
pio run -e cyd -t upload
```

Emparelhamento: no Véu, abra o app **Placa** e gere um token. Na placa, conecte-se ao AP `veu-placa`, abra `http://192.168.4.1` e informe a URL do Véu e o token. Guia completo em [`device/esp32-cyd/README.md`](../device/esp32-cyd/README.md).

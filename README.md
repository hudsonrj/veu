# Véu

Sistema operacional administrado por IA — Windows · Linux.

Projeto **independente** (não vive dentro de outro repo).

| Onde | Pasta |
|------|--------|
| Desenvolvimento | `/home/ubuntu/veu` |
| Servidor | `/root/veu` |
| GitHub | https://github.com/hudsonrj/veu |

Chat nativo. Construção e execução em tempo real. Nervos para WhatsApp, Teams, Outlook, Gmail, Google Chat, Notion, MCP e APIs. Musculatura [ECC](https://github.com/hudsonrj/ECC).

## No ar

- Desktop: http://169.58.19.232:8820  
- Kernel: http://169.58.19.232:8821/pulse  

## Desktop

```bash
cd desktop
npm install
npm run dev
```

Opcional: `VITE_VEU_KERNEL=http://127.0.0.1:8821`

## Kernel

```bash
cd engine
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/veu serve --host 127.0.0.1 --port 8821
```

APIs: `GET /pulse` · `GET /connectors` · `POST /weave` · `POST /chat` (SSE)

## ECC

```bash
git clone https://github.com/hudsonrj/ECC.git vendor/ecc
export VEU_ECC_ROOT=$PWD/vendor/ecc
```

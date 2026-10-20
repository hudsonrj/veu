# Véu · desktop

A pele do Véu: um SO web em **React 19 + Vite + framer-motion**. Tem janelas arrastáveis, dock, ícones em zonas, campo vivo animado, chat nativo e o painel **hoje**.

![Desktop](../docs/screenshots/desktop.png)

## Rodar

```bash
npm install
VITE_VEU_KERNEL=http://localhost:8821 npm run dev   # http://localhost:5173
npm run build                                       # gera dist/
npm run lint                                        # oxlint
```

`VITE_VEU_KERNEL` aponta para o kernel. Vazio = mesma origem (produção atrás do Caddy).

## Mapa do código

| Pasta | Conteúdo |
|---|---|
| `src/os/` | Shell do SO: `TopBar`, `Dock`, `WindowFrame`, `DesktopIcons`, `DayRail`, `CommandBar`, `LoginGate` |
| `src/os/apps/` | Apps do SO: Chat, Missão, Ajustes, Servidores, Inbox, Notion, OpenRAG, Grok Bot, Placa… |
| `src/components/` | Campo vivo (`LivingField`), chat (`NativeChat`), execução ao vivo (`LiveExecution`), órbita de autonomia |
| `src/lib/` | Cliente do kernel, SSE (`stream.ts`), fallback local (`weave.ts`) |
| `src/bridge/` | Ponte com a extensão Véu Host |
| `public/` | PWA (manifest, service worker), ícones, instalador do Véu Host |

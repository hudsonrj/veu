import { useCallback, useEffect, useMemo, useState } from "react";
import { LivingField } from "./components/LivingField";
import { EcosystemStage } from "./components/EcosystemStage";
import type { AutonomyBreath } from "./components/AutonomyOrbit";
import { useViewport } from "./hooks/useViewport";
import { isCompactMode } from "./lib/viewport";
import { TopBar } from "./os/TopBar";
import { DesktopIcons } from "./os/DesktopIcons";
import { AppsShelf } from "./os/AppsShelf";
import { DayRail } from "./os/DayRail";
import { Dock } from "./os/Dock";
import { CompactChrome } from "./os/CompactChrome";
import { WindowFrame } from "./os/WindowFrame";
import { ChatApp } from "./os/apps/ChatApp";
import { MissionControlApp } from "./os/apps/MissionControlApp";
import { GrokBotApp } from "./os/apps/GrokBotApp";
import { HostApp } from "./os/apps/HostApp";
import { WhatsAppApp } from "./os/apps/WhatsAppApp";
import { NerveApp } from "./os/apps/NerveApp";
import { FilesApp } from "./os/apps/FilesApp";
import { EditorApp } from "./os/apps/EditorApp";
import { VscodeApp } from "./os/apps/VscodeApp";
import { ReaApp } from "./os/apps/ReaApp";
import { Esp32App } from "./os/apps/Esp32App";
import { SettingsApp } from "./os/apps/SettingsApp";
import { EccApp } from "./os/apps/EccApp";
import { AiChatApp } from "./os/apps/AiChatApp";
import { PlaygroundApp } from "./os/apps/PlaygroundApp";
import { HermesApp } from "./os/apps/HermesApp";
import { AgendaApp } from "./os/apps/AgendaApp";
import { CompaniesApp } from "./os/apps/CompaniesApp";
import { ServersApp } from "./os/apps/ServersApp";
import { StudioApp } from "./os/apps/StudioApp";
import { OpenRagApp } from "./os/apps/OpenRagApp";
import { NotionApp } from "./os/apps/NotionApp";
import { McpApp } from "./os/apps/McpApp";
import { UsageApp } from "./os/apps/UsageApp";
import { BillingApp } from "./os/apps/BillingApp";
import { ProjectsApp } from "./os/apps/ProjectsApp";
import { CredentialsApp } from "./os/apps/CredentialsApp";
import { ControlCenterApp } from "./os/apps/ControlCenterApp";
import { DataApp } from "./os/apps/DataApp";
import { ApprovalsApp } from "./os/apps/ApprovalsApp";
import { AskLifeApp } from "./os/apps/AskLifeApp";
import { InboxApp } from "./os/apps/InboxApp";
import { DecisionsApp } from "./os/apps/DecisionsApp";
import { RoutinesApp } from "./os/apps/RoutinesApp";
import { WorkspaceApp } from "./os/apps/WorkspaceApp";
import { ProductivityApp } from "./os/apps/ProductivityApp";
import { CloneApp } from "./os/apps/CloneApp";
import { MentalHealthApp } from "./os/apps/MentalHealthApp";
import { RuosDesktopApp } from "./os/apps/RuosDesktopApp";
import { BrowserApp } from "./os/apps/BrowserApp";
import { ConsoleApp, type ConsoleSeed } from "./os/apps/ConsoleApp";
import { RegistroApp } from "./os/apps/RegistroApp";
import { ToGoApp } from "./os/apps/ToGoApp";
import { APP_TITLES, defaultGeom } from "./os/catalog";
import { hasPermission } from "./os/appManifest";
import type { OsWindow, WinApp } from "./os/types";
import { probeBridge, type BridgeInfo } from "./bridge/hostBridge";
import { apiFetch, KERNEL, probeKernel, type KernelPulse } from "./lib/kernel";
import {
  VEU_OPEN_URL_EVENT,
  type VeuOpenUrlDetail,
} from "./lib/openUrl";
import {
  activateWorkspace,
  saveWorkspace,
  windowsFromWorkspace,
} from "./lib/workspaces";
import { LoginGate } from "./os/LoginGate";
import { CommandBar } from "./os/CommandBar";
import { VoiceMic } from "./os/VoiceMic";
import { QuickCapture } from "./os/QuickCapture";

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export default function App() {
  return (
    <LoginGate>
      <OsShell />
    </LoginGate>
  );
}

function OsShell() {
  const [breath, setBreath] = useState<AutonomyBreath>("guided");
  const [windows, setWindows] = useState<OsWindow[]>(() => {
    const g = defaultGeom("ruos", 0);
    return [
      {
        id: "boot-veu",
        app: "ruos",
        title: APP_TITLES.ruos,
        ...g,
        z: 10,
        minimized: false,
      },
    ];
  });
  const [zTop, setZTop] = useState(10);
  const [bridge, setBridge] = useState<BridgeInfo>({
    status: "missing",
    capabilities: [],
    message: "detectando extensão…",
  });
  const [kernel, setKernel] = useState<KernelPulse>({ ok: false, error: "…" });
  const [clock, setClock] = useState("");
  const [seedIntent, setSeedIntent] = useState<string | null>(null);
  const [consoleSeed, setConsoleSeed] = useState<ConsoleSeed | null>(null);
  const [browserSeed, setBrowserSeed] = useState<string | null>(null);
  const [browserSeedTitle, setBrowserSeedTitle] = useState<string | null>(null);
  const [browserSeedKey, setBrowserSeedKey] = useState(0);
  const [activeCompany, setActiveCompany] = useState<string | null>(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [mobileApp, setMobileApp] = useState<WinApp>("ruos");
  const [dayOpen, setDayOpen] = useState(false);

  const setBreathAndMaybeOpen = useCallback((b: AutonomyBreath) => {
    setBreath(b);
    if (b !== "autonomous") return;
    setMobileApp("productivity");
    setZTop((z) => {
      const nextZ = z + 1;
      setWindows((prev) => {
        const existing = prev.find((w) => w.app === "productivity");
        if (existing) {
          return prev.map((w) =>
            w.id === existing.id ? { ...w, z: nextZ, minimized: false } : w,
          );
        }
        const g = defaultGeom("productivity", prev.length);
        return [
          ...prev,
          {
            id: uid(),
            app: "productivity" as WinApp,
            title: APP_TITLES.productivity,
            ...g,
            z: nextZ,
            minimized: false,
          },
        ];
      });
      return nextZ;
    });
  }, []);
  const { mode } = useViewport();
  const compact = isCompactMode(mode);

  useEffect(() => {
    const refreshBridge = () => {
      void probeBridge(1800).then(setBridge);
    };
    const refreshKernel = () => {
      void probeKernel().then(setKernel);
    };
    refreshBridge();
    refreshKernel();
    // re-probe: extensão pode injetar depois do boot / após reload
    const bridgeId = window.setInterval(refreshBridge, 12_000);
    const kernelId = window.setInterval(refreshKernel, 20_000);
    const tick = () =>
      setClock(
        new Date().toLocaleTimeString("pt-BR", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      );
    tick();
    const id = window.setInterval(tick, 15_000);
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "n") {
        e.preventDefault();
        setCaptureOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearInterval(id);
      window.clearInterval(kernelId);
      window.clearInterval(bridgeId);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  // tablet: fecha drawer ao mudar de app; desktop não usa drawer
  useEffect(() => {
    if (mode !== "tablet") setDayOpen(false);
  }, [mode, mobileApp]);

  const openApp = useCallback((app: WinApp) => {
    if (app !== "control") {
      const perm = hasPermission(app);
      if (!perm.ok) {
        window.alert(
          `Sem permissão para abrir «${APP_TITLES[app]}».\nFalta: ${perm.missing.join(", ")}\nConceda na Central de controle.`,
        );
        // abre controle sem recursão
        setMobileApp("control");
        return;
      }
    }
    setMobileApp(app);
    setZTop((z) => {
      const nextZ = z + 1;
      setWindows((prev) => {
        const existing = prev.find((w) => w.app === app && !w.minimized);
        if (existing) {
          return prev.map((w) =>
            w.id === existing.id ? { ...w, z: nextZ, minimized: false } : w,
          );
        }
        const minimized = prev.find((w) => w.app === app && w.minimized);
        if (minimized) {
          return prev.map((w) =>
            w.id === minimized.id
              ? { ...w, minimized: false, z: nextZ }
              : w,
          );
        }
        const g = defaultGeom(app, prev.length);
        return [
          ...prev,
          {
            id: uid(),
            app,
            title: APP_TITLES[app],
            ...g,
            z: nextZ,
            minimized: false,
          },
        ];
      });
      return nextZ;
    });
  }, []);

  /** Abre URL como aba no Browser do SO (não Chrome externo). */
  const openUrlInOs = useCallback(
    (url: string, title?: string) => {
      if (!url) return;
      setBrowserSeed(url);
      setBrowserSeedTitle(title || null);
      setBrowserSeedKey((k) => k + 1);
      openApp("browser");
    },
    [openApp],
  );

  useEffect(() => {
    const onOpen = (ev: Event) => {
      const detail = (ev as CustomEvent<VeuOpenUrlDetail>).detail;
      if (!detail?.url) return;
      openUrlInOs(detail.url, detail.title);
    };
    window.addEventListener(VEU_OPEN_URL_EVENT, onOpen);
    return () => window.removeEventListener(VEU_OPEN_URL_EVENT, onOpen);
  }, [openUrlInOs]);

  const restoreWorkspace = useCallback(async (wsId: string) => {
    const res = await activateWorkspace(wsId);
    if (!res.ok || !res.workspace) {
      window.alert(res.error || "workspace não encontrado");
      return;
    }
    const next = windowsFromWorkspace(res.workspace, uid);
    const maxZ = next.reduce((m, w) => Math.max(m, w.z), 10);
    setWindows((prev) => (next.length ? next : prev));
    setZTop(maxZ);
    setActiveCompany(res.workspace.company || res.workspace.name || null);
    if (next[0]) setMobileApp(next[0].app);
  }, []);

  const persistWorkspace = useCallback(
    async (name: string) => {
      const res = await saveWorkspace({
        name,
        windows,
        company: activeCompany || undefined,
      });
      if (!res.ok) {
        window.alert(res.error || "falha ao salvar workspace");
        return;
      }
      setActiveCompany(res.workspace?.company || name);
      window.alert(`Workspace «${res.workspace?.name || name}» salvo`);
    },
    [windows, activeCompany],
  );

  const launchIntent = useCallback(
    (intent: string, opts?: { breath?: AutonomyBreath }) => {
      if (opts?.breath) setBreath(opts.breath);
      setSeedIntent(intent);
      openApp("chat");
    },
    [openApp],
  );

  const focus = useCallback(
    (id: string) => {
      const z = zTop + 1;
      setZTop(z);
      setWindows((prev) => prev.map((w) => (w.id === id ? { ...w, z } : w)));
    },
    [zTop],
  );

  const close = useCallback((id: string) => {
    setWindows((prev) => prev.filter((w) => w.id !== id));
  }, []);

  const minimize = useCallback((id: string) => {
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, minimized: true } : w)),
    );
  }, []);

  const restore = useCallback(
    (id: string) => {
      const z = zTop + 1;
      setZTop(z);
      setWindows((prev) =>
        prev.map((w) => (w.id === id ? { ...w, minimized: false, z } : w)),
      );
    },
    [zTop],
  );

  const move = useCallback((id: string, x: number, y: number) => {
    setWindows((prev) => prev.map((w) => (w.id === id ? { ...w, x, y } : w)));
  }, []);

  const resize = useCallback(
    (id: string, geom: { x: number; y: number; w: number; h: number }) => {
      setWindows((prev) =>
        prev.map((w) => (w.id === id ? { ...w, ...geom } : w)),
      );
    },
    [],
  );

  const ecoOpen = useMemo(
    () => windows.some((w) => w.app === "ecosystem" && !w.minimized),
    [windows],
  );

  const renderBody = (app: WinApp) => {
    if (app === "ruflo" || app === "ruos") {
      return (
        <RuosDesktopApp
          initialTab={app === "ruflo" ? "ruflo" : "desktops"}
          onOpenBrowser={(url) => {
            if (url) openUrlInOs(url);
            else openApp("browser");
          }}
          onOpenConsole={(seed) => {
            setConsoleSeed(seed || { mode: "ai" });
            openApp("console");
          }}
          onOpenApp={(id) => {
            const known = id as WinApp;
            openApp(known);
          }}
        />
      );
    }
    if (app === "console") {
      return (
        <ConsoleApp
          seed={consoleSeed}
          onSeedConsumed={() => setConsoleSeed(null)}
          onOpenBrowser={(url) => {
            if (url) openUrlInOs(url);
            else openApp("browser");
          }}
          onOpenApp={(id) => openApp(id as WinApp)}
        />
      );
    }
    if (app === "registro") {
      return (
        <RegistroApp
          breath={breath}
          onOpenJobReport={(jobId) => {
            void apiFetch(`${KERNEL}/jobs/${jobId}/report?format=md`)
              .then(async (r) => {
                if (!r.ok) return;
                const md = await r.text();
                const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `veu-job-${jobId}.md`;
                a.click();
                URL.revokeObjectURL(a.href);
              })
              .catch(() => undefined);
          }}
        />
      );
    }
    if (app === "browser") {
      return (
        <BrowserApp
          seedUrl={browserSeed}
          seedTitle={browserSeedTitle}
          seedTabKey={browserSeedKey}
          company={activeCompany}
          onSeedConsumed={() => {
            setBrowserSeed(null);
            setBrowserSeedTitle(null);
          }}
          onOpenApp={(id) => openApp(id as WinApp)}
        />
      );
    }
    if (app === "mission") {
      return (
        <MissionControlApp
          onLaunch={launchIntent}
          onOpenRegistro={() => openApp("registro")}
          onOpenAgent={(agentId) =>
            launchIntent(
              `ative o agente ${agentId} e execute a próxima ação útil para o Véu`,
              { breath: "semi" },
            )
          }
        />
      );
    }
    if (app === "chat") {
      return (
        <ChatApp
          breath={breath}
          seedIntent={seedIntent}
          onSeedConsumed={() => setSeedIntent(null)}
        />
      );
    }
    if (app === "ecosystem")
      return (
        <div style={{ padding: "0.75rem" }}>
          <EcosystemStage />
        </div>
      );
    if (app === "grokbot") return <GrokBotApp />;
    if (app === "hermes") return <HermesApp />;
    if (app === "agenda") return <AgendaApp />;
    if (app === "companies") return <CompaniesApp />;
    if (app === "servers")
      return (
        <ServersApp
          onOpenConsole={(seed) => {
            setConsoleSeed(seed);
            openApp("console");
          }}
        />
      );
    if (app === "studio") return <StudioApp />;
    if (app === "ecc") {
      return (
        <EccApp
          onUse={(intent) => launchIntent(intent, { breath: "semi" })}
        />
      );
    }
    if (app === "playground") return <PlaygroundApp />;
    if (app === "chatgpt") return <AiChatApp surface="chatgpt" />;
    if (app === "claudeai") return <AiChatApp surface="claude" />;
    if (app === "grok") return <AiChatApp surface="grok" />;
    if (app === "codex") return <AiChatApp surface="codex" />;
    if (app === "claudework") return <AiChatApp surface="claude-work" />;
    if (app === "host") return <HostApp />;
    if (app === "files") return <FilesApp />;
    if (app === "editor") return <EditorApp />;
    if (app === "vscode") return <VscodeApp />;
    if (app === "rea") return <ReaApp />;
    if (app === "esp32") return <Esp32App />;
    if (app === "whatsapp") return <WhatsAppApp />;
    if (app === "openrag") return <OpenRagApp />;
    if (app === "asklife") return <AskLifeApp seed={seedIntent} />;
    if (app === "usage") return <UsageApp />;
    if (app === "billing") return <BillingApp />;
    if (app === "projects") return <ProjectsApp />;
    if (app === "control")
      return <ControlCenterApp onBreath={setBreathAndMaybeOpen} />;
    if (app === "togo") return <ToGoApp />;
    if (app === "credentials") return <CredentialsApp />;
    if (app === "approvals") return <ApprovalsApp />;
    if (app === "inbox") return <InboxApp />;
    if (app === "decisions") return <DecisionsApp />;
    if (app === "productivity") return <ProductivityApp breath={breath} />;
    if (app === "clone") return <CloneApp />;
    if (app === "mental") return <MentalHealthApp />;
    if (app === "routines") return <RoutinesApp />;
    if (app === "notion") return <NotionApp />;
    if (app === "mcp") return <McpApp />;
    if (app === "google") return <WorkspaceApp />;
    if (app === "gmail") return <WorkspaceApp />;
    if (app === "settings") return (
      <SettingsApp breath={breath} onBreath={setBreathAndMaybeOpen} />
    );
    if (app === "data") return <DataApp />;
    return <NerveApp app={app} />;
  };

  return (
    <div className={`os os--${mode}${compact ? " os--compact" : ""}`}>
      <LivingField
        intensity={
          kernel.ok ? (bridge.status === "connected" ? 1.05 : 0.95) : 0.7
        }
      />
      <div className="os__veil" />

      <TopBar
        breath={breath}
        onBreath={setBreathAndMaybeOpen}
        ecoOpen={ecoOpen}
        onToggleEco={() => openApp("ecosystem")}
        bridge={bridge}
        kernel={kernel}
        clock={clock}
        compact={compact}
        onOpenControl={() => openApp("control")}
      />

      <div className="os__desktop">
        {mode === "desktop" ? (
          <>
            <DesktopIcons onOpen={openApp} onOpenUrl={openUrlInOs} />
            <AppsShelf onOpen={openApp} onOpenUrl={openUrlInOs} />
          </>
        ) : null}
        {mode === "desktop" ? (
          <DayRail
            onOpenGrok={() => openApp("grokbot")}
            onOpenCompanies={() => openApp("companies")}
            onOpenServers={() => openApp("servers")}
          />
        ) : null}

        {compact ? (
          <div className="os__surface">
            <CompactChrome
              active={mobileApp}
              onOpen={openApp}
              title={APP_TITLES[mobileApp] || mobileApp}
              showDayToggle={mode === "tablet"}
              dayOpen={dayOpen}
              onToggleDay={() => setDayOpen((v) => !v)}
            />
            {renderBody(mobileApp)}
          </div>
        ) : (
          windows.map((w) => (
            <WindowFrame
              key={w.id}
              win={w}
              onFocus={focus}
              onClose={close}
              onMinimize={minimize}
              onMove={move}
              onResize={resize}
            >
              {renderBody(w.app)}
            </WindowFrame>
          ))
        )}

        {mode === "tablet" ? (
          <div className={`os__rail-drawer${dayOpen ? " is-open" : ""}`}>
            <DayRail
              onOpenGrok={() => {
                openApp("grokbot");
                setDayOpen(false);
              }}
              onOpenCompanies={() => {
                openApp("companies");
                setDayOpen(false);
              }}
              onOpenServers={() => {
                openApp("servers");
                setDayOpen(false);
              }}
            />
          </div>
        ) : null}
      </div>

      <div className="os__footer">
        <VoiceMic
          breath={breath}
          onText={(text) => {
            openApp("chat");
            setSeedIntent(text);
          }}
        />
        <Dock
          windows={windows}
          onOpen={openApp}
          onFocus={focus}
          onRestore={restore}
          compact={compact}
          activeApp={compact ? mobileApp : undefined}
        />
      </div>

      <CommandBar
        open={cmdOpen}
        onClose={() => setCmdOpen(false)}
        onOpenApp={openApp}
        onSaveWorkspace={(name) => void persistWorkspace(name)}
        onRestoreWorkspace={(id) => void restoreWorkspace(id)}
        onIntent={(intent) => {
          if (intent.startsWith("life:")) {
            openApp("asklife");
            setSeedIntent(intent);
            return;
          }
          openApp("chat");
          setSeedIntent(intent);
        }}
      />

      <QuickCapture
        open={captureOpen}
        onClose={() => setCaptureOpen(false)}
        breath={breath}
      />

      {compact ? (
        <button
          type="button"
          className="os__capture-fab"
          aria-label="captura rápida"
          onClick={() => setCaptureOpen(true)}
        >
          ✎
        </button>
      ) : null}

      <style>{`
        .os__veil {
          pointer-events: none;
          position: absolute;
          inset: 0;
          z-index: 1;
          background:
            radial-gradient(90% 70% at 50% 100%, rgba(7,9,12,0.75), transparent 55%),
            radial-gradient(60% 40% at 80% 0%, rgba(7,9,12,0.35), transparent 50%);
        }
        .os > :not(.living-field):not(.os__veil) { position: relative; z-index: 2; }
        .os--compact .win { display: none !important; }
        .os__capture-fab {
          position: fixed;
          right: max(0.75rem, env(safe-area-inset-right));
          bottom: calc(var(--veu-dock-h, 4.25rem) + env(safe-area-inset-bottom, 0px) + 0.5rem);
          z-index: 70;
          width: 2.85rem;
          height: 2.85rem;
          border: 1px solid rgba(232,194,122,0.4);
          border-radius: 0.45rem;
          background: rgba(10,12,16,0.92);
          color: #e8c27a;
          font-size: 1.1rem;
          cursor: pointer;
        }
      `}</style>
    </div>
  );
}

#!/usr/bin/env python3
"""Véu Native Messaging host — com.veu.host

Lê mensagens length-prefixed (Chrome) e abre apps / shell básico.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path


def read_msg() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if not raw or len(raw) < 4:
        return None
    (n,) = struct.unpack("<I", raw)
    data = sys.stdin.buffer.read(n)
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


def write_msg(msg: dict) -> None:
    blob = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(blob)))
    sys.stdout.buffer.write(blob)
    sys.stdout.buffer.flush()


def open_terminal() -> dict:
    if sys.platform.startswith("win"):
        for cmd in (
            ["wt.exe"],
            ["powershell.exe", "-NoExit"],
            ["cmd.exe"],
        ):
            try:
                subprocess.Popen(
                    cmd,
                    close_fds=True,
                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                )
                return {"ok": True, "data": {"opened": cmd[0], "mode": "native"}}
            except FileNotFoundError:
                continue
        return {"ok": False, "error": "nenhum terminal encontrado (wt/powershell/cmd)"}

    # Linux / macOS
    candidates = [
        ["x-terminal-emulator"],
        ["gnome-terminal"],
        ["konsole"],
        ["xfce4-terminal"],
        ["alacritty"],
        ["kitty"],
        ["xterm"],
        ["open", "-a", "Terminal"],  # macOS
    ]
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, start_new_session=True)
            return {"ok": True, "data": {"opened": " ".join(cmd), "mode": "native"}}
        except FileNotFoundError:
            continue
    return {"ok": False, "error": "nenhum emulador de terminal encontrado"}


def open_explorer(path: str | None = None) -> dict:
    target = Path(path).expanduser() if path else Path.home()
    try:
        target = target.resolve()
    except Exception:
        target = Path.home()
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer.exe", str(target)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return {"ok": True, "data": {"opened": str(target), "mode": "explorer"}}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def open_app(app: str) -> dict:
    app = (app or "").lower().strip()
    if app in ("terminal", "shell", "console"):
        return open_terminal()
    if app in ("explorer", "files", "finder", "arquivos"):
        return open_explorer()

    urls = {
        "whatsapp": "https://web.whatsapp.com/",
        "gmail": "https://mail.google.com/",
        "calendar": "https://calendar.google.com/",
        "agenda": "https://calendar.google.com/",
        "notion": "https://www.notion.so/",
        "teams": "https://teams.microsoft.com/",
        "outlook": "https://outlook.office.com/",
        "slack": "https://app.slack.com/",
        "grok": "https://grok.com/",
        "chatgpt": "https://chatgpt.com/",
        "claude": "https://claude.ai/new",
    }
    url = urls.get(app)
    if url:
        if sys.platform.startswith("win"):
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        return {"ok": True, "data": {"opened": url, "mode": "native-url"}}

    return {"ok": False, "error": f'app desconhecido: "{app}"'}


# Presets seguros — não precisam de VEU_HOST_ALLOW_SHELL
SAFE_PRESETS: dict[str, str] = {
    "whoami": "whoami" if not sys.platform.startswith("win") else "whoami",
    "date": "date" if not sys.platform.startswith("win") else "powershell -NoProfile -Command Get-Date",
    "pwd": "pwd" if not sys.platform.startswith("win") else "cd",
}


def list_open_apps() -> dict:
    """Lista processos/janelas relevantes no host (heurístico, sem senha)."""
    try:
        if sys.platform.startswith("win"):
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-Process | Where-Object { $_.MainWindowTitle } | "
                    "Select-Object -First 40 ProcessName, MainWindowTitle | "
                    "ForEach-Object { \"$($_.ProcessName) — $($_.MainWindowTitle)\" }",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            out = (proc.stdout or "").strip()
        elif sys.platform == "darwin":
            proc = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of every process whose background only is false',
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            out = (proc.stdout or "").strip()
        else:
            # Linux: janelas via wmctrl se existir; senão processos com tty/gui comuns
            if subprocess.run(["which", "wmctrl"], capture_output=True).returncode == 0:
                proc = subprocess.run(
                    ["wmctrl", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                out = (proc.stdout or "").strip()
            else:
                proc = subprocess.run(
                    ["ps", "-eo", "comm="],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                names = sorted(
                    {
                        n.strip()
                        for n in (proc.stdout or "").splitlines()
                        if n.strip()
                        and n.strip().lower()
                        in {
                            "chrome",
                            "chromium",
                            "firefox",
                            "code",
                            "slack",
                            "spotify",
                            "telegram",
                            "discord",
                            "nautilus",
                            "dolphin",
                            "gnome-terminal",
                            "kitty",
                            "alacritty",
                            "teams",
                            "outlook",
                        }
                    }
                )
                out = "\n".join(names) if names else (proc.stdout or "")[:2000]
        if not out:
            return {"ok": True, "data": {"preset": "apps-open", "stdout": "(nenhum processo/janela listado)", "items": []}}
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()][:40]
        return {
            "ok": True,
            "data": {
                "preset": "apps-open",
                "stdout": "\n".join(lines),
                "items": lines,
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_preset(preset: str) -> dict:
    key = (preset or "").lower().strip()
    if key in ("terminal", "open-terminal"):
        return open_terminal()
    if key in ("explorer", "files", "home"):
        return open_explorer()
    if key in ("gmail", "notion", "calendar", "agenda", "slack", "outlook", "grok", "whatsapp", "teams", "chatgpt"):
        return open_app(key)
    if key == "home-list":
        return list_dir(str(Path.home()))
    if key in ("apps-open", "list-apps", "open-apps"):
        return list_open_apps()
    cmd = SAFE_PRESETS.get(key)
    if not cmd:
        return {
            "ok": False,
            "error": f'preset desconhecido: "{preset}" — use whoami|date|pwd|terminal|explorer|apps-open|gmail|…',
        }
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return {
            "ok": proc.returncode == 0,
            "data": {
                "preset": key,
                "code": proc.returncode,
                "stdout": (proc.stdout or "")[:4000],
                "stderr": (proc.stderr or "")[:2000],
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_dir(path: str | None) -> dict:
    raw = (path or "").strip() or "."
    if raw in (".", "~", "$HOME", "%USERPROFILE%"):
        target = Path.home()
    else:
        target = Path(raw).expanduser()
    try:
        target = target.resolve()
    except Exception as e:
        return {"ok": False, "error": f"caminho inválido: {e}"}
    if not target.exists():
        return {"ok": False, "error": f"não existe: {target}"}
    if not target.is_dir():
        return {"ok": False, "error": f"não é pasta: {target}"}
    entries: list[dict] = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith("."):
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "type": "dir" if child.is_dir() else "file",
                    "is_dir": child.is_dir(),
                }
            )
            if len(entries) >= 80:
                break
    except PermissionError:
        return {"ok": False, "error": f"sem permissão: {target}"}
    return {"ok": True, "data": {"path": str(target), "entries": entries}}


def read_path(path: str | None) -> dict:
    if not path or not str(path).strip():
        return {"ok": False, "error": "path vazio"}
    target = Path(str(path)).expanduser()
    try:
        target = target.resolve()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not target.is_file():
        return {"ok": False, "error": f"não é arquivo: {target}"}
    if target.stat().st_size > 200_000:
        return {"ok": False, "error": "arquivo > 200KB — recusado"}
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "data": {"path": str(target), "text": text[:12000], "bytes": target.stat().st_size},
    }


def run_shell(command: str, cwd: str | None = None) -> dict:
    if not command or not command.strip():
        return {"ok": False, "error": "command vazio"}
    # Conservador: só permite se VEU_HOST_ALLOW_SHELL=1
    if os.environ.get("VEU_HOST_ALLOW_SHELL") != "1":
        return {
            "ok": False,
            "error": "shell desabilitado — exporte VEU_HOST_ALLOW_SHELL=1 no host",
        }
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "ok": proc.returncode == 0,
            "data": {
                "code": proc.returncode,
                "stdout": (proc.stdout or "")[:8000],
                "stderr": (proc.stderr or "")[:4000],
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main() -> int:
    while True:
        msg = read_msg()
        if msg is None:
            return 0
        typ = msg.get("type") or ""
        if typ in ("veu.host.info", "veu.ping", "ping"):
            write_msg(
                {
                    "ok": True,
                    "data": {
                        "version": "0.3.5",
                        "native": True,
                        "platform": sys.platform,
                        "host": str(Path(__file__).resolve()),
                        "presets": sorted(
                            set(SAFE_PRESETS)
                            | {
                                "terminal",
                                "explorer",
                                "home-list",
                                "apps-open",
                                "gmail",
                                "notion",
                                "calendar",
                                "slack",
                                "outlook",
                                "whatsapp",
                                "grok",
                            }
                        ),
                    },
                }
            )
        elif typ == "veu.host.openApp":
            write_msg(open_app(str(msg.get("app") or "")))
        elif typ == "veu.host.listDir":
            write_msg(list_dir(msg.get("path")))
        elif typ == "veu.host.readPath":
            write_msg(read_path(msg.get("path")))
        elif typ == "veu.host.shell":
            write_msg(run_shell(str(msg.get("command") or ""), msg.get("cwd")))
        elif typ == "veu.host.runPreset":
            write_msg(run_preset(str(msg.get("preset") or "")))
        else:
            write_msg({"ok": False, "error": f"tipo não suportado: {typ}"})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)

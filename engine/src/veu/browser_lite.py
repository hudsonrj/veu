"""Véu Lite — Chrome real (CDP) na janela do SO (padrão ruOS Lite).

Usa /json/new + websocket da *página* (não Target.attach), que é o caminho
estável no alpine-chrome / HeadlessChrome do host.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from typing import Any
from urllib.parse import quote

import httpx

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore

CDP_HTTP = os.environ.get("VEU_LITE_CDP", "http://127.0.0.1:9337").rstrip("/")
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_lock = threading.Lock()
_sessions: dict[str, "LiteSession"] = {}


def _open_page(url: str) -> dict[str, Any]:
    """Cria aba via HTTP PUT /json/new?url=…"""
    # Chrome exige PUT; alguns aceitam GET com aviso
    endpoint = f"{CDP_HTTP}/json/new?{quote(url, safe='')}"
    try:
        r = httpx.put(endpoint, timeout=10)
        if r.status_code >= 400:
            r = httpx.get(endpoint, timeout=10)
    except Exception:
        r = httpx.get(endpoint, timeout=10)
    r.raise_for_status()
    return r.json()


class CdpPage:
    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self._n = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._on_screencast: Any = None
        self._reader: asyncio.Task | None = None

    def start(self) -> None:
        self._reader = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass

    async def _read_loop(self) -> None:
        while True:
            raw = json.loads(await self.ws.recv())
            if "id" in raw and raw["id"] in self._pending:
                fut = self._pending.pop(raw["id"])
                if not fut.done():
                    if "error" in raw:
                        fut.set_exception(RuntimeError(str(raw["error"])))
                    else:
                        fut.set_result(raw.get("result") or {})
                continue
            if raw.get("method") == "Page.screencastFrame" and self._on_screencast:
                await self._on_screencast(raw.get("params") or {})

    async def call(self, method: str, params: dict | None = None) -> dict:
        self._n += 1
        nid = self._n
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[nid] = fut
        await self.ws.send(
            json.dumps({"id": nid, "method": method, "params": params or {}})
        )
        return await asyncio.wait_for(fut, timeout=45)


class LiteSession:
    def __init__(self, sid: str, url: str) -> None:
        self.id = sid
        self.url = url
        self.width = 1100
        self.height = 720
        self.frame_jpeg: bytes | None = None
        self.frame_ts = 0.0
        self.error: str | None = None
        self.ready = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._input_q: asyncio.Queue | None = None
        self.page_id: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"veu-lite-{self.id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        q = self._input_q
        if loop and q is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: q.put_nowait({"type": "_stop"}))
        # close page via HTTP
        if self.page_id:
            try:
                httpx.get(f"{CDP_HTTP}/json/close/{self.page_id}", timeout=3)
            except Exception:  # noqa: BLE001
                pass

    def enqueue_input(self, ev: dict[str, Any]) -> None:
        loop = self._loop
        q = self._input_q
        if loop and q is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: q.put_nowait(ev))

    def _run(self) -> None:
        if websockets is None:
            self.error = "websockets não instalado no kernel"
            return
        try:
            asyncio.run(self._async_main())
        except Exception as e:  # noqa: BLE001
            self.error = str(e)

    async def _async_main(self) -> None:
        assert websockets is not None
        self._loop = asyncio.get_running_loop()
        self._input_q = asyncio.Queue()

        info = _open_page(self.url)
        self.page_id = str(info.get("id") or "")
        page_ws = str(info.get("webSocketDebuggerUrl") or "")
        if not page_ws:
            raise RuntimeError(f"sem webSocketDebuggerUrl: {info}")
        page_ws = page_ws.replace(":9222/", ":9337/")

        async with websockets.connect(page_ws, max_size=40_000_000) as ws:
            cdp = CdpPage(ws)
            cdp.start()

            await cdp.call("Page.enable")
            await cdp.call("Runtime.enable")
            await cdp.call("Network.enable")
            await cdp.call(
                "Emulation.setUserAgentOverride",
                {
                    "userAgent": DEFAULT_UA,
                    "platform": "Linux",
                    "userAgentMetadata": {
                        "brands": [
                            {"brand": "Not-A.Brand", "version": "99"},
                            {"brand": "Chromium", "version": "124"},
                            {"brand": "Google Chrome", "version": "124"},
                        ],
                        "fullVersion": "124.0.6367.78",
                        "platform": "Linux",
                        "platformVersion": "6.8.0",
                        "architecture": "x86",
                        "model": "",
                        "mobile": False,
                    },
                },
            )
            await cdp.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": self.width,
                    "height": self.height,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            await cdp.call(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": (
                        "Object.defineProperty(navigator,'webdriver',"
                        "{get:()=>undefined});"
                        "window.chrome=window.chrome||{runtime:{}};"
                    )
                },
            )
            await cdp.call("Page.navigate", {"url": self.url})
            self.ready = True

            while not self._stop.is_set():
                # JPEG ~2fps — suficiente pro QR; sem screencast (mais estável)
                try:
                    shot = await cdp.call(
                        "Page.captureScreenshot",
                        {"format": "jpeg", "quality": 70},
                    )
                    data = shot.get("data")
                    if data:
                        self.frame_jpeg = base64.b64decode(data)
                        self.frame_ts = time.time()
                except Exception:  # noqa: BLE001
                    pass
                # processar cliques entre frames
                try:
                    while True:
                        ev = self._input_q.get_nowait()
                        if ev.get("type") == "_stop":
                            self._stop.set()
                            break
                        await self._handle_input(cdp, ev)
                except asyncio.QueueEmpty:
                    pass
                await asyncio.sleep(0.45)

            await cdp.close()

    async def _handle_input(self, cdp: CdpPage, ev: dict) -> None:
        kind = ev.get("type")
        if kind == "click":
            x = float(ev.get("x") or 0)
            y = float(ev.get("y") or 0)
            for t in ("mousePressed", "mouseReleased"):
                await cdp.call(
                    "Input.dispatchMouseEvent",
                    {
                        "type": t,
                        "x": x,
                        "y": y,
                        "button": "left",
                        "clickCount": 1,
                    },
                )
        elif kind == "wheel":
            await cdp.call(
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseWheel",
                    "x": float(ev.get("x") or 0),
                    "y": float(ev.get("y") or 0),
                    "deltaX": float(ev.get("dx") or 0),
                    "deltaY": float(ev.get("dy") or 0),
                },
            )
        elif kind == "key":
            text = str(ev.get("text") or "")
            if text:
                await cdp.call("Input.insertText", {"text": text})


def cdp_ok() -> dict[str, Any]:
    try:
        r = httpx.get(f"{CDP_HTTP}/json/version", timeout=2)
        j = r.json()
        return {"ok": True, "browser": j.get("Browser"), "cdp": CDP_HTTP}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "cdp": CDP_HTTP}


def start_session(url: str, sid: str | None = None) -> dict[str, Any]:
    status = cdp_ok()
    if not status.get("ok"):
        return {
            "ok": False,
            "error": f"Chrome Lite offline ({status.get('error')})",
            "hint": "systemctl start veu-lite-chrome",
        }
    with _lock:
        session_id = sid or f"lite-{int(time.time() * 1000)}"
        old = _sessions.pop(session_id, None)
        if old:
            old.stop()
        sess = LiteSession(session_id, url)
        _sessions[session_id] = sess
        sess.start()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if sess.error:
            return {"ok": False, "error": sess.error, "id": session_id}
        if sess.ready:
            break
        time.sleep(0.05)
    return {
        "ok": not bool(sess.error),
        "id": session_id,
        "url": url,
        "width": sess.width,
        "height": sess.height,
        "ready": sess.ready,
        "error": sess.error,
        "stream": f"/browser/lite/{session_id}/frame.jpg",
        "cdp": status,
    }


def get_session(sid: str) -> LiteSession | None:
    with _lock:
        return _sessions.get(sid)


def stop_session(sid: str) -> dict[str, Any]:
    with _lock:
        sess = _sessions.pop(sid, None)
    if sess:
        sess.stop()
    return {"ok": True, "id": sid}


def list_sessions() -> dict[str, Any]:
    with _lock:
        items = [
            {
                "id": s.id,
                "url": s.url,
                "ready": s.ready,
                "error": s.error,
                "has_frame": bool(s.frame_jpeg),
                "frame_age_ms": int((time.time() - s.frame_ts) * 1000)
                if s.frame_ts
                else None,
            }
            for s in _sessions.values()
        ]
    return {"ok": True, "sessions": items, "cdp": cdp_ok()}

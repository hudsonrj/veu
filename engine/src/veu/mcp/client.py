"""Client MCP mínimo — HTTP (JSON-RPC) e stdio (JSON-RPC newline)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from typing import Any

import httpx


PROTOCOL = "2024-11-05"


def _init_params() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL,
        "capabilities": {},
        "clientInfo": {"name": "veu", "version": "0.3.5"},
    }


class McpError(RuntimeError):
    pass


class HttpMcpClient:
    """MCP Streamable HTTP / JSON-RPC — reusa sessão e client httpx."""

    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: float = 20.0) -> None:
        self.url = url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout
        self._session_id: str | None = None
        self._client: httpx.Client | None = None

    def __enter__(self) -> "HttpMcpClient":
        self._client = httpx.Client(timeout=self.timeout, follow_redirects=True)
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        return h

    def _parse_body(self, res: httpx.Response) -> dict[str, Any]:
        sid = res.headers.get("mcp-session-id") or res.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        ct = (res.headers.get("content-type") or "").lower()
        text = res.text or ""
        if "text/event-stream" in ct or text.lstrip().startswith("event:"):
            data_lines = []
            for line in text.splitlines():
                if line.startswith("data:"):
                    chunk = line[5:].strip()
                    if chunk and chunk != "[DONE]":
                        data_lines.append(chunk)
            if not data_lines:
                return {}
            # último JSON-RPC com result/error
            for payload in reversed(data_lines):
                try:
                    msg = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and ("result" in msg or "error" in msg or "id" in msg):
                    return msg
            return json.loads(data_lines[-1])
        if not text.strip():
            return {}
        return res.json()

    def request(self, method: str, params: dict[str, Any] | None = None, *, notify: bool = False) -> Any:
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not notify:
            body["id"] = str(uuid.uuid4())
        owns = False
        client = self._client
        if client is None:
            client = httpx.Client(timeout=self.timeout, follow_redirects=True)
            owns = True
        try:
            res = client.post(self.url, headers=self._headers(), json=body)
        finally:
            if owns:
                client.close()
        # 202 Accepted comum em notifications
        if res.status_code >= 400:
            raise McpError(f"HTTP {res.status_code}: {(res.text or '')[:300]}")
        if notify:
            return None
        data = self._parse_body(res)
        if "error" in data and data["error"]:
            err = data["error"]
            raise McpError(str(err.get("message") or err))
        return data.get("result")

    def initialize(self) -> dict[str, Any]:
        result = self.request("initialize", _init_params()) or {}
        try:
            # sem params vazios — alguns servers preferem omitir
            self.request("notifications/initialized", notify=True)
        except Exception:
            pass
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {}) or {}
        tools = result.get("tools") if isinstance(result, dict) else None
        return list(tools or [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self.request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )


class StdioMcpClient:
    """MCP over stdio — um processo por sessão curta (probe/call)."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.timeout = timeout
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._next_id = 1

    def __enter__(self) -> "StdioMcpClient":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self) -> None:
        env = os.environ.copy()
        env.update(self.env)
        self._proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.cwd or None,
            env=env,
            bufsize=1,
        )

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _read_message(self, deadline: float) -> dict[str, Any]:
        proc = self._proc
        if not proc or not proc.stdout:
            raise McpError("processo MCP morto")
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                err = ""
                if proc.stderr:
                    try:
                        err = proc.stderr.read()[:400]
                    except Exception:
                        pass
                raise McpError(f"stdio fechou cedo{': ' + err if err else ''}")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg or "error" in msg or "result" in msg:
                return msg
        raise McpError("timeout lendo MCP stdio")

    def request(self, method: str, params: dict[str, Any] | None = None, *, notify: bool = False) -> Any:
        with self._lock:
            proc = self._proc
            if not proc or not proc.stdin:
                raise McpError("MCP stdio não iniciado")
            body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            req_id = None
            if not notify:
                req_id = self._next_id
                self._next_id += 1
                body["id"] = req_id
            if params is not None:
                body["params"] = params
            proc.stdin.write(json.dumps(body, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            if notify:
                return None
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                msg = self._read_message(deadline)
                if msg.get("id") != req_id and "result" not in msg and "error" not in msg:
                    continue
                if msg.get("error"):
                    err = msg["error"]
                    raise McpError(str(err.get("message") or err))
                return msg.get("result")
            raise McpError("timeout MCP stdio")

    def initialize(self) -> dict[str, Any]:
        result = self.request("initialize", _init_params()) or {}
        try:
            self.request("notifications/initialized", notify=True)
        except Exception:
            pass
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {}) or {}
        tools = result.get("tools") if isinstance(result, dict) else None
        return list(tools or [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return self.request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )


def open_client(row: dict[str, Any], env: dict[str, str], headers: dict[str, str]):
    transport = (row.get("transport") or "http").lower()
    if transport == "http":
        return HttpMcpClient(str(row.get("url") or ""), headers=headers, timeout=18.0)
    return StdioMcpClient(
        str(row.get("command") or ""),
        args=list(row.get("args") or []),
        env=env,
        cwd=row.get("cwd"),
    )

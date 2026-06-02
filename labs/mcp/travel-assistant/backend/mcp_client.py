import asyncio
import json
import os
import subprocess
from pathlib import Path

JAR_PATH = os.environ.get(
    "MCP_JAR_PATH",
    "../../utility-tools-mcp/target/utility-tools-mcp-0.0.1.jar",
)


class MCPClient:
    """Talks to the Java MCP server over stdio.

    Uses a blocking subprocess and runs its I/O in a worker thread
    (asyncio.to_thread). This avoids asyncio's subprocess transport, which on
    Windows requires the ProactorEventLoop — unavailable under `uvicorn
    --reload`, which forces the SelectorEventLoop.
    """

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._id = 0
        self._lock = asyncio.Lock()

    async def start(self):
        jar = Path(JAR_PATH).resolve()
        if not jar.exists():
            raise FileNotFoundError(
                f"MCP jar not found at {jar}. "
                "Run `mvn clean package` in utility-tools-mcp first."
            )
        self._proc = subprocess.Popen(
            ["java", "-jar", str(jar)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        await self._initialize()

    def _write(self, payload: dict):
        self._proc.stdin.write((json.dumps(payload) + "\n").encode())
        self._proc.stdin.flush()

    def _send_sync(self, payload: dict) -> dict:
        self._write(payload)
        # Skip blank lines; the server occasionally emits them between messages.
        while True:
            raw = self._proc.stdout.readline()
            if raw == b"":
                raise RuntimeError(
                    "MCP server closed the connection without responding. "
                    "Check that the jar started correctly (see mcp-server.log)."
                )
            line = raw.strip()
            if line:
                return json.loads(line)

    async def _send(self, method: str, params: dict) -> dict:
        async with self._lock:
            self._id += 1
            payload = {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": method,
                "params": params,
            }
            return await asyncio.to_thread(self._send_sync, payload)

    async def _notify(self, method: str, params: dict | None = None):
        """Send a JSON-RPC notification (no id, no response expected)."""
        async with self._lock:
            payload = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                payload["params"] = params
            await asyncio.to_thread(self._write, payload)

    async def _initialize(self):
        await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "travel-dashboard-bridge", "version": "1.0"},
        })
        # MCP handshake: the server will not service tools/call until it
        # receives this notification confirming initialization is complete.
        await self._notify("notifications/initialized")

    async def list_tools(self) -> list[dict]:
        """Discover available tools via the MCP `tools/list` method.

        Returns a list of {"name", "description", "inputSchema"} dicts, so the
        LLM agent can build provider-native tool definitions without us
        duplicating any schemas in Python.
        """
        response = await self._send("tools/list", {})
        if "error" in response:
            raise RuntimeError(f"MCP tools/list error: {response['error']}")
        return response["result"].get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> str:
        response = await self._send("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        if "error" in response:
            raise RuntimeError(f"MCP tool error: {response['error']}")
        text = response["result"]["content"][0]["text"]
        # Spring AI serializes a String tool result as a JSON string, so the
        # text arrives double-encoded (e.g. '"Hanoi...\\r\\n..."'). Unwrap it.
        if isinstance(text, str) and text.startswith('"') and text.endswith('"'):
            try:
                text = json.loads(text)
            except json.JSONDecodeError:
                pass
        return text

    async def stop(self):
        if self._proc:
            try:
                self._proc.stdin.close()
                await asyncio.to_thread(self._proc.wait)
            except Exception:
                pass


mcp = MCPClient()

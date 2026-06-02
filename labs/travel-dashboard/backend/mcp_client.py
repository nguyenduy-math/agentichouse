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

    def _send_sync(self, msg: str) -> dict:
        self._proc.stdin.write(msg.encode())
        self._proc.stdin.flush()
        raw = self._proc.stdout.readline()
        return json.loads(raw)

    async def _send(self, method: str, params: dict) -> dict:
        async with self._lock:
            self._id += 1
            msg = json.dumps({
                "jsonrpc": "2.0",
                "id": self._id,
                "method": method,
                "params": params,
            }) + "\n"
            return await asyncio.to_thread(self._send_sync, msg)

    async def _initialize(self):
        await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "travel-dashboard-bridge", "version": "1.0"},
        })

    async def call_tool(self, name: str, arguments: dict) -> str:
        response = await self._send("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        if "error" in response:
            raise RuntimeError(f"MCP tool error: {response['error']}")
        return response["result"]["content"][0]["text"]

    async def stop(self):
        if self._proc:
            try:
                self._proc.stdin.close()
                await asyncio.to_thread(self._proc.wait)
            except Exception:
                pass


mcp = MCPClient()

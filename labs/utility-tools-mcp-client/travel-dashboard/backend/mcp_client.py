import asyncio
import json
import os
from pathlib import Path

JAR_PATH = os.environ.get(
    "MCP_JAR_PATH",
    "../../utility-tools-mcp/target/utility-tools-mcp-0.0.1.jar",
)


class MCPClient:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._id = 0
        self._lock = asyncio.Lock()

    async def start(self):
        jar = Path(JAR_PATH).resolve()
        if not jar.exists():
            raise FileNotFoundError(
                f"MCP jar not found at {jar}. "
                "Run `mvn clean package` in utility-tools-mcp first."
            )
        self._proc = await asyncio.create_subprocess_exec(
            "java", "-jar", str(jar),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._initialize()

    async def _send(self, method: str, params: dict) -> dict:
        async with self._lock:
            self._id += 1
            msg = json.dumps({
                "jsonrpc": "2.0",
                "id": self._id,
                "method": method,
                "params": params,
            }) + "\n"
            self._proc.stdin.write(msg.encode())
            await self._proc.stdin.drain()
            raw = await self._proc.stdout.readline()
            return json.loads(raw)

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
                await self._proc.wait()
            except Exception:
                pass


mcp = MCPClient()

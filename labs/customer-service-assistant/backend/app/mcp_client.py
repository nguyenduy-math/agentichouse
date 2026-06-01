import os
import sys
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_SERVER_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")
)


class MCPClientManager:
    def __init__(self):
        self.session: ClientSession | None = None
        self._stack = AsyncExitStack()

    async def start(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=[_SERVER_SCRIPT],
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def call_tool(self, name: str, arguments: dict) -> str:
        assert self.session is not None, "MCP session not started"
        result = await self.session.call_tool(name, arguments)
        if result.content and len(result.content) > 0:
            content = result.content[0]
            if hasattr(content, "text"):
                return content.text
        return "{}"

    async def stop(self):
        await self._stack.aclose()

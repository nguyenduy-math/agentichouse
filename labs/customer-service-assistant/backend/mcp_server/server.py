#!/usr/bin/env python3
from mcp.server.fastmcp import FastMCP
from tools.query_tools import register_query_tools
from tools.utility_tools import register_utility_tools

mcp = FastMCP("customer-service-tools")
register_query_tools(mcp)
register_utility_tools(mcp)

if __name__ == "__main__":
    mcp.run()

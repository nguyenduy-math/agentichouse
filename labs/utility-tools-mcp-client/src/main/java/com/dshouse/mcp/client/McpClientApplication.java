package com.dshouse.mcp.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Console chat client. On startup it launches the Utility Tools MCP server (over stdio), discovers
 * its tools, and runs an interactive chat loop where Google Gemini decides which tools to call.
 */
@SpringBootApplication
public class McpClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(McpClientApplication.class, args);
    }
}

package com.dshouse.mcp.server;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Entry point for the Utility Tools MCP server.
 *
 * <p>The server communicates over stdio using the Model Context Protocol. Tools are exposed via
 * {@link com.dshouse.mcp.server.config.ToolConfig}, which collects every {@code @Tool}-annotated
 * bean into a single {@code ToolCallbackProvider}.
 */
@SpringBootApplication
public class McpServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(McpServerApplication.class, args);
    }
}

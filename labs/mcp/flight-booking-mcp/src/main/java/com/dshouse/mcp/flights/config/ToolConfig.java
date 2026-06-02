package com.dshouse.mcp.flights.config;

import com.dshouse.mcp.flights.tools.FlightTools;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Collects every {@code @Tool}-annotated bean into a single {@link ToolCallbackProvider}, which the
 * Spring AI MCP server auto-configuration exposes as MCP tools.
 *
 * <p>To add a new tool: create a {@code @Component} with {@code @Tool} methods and add it to the
 * {@code toolObjects(...)} list below.
 */
@Configuration
public class ToolConfig {

    @Bean
    public ToolCallbackProvider flightToolCallbackProvider(FlightTools flightTools) {
        return MethodToolCallbackProvider.builder()
                .toolObjects(flightTools)
                .build();
    }
}

package com.dshouse.mcp.server.config;

import com.dshouse.mcp.server.currency.CurrencyTools;
import com.dshouse.mcp.server.geo.AttractionsTools;
import com.dshouse.mcp.server.geo.GeocodingTools;
import com.dshouse.mcp.server.time.HolidaysTools;
import com.dshouse.mcp.server.time.TimeTools;
import com.dshouse.mcp.server.util.CryptoTools;
import com.dshouse.mcp.server.util.DateTools;
import com.dshouse.mcp.server.util.UnitConverterTools;
import com.dshouse.mcp.server.weather.WeatherTools;
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
    public ToolCallbackProvider utilityTools(
            WeatherTools weatherTools,
            GeocodingTools geocodingTools,
            AttractionsTools attractionsTools,
            CurrencyTools currencyTools,
            TimeTools timeTools,
            HolidaysTools holidaysTools,
            UnitConverterTools unitConverterTools,
            DateTools dateTools,
            CryptoTools cryptoTools) {
        return MethodToolCallbackProvider.builder()
                .toolObjects(
                        weatherTools,
                        geocodingTools,
                        attractionsTools,
                        currencyTools,
                        timeTools,
                        holidaysTools,
                        unitConverterTools,
                        dateTools,
                        cryptoTools)
                .build();
    }
}

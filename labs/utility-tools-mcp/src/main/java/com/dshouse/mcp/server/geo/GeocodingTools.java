package com.dshouse.mcp.server.geo;

import com.dshouse.mcp.server.weather.OpenMeteoClient;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

/** Resolve a place name to coordinates, so weather tools can be called with lat/lon. */
@Component
public class GeocodingTools {

    private final OpenMeteoClient client;

    public GeocodingTools(OpenMeteoClient client) {
        this.client = client;
    }

    @Tool(name = "geocode", description = "Look up the latitude and longitude of a place by name "
            + "(city, town, landmark). Returns coordinates you can pass to weather tools.")
    public String geocode(@ToolParam(description = "Place name, e.g. 'Hanoi' or 'Paris, France'")
                          String place) {
        try {
            OpenMeteoClient.GeoResult r = client.geocode(place);
            if (r == null) {
                return "No location found for '" + place + "'.";
            }
            String region = r.admin1() == null ? "" : ", " + r.admin1();
            return "%s%s, %s — latitude %.4f, longitude %.4f (timezone %s)".formatted(
                    r.name(), region, r.country(), r.latitude(), r.longitude(), r.timezone());
        } catch (RestClientException e) {
            return "Failed to geocode '" + place + "': " + e.getMessage();
        }
    }
}

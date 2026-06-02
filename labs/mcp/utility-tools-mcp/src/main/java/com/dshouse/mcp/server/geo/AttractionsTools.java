package com.dshouse.mcp.server.geo;

import java.util.List;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

/** List nearby attractions / points of interest at a coordinate, backed by Wikipedia GeoSearch. */
@Component
public class AttractionsTools {

    private final WikipediaClient client;

    public AttractionsTools(WikipediaClient client) {
        this.client = client;
    }

    @Tool(name = "get_attractions", description = "List notable places and points of interest near a "
            + "latitude/longitude (museums, landmarks, parks, neighborhoods). Useful for suggesting "
            + "things to do at a travel destination. Call 'geocode' first if you only have a place name.")
    public String getAttractions(
            @ToolParam(description = "Latitude in decimal degrees") double latitude,
            @ToolParam(description = "Longitude in decimal degrees") double longitude,
            @ToolParam(description = "Search radius in kilometers, 1-50 (default 10)", required = false)
                    Integer radiusKm,
            @ToolParam(description = "Maximum number of results, 1-50 (default 10)", required = false)
                    Integer limit) {
        int radiusMeters = ((radiusKm == null || radiusKm < 1 || radiusKm > 50) ? 10 : radiusKm) * 1000;
        int n = (limit == null || limit < 1 || limit > 50) ? 10 : limit;
        try {
            List<WikipediaClient.GeoPlace> places = client.nearby(latitude, longitude, radiusMeters, n);
            if (places.isEmpty()) {
                return "No notable places found near (%.4f, %.4f).".formatted(latitude, longitude);
            }
            StringBuilder sb = new StringBuilder(
                    "Attractions near (%.4f, %.4f):%n".formatted(latitude, longitude));
            for (WikipediaClient.GeoPlace p : places) {
                sb.append("- %s (%.1f km away)%n".formatted(p.title(), p.distanceMeters() / 1000.0));
            }
            return sb.toString();
        } catch (RestClientException e) {
            return "Failed to fetch attractions: " + e.getMessage();
        }
    }
}

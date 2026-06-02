package com.dshouse.mcp.server.geo;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Thin wrapper over Wikipedia's free, no-key GeoSearch API
 * ({@code https://en.wikipedia.org/w/api.php}). Returns articles near a coordinate, which serve as
 * a good proxy for nearby attractions / points of interest.
 */
@Component
public class WikipediaClient {

    // Wikipedia's API policy requires a descriptive User-Agent; requests without one get 403.
    private final RestClient client = RestClient.builder()
            .baseUrl("https://en.wikipedia.org")
            .defaultHeader("User-Agent",
                    "utility-tools-mcp/0.0.1 (travel-dashboard lab; +https://modelcontextprotocol.io)")
            .build();

    /** Find Wikipedia articles within {@code radiusMeters} of a coordinate. */
    public List<GeoPlace> nearby(double latitude, double longitude, int radiusMeters, int limit) {
        GeoSearchResponse response = client.get()
                .uri("/w/api.php?action=query&list=geosearch&gscoord={lat}|{lon}"
                        + "&gsradius={radius}&gslimit={limit}&format=json",
                        latitude, longitude, radiusMeters, limit)
                .retrieve()
                .body(GeoSearchResponse.class);
        if (response == null || response.query() == null || response.query().geosearch() == null) {
            return List.of();
        }
        return response.query().geosearch();
    }

    // --- Response DTOs (only the fields we need) ---

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record GeoSearchResponse(Query query) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Query(List<GeoPlace> geosearch) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record GeoPlace(
            String title,
            double lat,
            double lon,
            @JsonProperty("dist") double distanceMeters) {}
}

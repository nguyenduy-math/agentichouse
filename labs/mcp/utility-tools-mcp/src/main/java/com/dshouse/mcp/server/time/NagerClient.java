package com.dshouse.mcp.server.time;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Thin wrapper over the free, no-key Nager.Date public-holiday API
 * ({@code https://date.nager.at}).
 */
@Component
public class NagerClient {

    private final RestClient client = RestClient.create("https://date.nager.at");

    /** Public holidays for a country (ISO 3166-1 alpha-2 code) in a given year. */
    public List<Holiday> publicHolidays(int year, String countryCode) {
        Holiday[] response = client.get()
                .uri("/api/v3/PublicHolidays/{year}/{code}", year, countryCode)
                .retrieve()
                .body(Holiday[].class);
        return response == null ? List.of() : List.of(response);
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Holiday(String date, String localName, String name) {}
}

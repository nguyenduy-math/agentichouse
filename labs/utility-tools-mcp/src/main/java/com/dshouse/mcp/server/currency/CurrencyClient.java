package com.dshouse.mcp.server.currency;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Wrapper over the free, no-key ExchangeRate-API open endpoint
 * ({@code https://open.er-api.com/v6/latest/{base}}), which covers ~160 currencies including VND.
 */
@Component
public class CurrencyClient {

    private final RestClient rest = RestClient.create("https://open.er-api.com");

    /** Fetch the latest rates for a base currency, or {@code null} on failure. */
    public Rates latest(String baseCurrency) {
        Rates rates = rest.get()
                .uri("/v6/latest/{base}", baseCurrency.trim().toUpperCase())
                .retrieve()
                .body(Rates.class);
        if (rates == null || !"success".equals(rates.result())) {
            return null;
        }
        return rates;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Rates(
            String result,
            @JsonProperty("base_code") String base,
            @JsonProperty("time_last_update_utc") String updated,
            Map<String, Double> rates) {

        public Double rateFor(String currency) {
            return rates == null ? null : rates.get(currency.trim().toUpperCase());
        }
    }
}

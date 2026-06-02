package com.dshouse.mcp.server.currency;

import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

/** Live currency conversion backed by ExchangeRate-API's open endpoint. */
@Component
public class CurrencyTools {

    private final CurrencyClient client;

    public CurrencyTools(CurrencyClient client) {
        this.client = client;
    }

    @Tool(name = "convert_currency", description = "Convert an amount from one currency to another "
            + "using the latest exchange rate. Use ISO 4217 codes, e.g. USD, EUR, VND, JPY.")
    public String convertCurrency(
            @ToolParam(description = "The amount to convert") double amount,
            @ToolParam(description = "Source currency code, e.g. USD") String from,
            @ToolParam(description = "Target currency code, e.g. VND") String to) {
        try {
            CurrencyClient.Rates rates = client.latest(from);
            if (rates == null) {
                return "Unknown or unsupported source currency '" + from + "'.";
            }
            Double rate = rates.rateFor(to);
            if (rate == null) {
                return "Unknown or unsupported target currency '" + to + "'.";
            }
            double converted = amount * rate;
            return "%,.2f %s = %,.2f %s (rate %.6f, as of %s)".formatted(
                    amount, from.toUpperCase(), converted, to.toUpperCase(), rate, rates.updated());
        } catch (RestClientException e) {
            return "Failed to fetch exchange rates: " + e.getMessage();
        }
    }

    @Tool(name = "get_exchange_rate", description = "Get the latest exchange rate between two "
            + "currencies (how many units of the target currency equal one unit of the source). "
            + "Use ISO 4217 codes, e.g. USD, EUR, VND.")
    public String getExchangeRate(
            @ToolParam(description = "Source currency code, e.g. USD") String from,
            @ToolParam(description = "Target currency code, e.g. VND") String to) {
        try {
            CurrencyClient.Rates rates = client.latest(from);
            if (rates == null) {
                return "Unknown or unsupported source currency '" + from + "'.";
            }
            Double rate = rates.rateFor(to);
            if (rate == null) {
                return "Unknown or unsupported target currency '" + to + "'.";
            }
            return "1 %s = %.6f %s (as of %s)".formatted(
                    from.toUpperCase(), rate, to.toUpperCase(), rates.updated());
        } catch (RestClientException e) {
            return "Failed to fetch exchange rates: " + e.getMessage();
        }
    }
}

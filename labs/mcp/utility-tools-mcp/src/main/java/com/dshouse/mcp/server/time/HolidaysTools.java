package com.dshouse.mcp.server.time;

import java.time.Year;
import java.util.List;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

/** Public-holiday lookup by country, backed by the keyless Nager.Date API. */
@Component
public class HolidaysTools {

    private final NagerClient client;

    public HolidaysTools(NagerClient client) {
        this.client = client;
    }

    @Tool(name = "get_public_holidays", description = "List public holidays for a country in a given "
            + "year. Useful for planning travel dates and warning about closures. Provide the country "
            + "as an ISO 3166-1 alpha-2 code, e.g. 'VN' for Vietnam, 'JP' for Japan, 'FR' for France.")
    public String getPublicHolidays(
            @ToolParam(description = "ISO 3166-1 alpha-2 country code, e.g. VN, JP, US") String countryCode,
            @ToolParam(description = "Year, e.g. 2026 (default: current year)", required = false)
                    Integer year) {
        int y = (year == null || year < 1900 || year > 2100) ? Year.now().getValue() : year;
        String code = countryCode == null ? "" : countryCode.trim().toUpperCase();
        if (code.length() != 2) {
            return "Invalid country code '" + countryCode + "'. Use a 2-letter ISO code like VN or JP.";
        }
        try {
            List<NagerClient.Holiday> holidays = client.publicHolidays(y, code);
            if (holidays.isEmpty()) {
                return "No public holidays found for %s in %d.".formatted(code, y);
            }
            StringBuilder sb = new StringBuilder("Public holidays in %s, %d:%n".formatted(code, y));
            for (NagerClient.Holiday h : holidays) {
                sb.append("- %s — %s (%s)%n".formatted(h.date(), h.localName(), h.name()));
            }
            return sb.toString();
        } catch (RestClientException e) {
            return "Failed to fetch holidays for " + code + ": " + e.getMessage();
        }
    }
}

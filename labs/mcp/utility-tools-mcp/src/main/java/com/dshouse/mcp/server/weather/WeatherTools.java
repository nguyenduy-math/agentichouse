package com.dshouse.mcp.server.weather;

import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;

/** Current-weather and forecast tools backed by Open-Meteo. */
@Component
public class WeatherTools {

    private final OpenMeteoClient client;

    public WeatherTools(OpenMeteoClient client) {
        this.client = client;
    }

    @Tool(name = "get_weather", description = "Get the CURRENT weather at a latitude/longitude. "
            + "If you only have a place name, call 'geocode' first to obtain coordinates.")
    public String getWeather(
            @ToolParam(description = "Latitude in decimal degrees") double latitude,
            @ToolParam(description = "Longitude in decimal degrees") double longitude) {
        try {
            OpenMeteoClient.CurrentWeather c = client.current(latitude, longitude);
            if (c == null) {
                return "No weather data returned for those coordinates.";
            }
            return ("Current weather (%.4f, %.4f) at %s:%n"
                    + "- Conditions: %s%n"
                    + "- Temperature: %s°C (feels like %s°C)%n"
                    + "- Humidity: %s%%%n"
                    + "- Precipitation: %s mm%n"
                    + "- Wind: %s km/h").formatted(
                    latitude, longitude, c.time(),
                    OpenMeteoClient.describe(c.weatherCode()),
                    c.temperature(), c.feelsLike(), c.humidity(), c.precipitation(), c.windSpeed());
        } catch (RestClientException e) {
            return "Failed to fetch weather: " + e.getMessage();
        }
    }

    @Tool(name = "get_forecast", description = "Get a multi-day daily weather forecast at a "
            + "latitude/longitude. Use 'geocode' first if you only have a place name.")
    public String getForecast(
            @ToolParam(description = "Latitude in decimal degrees") double latitude,
            @ToolParam(description = "Longitude in decimal degrees") double longitude,
            @ToolParam(description = "Number of days, 1-16 (default 7)", required = false)
                    Integer days) {
        int n = (days == null || days < 1 || days > 16) ? 7 : days;
        try {
            OpenMeteoClient.DailyForecast d = client.daily(latitude, longitude, n);
            if (d == null || d.time() == null) {
                return "No forecast data returned for those coordinates.";
            }
            StringBuilder sb = new StringBuilder(
                    "%d-day forecast (%.4f, %.4f):%n".formatted(n, latitude, longitude));
            for (int i = 0; i < d.time().size(); i++) {
                sb.append("- %s: %s, %s°C – %s°C, precip %s mm%n".formatted(
                        d.time().get(i),
                        OpenMeteoClient.describe(d.weatherCode().get(i)),
                        d.tempMin().get(i), d.tempMax().get(i), d.precipitation().get(i)));
            }
            return sb.toString();
        } catch (RestClientException e) {
            return "Failed to fetch forecast: " + e.getMessage();
        }
    }
}

package com.dshouse.mcp.server.weather;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Thin wrapper over the free, no-key Open-Meteo APIs.
 *
 * <ul>
 *   <li>Geocoding: {@code https://geocoding-api.open-meteo.com}</li>
 *   <li>Forecast:  {@code https://api.open-meteo.com}</li>
 * </ul>
 */
@Component
public class OpenMeteoClient {

    private final RestClient geocoding =
            RestClient.create("https://geocoding-api.open-meteo.com");
    private final RestClient forecast =
            RestClient.create("https://api.open-meteo.com");

    /** Resolve a place name to its first matching location, or {@code null} if none found. */
    public GeoResult geocode(String name) {
        GeoResponse response = geocoding.get()
                .uri("/v1/search?name={name}&count=1&language=en&format=json", name)
                .retrieve()
                .body(GeoResponse.class);
        if (response == null || response.results() == null || response.results().isEmpty()) {
            return null;
        }
        return response.results().get(0);
    }

    public CurrentWeather current(double latitude, double longitude) {
        ForecastResponse response = forecast.get()
                .uri("/v1/forecast?latitude={lat}&longitude={lon}"
                        + "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                        + "precipitation,weather_code,wind_speed_10m&timezone=auto",
                        latitude, longitude)
                .retrieve()
                .body(ForecastResponse.class);
        return response == null ? null : response.current();
    }

    public DailyForecast daily(double latitude, double longitude, int days) {
        ForecastResponse response = forecast.get()
                .uri("/v1/forecast?latitude={lat}&longitude={lon}"
                        + "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
                        + "&forecast_days={days}&timezone=auto",
                        latitude, longitude, days)
                .retrieve()
                .body(ForecastResponse.class);
        return response == null ? null : response.daily();
    }

    // --- Response DTOs (only the fields we need) ---

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record GeoResponse(List<GeoResult> results) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record GeoResult(String name, String country, String admin1,
                            double latitude, double longitude, String timezone) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record ForecastResponse(CurrentWeather current, DailyForecast daily) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record CurrentWeather(
            String time,
            @com.fasterxml.jackson.annotation.JsonProperty("temperature_2m") Double temperature,
            @com.fasterxml.jackson.annotation.JsonProperty("apparent_temperature") Double feelsLike,
            @com.fasterxml.jackson.annotation.JsonProperty("relative_humidity_2m") Integer humidity,
            @com.fasterxml.jackson.annotation.JsonProperty("precipitation") Double precipitation,
            @com.fasterxml.jackson.annotation.JsonProperty("weather_code") Integer weatherCode,
            @com.fasterxml.jackson.annotation.JsonProperty("wind_speed_10m") Double windSpeed) {}

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record DailyForecast(
            List<String> time,
            @com.fasterxml.jackson.annotation.JsonProperty("weather_code") List<Integer> weatherCode,
            @com.fasterxml.jackson.annotation.JsonProperty("temperature_2m_max") List<Double> tempMax,
            @com.fasterxml.jackson.annotation.JsonProperty("temperature_2m_min") List<Double> tempMin,
            @com.fasterxml.jackson.annotation.JsonProperty("precipitation_sum") List<Double> precipitation) {}

    /** WMO weather interpretation codes → short human-readable text. */
    public static final Map<Integer, String> WMO = Map.ofEntries(
            Map.entry(0, "Clear sky"), Map.entry(1, "Mainly clear"), Map.entry(2, "Partly cloudy"),
            Map.entry(3, "Overcast"), Map.entry(45, "Fog"), Map.entry(48, "Depositing rime fog"),
            Map.entry(51, "Light drizzle"), Map.entry(53, "Moderate drizzle"),
            Map.entry(55, "Dense drizzle"), Map.entry(61, "Slight rain"), Map.entry(63, "Moderate rain"),
            Map.entry(65, "Heavy rain"), Map.entry(71, "Slight snow"), Map.entry(73, "Moderate snow"),
            Map.entry(75, "Heavy snow"), Map.entry(80, "Rain showers"), Map.entry(81, "Moderate showers"),
            Map.entry(82, "Violent showers"), Map.entry(95, "Thunderstorm"),
            Map.entry(96, "Thunderstorm with hail"), Map.entry(99, "Thunderstorm with heavy hail"));

    public static String describe(Integer code) {
        if (code == null) {
            return "Unknown";
        }
        return WMO.getOrDefault(code, "Code " + code);
    }
}

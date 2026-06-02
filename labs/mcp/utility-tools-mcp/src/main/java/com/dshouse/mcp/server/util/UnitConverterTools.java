package com.dshouse.mcp.server.util;

import java.util.Map;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

/** Unit conversion for length, mass, temperature, and digital storage (pure JDK, no network). */
@Component
public class UnitConverterTools {

    // Factors expressed relative to a base unit (length->metre, mass->gram, data->byte).
    private static final Map<String, Double> LENGTH = Map.of(
            "mm", 0.001, "cm", 0.01, "m", 1.0, "km", 1000.0,
            "in", 0.0254, "ft", 0.3048, "yd", 0.9144, "mi", 1609.344);

    private static final Map<String, Double> MASS = Map.of(
            "mg", 0.001, "g", 1.0, "kg", 1000.0, "t", 1_000_000.0,
            "oz", 28.349523125, "lb", 453.59237);

    private static final Map<String, Double> DATA = Map.of(
            "b", 1.0, "kb", 1024.0, "mb", 1048576.0, "gb", 1073741824.0, "tb", 1099511627776.0);

    @Tool(name = "convert_units", description = "Convert a value between units of the same kind. "
            + "Supported: length (mm, cm, m, km, in, ft, yd, mi), mass (mg, g, kg, t, oz, lb), "
            + "temperature (c, f, k), and digital storage (b, kb, mb, gb, tb). "
            + "The two units must belong to the same category.")
    public String convertUnits(
            @ToolParam(description = "The numeric value to convert") double value,
            @ToolParam(description = "Source unit, e.g. 'km', 'lb', 'c', 'mb'") String fromUnit,
            @ToolParam(description = "Target unit, e.g. 'mi', 'kg', 'f', 'gb'") String toUnit) {
        String from = fromUnit == null ? "" : fromUnit.trim().toLowerCase();
        String to = toUnit == null ? "" : toUnit.trim().toLowerCase();

        if (isTemperature(from) && isTemperature(to)) {
            double result = convertTemperature(value, from, to);
            return format(value, from, result, to);
        }
        Double result = convertWithin(LENGTH, value, from, to);
        if (result == null) {
            result = convertWithin(MASS, value, from, to);
        }
        if (result == null) {
            result = convertWithin(DATA, value, from, to);
        }
        if (result == null) {
            return "Cannot convert from '" + fromUnit + "' to '" + toUnit
                    + "'. Make sure both units are valid and in the same category.";
        }
        return format(value, from, result, to);
    }

    private static Double convertWithin(Map<String, Double> table, double value, String from, String to) {
        Double fromFactor = table.get(from);
        Double toFactor = table.get(to);
        if (fromFactor == null || toFactor == null) {
            return null;
        }
        return value * fromFactor / toFactor;
    }

    private static boolean isTemperature(String unit) {
        return unit.equals("c") || unit.equals("f") || unit.equals("k");
    }

    private static double convertTemperature(double value, String from, String to) {
        double celsius = switch (from) {
            case "c" -> value;
            case "f" -> (value - 32) * 5 / 9;
            case "k" -> value - 273.15;
            default -> value;
        };
        return switch (to) {
            case "c" -> celsius;
            case "f" -> celsius * 9 / 5 + 32;
            case "k" -> celsius + 273.15;
            default -> celsius;
        };
    }

    private static String format(double value, String from, double result, String to) {
        return "%s %s = %s %s".formatted(trim(value), from, trim(result), to);
    }

    private static String trim(double d) {
        if (d == Math.floor(d) && !Double.isInfinite(d)) {
            return String.valueOf((long) d);
        }
        return String.valueOf(Math.round(d * 1_000_000d) / 1_000_000d);
    }
}

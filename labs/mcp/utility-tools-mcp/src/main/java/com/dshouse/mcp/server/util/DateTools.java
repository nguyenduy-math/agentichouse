package com.dshouse.mcp.server.util;

import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

/** Date arithmetic tools using ISO-8601 dates (pure JDK, no network). */
@Component
public class DateTools {

    @Tool(name = "date_diff", description = "Compute the difference between two ISO dates "
            + "(format YYYY-MM-DD). Returns the number of days, plus a years/months/days breakdown.")
    public String dateDiff(
            @ToolParam(description = "Start date, format YYYY-MM-DD") String date1,
            @ToolParam(description = "End date, format YYYY-MM-DD") String date2) {
        LocalDate d1, d2;
        try {
            d1 = LocalDate.parse(date1.trim());
            d2 = LocalDate.parse(date2.trim());
        } catch (DateTimeParseException e) {
            return "Invalid date. Use the format YYYY-MM-DD (e.g. 2026-05-31).";
        }
        long days = ChronoUnit.DAYS.between(d1, d2);
        var period = java.time.Period.between(d1.isBefore(d2) ? d1 : d2, d1.isBefore(d2) ? d2 : d1);
        return "%d day(s) between %s and %s (%d year(s), %d month(s), %d day(s))".formatted(
                days, d1, d2, period.getYears(), period.getMonths(), period.getDays());
    }

    @Tool(name = "date_add", description = "Add (or subtract, with a negative amount) a number of "
            + "days, weeks, months, or years to an ISO date (format YYYY-MM-DD).")
    public String dateAdd(
            @ToolParam(description = "Base date, format YYYY-MM-DD") String date,
            @ToolParam(description = "Amount to add; use a negative number to subtract") long amount,
            @ToolParam(description = "Unit: days, weeks, months, or years") String unit) {
        LocalDate base;
        try {
            base = LocalDate.parse(date.trim());
        } catch (DateTimeParseException e) {
            return "Invalid date. Use the format YYYY-MM-DD (e.g. 2026-05-31).";
        }
        LocalDate result = switch (unit == null ? "" : unit.trim().toLowerCase()) {
            case "day", "days" -> base.plusDays(amount);
            case "week", "weeks" -> base.plusWeeks(amount);
            case "month", "months" -> base.plusMonths(amount);
            case "year", "years" -> base.plusYears(amount);
            default -> null;
        };
        if (result == null) {
            return "Unsupported unit '" + unit + "'. Use days, weeks, months, or years.";
        }
        return "%s %+d %s = %s (%s)".formatted(
                base, amount, unit, result, result.getDayOfWeek());
    }
}

package com.dshouse.mcp.server.time;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.zone.ZoneRulesException;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;

/** World-clock and timezone conversion tools (pure JDK, no network). */
@Component
public class TimeTools {

    private static final DateTimeFormatter OUT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss (EEEE) zzz");

    @Tool(name = "current_time", description = "Get the current date and time in a given IANA "
            + "timezone, e.g. 'Asia/Ho_Chi_Minh', 'Europe/London', 'America/New_York', or 'UTC'.")
    public String currentTime(
            @ToolParam(description = "IANA timezone id, e.g. Asia/Ho_Chi_Minh") String timezone) {
        ZoneId zone;
        try {
            zone = ZoneId.of(timezone.trim());
        } catch (ZoneRulesException | DateTimeParseException e) {
            return "Unknown timezone '" + timezone + "'. Use an IANA id like Asia/Ho_Chi_Minh.";
        }
        return ZonedDateTime.now(zone).format(OUT);
    }

    @Tool(name = "convert_time", description = "Convert a wall-clock date-time from one IANA "
            + "timezone to another. The input time uses the format 'YYYY-MM-DD HH:mm'.")
    public String convertTime(
            @ToolParam(description = "Date-time to convert, format 'YYYY-MM-DD HH:mm'") String dateTime,
            @ToolParam(description = "Source IANA timezone id") String fromZone,
            @ToolParam(description = "Target IANA timezone id") String toZone) {
        ZoneId from, to;
        try {
            from = ZoneId.of(fromZone.trim());
            to = ZoneId.of(toZone.trim());
        } catch (ZoneRulesException | DateTimeParseException e) {
            return "Unknown timezone. Use IANA ids like Asia/Ho_Chi_Minh or Europe/London.";
        }
        LocalDateTime local;
        try {
            local = LocalDateTime.parse(dateTime.trim(),
                    DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"));
        } catch (DateTimeParseException e) {
            return "Invalid date-time. Use the format 'YYYY-MM-DD HH:mm' (e.g. 2026-05-31 14:30).";
        }
        ZonedDateTime source = local.atZone(from);
        ZonedDateTime target = source.withZoneSameInstant(to);
        return "%s  →  %s".formatted(source.format(OUT), target.format(OUT));
    }
}

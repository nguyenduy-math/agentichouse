package com.dshouse.mcp.server;

import static org.assertj.core.api.Assertions.assertThat;

import com.dshouse.mcp.server.time.TimeTools;
import com.dshouse.mcp.server.util.CryptoTools;
import com.dshouse.mcp.server.util.DateTools;
import com.dshouse.mcp.server.util.UnitConverterTools;
import org.junit.jupiter.api.Test;

/** Deterministic unit tests for the pure-compute tools (no network required). */
class ComputeToolsTest {

    private final CryptoTools crypto = new CryptoTools();
    private final UnitConverterTools units = new UnitConverterTools();
    private final DateTools dates = new DateTools();
    private final TimeTools time = new TimeTools();

    @Test
    void sha256MatchesKnownDigest() {
        // SHA-256 of "abc"
        assertThat(crypto.hash("abc", "SHA-256"))
                .isEqualTo("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }

    @Test
    void base64RoundTrips() {
        String encoded = crypto.base64Encode("hello world");
        assertThat(encoded).isEqualTo("aGVsbG8gd29ybGQ=");
        assertThat(crypto.base64Decode(encoded)).isEqualTo("hello world");
    }

    @Test
    void uuidHasCanonicalForm() {
        assertThat(crypto.generateUuid())
                .matches("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}");
    }

    @Test
    void passwordRespectsLength() {
        assertThat(crypto.generatePassword(16, false)).hasSize(16);
        assertThat(crypto.generatePassword(2, false)).contains("between 4 and 128");
    }

    @Test
    void lengthConversionKmToMiles() {
        assertThat(units.convertUnits(1, "km", "mi")).contains("0.621371");
    }

    @Test
    void temperatureConversionCtoF() {
        assertThat(units.convertUnits(100, "c", "f")).isEqualTo("100 c = 212 f");
    }

    @Test
    void incompatibleUnitsRejected() {
        assertThat(units.convertUnits(1, "km", "kg")).contains("Cannot convert");
    }

    @Test
    void dateDiffCountsDays() {
        assertThat(dates.dateDiff("2026-01-01", "2026-01-31")).contains("30 day(s)");
    }

    @Test
    void dateAddMonths() {
        assertThat(dates.dateAdd("2026-01-31", 1, "months")).contains("2026-02-28");
    }

    @Test
    void currentTimeRejectsBadZone() {
        assertThat(time.currentTime("Not/AZone")).contains("Unknown timezone");
    }

    @Test
    void convertTimeShiftsAcrossZones() {
        String result = time.convertTime("2026-05-31 12:00", "UTC", "Asia/Ho_Chi_Minh");
        assertThat(result).contains("19:00");
    }
}

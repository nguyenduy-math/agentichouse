package com.dshouse.mcp.flights.tools;

import static org.assertj.core.api.Assertions.assertThat;

import com.dshouse.mcp.flights.model.Flight;
import com.dshouse.mcp.flights.repository.FlightRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

/** End-to-end test of the flight tools against the seeded in-memory H2 database. */
@SpringBootTest
class FlightToolsTest {

    @Autowired
    private FlightTools flightTools;

    @Autowired
    private FlightRepository flights;

    @Test
    void searchReturnsSeededRoute() {
        String result = flightTools.searchFlights("sgn", "HAN", null, 10);
        assertThat(result).contains("VN204").contains("Available flights from SGN to HAN");
    }

    @Test
    void bookDecrementsSeatsAndGetBookingEchoesDetails() {
        Flight before = flights.findByFlightNumber("VN122").orElseThrow();
        int seatsBefore = before.getSeatsAvailable();

        String booked = flightTools.bookFlight("vn122", "Nguyen Van A", 2);
        assertThat(booked).contains("Booking confirmed!").contains("BK-");

        String reference = extractReference(booked);
        Flight after = flights.findByFlightNumber("VN122").orElseThrow();
        assertThat(after.getSeatsAvailable()).isEqualTo(seatsBefore - 2);

        String lookup = flightTools.getBooking(reference);
        assertThat(lookup).contains(reference).contains("Nguyen Van A").contains("Seats: 2");
    }

    @Test
    void overbookingIsRejected() {
        Flight flight = flights.findByFlightNumber("VJ630").orElseThrow();
        String result = flightTools.bookFlight("VJ630", "Test Passenger",
                flight.getSeatsAvailable() + 5);
        assertThat(result).contains("Not enough seats");
    }

    @Test
    void unknownBookingReferenceReportsNotFound() {
        assertThat(flightTools.getBooking("BK-ZZZZZZ")).contains("No booking found");
    }

    private static String extractReference(String bookingMessage) {
        for (String token : bookingMessage.split("\\s+")) {
            if (token.startsWith("BK-")) {
                return token;
            }
        }
        throw new IllegalStateException("No reference in: " + bookingMessage);
    }
}

package com.dshouse.mcp.flights.tools;

import com.dshouse.mcp.flights.model.Booking;
import com.dshouse.mcp.flights.model.Flight;
import com.dshouse.mcp.flights.repository.BookingRepository;
import com.dshouse.mcp.flights.repository.FlightRepository;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** MCP tools for searching the sample flight catalogue, booking seats, and looking up bookings. */
@Component
public class FlightTools {

    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm");
    private static final char[] REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".toCharArray();

    private final FlightRepository flights;
    private final BookingRepository bookings;

    public FlightTools(FlightRepository flights, BookingRepository bookings) {
        this.flights = flights;
        this.bookings = bookings;
    }

    @Tool(name = "search_flights", description = "Find available flights between two airports. "
            + "Provide origin and destination as 3-letter IATA codes, e.g. 'SGN' (Ho Chi Minh City), "
            + "'HAN' (Hanoi), 'DAD' (Da Nang), 'SIN' (Singapore), 'BKK' (Bangkok), 'NRT' (Tokyo). "
            + "Optionally filter by departure date. Returns flight numbers, times, prices and seats left.")
    public String searchFlights(
            @ToolParam(description = "Origin airport IATA code, e.g. SGN") String origin,
            @ToolParam(description = "Destination airport IATA code, e.g. HAN") String destination,
            @ToolParam(description = "Departure date as YYYY-MM-DD (optional; omit for all dates)",
                    required = false) String date,
            @ToolParam(description = "Maximum number of results, 1-50 (default 10)", required = false)
                    Integer maxResults) {
        String from = normalizeCode(origin);
        String to = normalizeCode(destination);
        if (from.length() != 3 || to.length() != 3) {
            return "Invalid airport code. Use 3-letter IATA codes like SGN, HAN, DAD.";
        }

        LocalDate filterDate = null;
        if (date != null && !date.isBlank()) {
            try {
                filterDate = LocalDate.parse(date.trim());
            } catch (DateTimeParseException e) {
                return "Invalid date '" + date + "'. Use the format YYYY-MM-DD, e.g. 2026-06-10.";
            }
        }

        int limit = (maxResults == null || maxResults < 1 || maxResults > 50) ? 10 : maxResults;

        final LocalDate wanted = filterDate;
        List<Flight> matches = flights
                .findByOriginAndDestinationOrderByDepartureDateAscDepartureTimeAsc(from, to)
                .stream()
                .filter(f -> f.getSeatsAvailable() > 0)
                .filter(f -> wanted == null || f.getDepartureDate().equals(wanted))
                .limit(limit)
                .toList();

        if (matches.isEmpty()) {
            String when = wanted == null ? "" : " on " + wanted;
            return "No available flights found from %s to %s%s.".formatted(from, to, when);
        }

        StringBuilder sb = new StringBuilder(
                "Available flights from %s to %s:%n".formatted(from, to));
        for (Flight f : matches) {
            sb.append("- %s (%s): %s -> %s on %s, %s-%s, $%.0f, %d seat(s) left%n".formatted(
                    f.getFlightNumber(), f.getAirline(), f.getOrigin(), f.getDestination(),
                    f.getDepartureDate(), f.getDepartureTime().format(TIME),
                    f.getArrivalTime().format(TIME), f.getPriceUsd(), f.getSeatsAvailable()));
        }
        sb.append("To book, call book_flight with the flight number and passenger name.");
        return sb.toString();
    }

    @Tool(name = "book_flight", description = "Book one or more seats on a specific flight. "
            + "Provide the flight number (from search_flights) and the passenger name. Returns a "
            + "booking reference (e.g. BK-7F3K9Q) used later with get_booking.")
    @Transactional
    public String bookFlight(
            @ToolParam(description = "Flight number to book, e.g. VN204") String flightNumber,
            @ToolParam(description = "Full name of the passenger") String passengerName,
            @ToolParam(description = "Number of seats to book, default 1", required = false)
                    Integer seats) {
        String code = flightNumber == null ? "" : flightNumber.trim().toUpperCase();
        if (code.isEmpty()) {
            return "A flight number is required, e.g. VN204.";
        }
        if (passengerName == null || passengerName.isBlank()) {
            return "A passenger name is required.";
        }
        int requested = (seats == null) ? 1 : seats;
        if (requested < 1) {
            return "Number of seats must be at least 1.";
        }

        Optional<Flight> found = flights.findByFlightNumber(code);
        if (found.isEmpty()) {
            return "No flight found with number '" + code + "'. Use search_flights to find one.";
        }
        Flight flight = found.get();
        if (flight.getSeatsAvailable() < requested) {
            return "Not enough seats on %s: %d requested but only %d available.".formatted(
                    code, requested, flight.getSeatsAvailable());
        }

        flight.setSeatsAvailable(flight.getSeatsAvailable() - requested);
        flights.save(flight);

        double total = flight.getPriceUsd() * requested;
        String reference = generateReference();
        Booking booking = new Booking(reference, code, passengerName.trim(), requested, total,
                "CONFIRMED", Instant.now());
        bookings.save(booking);

        return ("Booking confirmed!%n"
                + "Reference: %s%n"
                + "Passenger: %s%n"
                + "Flight: %s (%s) %s -> %s on %s, %s-%s%n"
                + "Seats: %d%n"
                + "Total: $%.0f%n"
                + "Keep the reference to look up this booking with get_booking.").formatted(
                reference, booking.getPassengerName(), flight.getFlightNumber(), flight.getAirline(),
                flight.getOrigin(), flight.getDestination(), flight.getDepartureDate(),
                flight.getDepartureTime().format(TIME), flight.getArrivalTime().format(TIME),
                requested, total);
    }

    @Tool(name = "get_booking", description = "Look up an existing booking by its reference "
            + "(e.g. BK-7F3K9Q) returned from book_flight. Shows passenger, flight and price details.")
    public String getBooking(
            @ToolParam(description = "Booking reference, e.g. BK-7F3K9Q") String reference) {
        String ref = reference == null ? "" : reference.trim().toUpperCase();
        if (ref.isEmpty()) {
            return "A booking reference is required, e.g. BK-7F3K9Q.";
        }

        Optional<Booking> found = bookings.findByReference(ref);
        if (found.isEmpty()) {
            return "No booking found with reference '" + ref + "'.";
        }
        Booking b = found.get();

        StringBuilder sb = new StringBuilder("Booking %s (%s):%n".formatted(b.getReference(), b.getStatus()));
        sb.append("- Passenger: %s%n".formatted(b.getPassengerName()));
        sb.append("- Flight: %s%n".formatted(b.getFlightNumber()));
        flights.findByFlightNumber(b.getFlightNumber()).ifPresent(f ->
                sb.append("- Route: %s -> %s on %s, %s-%s%n".formatted(
                        f.getOrigin(), f.getDestination(), f.getDepartureDate(),
                        f.getDepartureTime().format(TIME), f.getArrivalTime().format(TIME))));
        sb.append("- Seats: %d%n".formatted(b.getSeatsBooked()));
        sb.append("- Total: $%.0f%n".formatted(b.getTotalPriceUsd()));
        sb.append("- Booked at: %s".formatted(b.getCreatedAt()));
        return sb.toString();
    }

    private String normalizeCode(String code) {
        return code == null ? "" : code.trim().toUpperCase();
    }

    /** Generates a unique human-friendly booking reference like {@code BK-7F3K9Q}. */
    private String generateReference() {
        for (int attempt = 0; attempt < 20; attempt++) {
            StringBuilder ref = new StringBuilder("BK-");
            for (int i = 0; i < 6; i++) {
                ref.append(REF_ALPHABET[ThreadLocalRandom.current().nextInt(REF_ALPHABET.length)]);
            }
            String candidate = ref.toString();
            if (!bookings.existsByReference(candidate)) {
                return candidate;
            }
        }
        // Extremely unlikely fallback.
        return "BK-" + Long.toString(System.nanoTime(), 36).toUpperCase();
    }
}

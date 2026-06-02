package com.dshouse.mcp.flights.data;

import com.dshouse.mcp.flights.model.Flight;
import com.dshouse.mcp.flights.repository.FlightRepository;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

/**
 * Seeds the in-memory database with a small catalogue of sample flights on startup.
 * Departure dates are generated relative to today so the data is always "upcoming".
 */
@Component
public class SampleDataLoader implements CommandLineRunner {

    private final FlightRepository flights;

    public SampleDataLoader(FlightRepository flights) {
        this.flights = flights;
    }

    @Override
    public void run(String... args) {
        if (flights.count() > 0) {
            return;
        }

        LocalDate today = LocalDate.now();

        flights.saveAll(List.of(
                // Ho Chi Minh City (SGN) <-> Hanoi (HAN)
                new Flight("VN204", "Vietnam Airlines", "SGN", "HAN",
                        today.plusDays(1), LocalTime.of(6, 0), LocalTime.of(8, 10), 95.0, 6),
                new Flight("VJ160", "VietJet Air", "SGN", "HAN",
                        today.plusDays(1), LocalTime.of(12, 30), LocalTime.of(14, 40), 72.0, 9),
                new Flight("QH202", "Bamboo Airways", "SGN", "HAN",
                        today.plusDays(2), LocalTime.of(18, 0), LocalTime.of(20, 5), 84.0, 4),
                new Flight("VN255", "Vietnam Airlines", "HAN", "SGN",
                        today.plusDays(2), LocalTime.of(7, 15), LocalTime.of(9, 25), 95.0, 5),
                new Flight("VJ171", "VietJet Air", "HAN", "SGN",
                        today.plusDays(3), LocalTime.of(15, 45), LocalTime.of(17, 55), 70.0, 8),

                // SGN <-> Da Nang (DAD)
                new Flight("VN122", "Vietnam Airlines", "SGN", "DAD",
                        today.plusDays(1), LocalTime.of(9, 0), LocalTime.of(10, 20), 58.0, 7),
                new Flight("VJ630", "VietJet Air", "SGN", "DAD",
                        today.plusDays(3), LocalTime.of(13, 0), LocalTime.of(14, 20), 49.0, 3),
                new Flight("VN123", "Vietnam Airlines", "DAD", "SGN",
                        today.plusDays(4), LocalTime.of(11, 30), LocalTime.of(12, 50), 58.0, 6),

                // HAN <-> DAD
                new Flight("QH112", "Bamboo Airways", "HAN", "DAD",
                        today.plusDays(2), LocalTime.of(8, 30), LocalTime.of(9, 50), 55.0, 5),
                new Flight("VN176", "Vietnam Airlines", "DAD", "HAN",
                        today.plusDays(5), LocalTime.of(16, 0), LocalTime.of(17, 20), 55.0, 4),

                // International: SGN <-> Singapore (SIN), SGN <-> Bangkok (BKK), HAN <-> Tokyo (NRT)
                new Flight("VN651", "Vietnam Airlines", "SGN", "SIN",
                        today.plusDays(2), LocalTime.of(10, 0), LocalTime.of(13, 0), 165.0, 6),
                new Flight("TG557", "Thai Airways", "SGN", "BKK",
                        today.plusDays(3), LocalTime.of(14, 15), LocalTime.of(15, 45), 130.0, 8),
                new Flight("VN310", "Vietnam Airlines", "HAN", "NRT",
                        today.plusDays(4), LocalTime.of(0, 30), LocalTime.of(7, 40), 420.0, 5),
                new Flight("NH858", "ANA", "NRT", "HAN",
                        today.plusDays(7), LocalTime.of(9, 50), LocalTime.of(14, 20), 430.0, 7)));
    }
}

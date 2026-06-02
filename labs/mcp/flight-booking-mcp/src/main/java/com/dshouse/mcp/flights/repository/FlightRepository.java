package com.dshouse.mcp.flights.repository;

import com.dshouse.mcp.flights.model.Flight;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FlightRepository extends JpaRepository<Flight, Long> {

    List<Flight> findByOriginAndDestinationOrderByDepartureDateAscDepartureTimeAsc(
            String origin, String destination);

    Optional<Flight> findByFlightNumber(String flightNumber);
}

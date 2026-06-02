package com.dshouse.mcp.flights.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import java.time.Instant;

/** A confirmed booking against a {@link Flight}. */
@Entity
public class Booking {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String reference;

    @Column(nullable = false)
    private String flightNumber;

    @Column(nullable = false)
    private String passengerName;

    @Column(nullable = false)
    private int seatsBooked;

    @Column(nullable = false)
    private double totalPriceUsd;

    @Column(nullable = false)
    private String status;

    @Column(nullable = false)
    private Instant createdAt;

    protected Booking() {
        // for JPA
    }

    public Booking(String reference, String flightNumber, String passengerName, int seatsBooked,
            double totalPriceUsd, String status, Instant createdAt) {
        this.reference = reference;
        this.flightNumber = flightNumber;
        this.passengerName = passengerName;
        this.seatsBooked = seatsBooked;
        this.totalPriceUsd = totalPriceUsd;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getReference() {
        return reference;
    }

    public String getFlightNumber() {
        return flightNumber;
    }

    public String getPassengerName() {
        return passengerName;
    }

    public int getSeatsBooked() {
        return seatsBooked;
    }

    public double getTotalPriceUsd() {
        return totalPriceUsd;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}

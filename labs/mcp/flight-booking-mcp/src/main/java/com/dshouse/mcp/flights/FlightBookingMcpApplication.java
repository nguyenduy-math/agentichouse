package com.dshouse.mcp.flights;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** Entry point for the flight-booking MCP server (stdio transport). */
@SpringBootApplication
public class FlightBookingMcpApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlightBookingMcpApplication.class, args);
    }
}

# flight-booking-mcp

A small, self-contained **Spring Boot MCP server** that exposes flight **search** and
**booking** tools over the Model Context Protocol (stdio transport). It is backed by an
in-memory **H2 database + Spring Data JPA**, seeded on startup with a catalogue of sample
flights — no external API or API key required.

## Tools

| Tool | Parameters | Description |
|---|---|---|
| `search_flights` | `origin` (IATA, req), `destination` (IATA, req), `date` (`YYYY-MM-DD`, optional), `maxResults` (optional, default 10) | Find available flights on a route, optionally on a given date. |
| `book_flight` | `flightNumber` (req), `passengerName` (req), `seats` (optional, default 1) | Book seats on a flight; decrements availability and returns a booking reference (`BK-XXXXXX`). |
| `get_booking` | `reference` (req) | Look up an existing booking by its reference. |

## Sample data

Flights are generated for the next ~7 days across Vietnamese and regional routes:

```
SGN <-> HAN   (Ho Chi Minh City <-> Hanoi)
SGN <-> DAD   (Ho Chi Minh City <-> Da Nang)
HAN <-> DAD   (Hanoi <-> Da Nang)
SGN  -> SIN   (Singapore)
SGN  -> BKK   (Bangkok)
HAN <-> NRT   (Tokyo)
```

Sample flight numbers include `VN204`, `VJ160`, `QH202`, `VN122`, `VJ630`, `VN651`, `TG557`,
`VN310`. Bookings live in the in-memory DB for the lifetime of the process (reset on restart).

## Build & run

Requires **JDK 21** and **Maven**.

```bash
mvn clean package                 # produces target/flight-booking-mcp-0.0.1.jar
mvn test                          # runs the end-to-end FlightToolsTest
java -jar target/flight-booking-mcp-0.0.1.jar
```

The server speaks JSON-RPC over **stdout/stdin**; all logging goes to `./mcp-server.log` so the
stdio channel stays clean.

## Register with an MCP client

Point your MCP client (e.g. Claude Desktop) at the built jar:

```json
{
  "mcpServers": {
    "flight-booking": {
      "command": "java",
      "args": ["-jar", "/absolute/path/to/flight-booking-mcp/target/flight-booking-mcp-0.0.1.jar"]
    }
  }
}
```

Then ask, for example: *"Find flights from SGN to HAN, then book VN204 for Nguyen Van A and
show me the booking."*

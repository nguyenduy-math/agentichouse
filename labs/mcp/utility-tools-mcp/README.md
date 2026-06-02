# Utility Tools MCP Server (Java)

A [Model Context Protocol](https://modelcontextprotocol.io) server written in Java with
**Spring AI**. It exposes a set of everyday utility tools over the **stdio** transport, so any MCP
client (Claude Desktop, Claude Code, the MCP Inspector, or the sibling
[`utility-tools-mcp-client`](../utility-tools-mcp-client)) can call them.

## Tools

| Tool | Description | Backed by |
|---|---|---|
| `geocode` | Place name → latitude/longitude | Open-Meteo (no key) |
| `get_weather` | Current weather at lat/lon | Open-Meteo (no key) |
| `get_forecast` | Multi-day daily forecast at lat/lon | Open-Meteo (no key) |
| `convert_currency` | Convert an amount between currencies | ExchangeRate-API open (no key) |
| `get_exchange_rate` | Latest rate between two currencies | ExchangeRate-API open (no key) |
| `current_time` | Current time in an IANA timezone | JDK `java.time` |
| `convert_time` | Convert a time between timezones | JDK `java.time` |
| `convert_units` | Length / mass / temperature / data units | pure JDK |
| `date_diff` | Days (and y/m/d) between two dates | pure JDK |
| `date_add` | Add/subtract days, weeks, months, years | pure JDK |
| `hash` | MD5 / SHA-1 / SHA-256 / SHA-512 hex digest | pure JDK |
| `base64_encode` / `base64_decode` | Base64 round-trip | pure JDK |
| `generate_uuid` | Random v4 UUID | pure JDK |
| `generate_password` | Random password (optional symbols) | pure JDK |

All HTTP-backed tools use free, no-API-key public endpoints, so the server runs out of the box.

## Requirements

- Java 21+
- Maven 3.6.3+

## Build

```bash
mvn clean package
```

Produces `target/utility-tools-mcp-0.0.1.jar` (an executable fat jar).

## Run / test

### MCP Inspector (quickest manual check)

```bash
npx @modelcontextprotocol/inspector java -jar target/utility-tools-mcp-0.0.1.jar
```

Then in the Inspector: list tools, and try e.g. `geocode("Hanoi")` → feed the coordinates into
`get_weather`, or `convert_currency(100, "USD", "VND")`.

### Register with Claude Code

```bash
claude mcp add java-utils -- java -jar /abs/path/to/target/utility-tools-mcp-0.0.1.jar
```

### Register with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "java-utils": {
      "command": "java",
      "args": ["-jar", "C:\\abs\\path\\to\\target\\utility-tools-mcp-0.0.1.jar"]
    }
  }
}
```

## Notes

- **stdio gotcha:** stdout is the JSON-RPC channel. The app therefore disables the banner and
  console logging and writes logs to `./mcp-server.log` (see `application.properties`). Never
  `System.out.println` from tool code.
- **Adding a tool:** create a `@Component` with `@Tool`/`@ToolParam` methods, then add it to the
  `toolObjects(...)` list in
  [`ToolConfig`](src/main/java/com/dshouse/mcp/server/config/ToolConfig.java).

## Project layout

```
src/main/java/com/dshouse/mcp/server/
├── McpServerApplication.java       # Spring Boot entry point
├── config/ToolConfig.java          # registers all tools into one ToolCallbackProvider
├── weather/{OpenMeteoClient,WeatherTools}.java
├── geo/GeocodingTools.java
├── currency/{CurrencyClient,CurrencyTools}.java
├── time/TimeTools.java
└── util/{UnitConverterTools,DateTools,CryptoTools}.java
```

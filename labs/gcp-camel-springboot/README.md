# Apache Camel + Google Pub/Sub — DLQ Error Handling Demo

A Spring Boot project demonstrating **Dead Letter Queue (DLQ) error handling** using Apache Camel's EIP patterns with Google Pub/Sub as the messaging backbone.

## Message Flow

```
POST /api/orders
      │
      ▼
 orders-topic (Pub/Sub)
      │
      ▼
 OrderConsumerRoute
      │
      ├── success ──► log "processed OK"
      │
      └── fail (~30%) ──► retry x3 (exponential backoff: 500ms → 1s → 2s)
                                │
                                └── exhausted ──► orders-dlq (Pub/Sub)
                                                        │
                                                        ▼
                                                 DLQConsumerRoute
                                                 (stored in memory)
                                                        │
                                          POST /api/recovery/{orderId}
                                                        │
                                                        ▼
                                            re-publish ──► orders-topic
```

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Spring Boot 3.4.5, Java 21 |
| Integration | Apache Camel 4.10.3 |
| Messaging | Google Cloud Pub/Sub (`camel-google-pubsub`) |
| Local infra | Pub/Sub Emulator via Docker |

## Project Structure

```
gcp-camel-springboot/
├── docker-compose.yml                        # Pub/Sub emulator (port 8085)
├── scripts/
│   └── setup-pubsub.sh                       # Creates topics + subscriptions
├── pom.xml
└── src/main/java/com/dshouse/camel/
    ├── CamelPubSubApplication.java
    ├── config/
    │   └── PubSubEmulatorConfig.java         # Wires emulator host at startup
    ├── model/
    │   └── Order.java
    ├── processor/
    │   ├── OrderProcessor.java               # Fails ~30% to trigger DLQ
    │   └── DLQProcessor.java                 # Stores dead-lettered orders
    └── routes/
        ├── OrderProducerRoute.java           # REST → Pub/Sub publish
        ├── OrderConsumerRoute.java           # Pub/Sub consume + retry + DLQ
        └── DLQConsumerRoute.java             # DLQ sink + recovery endpoints
```

## Prerequisites

- Java 21+
- Maven 3.9+
- Docker

## Running Locally

**1. Start the Pub/Sub emulator**

```bash
docker compose up -d
```

**2. Create topics and subscriptions**

```bash
chmod +x scripts/setup-pubsub.sh
./scripts/setup-pubsub.sh
```

This creates:

| Resource | Type |
|---|---|
| `orders-topic` | Topic — receives new orders |
| `orders-sub` | Subscription on `orders-topic` |
| `orders-dlq` | Topic — receives failed orders |
| `orders-dlq-sub` | Subscription on `orders-dlq` |

**3. Start the application**

```bash
mvn spring-boot:run
```

The app starts on `http://localhost:8080`.

Once running, open **Swagger UI** at:
```
http://localhost:8080/swagger-ui/index.html
```
The raw OpenAPI spec (generated from Camel REST DSL) is at:
```
http://localhost:8080/api/api-docs
```

## API Reference

### Publish an order

```bash
POST /api/orders
Content-Type: application/json

{
  "id": "order-1",
  "product": "laptop",
  "amount": 1500
}
```

### List orders in the DLQ

```bash
GET /api/recovery
```

### Recover (re-queue) a dead-lettered order

```bash
POST /api/recovery/{orderId}
```

## Demo Walkthrough

```bash
# 1. Publish 10 orders — roughly 3 will end up in the DLQ
for i in {1..10}; do
  curl -s -X POST http://localhost:8080/api/orders \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"order-$i\",\"product\":\"item-$i\",\"amount\":$((i*100))}"
  echo ""
done

# 2. Check which orders are waiting in the DLQ
curl -s http://localhost:8080/api/recovery | jq .

# 3. Recover a specific order (replace order-3 with an actual failed ID)
curl -s -X POST http://localhost:8080/api/recovery/order-3
```

### Expected log output

```
[order-consumer] Processing order: order-3
[order-consumer] WARN  Retry attempt 1 failed for order: order-3 — Simulated transient failure
[order-consumer] WARN  Retry attempt 2 failed for order: order-3 — Simulated transient failure
[order-consumer] WARN  Retry attempt 3 failed for order: order-3 — Simulated transient failure
[dlq-consumer]   [DLQ] Dead-lettered order stored: order-3 | Total in DLQ: 1
[order-recovery] [RECOVERY] Re-publishing order order-3 to orders-topic
[order-consumer] Order order-3 processed successfully — status: PROCESSED
```

## Key Camel Concepts Demonstrated

| Concept | Where |
|---|---|
| **Dead Letter Channel** | `OrderConsumerRoute` — `errorHandler(deadLetterChannel(...))` |
| **Exponential backoff** | 3 retries: 500ms → 1s → 2s before DLQ routing |
| **Content routing** | `DLQConsumerRoute` — choice between 404 and success path |
| **REST DSL** | Producer and recovery endpoints via `rest(...)` |
| **Marshal / Unmarshal** | JSON serialization with `camel-jackson` |

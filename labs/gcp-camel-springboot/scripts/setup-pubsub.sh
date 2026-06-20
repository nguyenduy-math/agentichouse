#!/usr/bin/env bash
# Creates Pub/Sub topics and subscriptions on the local emulator.
# Run once after `docker compose up -d` and before starting the app.

set -euo pipefail

BASE_URL="http://localhost:8085"
PROJECT="local-project"

echo "Waiting for Pub/Sub emulator to be ready..."
until curl -sf "${BASE_URL}" > /dev/null 2>&1; do
  sleep 1
done
echo "Emulator is up."

create_topic() {
  local topic=$1
  echo "Creating topic: ${topic}"
  curl -sf -X PUT "${BASE_URL}/v1/projects/${PROJECT}/topics/${topic}" \
    -H "Content-Type: application/json" \
    -d '{}' > /dev/null
  echo "  -> ${topic} OK"
}

create_subscription() {
  local sub=$1
  local topic=$2
  echo "Creating subscription: ${sub} -> ${topic}"
  curl -sf -X PUT "${BASE_URL}/v1/projects/${PROJECT}/subscriptions/${sub}" \
    -H "Content-Type: application/json" \
    -d "{\"topic\": \"projects/${PROJECT}/topics/${topic}\", \"ackDeadlineSeconds\": 30}" > /dev/null
  echo "  -> ${sub} OK"
}

create_topic "orders-topic"
create_topic "orders-dlq"

create_subscription "orders-sub"     "orders-topic"
create_subscription "orders-dlq-sub" "orders-dlq"

echo ""
echo "Setup complete. Resources created in project '${PROJECT}':"
echo "  Topics       : orders-topic, orders-dlq"
echo "  Subscriptions: orders-sub, orders-dlq-sub"

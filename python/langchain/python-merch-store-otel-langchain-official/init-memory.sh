#!/usr/bin/env bash
# Create the long-term-memory search index in the Agent Memory Server.
#
# AMS only creates the `memory_records` index on the first *write* to long-term
# memory, but this app *searches* (hydrate) before it writes — so on a fresh Redis
# the first search fails with "No such index". Run this once after bringing the
# stack up (and again after any `docker compose down -v`, which wipes the volume).
set -euo pipefail
cd "$(dirname "$0")"

echo "Waiting for the Agent Memory Server to be healthy..."
until curl -sf http://localhost:8000/v1/health >/dev/null 2>&1; do sleep 1; done

echo "Creating the long-term memory index..."
docker compose exec -T agent-memory-server agent-memory rebuild-index

echo "Long-term memory index ready."

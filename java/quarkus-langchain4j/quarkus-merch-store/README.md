# Quarkus Merch Store — Step 01

A Quarkus application that exposes an AI-powered chat assistant for a Quarkus merchandise store. Built with **Quarkus LangChain4j** and the **Anthropic Claude** model, it demonstrates tool calling, in-memory conversation history, and OpenTelemetry observability.

## Architecture

```
Client  ──POST /api/chat──►  ChatResource
                                    │
                                    ▼
                             Quarkus LangChain4j AiService
                             (Anthropic Claude)
                                    │
                              tool calling
                                    │
                                    ▼
                                ChatTools
                         (inventory + order tools)
```

- **`ChatResource`** — REST endpoint at `POST /api/chat`. Maintains per-conversation memory using `@MemoryId`.
- **`ChatAssistant`** — `@RegisterAiService` interface that defines the system prompt and chat methods (sync + streaming).
- **`ChatTools`** — CDI bean exposing `@Tool`-annotated methods to the LLM:
  - `listAllItems` — lists the full inventory
  - `getItemStock` — checks stock for a specific item
  - `displayMerchImages` — returns visual product card data
  - `placeOrder` — places a confirmed order
- **OpenTelemetry / Micrometer** — exports JVM metrics, HTTP traces, and logs via OTLP.

## Prerequisites

- Java 21+
- Maven 3.9+
- An Anthropic API key

## Running the Application

```bash
export ANTHROPIC_API_KEY=sk-ant-...
./mvnw quarkus:dev
```

The application starts on port `8080`.

## Chat API

**Endpoint:** `POST /api/chat`

**Request body:**
```json
{
  "conversationId": "<string>",
  "message": "<string>"
}
```

- `conversationId` — an arbitrary string used to scope conversation memory. Use the same value across requests to maintain context.
- `message` — the user's message to the assistant.

**Response body:**
```json
{
  "response": "<string>"
}
```

## curl Examples

### List all available merch

```bash
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversationId": "session-1", "message": "What items do you have in stock?"}' | jq .
```

### Check stock for a specific item

```bash
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversationId": "session-1", "message": "How many Quarkus T-Shirts are available?"}' | jq .
```

### Browse items for a specific project

```bash
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversationId": "session-1", "message": "Show me all Quarkus LangChain4j merch"}' | jq .
```

### Add items to order (multi-turn conversation)

```bash
# Turn 1
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversationId": "order-session", "message": "I want 2 Quarkus T-Shirts and 3 Quarkus LangChain4j Stickers"}' | jq .

# Turn 2 — confirm the order (same conversationId keeps context)
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"conversationId": "order-session", "message": "Yes, please place the order"}' | jq .
```

## Observability

The application is pre-configured for OpenTelemetry:

- **Tracing** — exports traces via OTLP to `${OTEL_EXPORTER_OTLP_ENDPOINT}`. All chat client prompts and completions are traced.
- **Metrics** — JVM and HTTP metrics exported via Micrometer OTLP registry.
- **Logs** — OpenTelemetry log appender exports application logs to OTLP.

## Tech Stack

| Component | Version |
|---|---|
| Quarkus Platform | 3.31.2 |
| Quarkus LangChain4j | 1.7.1 |
| LLM Provider | Anthropic Claude |
| Java | 21 |
| Observability | OpenTelemetry / Micrometer |

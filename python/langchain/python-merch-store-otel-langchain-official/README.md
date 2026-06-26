# Python Merch Store (Otel Langchain + Redis Agent Memory Server)

**Note:** This version of the application is using the [official OpenTelemetry GenAI LangChain Instrumentation](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai/opentelemetry-instrumentation-langchain)

> **Fork note:** Adapted for the *"Stateful and Observable Agents"* talk from
> [salaboy/observing-ai](https://github.com/salaboy/observing-ai) (`python-merch-store-otel-langchain-official`,
> upstream commit `f08fcbd`). The one functional change is **memory**: the original used
> LangGraph's in-process, volatile `MemorySaver`; this version uses the
> [Redis Agent Memory Server](https://github.com/redis/agent-memory-server) for persistent,
> cross-session memory. See **[Memory (Redis Agent Memory Server)](#memory-redis-agent-memory-server)**.

An AI-powered merch store chatbot for Python community projects. Chat with the store assistant to browse T-Shirts, Socks, and Stickers from projects like NumPy, Pandas, PyTorch, TensorFlow, LangChain, and more. The assistant can look up inventory, show product cards, and place orders on your behalf.

Built with [LangChain](https://docs.langchain.com) + [LangGraph](https://langchain-ai.github.io/langgraph/) for the AI agent, [Claude](https://docs.anthropic.com) as the LLM, [FastAPI](https://fastapi.tiangolo.com) for the backend, and a React/TypeScript frontend with a retro Windows 95 theme toggle.



## Architecture

```
┌─────────────────────────────────────────────┐
│  React Frontend (webapp/)                   │
│  - Chat UI with streaming messages          │
│  - Merch card rendering from <merch-items>  │
│  - Order confirmation display               │
│  - Modern / Retro theme toggle              │
└────────────────┬────────────────────────────┘
                 │ POST /api/chat/stream (SSE)
                 │ POST /api/chat
┌────────────────▼────────────────────────────┐
│  FastAPI (app/main.py)                      │
│  - Serves API + built static files          │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│  LangGraph ReAct Agent (app/agent.py)       │
│  - Claude model + system prompt             │
│  - Built per request (app/memory.py)         │
│  - 4 store tools + AMS memory tools          │
└──────┬──────────────────────────┬────────────┘
       │                          │ HTTP
       │                ┌─────────▼─────────────────────┐
       │                │ Redis Agent Memory Server      │
       │                │ - Working memory (this chat)   │
       │                │ - Long-term memory (this user) │
       │                │   → backed by Redis            │
       │                └────────────────────────────────┘
┌──────▼────────────────────────────────────────┐
│  In-Memory Inventory (app/inventory.py)        │
│  - 30 merch items across 11 Python projects    │
└────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Docker (to run the Redis Agent Memory Server + Redis)
- An [Anthropic API key](https://console.anthropic.com/) — for the agent (Claude)
- An [OpenAI API key](https://platform.openai.com/) — used by the memory server for embeddings + fact extraction

### Installing Python on macOS

If you install Python via Homebrew, `pip` is not included by default. Use a virtual environment instead, which is the recommended approach:

```bash
brew install python

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate
```

Once the virtual environment is active, `pip` is available and all packages will be installed locally to the project. You'll see `(.venv)` in your shell prompt.

> **Note:** Run `source .venv/bin/activate` each time you open a new terminal before working with the project.

## Setup

### 1. Build the React frontend

```bash
cd webapp
npm install
npm run build
cd ..
```

This compiles the TypeScript and bundles the React app into the `static/` directory, which FastAPI serves automatically.

### 2. Install Python dependencies

```bash
pip install --pre -e .
```

### 3. Set your API keys

```bash
export ANTHROPIC_API_KEY=your-anthropic-key   # the agent (Claude)
export OPENAI_API_KEY=your-openai-key         # the memory server (embeddings + extraction)
```

### 4. Start the memory backend (Redis + AMS)

```bash
docker compose up -d        # starts Redis + the Agent Memory Server on :8000
./init-memory.sh            # creates the long-term memory search index (once per fresh Redis)
```

> **Why `init-memory.sh`?** AMS only creates the `memory_records` search index on the first
> *write* to long-term memory, but this app *searches* before it writes — so on a brand-new Redis
> the first search would fail with *"No such index"*. The script runs `agent-memory rebuild-index`
> to create it up front. The index lives in the Redis volume, so you only need this once — and
> again after any `docker compose down -v` (which wipes the volume).
>
> **Changed a key or setting in `.env`?** A running container keeps its original environment.
> Recreate it: `docker compose up -d --force-recreate agent-memory-server`.

### 5. Run the application

```bash
python -m app.main
```

The server starts on **http://localhost:8080**. Open it in your browser to use the chat UI.

## Memory (Redis Agent Memory Server)

This demo's memory is provided by the [Redis Agent Memory Server](https://github.com/redis/agent-memory-server)
(AMS) instead of LangGraph's in-process `MemorySaver`. The agent now has two tiers of memory,
both backed by Redis:

| Tier | Scope | Key | What it gives the demo |
|------|-------|-----|------------------------|
| **Working memory** | one chat | `conversation_id` | Conversation history that survives an app restart |
| **Long-term memory** | one shopper, across chats | `user_id` | Recalls a returning customer's preferences and past orders |

### How it's wired (`app/memory.py`, `app/agent.py`, `app/main.py`)

On every turn the FastAPI endpoint:

1. **Hydrates** the prompt — `client.memory_prompt(...)` asks AMS for the conversation history
   plus the most relevant long-term memories for this `user_id`, returned as ready-to-send messages.
2. **Runs** a per-request ReAct agent (no LangGraph checkpointer — AMS is the source of truth). The
   agent also gets AMS tools (`search_memory`, `eagerly_create_long_term_memory`, `get_current_datetime`)
   so it can deliberately recall/store facts.
3. **Persists** the turn — `client.append_messages_to_working_memory(...)`. AMS extracts durable
   facts in the background and promotes them to long-term memory.

`user_id` is the cross-session key. It defaults to `DEFAULT_USER_ID` (`merch-shopper`) server-side,
so starting a **new chat** (new `conversation_id`, same `user_id`) still recalls past preferences —
no frontend change needed.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_MEMORY_URL` | `http://localhost:8000` | Base URL of the Agent Memory Server |
| `DEFAULT_USER_ID` | `merch-shopper` | Cross-session identity when the request omits `user_id` |
| `AGENT_MEMORY_NAMESPACE` | `merch-store` | Logical grouping for this demo's memories |
| `LONG_TERM_RECALL_LIMIT` | `6` | Long-term memories injected into each turn |

> AMS uses **OpenAI** for embeddings and background fact extraction even though the agent itself
> uses Claude — hence both API keys. If AMS is unreachable, the app degrades gracefully (it falls
> back to a stateless turn and logs a warning) so a live demo won't crash.

### Demo script (goldfish → elephant)

1. `docker compose up -d` then `python -m app.main`.
2. **Chat A:** *"Hi, I'm really into PyTorch and I prefer stickers over t-shirts."* Browse and place an order.
3. **Restart the app** (`Ctrl-C`, rerun `python -m app.main`). Working memory is in Redis, not process memory.
4. **New chat (same user):** *"What do you remember about me?"* → the assistant recalls PyTorch + the
   sticker preference from long-term memory.
5. **Observability tie-in:** open your traces and show the agent run, tool calls, and the AMS HTTP
   calls as spans. You can also open **RedisInsight** at http://localhost:8001 to show the memories in Redis.

## Docker

The multi-stage Dockerfile builds the React frontend and installs Python dependencies in a single image — no local Python or Node.js required.

### Build the image

```bash
docker build -t python-merch-store .
```

### Push to a container registry

Tag the image for your registry and push it. Replace `your-registry.com/your-org` with your actual registry URL (e.g. Docker Hub, GitHub Container Registry, AWS ECR, Google Artifact Registry):

```bash
# Docker Hub
docker tag python-merch-store your-dockerhub-user/python-merch-store:latest
docker push your-dockerhub-user/python-merch-store:latest

# GitHub Container Registry
docker tag python-merch-store ghcr.io/your-org/python-merch-store:latest
docker push ghcr.io/your-org/python-merch-store:latest
```

You may need to authenticate first with `docker login` (Docker Hub) or `echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin` (GHCR).

### Run the container

Minimal run (no observability):

```bash
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=your-key-here \
  python-merch-store
```

With Dash0 observability:

```bash
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=your-key-here \
  -e OTEL_SERVICE_NAME=python-merch-store \
  -e OTEL_EXPORTER_OTLP_ENDPOINT=<your-dash0-endpoint> \
  -e OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION=<your-dash0-auth-token> \
  -e DASH0_DATASET=<your-dash0-dataset> \
  -e 'OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <your-dash0-auth-token>,Dash0-Dataset=<your-dash0-dataset>' \
  python-merch-store
```

The server starts on **http://localhost:8080**.

## Development

To develop the frontend with hot-reload, run the Vite dev server and the Python backend separately:

**Terminal 1 -- Python backend:**

```bash
python -m app.main
```

**Terminal 2 -- Vite dev server:**

```bash
cd webapp
npm run dev
```

The Vite dev server runs on http://localhost:5173 and proxies `/api` requests to `http://localhost:8080`.

## Observability with Dash0

The application is instrumented with [OpenTelemetry](https://opentelemetry.io/) using the official [`opentelemetry-instrumentation-langchain`](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai/opentelemetry-instrumentation-langchain) package from the OpenTelemetry Python Contrib project. This automatically traces all LangChain/LangGraph operations — LLM calls, tool invocations, and agent reasoning steps — and exports them via OTLP.

To send telemetry data to [Dash0](https://www.dash0.com/), set the following environment variables before starting the application:

```bash
export OTEL_SERVICE_NAME=python-merch-store
export OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION=<your-dash0-auth-token>
export DASH0_DATASET=<your dash0 dataset>
export OTEL_EXPORTER_OTLP_ENDPOINT=<your-dash0-endpoint>
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer ${OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION},Dash0-Dataset=${DASH0_DATASET}"

```

| Variable | Description |
|----------|-------------|
| `OTEL_SERVICE_NAME` | Identifies this service in Dash0 (e.g. `python-merch-store`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Dash0 OTLP ingestion endpoint |
| `OTEL_EXPORTER_OTLP_HEADERS` | Auth and dataset headers sent with every OTLP request |
| `OTEL_EXPORTER_OTLP_HEADERS_AUTHORIZATION` | Your Dash0 API auth token (found in Dash0 settings) |
| `DASH0_DATASET` | Dash0 dataset to route data to (use `default` if unsure) |

To disable prompt/completion content capture for privacy, set:

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Synchronous chat -- returns the full response |
| `POST` | `/api/chat/stream` | Streaming chat via Server-Sent Events |

Both endpoints accept:

```json
{
  "conversation_id": "unique-session-id",
  "message": "What NumPy merch do you have?"
}
```

## Project Structure

```
python-merch-store/
├── app/
│   ├── main.py          # FastAPI app, API routes, static file serving
│   ├── agent.py         # LangGraph agent with Claude, tools, and system prompt
│   ├── tools.py         # 4 tool functions (stock, display, order, list)
│   ├── inventory.py     # In-memory inventory (30 items, 11 projects)
│   ├── memory.py        # Redis Agent Memory Server integration (hydrate/persist + tools)
│   └── models.py        # Pydantic models (MerchItem, OrderLine, ChatRequest, etc.)
├── webapp/              # React/TypeScript frontend source
│   ├── src/
│   │   ├── App.tsx      # Main chat UI component
│   │   └── main.tsx     # Entry point
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── static/              # Built frontend (generated by npm run build)
├── pyproject.toml
└── README.md
```

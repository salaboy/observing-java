import os
from pathlib import Path

# Load .env (if present) before anything reads env vars — API keys and OTEL_* settings.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sse_starlette.sse import EventSourceResponse

# Configure OpenTelemetry SDK — reads OTEL_SERVICE_NAME,
# OTEL_EXPORTER_OTLP_ENDPOINT, and OTEL_EXPORTER_OTLP_HEADERS from env.
resource = Resource.create()
provider = TracerProvider(resource=resource)
# Only export spans when an OTLP endpoint is configured. Without this guard the
# exporter defaults to localhost:4318 and floods the log with connection-refused
# retries whenever no collector is running.
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

LangChainInstrumentor().instrument()
AnthropicInstrumentor().instrument()

from app.agent import build_agent  # noqa: E402 — must import after instrumentation
from app.memory import (  # noqa: E402
    DEFAULT_USER_ID,
    hydrate_messages,
    persist_turn,
)
from app.models import ChatRequest, ChatResponse

app = FastAPI(title="Python Merch Store - LangChain")
FastAPIInstrumentor.instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _extract_text(content: str | list) -> str:
    """Extract plain text from an AI message content field."""
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") if isinstance(block, dict) else str(block)
        for block in content
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    user_id = request.user_id or DEFAULT_USER_ID

    # Load conversation history + relevant long-term memories from Redis (AMS).
    messages = await hydrate_messages(request.conversation_id, user_id, request.message)
    agent = build_agent(request.conversation_id, user_id)

    result = await agent.ainvoke({"messages": messages})
    reply = _extract_text(result["messages"][-1].content)

    # Persist the turn; the server promotes durable facts to long-term in the background.
    await persist_turn(request.conversation_id, user_id, request.message, reply)
    return ChatResponse(response=reply)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    user_id = request.user_id or DEFAULT_USER_ID
    messages = await hydrate_messages(request.conversation_id, user_id, request.message)
    agent = build_agent(request.conversation_id, user_id)

    async def event_generator():
        parts: list[str] = []
        async for event in agent.astream_events(
            {"messages": messages},
            version="v2",
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    text = _extract_text(chunk.content)
                    if text:
                        parts.append(text)
                        yield {"data": text}

        # Persist the full turn once streaming completes.
        await persist_turn(
            request.conversation_id, user_id, request.message, "".join(parts)
        )

    return EventSourceResponse(event_generator())


# Serve the React frontend (built files from webapp/)
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve static files or fall back to index.html for SPA routing."""
        file = STATIC_DIR / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)

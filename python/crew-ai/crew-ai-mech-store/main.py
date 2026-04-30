import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sse_starlette.sse import EventSourceResponse

# Disable CrewAI's built-in telemetry so it doesn't override our TracerProvider.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

# Configure OpenTelemetry SDK — reads OTEL_SERVICE_NAME,
# OTEL_EXPORTER_OTLP_ENDPOINT, and OTEL_EXPORTER_OTLP_HEADERS from env.
resource = Resource.create()
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

AnthropicInstrumentor().instrument()

from agent import create_crew_for_message  # noqa: E402 — must import after instrumentation
from memory import memory  # noqa: E402
from models import ChatRequest, ChatResponse  # noqa: E402

app = FastAPI(title="Python Merch Store - CrewAI")
FastAPIInstrumentor.instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    history_text = memory.format_history_for_task(request.conversation_id)
    crew = create_crew_for_message(request.message, history_text)

    result = crew.kickoff()
    response_text = result.raw

    memory.add_message(request.conversation_id, "user", request.message)
    memory.add_message(request.conversation_id, "assistant", response_text)

    return ChatResponse(response=response_text)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> EventSourceResponse:
    history_text = memory.format_history_for_task(request.conversation_id)
    crew = create_crew_for_message(request.message, history_text, stream=True)

    async def event_generator():
        full_response = ""
        streaming_output = await crew.akickoff()

        async for chunk in streaming_output:
            if chunk.chunk_type.value == "text" and chunk.content:
                full_response += chunk.content
                yield {"data": chunk.content}

        memory.add_message(request.conversation_id, "user", request.message)
        memory.add_message(request.conversation_id, "assistant", full_response)

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
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

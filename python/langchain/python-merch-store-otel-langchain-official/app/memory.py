"""Redis Agent Memory Server (AMS) integration.

This replaces LangGraph's in-process ``MemorySaver`` with the Redis Agent Memory
Server, giving the store assistant two tiers of persistent memory:

- **Working memory** — the conversation history for a chat session, stored in Redis
  so it survives process restarts (keyed by ``conversation_id``).
- **Long-term memory** — durable facts and preferences extracted from conversations,
  searchable across *all* of a user's sessions (keyed by ``user_id``).

The agent talks to AMS over HTTP via ``agent-memory-client``. AMS itself runs as a
separate service (see ``docker-compose.yml``).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from agent_memory_client import MemoryAPIClient, MemoryClientConfig
from agent_memory_client.integrations.langchain import get_memory_tools
from agent_memory_client.models import MemoryMessage

logger = logging.getLogger(__name__)

# --- Configuration -----------------------------------------------------------

AGENT_MEMORY_URL = os.getenv("AGENT_MEMORY_URL", "http://localhost:8000")

# Cross-session identity. ``conversation_id`` scopes one chat (working memory);
# ``user_id`` scopes everything we remember about a person (long-term memory).
# A brand-new chat with the same user_id is how we demo cross-session recall.
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "merch-shopper")

# Logical grouping for all memories created by this demo.
NAMESPACE = os.getenv("AGENT_MEMORY_NAMESPACE", "merch-store")

# How many relevant long-term memories to inject into each turn.
LONG_TERM_RECALL_LIMIT = int(os.getenv("LONG_TERM_RECALL_LIMIT", "6"))

# Long-term memory tools we expose to the agent so it can deliberately recall and
# store facts mid-conversation. Working memory is handled by the server for us.
AGENT_MEMORY_TOOLS = [
    "search_memory",
    "eagerly_create_long_term_memory",
    "get_current_datetime",
]

# A single shared async client for the process.
client = MemoryAPIClient(
    MemoryClientConfig(base_url=AGENT_MEMORY_URL, default_namespace=NAMESPACE)
)

# Map AMS / OpenAI-style roles to LangChain-native roles that LangGraph accepts
# regardless of langchain version.
_ROLE_MAP = {
    "user": "human",
    "human": "human",
    "assistant": "ai",
    "ai": "ai",
    "system": "system",
}


# --- Per-request helpers -----------------------------------------------------


def _content_to_text(content) -> str:
    """Flatten AMS message content to a plain string.

    ``memory_prompt`` may return content as a string, a single structured block
    (``{"type": "text", "text": ...}``), or a list of such blocks. LangChain's
    message classes want a plain string, so normalise everything here.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text", "") or ""
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content) if content is not None else ""


def memory_tools(conversation_id: str, user_id: str):
    """Build the AMS-backed LangChain tools bound to this session/user."""
    return get_memory_tools(
        memory_client=client,
        session_id=conversation_id,
        user_id=user_id,
        namespace=NAMESPACE,
        tools=AGENT_MEMORY_TOOLS,
    )


async def hydrate_messages(
    conversation_id: str, user_id: str, message: str
) -> list[dict[str, str]]:
    """Build the message list for the agent for this turn.

    Asks AMS to assemble: the working-memory conversation history + the most
    relevant long-term memories for this user (as system messages) + the new user
    message at the end. Returns a list of ``{"role", "content"}`` dicts that
    LangGraph accepts directly.

    Falls back to just the raw user message if AMS is unreachable, so a live demo
    degrades gracefully instead of crashing.
    """
    try:
        prompt = await client.memory_prompt(
            query=message,
            session_id=conversation_id,
            user_id=user_id,
            long_term_search={
                "limit": LONG_TERM_RECALL_LIMIT,
                "user_id": {"eq": user_id},
            },
        )

        print("===========")
        print("===========")
        print(prompt)
        print("===========")
        # Split into system context vs. conversation. AMS returns long-term
        # memories as a system message placed *after* the history; Anthropic
        # requires all system content to be consecutive, so we merge every
        # system message into one block at the front and keep the conversation
        # (ending with the user's query) after it.
        system_parts: list[str] = []
        conversation: list[dict[str, str]] = []
        for m in prompt.get("messages", []):
            if not isinstance(m, dict):
                continue
            text = _content_to_text(m.get("content"))
            if not text:
                continue
            role = _ROLE_MAP.get(m.get("role"), "human")
            if role == "system":
                system_parts.append(text)
            else:
                conversation.append({"role": role, "content": text})

        messages: list[dict[str, str]] = []
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.extend(conversation)
        if messages:
            return messages
    except Exception:  # pragma: no cover - demo resilience
        logger.warning("AMS hydrate failed; using bare user message", exc_info=True)

    return [{"role": "user", "content": message}]


async def persist_turn(
    conversation_id: str, user_id: str, user_message: str, assistant_message: str
) -> None:
    """Save the completed turn to AMS working memory.

    This both keeps the durable conversation history *and* triggers the server's
    background extraction, which promotes important facts to long-term memory.
    """
    try:
        now = datetime.now(UTC)
        await client.append_messages_to_working_memory(
            session_id=conversation_id,
            user_id=user_id,
            # Pass MemoryMessage objects (not dicts) so we can set created_at —
            # the dict path drops it, which triggers a deprecation warning and
            # loses correct message ordering when promoted to long-term memory.
            messages=[
                MemoryMessage(role="user", content=user_message, created_at=now),
                MemoryMessage(
                    role="assistant", content=assistant_message, created_at=now
                ),
            ],
        )
    except Exception:  # pragma: no cover - demo resilience
        logger.warning("AMS persist failed; turn not saved", exc_info=True)

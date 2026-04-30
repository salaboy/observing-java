from collections import defaultdict


class ConversationMemory:
    """In-memory conversation history keyed by conversation_id."""

    def __init__(self):
        self._history: dict[str, list[dict[str, str]]] = defaultdict(list)

    def get_history(self, conversation_id: str) -> list[dict[str, str]]:
        return self._history[conversation_id]

    def add_message(self, conversation_id: str, role: str, content: str):
        self._history[conversation_id].append({"role": role, "content": content})

    def format_history_for_task(self, conversation_id: str) -> str:
        """Format conversation history as text to inject into task description."""
        history = self._history[conversation_id]
        if not history:
            return ""
        lines = []
        for msg in history:
            prefix = "Customer" if msg["role"] == "user" else "You (assistant)"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)


memory = ConversationMemory()

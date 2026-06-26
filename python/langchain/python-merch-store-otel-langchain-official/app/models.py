from pydantic import BaseModel


class MerchItem(BaseModel):
    project_name: str
    type: str  # "T-Shirt", "Socks", "Sticker"
    quantity: int
    price: float
    logo_url: str

    @property
    def display_name(self) -> str:
        return f"{self.project_name} {self.type}"


class OrderLine(BaseModel):
    project_name: str
    type: str
    quantity: int


class ChatRequest(BaseModel):
    conversation_id: str
    message: str
    # Stable across chats; the cross-session key for long-term memory.
    # Defaults server-side to DEFAULT_USER_ID when the frontend doesn't send one.
    user_id: str | None = None


class ChatResponse(BaseModel):
    response: str

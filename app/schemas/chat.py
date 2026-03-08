"""Pydantic schemas for request/response validation."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import MessageRole

# ── Chat / Stream ─────────────────────────────────────────────────────────────


_MAX_MESSAGE_LENGTH = 32_000  # ~8k tokens


class ChatRequest(BaseModel):
    session_id: uuid.UUID = Field(..., description="UUID of the chat session")
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Identifier of the requesting user",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_MESSAGE_LENGTH,
        description="User message text",
    )


# ── Session history ───────────────────────────────────────────────────────────


class MessageOut(BaseModel):
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionHistoryOut(BaseModel):
    session_id: uuid.UUID
    messages: list[MessageOut]

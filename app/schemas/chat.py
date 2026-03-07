"""Pydantic schemas for request/response validation."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import MessageRole

# ── Chat / Stream ─────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    session_id: uuid.UUID = Field(..., description="UUID of the chat session")
    user_id: str = Field(..., description="Identifier of the requesting user")
    message: str = Field(..., min_length=1, description="User message text")


# ── Session history ───────────────────────────────────────────────────────────


class MessageOut(BaseModel):
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionHistoryOut(BaseModel):
    session_id: uuid.UUID
    messages: list[MessageOut]

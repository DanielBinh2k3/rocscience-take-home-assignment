"""Integration tests for chat — verify messages are persisted to the database."""

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.models import ChatMessage, ChatSession, MessageRole
from app.utils.serializer import make_sse_event


async def _mock_agent_stream(*, session_id: uuid.UUID, reply: str):
    """Fake agent stream that yields SSE events and fills result_holder."""
    for char in reply:
        yield make_sse_event("agent.message.delta", {"text": char})
    yield make_sse_event("agent.message.done", {"session_id": str(session_id)})


@pytest_asyncio.fixture
def mock_agent_for_persistence():
    """Patch agent.stream_response to return a controlled reply without calling LLM."""
    with patch("app.api.v1.chat.agent") as mock_agent:

        async def _stream(user_message, history, session_id, result_holder=None):
            reply = "This is the assistant reply."
            async for chunk in _mock_agent_stream(session_id=session_id, reply=reply):
                yield chunk
            if result_holder is not None:
                result_holder.clear()
                result_holder.append(reply)

        mock_agent.stream_response = _stream
        yield mock_agent


@pytest.mark.asyncio
async def test_messages_persisted_after_chat_turn(
    test_client,
    db_session,
    mock_agent_for_persistence,
    sample_session_id: uuid.UUID,
    sample_user_id: str,
):
    """Integration test: user message and assistant reply are correctly persisted."""
    user_message = "What is 2 + 2?"
    response = await test_client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": str(sample_session_id),
            "user_id": sample_user_id,
            "message": user_message,
        },
    )

    assert response.status_code == 200

    # Verify session was created
    session_result = await db_session.execute(
        select(ChatSession).where(
            ChatSession.id == sample_session_id,
            ChatSession.user_id == sample_user_id,
        )
    )
    session = session_result.scalar_one_or_none()
    assert session is not None

    # Verify messages were persisted (user + assistant)
    messages_result = await db_session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == sample_session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = list(messages_result.scalars().all())

    assert len(messages) == 2

    user_msg = messages[0]
    assert user_msg.role == MessageRole.user
    assert user_msg.content == user_message
    assert user_msg.session_id == sample_session_id

    assistant_msg = messages[1]
    assert assistant_msg.role == MessageRole.assistant
    assert assistant_msg.content == "This is the assistant reply."
    assert assistant_msg.session_id == sample_session_id

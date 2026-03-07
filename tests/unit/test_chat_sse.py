"""Unit tests for chat SSE stream — verify event order with mocked agent."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.utils.serializer import make_sse_event


async def _mock_agent_stream(*, delta_chunks: list[str], session_id: uuid.UUID):
    """Fake agent stream that yields SSE events in the expected order."""
    for chunk in delta_chunks:
        yield make_sse_event("agent.message.delta", {"text": chunk})
    yield make_sse_event("agent.message.done", {"session_id": str(session_id)})


@pytest_asyncio.fixture
async def mock_agent_stream():
    """Patch agent.stream_response to return controlled events (async generator)."""
    with patch("app.api.v1.chat.agent") as mock_agent:
        # Use MagicMock so calling stream_response() returns our async gen directly
        # (AsyncMock would return a coroutine, but we need async for to receive an async iterator)
        mock_agent.stream_response = MagicMock()
        yield mock_agent.stream_response


@pytest_asyncio.fixture
async def mock_repositories():
    """Patch SessionRepository and MessageRepository so no real DB calls are made."""
    with (
        patch("app.api.v1.chat.SessionRepository") as mock_sessions_cls,
        patch("app.api.v1.chat.MessageRepository") as mock_messages_cls,
    ):
        mock_sessions = mock_sessions_cls.return_value
        mock_messages = mock_messages_cls.return_value

        async def get_or_create(session_id, user_id):
            session = MagicMock()
            session.id = session_id
            return session

        mock_sessions.get_or_create = AsyncMock(side_effect=get_or_create)
        mock_messages.create = AsyncMock(return_value=MagicMock())
        mock_messages.list_by_session = AsyncMock(return_value=[])

        yield mock_sessions, mock_messages


@pytest_asyncio.fixture
async def test_client_no_db(mock_repositories):
    """Async client with mocked DB — for unit tests we mock agent and repositories."""
    from app.db.database import get_db

    async def _fake_db():
        from sqlalchemy.ext.asyncio import AsyncSession

        session = AsyncMock(spec=AsyncSession)
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = lambda x: None
        session.execute = AsyncMock()
        session.rollback = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = _fake_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _parse_sse_events(response_text: str) -> list[tuple[str, str]]:
    """Parse SSE response into list of (event, data) tuples."""
    events = []
    current_event = None
    current_data = []
    for line in response_text.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data.append(line[6:])
        elif line == "" and current_event is not None:
            data = "\n".join(current_data) if current_data else ""
            events.append((current_event, data))
            current_event = None
            current_data = []
    return events


@pytest.mark.asyncio
async def test_sse_events_emitted_in_correct_order(
    test_client_no_db: AsyncClient,
    mock_agent_stream: MagicMock,
    sample_session_id: uuid.UUID,
    sample_user_id: str,
):
    """Unit test: SSE events are emitted in correct order (deltas first, then done)."""
    delta_chunks = ["Hello", " ", "world", "!"]
    mock_agent_stream.return_value = _mock_agent_stream(
        delta_chunks=delta_chunks,
        session_id=sample_session_id,
    )

    response = await test_client_no_db.post(
        "/api/v1/chat/stream",
        json={
            "session_id": str(sample_session_id),
            "user_id": sample_user_id,
            "message": "Hi",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    body = response.text
    events = _parse_sse_events(body)

    # Must have: N delta events + 1 done event (heartbeats may appear between)
    event_types = [e[0] for e in events]
    assert "agent.message.delta" in event_types
    assert "agent.message.done" in event_types

    # Deltas must appear before done
    delta_indices = [i for i, t in enumerate(event_types) if t == "agent.message.delta"]
    done_indices = [i for i, t in enumerate(event_types) if t == "agent.message.done"]
    assert all(di < max(done_indices) for di in delta_indices)

    # Verify delta payloads match
    import json

    delta_events = [e for e in events if e[0] == "agent.message.delta"]
    concatenated = "".join(json.loads(data)["text"] for _, data in delta_events)
    assert concatenated == "Hello world!"

    # Verify done payload contains session_id
    done_events = [e for e in events if e[0] == "agent.message.done"]
    assert len(done_events) >= 1
    done_data = json.loads(done_events[-1][1])  # [1] is the data string
    assert done_data["session_id"] == str(sample_session_id)

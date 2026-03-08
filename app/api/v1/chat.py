"""POST /api/v1/chat/stream endpoint."""

import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent import agent
from app.db.crud import MessageRepository, SessionOwnershipError, SessionRepository
from app.db.database import AsyncSessionLocal, get_db
from app.db.models import ChatSession, MessageRole
from app.schemas.chat import ChatRequest
from app.utils.serializer import make_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()

_HEARTBEAT_INTERVAL = 15  # seconds
_STREAM_TIMEOUT = 120  # seconds — hard limit per stream
# Keep the last N *turns* (user + assistant pairs) worth of messages in context.
_MAX_HISTORY_MESSAGES = 20


async def _persist_assistant_reply(
    session_id: uuid.UUID, result_holder: list[str]
) -> None:
    """Background task: persist the assistant reply using a dedicated DB session."""
    full_reply = result_holder[0] if result_holder else ""
    content = full_reply if full_reply else "[Phản hồi bị gián đoạn — vui lòng thử lại]"
    async with AsyncSessionLocal() as db:
        try:
            messages = MessageRepository(db)
            await messages.create(session_id, MessageRole.assistant, content)
            await db.commit()
        except Exception:
            logger.exception(
                "Failed to persist assistant reply for session %s", session_id
            )


async def _event_stream(
    request: ChatRequest,
    db: AsyncSession,
    session: ChatSession,
    result_holder: list[str],
):
    """Core SSE generator: persists user message, streams agent output, emits heartbeats."""
    messages = MessageRepository(db)

    # 1. Persist user message BEFORE calling agent
    await messages.create(session.id, MessageRole.user, request.message)
    await db.commit()

    # 2. Fetch conversation history for context (exclude the message just persisted).
    # Truncate to the most recent _MAX_HISTORY_MESSAGES to avoid overflowing the
    # model's context window on long-lived sessions.
    history_rows = await messages.list_by_session(session.id)
    prior_rows = history_rows[:-1]  # exclude the user message just saved
    if len(prior_rows) > _MAX_HISTORY_MESSAGES:
        prior_rows = prior_rows[-_MAX_HISTORY_MESSAGES:]
    history = [{"role": row.role, "content": row.content} for row in prior_rows]

    # 3. Stream agent response with concurrent heartbeat
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                await queue.put(make_sse_event("heartbeat", {}))
        except asyncio.CancelledError:
            pass

    async def _producer() -> None:
        try:
            async with asyncio.timeout(_STREAM_TIMEOUT):
                async for chunk in agent.stream_response(
                    user_message=request.message,
                    history=history,
                    session_id=session.id,
                    result_holder=result_holder,
                ):
                    await queue.put(chunk)
        except TimeoutError:
            logger.error("Agent stream timed out after %ds", _STREAM_TIMEOUT)
            await queue.put(
                make_sse_event("agent.workflow.failed", {"error": "Stream timed out"})
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Event stream producer failed: %s", exc)
            await queue.put(
                make_sse_event("agent.workflow.failed", {"error": str(exc)})
            )
        finally:
            queue.put_nowait(None)

    heartbeat_task = asyncio.create_task(_heartbeat())
    producer_task = asyncio.create_task(_producer())

    try:
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
    finally:
        heartbeat_task.cancel()
        producer_task.cancel()
        await asyncio.gather(heartbeat_task, producer_task, return_exceptions=True)

    # Assistant reply is persisted by the BackgroundTask registered in chat_stream.


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    sessions = SessionRepository(db)

    try:
        session = await sessions.get_or_create(request.session_id, request.user_id)
    except SessionOwnershipError as err:
        raise HTTPException(
            status_code=403, detail="Session belongs to another user"
        ) from err

    result_holder: list[str] = []

    # Register the assistant reply persist as a background task so it:
    # always runs even if the client disconnects mid-stream, and
    # uses its own DB session — errors are logged but cannot corrupt the stream.
    background_tasks.add_task(_persist_assistant_reply, session.id, result_holder)

    return StreamingResponse(
        _event_stream(request, db, session, result_holder),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
            "X-Accel-Buffering": "no",
        },
    )

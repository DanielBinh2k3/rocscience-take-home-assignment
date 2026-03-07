"""POST /api/v1/chat/stream endpoint."""

import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent import agent
from app.db.crud import MessageRepository, SessionRepository
from app.db.database import get_db
from app.db.models import MessageRole
from app.schemas.chat import ChatRequest
from app.utils.serializer import make_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()

_HEARTBEAT_INTERVAL = 15  # seconds
_STREAM_TIMEOUT = 120  # seconds — hard limit per stream


async def _event_stream(request: ChatRequest, db: AsyncSession):
    """Core SSE generator: persists messages, streams agent output, emits heartbeats."""
    sessions = SessionRepository(db)
    messages = MessageRepository(db)

    # 1. Ensure session exists (create if new)
    session = await sessions.get_or_create(request.session_id, request.user_id)

    # 2. Persist user message BEFORE calling agent
    await messages.create(session.id, MessageRole.user, request.message)
    await db.commit()

    # 3. Fetch conversation history for context (exclude the message just persisted)
    history_rows = await messages.list_by_session(session.id)
    history = [{"role": row.role, "content": row.content} for row in history_rows[:-1]]

    # 4. Stream agent response with concurrent heartbeat
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    result_holder: list[str] = []

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
            raise  # re-raise so the task is properly marked cancelled
        except Exception as exc:
            logger.exception("Event stream producer failed: %s", exc)
            await queue.put(
                make_sse_event("agent.workflow.failed", {"error": str(exc)})
            )
        finally:
            queue.put_nowait(None)  # sentinel — always signals consumer to stop

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

    # 5. Persist assistant reply — only reached on normal completion, not on client disconnect
    full_reply = result_holder[0] if result_holder else ""
    if full_reply:
        await messages.create(session.id, MessageRole.assistant, full_reply)
        await db.commit()


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    return StreamingResponse(
        _event_stream(request, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
            "X-Accel-Buffering": "no",
        },
    )

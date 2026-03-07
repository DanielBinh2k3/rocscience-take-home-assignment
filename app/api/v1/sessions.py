"""GET /sessions/{session_id}/history and DELETE /sessions/{session_id}."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud import MessageRepository, SessionRepository
from app.db.database import get_db
from app.schemas.chat import MessageOut, SessionHistoryOut

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sessions/{session_id}/history", response_model=SessionHistoryOut)
async def get_history(
    session_id: uuid.UUID,
    user_id: str = Query(..., description="Owner of the session"),
    db: AsyncSession = Depends(get_db),
):
    sessions = SessionRepository(db)
    messages = MessageRepository(db)

    session = await sessions.get(session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = await messages.list_by_session(session_id)
    return SessionHistoryOut(
        session_id=session_id,
        messages=[MessageOut.model_validate(m) for m in rows],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def remove_session(
    session_id: uuid.UUID,
    user_id: str = Query(..., description="Owner of the session"),
    db: AsyncSession = Depends(get_db),
):
    sessions = SessionRepository(db)

    deleted = await sessions.delete(session_id, user_id)
    await db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

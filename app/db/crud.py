"""Repository classes for database access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, ChatSession, MessageRole


class SessionOwnershipError(Exception):
    """Raised when a user tries to access a session owned by another user."""


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, session_id: uuid.UUID, user_id: str) -> ChatSession | None:
        result = await self.db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, session_id: uuid.UUID, user_id: str) -> ChatSession:
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            if existing.user_id != user_id:
                raise SessionOwnershipError(
                    f"Session {session_id} belongs to another user"
                )
            return existing

        session = ChatSession(id=session_id, user_id=user_id)
        self.db.add(session)
        try:
            await self.db.flush()
            return session
        except IntegrityError as err:
            # A concurrent request created the same session between our SELECT and INSERT.
            # Roll back the failed insert and re-fetch the now-existing row.
            await self.db.rollback()
            result = await self.db.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise  # Unexpected error — re-raise original IntegrityError
            if existing.user_id != user_id:
                raise SessionOwnershipError(
                    f"Session {session_id} belongs to another user"
                ) from err
            return existing

    async def delete(self, session_id: uuid.UUID, user_id: str) -> bool:
        """Delete session + messages (CASCADE). Returns True if deleted."""
        session = await self.get(session_id, user_id)
        if session is None:
            return False
        await self.db.delete(session)
        await self.db.flush()
        return True


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self, session_id: uuid.UUID, role: MessageRole, content: str
    ) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=role, content=content)
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def list_by_session(self, session_id: uuid.UUID) -> Sequence[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return result.scalars().all()

"""Pytest fixtures for chat API tests."""

# Test database URL — use env TEST_DATABASE_URL or default to localhost.
# Uses chatdb (same as main) — we truncate before each test. Ensure PostgreSQL is running
# (e.g. docker-compose up -d db) and migrations applied.
import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/chatdb",
)

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=0,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh DB session for each test. Truncates tables before each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # Truncate tables for a clean slate (order matters due to FK)
        await session.execute(text("TRUNCATE chat_messages, chat_sessions CASCADE"))
        await session.commit()
        yield session


@pytest_asyncio.fixture
async def test_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with overridden DB dependency."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_session_id() -> uuid.UUID:
    """Sample session UUID for tests."""
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> str:
    """Sample user ID for tests."""
    return "test-user-123"

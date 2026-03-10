"""Tests for the database layer using SQLite (aiosqlite) as a test backend."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, ChatMessage, ChatSession, MemoryEntry, User


@pytest_asyncio.fixture
async def async_session() -> async_sessionmaker[AsyncSession]:
    """Create an in-memory SQLite engine and yield a session factory."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_tables(async_session: async_sessionmaker[AsyncSession]) -> None:
    """Verify that all expected tables are created."""
    async with async_session() as session:
        # Use the connection to inspect table names
        conn = await session.connection()
        raw = await conn.run_sync(
            lambda sync_conn: sync_conn.dialect.get_table_names(sync_conn)
        )
        expected = {"users", "chat_sessions", "chat_messages", "memory_entries", "plugin_records"}
        assert expected.issubset(set(raw)), f"Missing tables: {expected - set(raw)}"


@pytest.mark.asyncio
async def test_create_user(async_session: async_sessionmaker[AsyncSession]) -> None:
    """Insert and retrieve a user."""
    async with async_session() as session:
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_pw_123",
        )
        session.add(user)
        await session.commit()

        result = await session.execute(select(User).where(User.username == "testuser"))
        fetched = result.scalar_one()

        assert fetched.username == "testuser"
        assert fetched.email == "test@example.com"
        assert fetched.is_active is True
        assert fetched.is_admin is False
        assert fetched.id is not None


@pytest.mark.asyncio
async def test_create_session_with_messages(
    async_session: async_sessionmaker[AsyncSession],
) -> None:
    """Create a chat session with messages and verify relationships."""
    async with async_session() as session:
        user = User(
            username="chatuser",
            email="chat@example.com",
            hashed_password="hashed_pw_456",
        )
        session.add(user)
        await session.flush()

        chat_session = ChatSession(
            user_id=user.id,
            working_dir="/tmp/test",
            model_name="qwen2.5-coder:32b",
            rag_enabled=True,
        )
        session.add(chat_session)
        await session.flush()

        messages = [
            ChatMessage(
                session_id=chat_session.id,
                role="user",
                content="Hello, world!",
                tokens_used=5,
            ),
            ChatMessage(
                session_id=chat_session.id,
                role="assistant",
                content="Hi there!",
                tool_calls={"name": "bash", "args": {"command": "ls"}},
                tokens_used=10,
            ),
        ]
        session.add_all(messages)
        await session.commit()

        # Verify session and messages
        result = await session.execute(
            select(ChatSession).where(ChatSession.user_id == user.id)
        )
        fetched_session = result.scalar_one()
        assert fetched_session.model_name == "qwen2.5-coder:32b"
        assert fetched_session.rag_enabled is True
        assert fetched_session.session_id is not None

        msg_result = await session.execute(
            select(ChatMessage).where(ChatMessage.session_id == fetched_session.id)
        )
        fetched_messages = msg_result.scalars().all()
        assert len(fetched_messages) == 2
        assert fetched_messages[0].role == "user"
        assert fetched_messages[1].tool_calls == {"name": "bash", "args": {"command": "ls"}}


@pytest.mark.asyncio
async def test_memory_entry_unique_constraint(
    async_session: async_sessionmaker[AsyncSession],
) -> None:
    """Verify that the user_id + key unique constraint is enforced."""
    async with async_session() as session:
        user = User(
            username="memuser",
            email="mem@example.com",
            hashed_password="hashed_pw_789",
        )
        session.add(user)
        await session.flush()

        entry1 = MemoryEntry(
            user_id=user.id,
            type="preference",
            key="theme",
            value="dark",
        )
        session.add(entry1)
        await session.commit()

    # Attempt to insert a duplicate key for the same user in a new session
    async with async_session() as session:
        # Re-fetch the user id
        result = await session.execute(select(User).where(User.username == "memuser"))
        user = result.scalar_one()

        entry2 = MemoryEntry(
            user_id=user.id,
            type="preference",
            key="theme",
            value="light",
        )
        session.add(entry2)
        with pytest.raises(IntegrityError):
            await session.flush()

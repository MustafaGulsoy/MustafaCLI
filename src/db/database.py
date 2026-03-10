"""Async database engine and session management."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = structlog.get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str, echo: bool = False) -> AsyncEngine:
    """Initialize the async database engine and session factory.

    Args:
        database_url: Database connection URL (e.g. postgresql+asyncpg://...).
        echo: Whether to echo SQL statements for debugging.

    Returns:
        The created AsyncEngine instance.
    """
    global _engine, _session_factory
    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_size=10,
        max_overflow=20,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info("database_initialized", url=database_url.split("@")[-1])
    return _engine


async def close_db() -> None:
    """Dispose of the database engine and reset module state."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        logger.info("database_closed")
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    """Return the current async engine, raising if not initialized."""
    if not _engine:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session with automatic commit/rollback."""
    if not _session_factory:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables defined in the ORM models."""
    from .models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created")

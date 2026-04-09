"""Database configuration - engine and session factory."""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from i18n import _

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aiagent:bB6C8tQu9YuLWqMq@192.168.1.252:5432/aiagent",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "").lower() == "true",
    pool_size=int(os.getenv("POOL_MIN_SIZE", "10")),
    max_overflow=int(os.getenv("POOL_MAX_SIZE", "20")) - int(os.getenv("POOL_MIN_SIZE", "10")),
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database connection."""
    pass


async def close_db() -> None:
    """Close database connection."""
    await engine.dispose()

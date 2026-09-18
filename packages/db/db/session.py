"""Async SQLAlchemy engine / session factory."""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_engine(database_url: str | None = None) -> AsyncEngine:
    global _engine, _session_factory
    url = database_url or os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://arpa:arpa@localhost:5432/arpa"
    )
    # sqlite+aiosqlite for unit tests
    kwargs: dict = {"echo": False}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    _engine = create_async_engine(url, **kwargs)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session

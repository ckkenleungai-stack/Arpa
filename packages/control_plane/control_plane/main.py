"""Arpa control plane — FastAPI app factory / uvicorn entry."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from control_plane.routes import conversations, health, runs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Init DB engine (sqlite OK for tests via env)
    from control_plane.deps import ensure_db_initialized, get_checkpointer
    from db.session import init_engine

    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        init_engine(db_url)
        # Create tables for sqlite / when migrations not run (dev convenience)
        if db_url.startswith("sqlite"):
            from db.models import Base

            engine = init_engine(db_url)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    # LangSmith: enable only when key present (graceful skip otherwise)
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and not os.environ.get(
        "LANGSMITH_API_KEY"
    ):
        # Do not fail startup — tracing is optional for local smoke
        os.environ["LANGSMITH_TRACING"] = "false"

    # Warm checkpointer (MemorySaver fallback if Postgres down)
    try:
        get_checkpointer()
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Arpa Control Plane",
        version="0.1.0",
        description="W1 first-slice — JWT auth, conversations, runs, SSE, HITL, AR stub",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(conversations.router)
    app.include_router(runs.router)
    return app


app = create_app()

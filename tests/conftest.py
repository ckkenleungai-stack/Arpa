"""Shared fixtures — sqlite + MemorySaver; mint HS256 JWTs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    ROOT / "packages" / "control_plane",
    ROOT / "packages" / "workflows",
    ROOT / "packages" / "gateway",
    ROOT / "packages" / "tools",
    ROOT / "packages" / "db",
    ROOT / "packages" / "ar",
    ROOT / "packages" / "evals",
]
for p in PACKAGES:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

# Env before imports that read settings
os.environ.setdefault("JWT_SECRET", "test-secret-hs256-long-enough-32b!!")
os.environ.setdefault("JWT_ISSUER", "arpa-local")
os.environ.setdefault("JWT_AUDIENCE", "arpa-api")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_arpa.db"
os.environ["ALLOWED_ROOT"] = str(ROOT / "workspace_data")
os.environ["OPENROUTER_API_KEY"] = ""  # force offline stub


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def app_client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("JWT_SECRET", "test-secret-hs256-long-enough-32b!!")
    monkeypatch.setenv("ALLOWED_ROOT", str(ROOT / "workspace_data"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    # Reset settings cache + runtime
    from control_plane.settings import get_settings

    get_settings.cache_clear()

    from control_plane.deps import reset_runtime_for_tests
    from db.models import Base
    from db.session import init_engine

    reset_runtime_for_tests(use_memory=True)
    engine = init_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from control_plane.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


@pytest.fixture
def auth_headers():
    from control_plane.auth import mint_dev_token
    from control_plane.settings import Settings

    settings = Settings()
    settings.jwt_secret = "test-secret-hs256-long-enough-32b!!"
    token = mint_dev_token(
        user_id="user-1",
        tenant_id="tenant-a",
        settings=settings,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_tenant_headers():
    from control_plane.auth import mint_dev_token
    from control_plane.settings import Settings

    settings = Settings()
    settings.jwt_secret = "test-secret-hs256-long-enough-32b!!"
    token = mint_dev_token(
        user_id="user-2",
        tenant_id="tenant-b",
        settings=settings,
    )
    return {"Authorization": f"Bearer {token}"}

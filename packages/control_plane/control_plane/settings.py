"""App settings from env."""
from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        self.jwt_secret = os.environ.get("JWT_SECRET", "dev-only-change-me-not-a-real-secret-32b-min")
        self.jwt_issuer = os.environ.get("JWT_ISSUER", "arpa-local")
        self.jwt_audience = os.environ.get("JWT_AUDIENCE", "arpa-api")
        self.jwt_algorithm = os.environ.get("JWT_ALGORITHM", "HS256")
        self.jwt_jwks_url = os.environ.get("JWT_JWKS_URL", "")  # Google-ready stub
        self.database_url = os.environ.get(
            "DATABASE_URL", "postgresql+asyncpg://arpa:arpa@localhost:5432/arpa"
        )
        self.database_url_sync = os.environ.get(
            "DATABASE_URL_SYNC", "postgresql://arpa:arpa@localhost:5432/arpa"
        )
        self.allowed_root = os.environ.get("ALLOWED_ROOT", "./workspace_data")
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()

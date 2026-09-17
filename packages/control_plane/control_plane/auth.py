"""JWT auth stub — HS256 local; Google JWKS-ready."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from control_plane.settings import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    tenant_id: str
    user_id: str
    roles: list[str]
    raw_claims: dict[str, Any]


def decode_token(token: str, settings: Settings | None = None) -> AuthContext:
    settings = settings or get_settings()
    # Google JWKS path stubbed — when JWT_JWKS_URL set, future: fetch keys.
    # Local HS256 for W1 scaffold.
    try:
        options = {"require": ["sub", "exp"]}
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub"]},  # exp optional for short-lived test tokens
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id") or claims.get("org_id") or claims.get("tid")
    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token must resolve tenant_id and user_id (sub)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    roles = claims.get("roles") or claims.get("role") or ["end-user"]
    if isinstance(roles, str):
        roles = [roles]
    return AuthContext(
        tenant_id=str(tenant_id),
        user_id=str(user_id),
        roles=list(roles),
        raw_claims=claims,
    )


def mint_dev_token(
    *,
    user_id: str = "user-1",
    tenant_id: str = "tenant-1",
    settings: Settings | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Helper for tests / demo curls — not for production."""
    import time

    settings = settings or get_settings()
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400,
        "roles": ["end-user"],
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def require_auth(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(creds.credentials, settings)

"""API key authentication for write endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(_header)) -> str:
    """Dependency that enforces API key auth on write endpoints.

    If no API_KEY is configured (empty string), all requests are allowed
    so local development works without extra setup.
    """
    if not settings.api_key:
        return ""
    if not key or key != settings.api_key:
        raise HTTPException(401, "Invalid or missing API key")
    return key

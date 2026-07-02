"""API key authentication for write endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(_header)) -> str:
    """Dependency that enforces API key auth on write endpoints.

    Fails CLOSED: if no API_KEY is configured, write requests are rejected
    (503) rather than allowed. Set the API_KEY env var to enable writes —
    including for local development.
    """
    if not settings.api_key:
        raise HTTPException(503, "Write API is disabled: no API_KEY configured")
    if not key or key != settings.api_key:
        raise HTTPException(401, "Invalid or missing API key")
    return key

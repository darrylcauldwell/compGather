"""Security tests: SSRF URL guard + API-key fail-closed auth.

Network-independent — uses IP literals and loopback names so no external DNS
is required (getaddrinfo on an IP literal returns it directly).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import require_api_key
from app.config import settings
from app.services.url_guard import is_public_http_url


class TestSSRFUrlGuard:
    def test_blocks_non_http_schemes(self):
        assert not is_public_http_url("ftp://example.com/")
        assert not is_public_http_url("file:///etc/passwd")
        assert not is_public_http_url("gopher://8.8.8.8/")

    def test_blocks_loopback_and_localhost(self):
        assert not is_public_http_url("http://127.0.0.1/")
        assert not is_public_http_url("http://localhost/admin")

    def test_blocks_private_and_cloud_metadata(self):
        assert not is_public_http_url("http://10.0.0.5/")
        assert not is_public_http_url("http://192.168.1.1/")
        assert not is_public_http_url("http://172.16.0.1/")
        # AWS/GCP link-local metadata endpoint — the classic SSRF target.
        assert not is_public_http_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_malformed_or_hostless(self):
        assert not is_public_http_url("http:///nohost")
        assert not is_public_http_url("not a url at all")
        assert not is_public_http_url("")

    def test_allows_public_ip_literals(self):
        assert is_public_http_url("http://8.8.8.8/")
        assert is_public_http_url("https://1.1.1.1/some/path")


@pytest.mark.asyncio
async def test_api_key_rejects_when_unset(monkeypatch):
    """Fail closed: no configured key => writes rejected (503), not allowed."""
    monkeypatch.setattr(settings, "api_key", "")
    with pytest.raises(HTTPException) as exc:
        await require_api_key(key="anything")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_api_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    with pytest.raises(HTTPException) as exc:
        await require_api_key(key="wrong")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_api_key_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    assert await require_api_key(key="secret") == "secret"

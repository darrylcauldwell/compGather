"""SSRF guard for outbound fetches.

Only allow HTTP(S) requests to public, globally-routable hosts. Blocks non-HTTP
schemes and any host that resolves to a private, loopback, link-local, reserved,
or otherwise non-global address — the classic SSRF vectors (cloud metadata at
169.254.169.254, 127.0.0.1, 10.x/192.168.x internal services, etc.).

`SSRFGuardTransport` validates every request an httpx client makes — including
each redirect hop, since httpx re-dispatches redirects through the transport —
so a public URL that 302s to an internal one is also blocked.

Residual: this does not pin the resolved IP, so a determined DNS-rebinding
attacker who controls a source's DNS is not fully defeated. It blocks the
common direct and redirect cases, which is what the source data exposes.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import anyio
import httpx

logger = logging.getLogger(__name__)


def is_public_http_url(url: str) -> bool:
    """True only if `url` is http(s) and every resolved IP is globally routable."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        # Unresolvable host — the fetch would fail anyway; treat as unsafe.
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


class SSRFGuardTransport(httpx.AsyncHTTPTransport):
    """httpx transport that rejects requests to non-public hosts.

    Every request (initial and each redirect hop) is re-dispatched through the
    transport, so this closes redirect-based SSRF too. DNS resolution runs in a
    worker thread to avoid blocking the event loop.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not await anyio.to_thread.run_sync(is_public_http_url, str(request.url)):
            logger.warning("SSRF guard blocked request to host %s", request.url.host)
            raise httpx.ConnectError(
                f"SSRF guard blocked non-public URL host: {request.url.host!r}",
                request=request,
            )
        return await super().handle_async_request(request)

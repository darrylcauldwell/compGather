"""Base classes for EquiCalendar parsers.

Inheritance hierarchy:

    BaseParser (abstract)
    ├── HttpParser — shared httpx client, fetch helpers, dedup, date parsing
    │   ├── SingleVenueParser — auto-fills venue_name/venue_postcode
    │   │   └── TribeEventsParser — Tribe Events v1 REST API pagination
    │   └── TwoPhaseParser — concurrent detail-page enrichment
    └── PlaywrightParser — Playwright browser lifecycle for SPAs
"""

from __future__ import annotations

import asyncio
import contextlib
import html as html_mod
import logging
import re
from datetime import date, datetime
from typing import Any, Callable, Sequence, TypeVar

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Browser-like User-Agent (some sites need this to avoid WAF blocks)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# HttpParser
# ---------------------------------------------------------------------------


class HttpParser(BaseParser):
    """Base for parsers that use httpx for HTTP requests.

    Provides shared httpx client creation, fetch helpers, dedup,
    date parsing, and event building.
    """

    HEADERS: dict[str, str] = {"User-Agent": "EquiCalendar/1.0"}
    TIMEOUT: float = 30.0

    @contextlib.asynccontextmanager
    async def _make_client(self, **overrides):
        """Create an httpx.AsyncClient with standard defaults."""
        kwargs: dict[str, Any] = {
            "follow_redirects": True,
            "timeout": self.TIMEOUT,
            "headers": {**self.HEADERS},
        }
        kwargs.update(overrides)
        async with httpx.AsyncClient(**kwargs) as client:
            yield client

    async def _fetch_json(
        self, client: httpx.AsyncClient, url: str, **kw
    ) -> Any:
        """GET *url* and return parsed JSON."""
        resp = await client.get(url, **kw)
        resp.raise_for_status()
        return resp.json()

    async def _post_json(
        self, client: httpx.AsyncClient, url: str, **kw
    ) -> Any:
        """POST to *url* and return parsed JSON."""
        resp = await client.post(url, **kw)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_html(
        self, client: httpx.AsyncClient, url: str, **kw
    ) -> BeautifulSoup:
        """GET *url* and return a BeautifulSoup document."""
        resp = await client.get(url, **kw)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")

    async def _fetch_text(
        self, client: httpx.AsyncClient, url: str, **kw
    ) -> str:
        """GET *url* and return the response body as text."""
        resp = await client.get(url, **kw)
        resp.raise_for_status()
        return resp.text

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        max_retries: int = 2,
        **kw,
    ) -> httpx.Response:
        """GET *url* with retries on transient failures."""
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                resp = await client.get(url, **kw)
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    # -- builders / helpers --------------------------------------------------

    def _build_event(self, **fields: Any) -> ExtractedEvent:
        """Build an ExtractedEvent from keyword arguments."""
        return ExtractedEvent(**fields)

    def _dedup(
        self,
        events: list[ExtractedEvent],
        key_fn: Callable[[ExtractedEvent], Any] | None = None,
    ) -> list[ExtractedEvent]:
        """Remove duplicate events.  Default key: (name, date_start)."""
        def _default_key(e: ExtractedEvent) -> Any:
            return (e.name, e.date_start)

        if key_fn is None:
            key_fn = _default_key
        seen: set[Any] = set()
        result: list[ExtractedEvent] = []
        for e in events:
            k = key_fn(e)
            if k not in seen:
                seen.add(k)
                result.append(e)
        return result

    def _parse_date(
        self,
        text: str,
        formats: Sequence[str] | None = None,
    ) -> str | None:
        """Try *formats* in order; return ``YYYY-MM-DD`` or ``None``."""
        if not text:
            return None
        if formats is None:
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S.%fZ",
            ]
        for fmt in formats:
            try:
                return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _log_result(self, parser_name: str, count: int) -> None:
        logger.info("%s: extracted %d events", parser_name, count)


# ---------------------------------------------------------------------------
# SingleVenueParser
# ---------------------------------------------------------------------------


class SingleVenueParser(HttpParser):
    """Base for parsers where every event is at the same known venue.

    Subclasses set ``VENUE_NAME``, ``VENUE_POSTCODE``, and ``BASE_URL``
    as class attributes.  ``_build_event()`` auto-fills venue fields.
    """

    VENUE_NAME: str = ""
    VENUE_POSTCODE: str | None = None
    BASE_URL: str = ""

    def _build_event(self, **fields: Any) -> ExtractedEvent:
        fields.setdefault("venue_name", self.VENUE_NAME)
        fields.setdefault("venue_postcode", self.VENUE_POSTCODE)
        return ExtractedEvent(**fields)


# ---------------------------------------------------------------------------
# TribeEventsParser
# ---------------------------------------------------------------------------


class TribeEventsParser(SingleVenueParser):
    """Base for single-venue WordPress sites using the Tribe Events v1 REST API.

    Subclasses only need to set venue constants.  Override
    ``_parse_tribe_event`` to customise field extraction.
    """

    API_PATH: str = "/wp-json/tribe/events/v1/events"
    PER_PAGE: int = 50
    USE_START_DATE: bool = True

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        api_url = self.BASE_URL + self.API_PATH if self.BASE_URL else url
        events: list[ExtractedEvent] = []

        async with self._make_client() as client:
            params: dict[str, Any] = {"per_page": self.PER_PAGE}
            if self.USE_START_DATE:
                params["start_date"] = date.today().isoformat()

            resp = await client.get(api_url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for ev in data.get("events", []):
                comp = self._parse_tribe_event(ev)
                if comp:
                    events.append(comp)

            total_pages = data.get("total_pages", 1)
            logger.info(
                "%s: %d total events, %d pages",
                self.VENUE_NAME,
                data.get("total", len(events)),
                total_pages,
            )

            for _page in range(2, total_pages + 1):
                next_url = data.get("next_rest_url")
                if not next_url:
                    break
                resp = await client.get(next_url)
                resp.raise_for_status()
                data = resp.json()
                for ev in data.get("events", []):
                    comp = self._parse_tribe_event(ev)
                    if comp:
                        events.append(comp)

        self._log_result(self.VENUE_NAME, len(events))
        return events

    def _parse_tribe_event(self, event: dict) -> ExtractedEvent | None:
        """Convert a single Tribe Events API event dict to an ExtractedEvent."""
        name = html_mod.unescape(event.get("title", "")).strip()
        if not name:
            return None

        date_start = (event.get("start_date") or "")[:10]
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_start):
            return None

        date_end = (event.get("end_date") or "")[:10]
        if date_end == date_start:
            date_end = None

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end,
            discipline=infer_discipline(name),
            has_pony_classes=detect_pony_classes(name),
            url=event.get("url", f"{self.BASE_URL}/events/"),
        )


# ---------------------------------------------------------------------------
# TwoPhaseParser
# ---------------------------------------------------------------------------


class TwoPhaseParser(HttpParser):
    """Base for parsers that scrape a listing then enrich from detail pages.

    Provides ``_concurrent_fetch`` to run an async function over a list
    of items with semaphore-limited concurrency.
    """

    CONCURRENCY: int = 8

    async def _concurrent_fetch(
        self,
        items: Sequence[T],
        fetch_fn: Callable[..., Any],
        fallback_fn: Callable[..., Any] | None = None,
    ) -> list[ExtractedEvent]:
        """Run *fetch_fn* over *items* concurrently.

        Returns a flat list of non-None results.  On exception, calls
        *fallback_fn(item)* if provided.
        """
        sem = asyncio.Semaphore(self.CONCURRENCY)

        async def _one(item: T) -> ExtractedEvent | None:
            async with sem:
                try:
                    return await fetch_fn(item)
                except Exception as exc:
                    logger.debug("Concurrent fetch failed: %s", exc)
                    if fallback_fn:
                        return fallback_fn(item)
                    return None

        results = await asyncio.gather(*[_one(i) for i in items])
        return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# PlaywrightParser
# ---------------------------------------------------------------------------


class PlaywrightParser(BaseParser):
    """Base for parsers that need Playwright to render JavaScript SPAs.

    Provides ``_render_page`` for single-page rendering with configurable
    wait strategies.
    """

    WAIT_STRATEGY: str = "networkidle"
    EXTRA_WAIT_MS: int = 0
    TIMEOUT_MS: int = 30000

    async def _render_page(self, url: str) -> str | None:
        """Load *url* with Playwright and return the rendered HTML."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning(
                "%s: Playwright not available", self.__class__.__name__
            )
            return None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(
                    url,
                    wait_until=self.WAIT_STRATEGY,
                    timeout=self.TIMEOUT_MS,
                )
                if self.EXTRA_WAIT_MS > 0:
                    await page.wait_for_timeout(self.EXTRA_WAIT_MS)
                return await page.content()
            except Exception as exc:
                logger.warning(
                    "%s: failed to load %s: %s",
                    self.__class__.__name__,
                    url,
                    exc,
                )
                return None
            finally:
                await browser.close()

    # -- utilities also needed by Playwright parsers -------------------------

    def _build_event(self, **fields: Any) -> ExtractedEvent:
        return ExtractedEvent(**fields)

    def _dedup(
        self,
        events: list[ExtractedEvent],
        key_fn: Callable[[ExtractedEvent], Any] | None = None,
    ) -> list[ExtractedEvent]:
        def _default_key(e: ExtractedEvent) -> Any:
            return (e.name, e.date_start)

        if key_fn is None:
            key_fn = _default_key
        seen: set[Any] = set()
        result: list[ExtractedEvent] = []
        for e in events:
            k = key_fn(e)
            if k not in seen:
                seen.add(k)
                result.append(e)
        return result

    def _parse_date(
        self,
        text: str,
        formats: Sequence[str] | None = None,
    ) -> str | None:
        if not text:
            return None
        if formats is None:
            formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
        for fmt in formats:
            try:
                return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _log_result(self, parser_name: str, count: int) -> None:
        logger.info("%s: extracted %d events", parser_name, count)

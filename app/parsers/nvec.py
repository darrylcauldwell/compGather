from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

# NVEC = Newbold Verdon Equestrian Centre
VENUE_NAME = "Newbold Verdon Equestrian Centre"
VENUE_POSTCODE = "LE9 9NE"

# The Equus Organiser hub is a JS SPA
EQUUS_HUB_URL = "https://nvec.equusorganiser.com/"

# Date pattern: "Saturday 1st March 2026 - Show Jumping"
DATE_EVENT_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})\s*[-–]?\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)


@register_parser("nvec")
class NVECParser(BaseParser):
    """Parser for Newbold Verdon Equestrian Centre.

    Strategy:
    1. Try Playwright to render the Equus Organiser SPA and intercept API calls
    2. Fall back to the NVEC diary-dates page for regex-based extraction
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        competitions: list[ExtractedCompetition] = []

        # Strategy 1: Try Playwright for the Equus Organiser SPA
        try:
            pw_comps = await self._parse_equus_with_playwright()
            competitions.extend(pw_comps)
            logger.info("NVEC: %d events from Equus Organiser (Playwright)", len(pw_comps))
        except Exception as e:
            logger.warning("NVEC: Playwright approach failed: %s", e)

        # Strategy 2: Try the Equus hub with static fetch (may have some server-rendered data)
        if not competitions:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                try:
                    hub_comps = await self._parse_equus_hub_static(client)
                    competitions.extend(hub_comps)
                    logger.info("NVEC: %d events from Equus hub (static)", len(hub_comps))
                except Exception as e:
                    logger.debug("NVEC: static Equus hub parse failed: %s", e)

        # Strategy 3: Fall back to diary-dates page
        if not competitions:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                try:
                    diary_comps = await self._parse_diary_page(client, url)
                    competitions.extend(diary_comps)
                    logger.info("NVEC: %d events from diary page", len(diary_comps))
                except Exception as e:
                    logger.warning("NVEC: diary page parse failed: %s", e)

        logger.info("NVEC: extracted %d competitions total", len(competitions))
        return competitions

    async def _parse_equus_with_playwright(self) -> list[ExtractedCompetition]:
        """Use Playwright to render the Equus Organiser SPA and extract events.

        Also intercepts XHR/fetch calls to discover API endpoints.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.debug("NVEC: Playwright not available")
            return []

        competitions: list[ExtractedCompetition] = []
        api_responses: list[dict] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                # Intercept API calls to find data endpoints
                async def handle_response(response):
                    if response.url.startswith(EQUUS_HUB_URL) or "equusorganiser" in response.url:
                        content_type = response.headers.get("content-type", "")
                        if "json" in content_type:
                            try:
                                data = await response.json()
                                api_responses.append({"url": response.url, "data": data})
                            except Exception:
                                pass

                page.on("response", handle_response)

                await page.goto(EQUUS_HUB_URL, wait_until="networkidle", timeout=30000)

                # Try to extract events from intercepted API responses
                for api_resp in api_responses:
                    comps = self._parse_api_response(api_resp["data"])
                    competitions.extend(comps)

                # If no API data found, parse the rendered DOM
                if not competitions:
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    competitions = self._parse_rendered_dom(soup)

            finally:
                await browser.close()

        return competitions

    def _parse_api_response(self, data: object) -> list[ExtractedCompetition]:
        """Parse events from an intercepted API response."""
        competitions = []

        # Handle various response shapes
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Try common wrapper keys
            for key in ["events", "data", "items", "results"]:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break

        for item in items:
            if not isinstance(item, dict):
                continue

            name = item.get("name") or item.get("title") or item.get("event_name", "")
            if not name:
                continue

            # Try to find date fields
            date_start = None
            for date_key in ["date", "start_date", "startDate", "event_date"]:
                if date_key in item:
                    date_start = self._normalize_date(str(item[date_key]))
                    break
            if not date_start:
                continue

            date_end = None
            for date_key in ["end_date", "endDate"]:
                if date_key in item:
                    date_end = self._normalize_date(str(item[date_key]))

            if not is_future_event(date_start, date_end):
                continue

            has_pony = detect_pony_classes(name)

            competitions.append(ExtractedCompetition(
                name=name.strip(),
                date_start=date_start,
                date_end=date_end if date_end and date_end != date_start else None,
                venue_name=VENUE_NAME,
                venue_postcode=VENUE_POSTCODE,
                discipline=infer_discipline(name),
                has_pony_classes=has_pony,
                url=EQUUS_HUB_URL,
            ))

        return competitions

    def _parse_rendered_dom(self, soup: BeautifulSoup) -> list[ExtractedCompetition]:
        """Parse events from the Playwright-rendered DOM."""
        competitions = []

        # Look for card-like elements with event data
        for card in soup.find_all(class_=re.compile(r"card|event|competition", re.IGNORECASE)):
            title_el = card.find(["h1", "h2", "h3", "h4", "h5"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            # Try to find a date in the card
            card_text = card.get_text()
            date_match = re.search(
                r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})",
                card_text, re.IGNORECASE,
            )
            if not date_match:
                continue

            try:
                date_start = datetime.strptime(
                    f"{date_match.group(1)} {date_match.group(2)[:3]} {date_match.group(3)}",
                    "%d %b %Y",
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue

            if not is_future_event(date_start):
                continue

            has_pony = detect_pony_classes(title)

            competitions.append(ExtractedCompetition(
                name=title,
                date_start=date_start,
                venue_name=VENUE_NAME,
                venue_postcode=VENUE_POSTCODE,
                discipline=infer_discipline(title),
                has_pony_classes=has_pony,
                url=EQUUS_HUB_URL,
            ))

        return competitions

    async def _parse_equus_hub_static(self, client: httpx.AsyncClient) -> list[ExtractedCompetition]:
        """Try to extract server-rendered event data from the Equus hub."""
        resp = await client.get(EQUUS_HUB_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        competitions = []

        # Check for inline JSON data in script tags
        for script in soup.find_all("script"):
            if script.string and ("event" in script.string.lower() or "competition" in script.string.lower()):
                # Try to extract JSON arrays/objects
                for match in re.finditer(r'(\[{.+?}\])', script.string, re.DOTALL):
                    try:
                        data = json.loads(match.group(1))
                        comps = self._parse_api_response(data)
                        competitions.extend(comps)
                    except (json.JSONDecodeError, TypeError):
                        continue

        # Fall back to DOM parsing
        if not competitions:
            competitions = self._parse_rendered_dom(soup)

        return competitions

    async def _parse_diary_page(self, client: httpx.AsyncClient, url: str) -> list[ExtractedCompetition]:
        """Parse events from the NVEC diary-dates page."""
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text()

        competitions = []
        seen: set[tuple[str, str]] = set()  # (name, date) for dedup

        # Look for date + event patterns in the page text
        for match in DATE_EVENT_RE.finditer(page_text):
            try:
                date_start = datetime.strptime(
                    f"{match.group(1)} {match.group(2)} {match.group(3)}",
                    "%d %B %Y",
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue

            event_name = match.group(4).strip()
            if not event_name or len(event_name) < 3:
                continue
            # Clean up trailing punctuation
            event_name = re.sub(r"\s*[|•\-–]\s*$", "", event_name).strip()

            if not is_future_event(date_start):
                continue

            key = (event_name, date_start)
            if key in seen:
                continue
            seen.add(key)

            has_pony = detect_pony_classes(event_name)

            competitions.append(ExtractedCompetition(
                name=event_name,
                date_start=date_start,
                venue_name=VENUE_NAME,
                venue_postcode=VENUE_POSTCODE,
                discipline=infer_discipline(event_name),
                has_pony_classes=has_pony,
                url=url,
            ))

        # Also look for structured elements (tables, lists with dates)
        for li in soup.find_all("li"):
            text = li.get_text(strip=True)
            match = DATE_EVENT_RE.search(text)
            if not match:
                continue

            try:
                date_start = datetime.strptime(
                    f"{match.group(1)} {match.group(2)} {match.group(3)}",
                    "%d %B %Y",
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue

            event_name = match.group(4).strip()
            if not event_name or len(event_name) < 3:
                continue

            if not is_future_event(date_start):
                continue

            key = (event_name, date_start)
            if key in seen:
                continue
            seen.add(key)

            competitions.append(ExtractedCompetition(
                name=event_name,
                date_start=date_start,
                venue_name=VENUE_NAME,
                venue_postcode=VENUE_POSTCODE,
                discipline=infer_discipline(event_name),
                has_pony_classes=detect_pony_classes(event_name),
                url=url,
            ))

        if not competitions:
            logger.warning("NVEC: diary page at %s yielded no events — page content may have changed", url)

        return competitions

    def _normalize_date(self, date_str: str) -> str | None:
        """Normalize various date formats to YYYY-MM-DD."""
        if not date_str:
            return None
        # Strip time portion
        date_str = date_str.split("T")[0].split(" ")[0]
        # Try ISO format
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            pass
        # Try DD/MM/YYYY
        try:
            return datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
        return None

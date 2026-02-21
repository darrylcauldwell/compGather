from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://pcuk.org/calendar/"
BRANCH_DISCOVERY_URLS = [
    "https://pcuk.org/find-a-pony-club/",
    "https://pcuk.org/area-information/",
]
BRANCH_BASE = "https://branches.pcuk.org"


@register_parser("pony_club")
class PonyClubParser(BaseParser):
    """Parser for pcuk.org — The Pony Club central + branch calendars.

    Scrapes the main pcuk.org/calendar/ and also discovers branch calendars
    at branches.pcuk.org/[area]/calendar/ for comprehensive coverage.
    All Pony Club events have has_pony_classes=True by definition.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        seen: set[tuple[str, str, str]] = set()  # (name, date_start, venue_name) for dedup
        competitions: list[ExtractedCompetition] = []

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Phase 1: Scrape the main national calendar
            main_comps = await self._scrape_calendar(client, url)
            for comp in main_comps:
                key = (comp.name, comp.date_start, comp.venue_name)
                if key not in seen:
                    seen.add(key)
                    competitions.append(comp)
            logger.info("Pony Club: %d events from main calendar", len(competitions))

            # Phase 2: Discover branch calendar URLs
            branch_urls = await self._discover_branches(client)
            logger.info("Pony Club: discovered %d branch calendars", len(branch_urls))

            # Phase 3: Scrape each branch calendar with rate limiting
            for branch_url in branch_urls:
                try:
                    branch_comps = await self._scrape_calendar(client, branch_url)
                    for comp in branch_comps:
                        key = (comp.name, comp.date_start, comp.venue_name)
                        if key not in seen:
                            seen.add(key)
                            competitions.append(comp)
                    await asyncio.sleep(0.5)  # Rate limiting between branches
                except Exception as e:
                    logger.debug("Pony Club: failed to scrape branch %s: %s", branch_url, e)

        logger.info("Pony Club: extracted %d total competitions", len(competitions))
        return competitions

    async def _discover_branches(self, client: httpx.AsyncClient) -> list[str]:
        """Discover branch calendar URLs from Pony Club discovery pages."""
        branch_urls: list[str] = []

        for discovery_url in BRANCH_DISCOVERY_URLS:
            try:
                resp = await client.get(discovery_url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for a in soup.find_all("a", href=re.compile(r"branches\.pcuk\.org/[^/]+/?$")):
                    href = a["href"].rstrip("/")
                    calendar_url = f"{href}/calendar/"
                    if calendar_url not in branch_urls:
                        branch_urls.append(calendar_url)
            except Exception as e:
                logger.debug("Pony Club: branch discovery from %s failed: %s", discovery_url, e)

        # Also try the main site for branch links
        if not branch_urls:
            try:
                resp = await client.get("https://pcuk.org")
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=re.compile(r"branches\.pcuk\.org/[^/]+/?$")):
                    href = a["href"].rstrip("/")
                    calendar_url = f"{href}/calendar/"
                    if calendar_url not in branch_urls:
                        branch_urls.append(calendar_url)
            except Exception as e:
                logger.debug("Pony Club: main site branch discovery failed: %s", e)

        return branch_urls

    async def _scrape_calendar(self, client: httpx.AsyncClient, url: str) -> list[ExtractedCompetition]:
        """Scrape a single calendar page (main or branch) for events."""
        resp = await client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find all event divs with data-event-date attribute
        event_divs = soup.find_all("div", attrs={"data-event-date": True})
        if not event_divs:
            # Fallback: look for elements with class "event"
            event_divs = soup.find_all("div", class_="event")

        competitions = []
        for div in event_divs:
            comp = self._parse_event_div(div, url)
            if comp:
                competitions.append(comp)

        return competitions

    def _parse_event_div(self, div, base_url: str) -> ExtractedCompetition | None:
        """Parse a single event div element."""
        # Date from data attribute: DD.MM.YYYY
        date_str = div.get("data-event-date", "")
        event_type = div.get("data-event-type", "")
        organiser = div.get("data-event-organiser", "")

        if not date_str:
            return None

        # Parse date
        date_start = self._parse_date(date_str)
        if not date_start:
            return None

        # Filter past events
        if not is_future_event(date_start):
            return None

        # Title from h3
        h3 = div.find("h3")
        title = h3.get_text(strip=True) if h3 else ""
        if not title:
            return None

        # Extract venue/location from paragraph text (pipe-delimited)
        venue_name = "TBC"
        p_tag = div.find("p")
        if p_tag:
            p_text = p_tag.get_text(strip=True)
            parts = [part.strip() for part in p_text.split("|")]
            # Last part is usually location
            if len(parts) >= 2:
                venue_name = parts[-1] if parts[-1] else parts[0]

        # Booking URL
        booking_link = div.find("a", href=True)
        booking_url = booking_link["href"] if booking_link else None
        if booking_url and not booking_url.startswith("http"):
            booking_url = f"https://pcuk.org{booking_url}"

        # Build a descriptive name including organiser
        name = title
        if organiser and organiser.lower() not in title.lower():
            name = f"{organiser}: {title}"

        # Detect discipline from event type or title
        classes = []
        if event_type:
            classes.append(event_type)
        discipline = infer_discipline(f"{event_type} {title}") or event_type or None

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            venue_name=venue_name,
            venue_postcode=None,  # Not available on calendar page
            discipline=discipline,
            has_pony_classes=True,  # All PC events are pony/junior
            classes=classes,
            url=booking_url or base_url,
        )

    def _parse_date(self, date_str: str) -> str | None:
        """Parse DD.MM.YYYY to YYYY-MM-DD."""
        try:
            dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            # Try other formats
            for fmt in ["%d/%m/%Y", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

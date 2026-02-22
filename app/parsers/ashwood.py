from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import (
    detect_pony_classes,
    infer_discipline,
    is_competition_event,
    is_future_event,
)
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

# All events are at the same venue
VENUE_NAME = "Ashwood Equestrian"
VENUE_POSTCODE = "ST20 0JR"

EVENTS_URL = "https://ashwoodequestrian.com/events/"
RSS_URL = "https://ashwoodequestrian.com/events/feed/"


@register_parser("ashwood")
class AshwoodParser(BaseParser):
    """Parser for ashwoodequestrian.com — WordPress MEC (Modern Events Calendar).

    Combines the RSS feed (rich structured data) with the listing page HTML
    (more events) and deduplicates by event name + date.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Source 1: RSS feed (structured dates + categories)
            rss_events = await self._parse_rss(client)
            logger.info("Ashwood: %d events from RSS feed", len(rss_events))

            # Source 2: Listing page HTML (may have more events)
            html_events = await self._parse_listing(client)
            logger.info("Ashwood: %d events from listing page", len(html_events))

        # Merge: RSS events take priority (better data), add HTML-only events
        seen: set[tuple[str, str]] = set()
        competitions: list[ExtractedCompetition] = []

        for comp in rss_events:
            key = (comp.name.lower(), comp.date_start)
            if key not in seen:
                seen.add(key)
                competitions.append(comp)

        for comp in html_events:
            key = (comp.name.lower(), comp.date_start)
            if key not in seen:
                seen.add(key)
                competitions.append(comp)

        logger.info("Ashwood: %d competitions after deduplication", len(competitions))
        return competitions

    async def _parse_rss(self, client: httpx.AsyncClient) -> list[ExtractedCompetition]:
        """Parse the MEC RSS feed for structured event data."""
        events: list[ExtractedCompetition] = []
        try:
            resp = await client.get(RSS_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Ashwood: RSS feed fetch failed: %s", e)
            return events

        soup = BeautifulSoup(resp.text, "html.parser")

        for item in soup.find_all("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            event_url = link_el.get_text(strip=True) if link_el else None

            # MEC namespace dates: <mec:startDate>, <mec:endDate>
            start_el = item.find("mec:startdate") or item.find("mec:startDate")
            end_el = item.find("mec:enddate") or item.find("mec:endDate")

            date_start = self._parse_mec_date(start_el.get_text(strip=True)) if start_el else None
            date_end = self._parse_mec_date(end_el.get_text(strip=True)) if end_el else None

            if not date_start:
                continue

            if not is_future_event(date_start, date_end):
                continue

            if not is_competition_event(name):
                continue

            # Category from RSS
            categories = [c.get_text(strip=True) for c in item.find_all("category")]
            cat_text = " ".join(categories)

            text = f"{name} {cat_text}"
            discipline = infer_discipline(text)
            has_pony = detect_pony_classes(text)

            events.append(ExtractedCompetition(
                name=name,
                date_start=date_start,
                date_end=date_end if date_end != date_start else None,
                venue_name=VENUE_NAME,
                venue_postcode=VENUE_POSTCODE,
                discipline=discipline,
                has_pony_classes=has_pony,
                classes=[],
                url=event_url or EVENTS_URL,
            ))

        return events

    async def _parse_listing(self, client: httpx.AsyncClient) -> list[ExtractedCompetition]:
        """Parse the events listing page HTML for MEC event articles."""
        events: list[ExtractedCompetition] = []
        try:
            resp = await client.get(EVENTS_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Ashwood: listing page fetch failed: %s", e)
            return events

        soup = BeautifulSoup(resp.text, "html.parser")

        # Track current month/year from month dividers
        current_year = datetime.now().year

        # Find all month dividers to build a date-order mapping
        dividers = soup.find_all("div", class_="mec-month-divider")
        divider_years: dict[str, int] = {}
        for div in dividers:
            h5 = div.find("h5")
            if h5:
                text = h5.get_text(strip=True)  # e.g. "March 2026"
                parts = text.strip().split()
                if len(parts) >= 2:
                    try:
                        divider_years[parts[0]] = int(parts[-1])
                    except ValueError:
                        pass

        # Find all event articles (may be nested inside wrapper divs)
        articles = soup.find_all("article", class_="mec-event-article")
        if not articles:
            logger.warning("Ashwood: no MEC event articles found")
            return events

        for article in articles:
            # Walk backwards to find the nearest month divider for year context
            month_year = self._find_month_divider(article, current_year)
            comp = self._parse_article(article, month_year, current_year)
            if comp:
                events.append(comp)

        return events

    def _find_month_divider(self, article, fallback_year: int) -> str | None:
        """Walk backward from an article to find the nearest mec-month-divider."""
        sibling = article.find_previous("div", class_="mec-month-divider")
        if sibling:
            h5 = sibling.find("h5")
            if h5:
                return h5.get_text(strip=True)
        return None

    def _parse_article(
        self, article, month_year: str | None, fallback_year: int
    ) -> ExtractedCompetition | None:
        """Parse a single MEC event article element."""
        # Title and URL
        title_link = article.find("h3", class_="mec-event-title")
        if not title_link:
            return None
        a_tag = title_link.find("a")
        if not a_tag:
            return None

        name = a_tag.get_text(strip=True)
        event_url = a_tag.get("href")

        if not name:
            return None

        if not is_competition_event(name):
            return None

        # Date: "08 Mar" from mec-start-date-label
        date_label = article.find("span", class_="mec-start-date-label")
        if not date_label:
            return None

        date_text = date_label.get_text(strip=True)  # e.g. "08 Mar"

        # Determine year from month divider context
        year = fallback_year
        if month_year:
            # "March 2026" -> extract year
            parts = month_year.strip().split()
            if len(parts) >= 2:
                try:
                    year = int(parts[-1])
                except ValueError:
                    pass

        date_start = self._parse_day_month(date_text, year)
        if not date_start:
            return None

        if not is_future_event(date_start):
            return None

        text = name
        discipline = infer_discipline(text)
        has_pony = detect_pony_classes(text)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=None,
            venue_name=VENUE_NAME,
            venue_postcode=VENUE_POSTCODE,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=[],
            url=event_url or EVENTS_URL,
        )

    def _parse_day_month(self, text: str, year: int) -> str | None:
        """Parse 'DD Mon' with a known year to 'YYYY-MM-DD'."""
        if not text:
            return None
        try:
            dt = datetime.strptime(f"{text.strip()} {year}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            logger.debug("Ashwood: unparseable date '%s'", text)
            return None

    def _parse_mec_date(self, text: str) -> str | None:
        """Parse MEC RSS date format to 'YYYY-MM-DD'.

        Handles formats like '2026-03-08', 'March 8, 2026', etc.
        """
        if not text:
            return None
        # Try ISO format first
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            return text
        # Try common MEC formats
        for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d %H:%M:%S", "%b %d, %Y"]:
            try:
                return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        logger.debug("Ashwood: unparseable MEC date '%s'", text)
        return None

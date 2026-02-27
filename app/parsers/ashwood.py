from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

EVENTS_URL = "https://ashwoodequestrian.com/events/"
RSS_URL = "https://ashwoodequestrian.com/events/feed/"


@register_parser("ashwood")
class AshwoodParser(SingleVenueParser):
    """Parser for ashwoodequestrian.com — WordPress MEC (Modern Events Calendar).

    Combines the RSS feed (rich structured data) with the listing page HTML
    (more events) and deduplicates by event name + date.
    """

    VENUE_NAME = "Ashwood Equestrian"
    VENUE_POSTCODE = "ST20 0JR"
    BASE_URL = "https://ashwoodequestrian.com"

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            # Source 1: RSS feed (structured dates + categories)
            rss_events = await self._parse_rss(client)
            logger.info("Ashwood: %d events from RSS feed", len(rss_events))

            # Source 2: Listing page HTML (may have more events)
            html_events = await self._parse_listing(client)
            logger.info("Ashwood: %d events from listing page", len(html_events))

        # Merge: RSS events take priority (better data), add HTML-only events
        competitions = self._dedup(
            rss_events + html_events,
            key_fn=lambda e: (e.name.lower(), e.date_start),
        )

        self._log_result("Ashwood", len(competitions))
        return competitions

    async def _parse_rss(self, client):
        """Parse the MEC RSS feed for structured event data."""
        events: list[ExtractedEvent] = []
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

            events.append(self._build_event(
                name=name,
                date_start=date_start,
                date_end=date_end if date_end != date_start else None,
                url=event_url or EVENTS_URL,
            ))

        return events

    async def _parse_listing(self, client):
        """Parse the events listing page HTML for MEC event articles."""
        events: list[ExtractedEvent] = []
        try:
            resp = await client.get(EVENTS_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Ashwood: listing page fetch failed: %s", e)
            return events

        soup = BeautifulSoup(resp.text, "html.parser")
        current_year = datetime.now().year

        articles = soup.find_all("article", class_="mec-event-article")
        if not articles:
            logger.warning("Ashwood: no MEC event articles found")
            return events

        for article in articles:
            month_year = self._find_month_divider(article)
            comp = self._parse_article(article, month_year, current_year)
            if comp:
                events.append(comp)

        return events

    def _find_month_divider(self, article) -> str | None:
        sibling = article.find_previous("div", class_="mec-month-divider")
        if sibling:
            h5 = sibling.find("h5")
            if h5:
                return h5.get_text(strip=True)
        return None

    def _parse_article(self, article, month_year, fallback_year):
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

        date_label = article.find("span", class_="mec-start-date-label")
        if not date_label:
            return None

        date_text = date_label.get_text(strip=True)

        year = fallback_year
        if month_year:
            parts = month_year.strip().split()
            if len(parts) >= 2:
                try:
                    year = int(parts[-1])
                except ValueError:
                    pass

        date_start = self._parse_day_month(date_text, year)
        if not date_start:
            return None

        return self._build_event(
            name=name,
            date_start=date_start,
            url=event_url or EVENTS_URL,
        )

    def _parse_day_month(self, text, year):
        if not text:
            return None
        try:
            dt = datetime.strptime(f"{text.strip()} {year}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            logger.debug("Ashwood: unparseable date '%s'", text)
            return None

    def _parse_mec_date(self, text):
        if not text:
            return None
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            return text
        for fmt in ["%B %d, %Y", "%d %B %Y", "%Y-%m-%d %H:%M:%S", "%b %d, %Y"]:
            try:
                return datetime.strptime(text.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        logger.debug("Ashwood: unparseable MEC date '%s'", text)
        return None

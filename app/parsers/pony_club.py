from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://pcuk.org/calendar/"
BRANCH_DISCOVERY_URLS = [
    "https://pcuk.org/find-a-pony-club/",
    "https://pcuk.org/area-information/",
]
BRANCH_BASE = "https://branches.pcuk.org"


@register_parser("pony_club")
class PonyClubParser(HttpParser):
    """Parser for pcuk.org — The Pony Club central + branch calendars.

    Scrapes the main pcuk.org/calendar/ and also discovers branch calendars
    at branches.pcuk.org/[area]/calendar/.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        seen: set[tuple[str, str, str]] = set()
        competitions: list[ExtractedEvent] = []

        async with self._make_client() as client:
            main_comps = await self._scrape_calendar(client, url)
            for comp in main_comps:
                key = (comp.name, comp.date_start, comp.venue_name)
                if key not in seen:
                    seen.add(key)
                    competitions.append(comp)
            logger.info("Pony Club: %d events from main calendar", len(competitions))

            branch_urls = await self._discover_branches(client)
            logger.info("Pony Club: discovered %d branch calendars", len(branch_urls))

            for branch_url in branch_urls:
                try:
                    branch_comps = await self._scrape_calendar(client, branch_url)
                    for comp in branch_comps:
                        key = (comp.name, comp.date_start, comp.venue_name)
                        if key not in seen:
                            seen.add(key)
                            competitions.append(comp)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.debug("Pony Club: failed to scrape branch %s: %s", branch_url, e)

        self._log_result("Pony Club", len(competitions))
        return competitions

    async def _discover_branches(self, client):
        branch_urls: list[str] = []
        for discovery_url in BRANCH_DISCOVERY_URLS:
            try:
                soup = await self._fetch_html(client, discovery_url)
                for a in soup.find_all("a", href=re.compile(r"branches\.pcuk\.org/[^/]+/?$")):
                    href = a["href"].rstrip("/")
                    calendar_url = f"{href}/calendar/"
                    if calendar_url not in branch_urls:
                        branch_urls.append(calendar_url)
            except Exception as e:
                logger.debug("Pony Club: branch discovery from %s failed: %s", discovery_url, e)

        if not branch_urls:
            try:
                soup = await self._fetch_html(client, "https://pcuk.org")
                for a in soup.find_all("a", href=re.compile(r"branches\.pcuk\.org/[^/]+/?$")):
                    href = a["href"].rstrip("/")
                    calendar_url = f"{href}/calendar/"
                    if calendar_url not in branch_urls:
                        branch_urls.append(calendar_url)
            except Exception as e:
                logger.debug("Pony Club: main site branch discovery failed: %s", e)

        return branch_urls

    async def _scrape_calendar(self, client, url):
        soup = await self._fetch_html(client, url)

        event_divs = soup.find_all("div", attrs={"data-event-date": True})
        if not event_divs:
            event_divs = soup.find_all("div", class_="event")

        competitions = []
        for div in event_divs:
            comp = self._parse_event_div(div, url)
            if comp:
                competitions.append(comp)
        return competitions

    def _parse_event_div(self, div, base_url):
        date_str = div.get("data-event-date", "")
        event_type = div.get("data-event-type", "")
        organiser = div.get("data-event-organiser", "")

        if not date_str:
            return None

        h3 = div.find("h3")
        title = h3.get_text(strip=True) if h3 else ""

        date_start = self._parse_pc_date(date_str)
        if not date_start:
            return None

        if not self._is_valid_title(title):
            return None

        name = title
        if organiser and organiser.lower() not in name.lower():
            name = f"{organiser}: {name}"

        venue_name = "TBC"
        venue_postcode = None
        p_tag = div.find("p")
        if p_tag:
            p_text = p_tag.get_text(strip=True)
            venue_postcode = extract_postcode(p_text)
            parts = [part.strip() for part in p_text.split("|")]
            if len(parts) >= 2:
                venue_name = parts[-1] if parts[-1] else parts[0]
            if venue_postcode and venue_postcode in venue_name:
                venue_name = venue_name.replace(venue_postcode, "").strip()

        booking_link = div.find("a", href=True)
        booking_url = booking_link["href"] if booking_link else None
        if booking_url and not booking_url.startswith("http"):
            booking_url = f"https://pcuk.org{booking_url}"
        if booking_url and not self._is_valid_booking_url(booking_url):
            booking_url = None

        enriched_name = None
        if booking_url and "horse-events.co.uk" in booking_url.lower():
            enriched_name = self._extract_event_name_from_horse_events_url(booking_url)
        if enriched_name and enriched_name.lower() != name.lower():
            name = enriched_name

        discipline = infer_discipline(name) or event_type or None

        return self._build_event(
            name=name,
            date_start=date_start,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            discipline=discipline,
            has_pony_classes=True,
            classes=[event_type] if event_type else [],
            url=booking_url or base_url,
        )

    def _parse_pc_date(self, date_str):
        try:
            dt = datetime.strptime(date_str.strip(), "%d.%m.%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            for fmt in ["%d/%m/%Y", "%Y-%m-%d"]:
                try:
                    return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    def _is_valid_booking_url(self, url):
        return bool(url and url.startswith("http"))

    def _is_valid_title(self, title):
        if not title or len(title) < 3:
            return False
        bad_patterns = [
            "index.php", "ndpcevent", "nzpcevent", "midantrimpc",
            "iveaghpc", "killultagh", "seskinore", "tpc#event", "error", "404",
        ]
        title_lower = title.lower()
        return not any(bad in title_lower for bad in bad_patterns)

    def _extract_event_name_from_horse_events_url(self, url):
        try:
            path = url.split("?")[0]
            parts = path.rstrip("/").split("/")
            if len(parts) < 2:
                return None

            slug = parts[-1]
            invalid_patterns = ["index.php", "error", "404", "blank", "default"]
            if any(pattern in slug.lower() for pattern in invalid_patterns):
                return None

            if not re.search(r"[a-z]", slug, re.IGNORECASE) or "-" not in slug:
                return None

            slug_no_date = re.sub(r"-\d{8}$", "", slug)
            if re.search(r"-\d+$", slug_no_date) and not re.search(r"[a-z]-\d+$", slug_no_date):
                slug_no_date = re.sub(r"-\d+$", "", slug_no_date)

            readable = slug_no_date.replace("-", " ").title()
            words = readable.split()
            if len(words) < 2 or len(readable) > 100:
                return None
            return readable
        except Exception:
            return None

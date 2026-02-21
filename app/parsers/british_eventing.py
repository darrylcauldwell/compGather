from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://www.britisheventing.com"

# Status codes: O=Open, C=Closed, X=Cancelled, S=Sold Out, P=Pending
CANCELLED_STATUSES = {"X"}

# Date: "12 Apr 26" or "1 - 2 Aug 26" or "28 Feb - 1 Mar 26"
SINGLE_DATE_RE = re.compile(r"^(\d{1,2})\s+(\w{3})\s+(\d{2})$")
RANGE_SAME_MONTH_RE = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})\s+(\w{3})\s+(\d{2})$")
RANGE_CROSS_MONTH_RE = re.compile(r"^(\d{1,2})\s+(\w{3})\s*-\s*(\d{1,2})\s+(\w{3})\s+(\d{2})$")


@register_parser("british_eventing")
class BritishEventingParser(BaseParser):
    """Parser for britisheventing.com/search-events.

    Server-rendered table with 7 columns:
    Dates | Name | Classes | Location | Entries Open | Ballot Date | Status
    ~110 events, single page, no pagination.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        competitions = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 7:
                continue

            date_text = tds[0].get_text(strip=True)
            name = tds[1].get_text(strip=True)
            classes_text = tds[2].get_text(strip=True)
            location = tds[3].get_text(strip=True)
            status = tds[6].get_text(strip=True)

            if not name or not date_text:
                continue

            # Skip cancelled events
            if status in CANCELLED_STATUSES:
                continue

            date_start, date_end = self._parse_date(date_text)
            if not date_start:
                continue

            if not is_future_event(date_start, date_end):
                continue

            # Extract detail URL
            event_url = None
            link = tds[1].find("a", href=True)
            if link:
                href = link["href"]
                event_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            # Parse classes into list
            classes = [c.strip() for c in classes_text.split(",") if c.strip()] if classes_text else []

            has_pony = detect_pony_classes(name) or detect_pony_classes(classes_text)

            competitions.append(ExtractedCompetition(
                name=name,
                date_start=date_start,
                date_end=date_end if date_end and date_end != date_start else None,
                venue_name=name,
                discipline="Eventing",
                has_pony_classes=has_pony,
                classes=classes,
                url=event_url or url,
            ))

        logger.info("British Eventing: extracted %d competitions", len(competitions))
        return competitions

    def _parse_date(self, text: str) -> tuple[str | None, str | None]:
        """Parse BE date formats with 2-digit year."""
        text = text.strip()

        # "28 Feb - 1 Mar 26"
        m = RANGE_CROSS_MONTH_RE.match(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(5)}", "%d %b %y")
                end = datetime.strptime(f"{m.group(3)} {m.group(4)} {m.group(5)}", "%d %b %y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # "1 - 2 Aug 26"
        m = RANGE_SAME_MONTH_RE.match(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(3)} {m.group(4)}", "%d %b %y")
                end = datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %b %y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # "12 Apr 26"
        m = SINGLE_DATE_RE.match(text)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

        return None, None

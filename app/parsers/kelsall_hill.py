from __future__ import annotations

import html
import json
import logging
import re
from datetime import date, datetime

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

BASE_URL = "https://kelsallhill.co.uk"
AJAX_URL = f"{BASE_URL}/wp-admin/admin-ajax.php"
VENUE_NAME = "Kelsall Hill"
VENUE_POSTCODE = "CW6 0PE"

# MEC calendar skin ID (from the equestrian-centre-forthcoming-events page)
MEC_SKIN_ID = "1394"

# How many months ahead to scan
MONTHS_AHEAD = 18


@register_parser("kelsall_hill")
class KelsallHillParser(BaseParser):
    """Parser for kelsallhill.co.uk — WordPress with Modern Events Calendar.

    Uses the MEC AJAX monthly view API to load events month by month.
    Each response contains JSON-LD structured data for all events in that month.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Iterate through months from now to MONTHS_AHEAD in the future
            today = date.today()
            all_competitions: list[ExtractedCompetition] = []
            seen: set[str] = set()  # Deduplicate by URL

            year, month = today.year, today.month
            for i in range(MONTHS_AHEAD):
                try:
                    events = await self._fetch_month(client, year, month)
                    for comp in events:
                        if comp.url not in seen:
                            seen.add(comp.url)
                            all_competitions.append(comp)
                except Exception as e:
                    logger.warning("Kelsall Hill: failed to fetch %d-%02d: %s", year, month, e)

                # Advance to next month
                month += 1
                if month > 12:
                    month = 1
                    year += 1

                if i % 6 == 5:
                    logger.info(
                        "Kelsall Hill: fetched %d months, %d events so far",
                        i + 1, len(all_competitions),
                    )

        logger.info("Kelsall Hill: extracted %d competitions total", len(all_competitions))
        return all_competitions

    async def _fetch_month(
        self, client: httpx.AsyncClient, year: int, month: int
    ) -> list[ExtractedCompetition]:
        """Fetch all events for a given month via the MEC AJAX API."""
        data = {
            "action": "mec_monthly_view_load_month",
            "mec_year": str(year),
            "mec_month": f"{month:02d}",
            "id": MEC_SKIN_ID,
        }

        resp = await client.post(AJAX_URL, data=data)
        resp.raise_for_status()

        result = resp.json()
        month_html = result.get("month", "")

        if not month_html:
            return []

        return self._parse_month_html(month_html)

    def _parse_month_html(self, html: str) -> list[ExtractedCompetition]:
        """Extract events from the MEC monthly view HTML response.

        Each event in the response has a JSON-LD script block with full event data.
        """
        soup = BeautifulSoup(html, "html.parser")
        competitions: list[ExtractedCompetition] = []

        # Extract all JSON-LD blocks from the month HTML
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                event_data = json.loads(script.string)
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(event_data, dict) or event_data.get("@type") != "Event":
                continue

            comp = self._json_ld_to_competition(event_data)
            if comp:
                competitions.append(comp)

        return competitions

    def _json_ld_to_competition(self, data: dict) -> ExtractedCompetition | None:
        """Convert a JSON-LD Event object to an ExtractedCompetition."""
        name = html.unescape((data.get("name") or "").strip())
        start_date = data.get("startDate", "")
        end_date = data.get("endDate", "")
        event_url = data.get("url", "")

        if not name or not start_date:
            return None

        # Normalise ISO datetime to date string for filtering
        date_start = self._normalise_date(start_date)
        date_end = self._normalise_date(end_date)

        if not date_start:
            return None

        if not is_future_event(date_start, date_end):
            return None

        # Filter non-competition events (clinics, workshops, etc.)
        if not is_competition_event(name):
            return None

        description = data.get("description", "")
        text = f"{name} {description}"
        discipline = infer_discipline(text)
        has_pony = detect_pony_classes(text)
        classes = self._extract_classes(description)

        return ExtractedCompetition(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=VENUE_NAME,
            venue_postcode=VENUE_POSTCODE,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=classes,
            url=event_url or f"{BASE_URL}/events/",
        )

    def _normalise_date(self, dt_str: str) -> str | None:
        """Normalise an ISO datetime like '2026-02-27T08:00:00+00:00' to 'YYYY-MM-DD'."""
        if not dt_str:
            return None
        # Try full ISO datetime first
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(dt_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # Fallback: extract date portion
        m = re.match(r"(\d{4}-\d{2}-\d{2})", dt_str)
        return m.group(1) if m else None

    def _extract_classes(self, description: str) -> list[str]:
        """Extract class heights/names from description text."""
        classes = []
        match = re.search(
            r"(?:Classes?|Heights?)\s*[:\-]\s*(.+?)(?:\n|$)",
            description,
            re.IGNORECASE,
        )
        if match:
            raw = match.group(1)
            classes = [c.strip() for c in re.split(r"[|,/]", raw) if c.strip()]
        return classes

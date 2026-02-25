from __future__ import annotations

import html
import json
import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

BASE_URL = "https://kelsallhill.co.uk"
AJAX_URL = f"{BASE_URL}/wp-admin/admin-ajax.php"
MEC_SKIN_ID = "1394"
MONTHS_AHEAD = 18


@register_parser("kelsall_hill")
class KelsallHillParser(SingleVenueParser):
    """Parser for kelsallhill.co.uk — WordPress with Modern Events Calendar.

    Uses the MEC AJAX monthly view API to load events month by month.
    """

    VENUE_NAME = "Kelsall Hill"
    VENUE_POSTCODE = "CW6 0PE"

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            today = date.today()
            all_competitions: list[ExtractedEvent] = []
            seen: set[str] = set()

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

                month += 1
                if month > 12:
                    month = 1
                    year += 1

                if i % 6 == 5:
                    logger.info("Kelsall Hill: fetched %d months, %d events so far", i + 1, len(all_competitions))

        self._log_result("Kelsall Hill", len(all_competitions))
        return all_competitions

    async def _fetch_month(self, client, year, month):
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

    def _parse_month_html(self, month_html):
        soup = BeautifulSoup(month_html, "html.parser")
        competitions: list[ExtractedEvent] = []

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

    def _json_ld_to_competition(self, data):
        name = html.unescape((data.get("name") or "").strip())
        start_date = data.get("startDate", "")
        end_date = data.get("endDate", "")
        event_url = data.get("url", "")

        if not name or not start_date:
            return None

        date_start = self._normalise_date(start_date)
        date_end = self._normalise_date(end_date)
        if not date_start:
            return None

        description = data.get("description", "")
        has_pony = detect_pony_classes(f"{name} {description}")
        classes = self._extract_classes(description)

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            has_pony_classes=has_pony,
            classes=classes,
            url=event_url or f"{BASE_URL}/events/",
        )

    def _normalise_date(self, dt_str):
        if not dt_str:
            return None
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(dt_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        m = re.match(r"(\d{4}-\d{2}-\d{2})", dt_str)
        return m.group(1) if m else None

    def _extract_classes(self, description):
        classes = []
        match = re.search(
            r"(?:Classes?|Heights?)\s*[:\-]\s*(.+?)(?:\n|$)",
            description, re.IGNORECASE,
        )
        if match:
            raw = match.group(1)
            classes = [c.strip() for c in re.split(r"[|,/]", raw) if c.strip()]
        return classes

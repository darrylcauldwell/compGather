from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from app.parsers.bases import BROWSER_UA, SingleVenueParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)


@register_parser("ballavartyn")
class BallavartynParser(SingleVenueParser):
    """Parser for equestrian.ballavartyn.com — Event Organiser RSS feed.

    Single venue: Ballavartyn Equestrian Centre (IM4 1HT), Isle of Man.
    """

    VENUE_NAME = "Ballavartyn"
    VENUE_POSTCODE = "IM4 1HT"
    BASE_URL = "https://equestrian.ballavartyn.com"
    HEADERS = {"User-Agent": BROWSER_UA}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            resp = await client.get(url)
            resp.raise_for_status()

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            logger.warning("Ballavartyn: failed to parse RSS XML")
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        competitions: list[ExtractedEvent] = []
        for item in channel.findall("item"):
            comp = self._item_to_competition(item)
            if comp:
                competitions.append(comp)

        competitions = self._dedup(competitions)
        self._log_result("Ballavartyn", len(competitions))
        return competitions

    def _item_to_competition(self, item: ET.Element) -> ExtractedEvent | None:
        title_el = item.find("title")
        link_el = item.find("link")
        pub_date_el = item.find("pubDate")

        if title_el is None or title_el.text is None:
            return None

        raw_title = title_el.text.strip()
        event_url = link_el.text.strip() if link_el is not None and link_el.text else ""

        # Extract date from URL (/on/YYYY/MM/DD) or title
        date_start = None

        if event_url:
            m = re.search(r"/on/(\d{4})/(\d{2})/(\d{2})", event_url)
            if m:
                date_start = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        if not date_start:
            m = re.search(r"(\d{2})-(\d{2})-(\d{2,4})$", raw_title)
            if m:
                day, month, year = m.groups()
                if len(year) == 2:
                    year = f"20{year}"
                try:
                    dt = datetime(int(year), int(month), int(day))
                    date_start = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        if not date_start:
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", raw_title)
            if m:
                day, month, year = m.groups()
                try:
                    dt = datetime(int(year), int(month), int(day))
                    date_start = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        if not date_start and pub_date_el is not None and pub_date_el.text:
            try:
                pub_dt = parsedate_to_datetime(pub_date_el.text)
                date_start = pub_dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        if not date_start:
            return None

        title = re.sub(r"\s+\d{2}[-/]\d{2}[-/]\d{2,4}$", "", raw_title).strip()
        if not title:
            title = raw_title

        return self._build_event(
            name=title,
            date_start=date_start,
            discipline=None,
            url=event_url,
        )

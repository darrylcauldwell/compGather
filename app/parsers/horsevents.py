from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

BASE_URL = "https://horsevents.co.uk"
DIARY_URL = f"{BASE_URL}/diary/?dateFilter=5&counties=-1&showType=-1&cmdApply=Apply+Filter"


@register_parser("horsevents")
class HorsEventsParser(TwoPhaseParser):
    """Parser for horsevents.co.uk — diary listing + concurrent JSON-LD detail pages."""

    CONCURRENCY = 8

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        today = date.today()
        async with self._make_client() as client:
            event_stubs = await self._scrape_diary(client, today)
            logger.info("HorsEvents: %d events from diary listing", len(event_stubs))

            competitions = await self._concurrent_fetch(
                event_stubs,
                lambda stub: self._enrich_from_detail(client, stub, today),
                fallback_fn=self._build_from_stub,
            )

        self._log_result("HorsEvents", len(competitions))
        return competitions

    async def _scrape_diary(self, client, today):
        try:
            resp = await client.get(DIARY_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("HorsEvents: diary fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        stubs, seen_ids = [], set()

        for div in soup.find_all("div", id="colwholeevent"):
            stub = self._parse_listing_item(div, today)
            if stub and stub["event_id"] not in seen_ids:
                seen_ids.add(stub["event_id"])
                stubs.append(stub)
        return stubs

    def _parse_listing_item(self, div, today):
        title_span = div.find("span", class_="titleev")
        if not title_span:
            return None
        link = title_span.find("a", href=True)
        if not link:
            return None

        name = link.get_text(strip=True)
        if not name:
            return None

        eid_match = re.search(r"/events/(\d+)", link["href"])
        if not eid_match:
            return None
        event_id = eid_match.group(1)

        subtitle = div.find("p", class_="subtitleev")
        date_start, venue_name, discipline = None, "TBC", None

        if subtitle:
            parts = [p.strip() for p in subtitle.get_text(separator="|", strip=True).split("|")]
            if parts:
                date_start = self._extract_date_from_text(parts[0])

            venue_el = subtitle.find("span", class_="darkGrey")
            if venue_el:
                venue_name = venue_el.get_text(strip=True) or "TBC"

            disc_link = subtitle.find("a", href=re.compile(r"/disciplines/"))
            if disc_link:
                discipline = disc_link.get_text(strip=True)

        if not date_start:
            return None

        try:
            if date.fromisoformat(date_start) < today:
                return None
        except ValueError:
            pass

        return {
            "event_id": event_id, "name": name, "date_start": date_start,
            "venue_name": venue_name, "discipline": discipline,
            "url": f"{BASE_URL}/events/?e={event_id}",
        }

    async def _enrich_from_detail(self, client, stub, today):
        url = stub["url"]
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        json_ld = self._extract_json_ld(soup)
        if json_ld:
            name = json_ld.get("name", stub["name"]).strip()
            date_start = self._normalize_date(json_ld.get("startDate", "")) or stub["date_start"]
            date_end = self._normalize_date(json_ld.get("endDate", ""))
            location = json_ld.get("location", {})
            venue_name = location.get("name", "").strip() if isinstance(location, dict) else ""
            address = location.get("address", {}) if isinstance(location, dict) else {}
            postcode = address.get("postalCode", "").strip() if isinstance(address, dict) else ""
        else:
            name, date_start, date_end = stub["name"], stub["date_start"], None
            venue_name, postcode = "", ""

        if not name or not date_start:
            return None

        if not postcode:
            postcode = extract_postcode(soup.get_text())

        return self._build_event(
            name=name, date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue_name or stub.get("venue_name", "TBC"),
            venue_postcode=postcode or None,
            discipline=stub.get("discipline"),
            url=url,
        )

    def _build_from_stub(self, stub):
        if not stub.get("date_start") or not stub.get("name"):
            return None
        return self._build_event(
            name=stub["name"], date_start=stub["date_start"],
            venue_name=stub.get("venue_name", "TBC"),
            discipline=stub.get("discipline"),
            url=stub.get("url"),
        )

    def _extract_json_ld(self, soup):
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "Event":
                    return data
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Event":
                            return item
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _normalize_date(self, date_str):
        if not date_str:
            return None
        date_part = date_str.split("T")[0]
        parts = date_part.split("-")
        if len(parts) == 3:
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
        return date_part

    def _extract_date_from_text(self, text):
        match = re.search(r"(\d{1,2})\s+(\w{3,})\s+(\d{4})", text)
        if match:
            try:
                return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if match:
            return f"{match.group(3)}-{match.group(2).zfill(2)}-{match.group(1).zfill(2)}"
        return None

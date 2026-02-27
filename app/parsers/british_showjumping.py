from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

BASE_URL = "https://www.britishshowjumping.co.uk"
CALENDAR_URL = f"{BASE_URL}/show-calendar.cfm"
LATLNG_RE = re.compile(r"maps/@([\d.-]+),([\d.-]+)")


@register_parser("british_showjumping")
class BritishShowjumpingParser(TwoPhaseParser):
    """Parser for britishshowjumping.co.uk show calendar."""

    CONCURRENCY = 15

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        today = date.today()
        date_from = today.strftime("%d/%m/%Y")
        date_to = (today + timedelta(days=365)).strftime("%d/%m/%Y")

        limits = httpx.Limits(max_connections=20, max_keepalive_connections=15)
        async with self._make_client(limits=limits) as client:
            shows = await self._fetch_all_pages(client, date_from, date_to)
            logger.info("British Showjumping: %d show-days from calendar pages", len(shows))

            deduplicated = self._deduplicate_multiday(shows)
            logger.info("British Showjumping: %d unique shows after dedup", len(deduplicated))

            competitions = await self._concurrent_fetch(
                deduplicated,
                lambda show: self._enrich_from_detail(client, show),
                fallback_fn=self._build_basic_competition,
            )

        self._log_result("British Showjumping", len(competitions))
        return competitions

    async def _fetch_all_pages(self, client, date_from, date_to):
        all_shows = []
        page = 1
        max_pages = 200

        while page <= max_pages:
            params = {
                "showFrom": date_from, "showTo": date_to,
                "showMultiDay": "0", "PageNum_rsEvents": str(page),
            }
            try:
                resp = await client.get(CALENDAR_URL, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("BS: page %d fetch failed: %s", page, e)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            shows_on_page = self._parse_calendar_table(soup, date_from)

            if not shows_on_page:
                break
            if len(shows_on_page) == 1 and all_shows:
                if shows_on_page[0]["name"] == all_shows[-1]["name"]:
                    break

            all_shows.extend(shows_on_page)
            if not soup.find("a", string=re.compile(r"NEXT", re.IGNORECASE)):
                break
            page += 1

        return all_shows

    def _parse_calendar_table(self, soup, date_from):
        shows = []
        year = int(date_from.split("/")[2])

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 4:
                continue

            detail_link = tds[3].find("a", href=re.compile(r"centre-detail\.cfm"))
            if not detail_link:
                continue

            date_text = tds[0].get_text(strip=True)
            show_type = tds[1].get_text(strip=True)
            area = tds[2].get_text(strip=True)
            show_name = detail_link.get_text(strip=True)
            detail_href = detail_link["href"]

            shid_match = re.search(r"shid=(\d+)", detail_href)
            show_id = shid_match.group(1) if shid_match else None

            parsed_date = self._parse_calendar_date(date_text, year)
            if not parsed_date:
                continue

            categories = self._extract_categories(show_type)
            detail_url = detail_href if detail_href.startswith("http") else f"{BASE_URL}/{detail_href.lstrip('/')}"

            shows.append({
                "name": show_name, "date_text": parsed_date, "show_type": show_type,
                "area": area, "show_id": show_id, "detail_url": detail_url,
                "categories": categories,
            })

        return shows

    def _deduplicate_multiday(self, shows):
        by_id: dict[str, dict] = {}
        for show in shows:
            sid = show.get("show_id")
            if not sid:
                by_id[f"_no_id_{id(show)}"] = show
                continue

            if sid in by_id:
                existing = by_id[sid]
                if show["date_text"] < existing["date_text"]:
                    existing["date_start_override"] = show["date_text"]
                if show["date_text"] > existing.get("date_end_override", existing["date_text"]):
                    existing["date_end_override"] = show["date_text"]
                existing["categories"] |= show["categories"]
            else:
                by_id[sid] = show.copy()

        return list(by_id.values())

    async def _enrich_from_detail(self, client, show):
        resp = await client.get(show["detail_url"])
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text()

        postcode = extract_postcode(page_text)

        date_start = show.get("date_start_override", show["date_text"])
        date_end = show.get("date_end_override")
        h1 = soup.find("h1")
        if h1:
            date_range = self._parse_detail_date_range(h1.get_text(strip=True))
            if date_range:
                date_start, date_end = date_range

        classes = self._extract_classes(soup)

        name = self._build_event_name(show)

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=show["name"],
            venue_postcode=postcode,
            discipline="Show Jumping",
            classes=classes,
            url=show["detail_url"],
        )

    def _build_basic_competition(self, show):
        date_start = show.get("date_start_override", show.get("date_text"))
        if not date_start:
            return None
        return self._build_event(
            name=self._build_event_name(show),
            date_start=date_start,
            date_end=show.get("date_end_override"),
            venue_name=show["name"],
            discipline="Show Jumping",
            url=show["detail_url"],
        )

    def _build_event_name(self, show):
        venue = show["name"]
        show_type = show.get("show_type", "").strip()
        if show_type:
            level = show_type.split("(")[0].strip()
            if level:
                return f"BS {level.title()} Show Jumping - {venue}"
        return f"BS Show Jumping - {venue}"

    def _parse_calendar_date(self, text, year):
        cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text).strip()
        try:
            return datetime.strptime(f"{cleaned} {year}", "%a %d %b %Y").strftime("%Y-%m-%d")
        except ValueError:
            match = re.search(r"(\d{1,2})\s+(\w+)", cleaned)
            if match:
                try:
                    return datetime.strptime(f"{match.group(1)} {match.group(2)} {year}", "%d %b %Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass
        return None

    def _parse_detail_date_range(self, h1_text):
        match = re.search(r"\w+\s+(\d{1,2})\s+TO\s+\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})", h1_text, re.IGNORECASE)
        if match:
            try:
                start = datetime.strptime(f"{match.group(1)} {match.group(3)} {match.group(4)}", "%d %B %Y")
                end = datetime.strptime(f"{match.group(2)} {match.group(3)} {match.group(4)}", "%d %B %Y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        match = re.search(r"\w+\s+(\d{1,2})\s+(\w+)\s+(\d{4})", h1_text, re.IGNORECASE)
        if match:
            try:
                dt = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass
        return None

    def _extract_categories(self, show_type):
        match = re.search(r"\(([^)]+)\)", show_type)
        return {c.strip() for c in match.group(1).split(",")} if match else set()

    def _extract_classes(self, soup):
        classes = []
        for table in soup.find_all("table"):
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 4:
                    class_text = tds[2].get_text(strip=True)
                    class_text = re.sub(r"\s+\d{7}$", "", class_text)
                    if class_text and len(class_text) > 5:
                        classes.append(class_text)
        return classes

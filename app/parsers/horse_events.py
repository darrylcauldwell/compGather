from __future__ import annotations

import json
import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from app.parsers.bases import TwoPhaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, extract_venue_from_name, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.horse-events.co.uk/event/event-sitemap.xml"
BASE_URL = "https://www.horse-events.co.uk"
RALLIES_VIEWALL = f"{BASE_URL}/pony-club-rallies/?viewall=1"

_SLUG_DATE_RE = re.compile(r"(\d{4})(\d{2})(\d{2})(?:-\d+)?/?$")

_LISTING_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})",
    re.IGNORECASE,
)

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_JUNK_VENUE_RE = re.compile(
    r"^Booking\s+Status|^Book\s+Now|\d+\s+\w+\s+(Street|Road|Lane|Close|Drive|Avenue|Way|Crescent)\b",
    re.IGNORECASE,
)


def _is_junk_venue(name: str) -> bool:
    return bool(_JUNK_VENUE_RE.search(name))


def _date_from_slug(url: str) -> date | None:
    m = _SLUG_DATE_RE.search(url)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


@register_parser("horse_events")
class HorseEventsParser(TwoPhaseParser):
    """Parser for horse-events.co.uk — bulk listing + concurrent detail fetches."""

    CONCURRENCY = 8

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        today = date.today()
        async with self._make_client() as client:
            # Phase 1: bulk-parse the pony-club-rallies viewall listing
            rallies, rally_urls = await self._parse_rallies_listing(client, today)
            logger.info("Horse Events: %d competitions from rallies listing page", len(rallies))

            # Phase 1b: enrich rallies with postcodes from detail pages
            needs_postcode = [c for c in rallies if not c.venue_postcode and c.url]
            if needs_postcode:
                enriched = await self._concurrent_fetch(
                    needs_postcode,
                    lambda comp: self._enrich_rally_postcode(client, comp),
                    fallback_fn=lambda comp: comp,
                )
                by_url = {c.url: c for c in enriched}
                rallies = [by_url.get(c.url, c) for c in rallies]
                pc_count = sum(1 for c in rallies if c.venue_postcode)
                logger.info("Horse Events: %d/%d rallies now have postcodes", pc_count, len(rallies))

            # Phase 2: get /horse-events/ URLs from sitemap (rallies already covered)
            sitemap_urls = await self._get_event_urls_from_sitemap(client)
            detail_urls = [
                u for u in sitemap_urls
                if "/horse-events/" in u and self._is_future_url(u, today)
            ]
            logger.info(
                "Horse Events: %d sitemap URLs, %d to fetch after filtering",
                len(sitemap_urls), len(detail_urls),
            )

            detail_comps = await self._concurrent_fetch(
                detail_urls,
                lambda u: self._parse_event_page(client, u, today),
            )
            logger.info("Horse Events: %d competitions from detail pages", len(detail_comps))

            competitions = rallies + detail_comps

        logger.info("Horse Events: %d total competitions", len(competitions))
        return competitions

    # -- Bulk rallies listing --

    async def _parse_rallies_listing(self, client, today):
        comps: list[ExtractedEvent] = []
        urls_seen: set[str] = set()
        try:
            resp = await client.get(RALLIES_VIEWALL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Horse Events: rallies listing fetch failed: %s", e)
            return comps, urls_seen

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.find_all("div", class_=re.compile(r"search-result|event-listing-item"))
        if not items:
            items = soup.find_all("div", attrs={"data-href": True})
        if not items:
            items = soup.select(".content-area h3, main h3, #content h3")

        for item in items:
            comp = self._parse_listing_item(item, today)
            if comp:
                comps.append(comp)
                urls_seen.add(comp.url)

        return comps, urls_seen

    def _parse_listing_item(self, item, today):
        link = item.find("a", href=True)
        if not link:
            if item.get("data-href"):
                event_url = item["data-href"]
            else:
                return None
        else:
            event_url = link["href"]
        if not event_url.startswith("http"):
            event_url = BASE_URL + event_url

        title_el = item.find("h3") or item.find(class_="result-title")
        if not title_el:
            return None
        name = title_el.get_text(strip=True)
        if not name:
            return None

        item_text = item.get_text(" ", strip=True)
        start_date, end_date = None, None

        date_matches = list(_LISTING_DATE_RE.finditer(item_text))
        if date_matches:
            first = date_matches[0]
            try:
                start_date = date(
                    int(first.group(3)), _MONTH_MAP[first.group(2).lower()], int(first.group(1)),
                )
            except (ValueError, KeyError):
                pass
            if len(date_matches) >= 2:
                last = date_matches[-1]
                try:
                    end_date = date(
                        int(last.group(3)), _MONTH_MAP[last.group(2).lower()], int(last.group(1)),
                    )
                except (ValueError, KeyError):
                    pass

        if not start_date:
            start_date = _date_from_slug(event_url)
        if not start_date or start_date < today:
            return None
        if end_date and end_date == start_date:
            end_date = None

        venue_name = "TBC"
        loc_match = re.search(r"Location:\s*(.+?)(?:\s*Booking|\s*Withdrawal|\s*$)", item_text)
        if loc_match:
            raw_venue = loc_match.group(1).strip()
            if raw_venue and not _is_junk_venue(raw_venue):
                venue_name = raw_venue
        if venue_name == "TBC":
            from_name = extract_venue_from_name(name)
            if from_name:
                venue_name = from_name

        is_pony = (
            "/pony-club-rallies/" in event_url
            or any(kw in name.lower() for kw in ["pony", "junior", "u18", "u16", "u14"])
        )
        discipline = infer_discipline(name)
        if not discipline and "/pony-club-rallies/" in event_url:
            discipline = "Pony Club"

        return self._build_event(
            name=name,
            date_start=start_date.isoformat(),
            date_end=end_date.isoformat() if end_date else None,
            venue_name=venue_name,
            discipline=discipline,
            has_pony_classes=is_pony,
            url=event_url,
        )

    # -- Sitemap discovery --

    async def _get_event_urls_from_sitemap(self, client):
        try:
            resp = await client.get(SITEMAP_URL)
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Horse Events: sitemap fetch failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "xml")
        urls = []
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            if "/horse-events/" in url or "/pony-club-rallies/" in url:
                urls.append(url)
        return urls

    def _is_future_url(self, url, today):
        d = _date_from_slug(url)
        return d >= today if d else True

    # -- Detail page parsing --

    async def _parse_event_page(self, client, url, today):
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        json_ld = self._extract_json_ld(soup)
        if not json_ld:
            return None

        name = json_ld.get("name", "").strip()
        start_date_str = json_ld.get("startDate", "")
        end_date_str = json_ld.get("endDate", "")

        if not name or not start_date_str:
            return None

        try:
            if date.fromisoformat(start_date_str) < today:
                return None
        except ValueError:
            pass

        location = json_ld.get("location", {})
        raw_venue = location.get("name", "").strip() if isinstance(location, dict) else ""
        venue_name = raw_venue if raw_venue and not _is_junk_venue(raw_venue) else ""
        if not venue_name:
            from_name = extract_venue_from_name(name)
            if from_name:
                venue_name = from_name

        postcode = self._extract_postcode(html, soup)

        is_pony = (
            "/pony-club-rallies/" in url
            or any(kw in name.lower() for kw in ["pony", "junior", "u18", "u16", "u14"])
        )
        discipline = infer_discipline(name)
        if not discipline and "/pony-club-rallies/" in url:
            discipline = "Pony Club"

        end_date = end_date_str if end_date_str and end_date_str != start_date_str else None

        return self._build_event(
            name=name,
            date_start=start_date_str,
            date_end=end_date,
            venue_name=venue_name or "TBC",
            venue_postcode=postcode,
            discipline=discipline,
            has_pony_classes=is_pony,
            url=url,
        )

    # -- Rally postcode enrichment --

    async def _enrich_rally_postcode(self, client, comp):
        """Fetch a rally detail page to extract its postcode."""
        resp = await client.get(comp.url)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        postcode = self._extract_postcode(html, soup)
        if postcode:
            return comp.model_copy(update={"venue_postcode": postcode})
        return comp

    # -- Helpers --

    def _extract_json_ld(self, soup):
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") == "Event":
                        return data
                    for item in data.get("@graph", []):
                        if item.get("@type") == "Event":
                            return item
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Event":
                            return item
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _extract_postcode(self, html, soup):
        m = re.search(r"var\s+event_postcode\s*=\s*['\"]([^'\"]+)['\"]", html)
        if m:
            return m.group(1).strip()
        return extract_postcode(soup.get_text())

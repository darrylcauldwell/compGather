from __future__ import annotations

import json
import logging
import re
from datetime import date

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import infer_discipline
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

SITEMAP_URL = "https://www.horse-events.co.uk/event/event-sitemap.xml"
BASE_URL = "https://www.horse-events.co.uk"

# UK postcode regex
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)


@register_parser("horse_events")
class HorseEventsParser(BaseParser):
    """Parser for horse-events.co.uk — WordPress event platform with sitemap + JSON-LD."""

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Phase 1: Discover event URLs from sitemap
            event_urls = await self._get_event_urls_from_sitemap(client)
            logger.info("Horse Events: %d event URLs from sitemap", len(event_urls))

            # Phase 2: Fetch each event page and extract data
            competitions = []
            for event_url in event_urls:
                try:
                    comp = await self._parse_event_page(client, event_url)
                    if comp:
                        competitions.append(comp)
                except Exception as e:
                    logger.debug("Horse Events: failed to parse %s: %s", event_url, e)

        logger.info("Horse Events: extracted %d competitions", len(competitions))
        return competitions

    async def _get_event_urls_from_sitemap(self, client: httpx.AsyncClient) -> list[str]:
        """Fetch the event sitemap XML and extract all event URLs."""
        try:
            resp = await client.get(SITEMAP_URL)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Horse Events: sitemap fetch failed: %s", e)
            # Fallback: try paginated listing
            return await self._get_event_urls_from_listing(client)

        soup = BeautifulSoup(resp.text, "xml")
        urls = []
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            # Only include horse-events and pony-club-rallies paths
            if "/horse-events/" in url or "/pony-club-rallies/" in url:
                urls.append(url)
        return urls

    async def _get_event_urls_from_listing(self, client: httpx.AsyncClient) -> list[str]:
        """Fallback: paginate through /pony-club-rallies/ listing."""
        urls = []
        page = 1
        max_pages = 200  # Safety limit

        while page <= max_pages:
            resp = await client.get(f"{BASE_URL}/pony-club-rallies/", params={"page": str(page)})
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            links_found = 0
            for a in soup.find_all("a", href=re.compile(r"/(?:horse-events|pony-club-rallies)/[^/]+/")):
                href = a["href"]
                full_url = href if href.startswith("http") else BASE_URL + href
                if full_url not in urls:
                    urls.append(full_url)
                    links_found += 1

            if links_found == 0:
                break
            page += 1

        return urls

    async def _parse_event_page(self, client: httpx.AsyncClient, url: str) -> ExtractedCompetition | None:
        """Parse a single event page using JSON-LD + JS variables + HTML."""
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Extract JSON-LD Event data
        json_ld = self._extract_json_ld(soup)

        # Extract JS variables (event_postcode, event_id, etc.)
        js_vars = self._extract_js_variables(html)

        if not json_ld:
            logger.debug("Horse Events: no JSON-LD on %s", url)
            return None

        name = json_ld.get("name", "").strip()
        start_date = json_ld.get("startDate", "")
        end_date = json_ld.get("endDate", "")

        if not name or not start_date:
            return None

        # Filter out past events
        try:
            start_dt = date.fromisoformat(start_date)
            if start_dt < date.today():
                return None
        except ValueError:
            pass

        # Venue from JSON-LD location
        location = json_ld.get("location", {})
        venue_name = location.get("name", "").strip() if isinstance(location, dict) else ""

        # Postcode: prefer JS variable, then try page text
        postcode = js_vars.get("event_postcode")
        if not postcode:
            page_text = soup.get_text()
            pc_match = POSTCODE_RE.search(page_text)
            if pc_match:
                postcode = pc_match.group(0).strip()

        # Extract classes from HTML
        classes = self._extract_classes(soup)

        # Detect pony classes
        page_text = soup.get_text().lower()
        has_pony = (
            "/pony-club-rallies/" in url
            or any(kw in name.lower() for kw in ["pony", "junior", "u18", "u16", "u14"])
            or any(kw in page_text for kw in ["pony classes", "pony class"])
        )

        discipline = infer_discipline(name) or ("Pony Club" if "/pony-club-rallies/" in url else None)

        return ExtractedCompetition(
            name=name,
            date_start=start_date,
            date_end=end_date if end_date and end_date != start_date else None,
            venue_name=venue_name or "TBC",
            venue_postcode=postcode,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=classes,
            url=url,
        )

    def _extract_json_ld(self, soup: BeautifulSoup) -> dict | None:
        """Extract Event JSON-LD from the page."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") == "Event":
                        return data
                    # Yoast sometimes wraps in @graph
                    graph = data.get("@graph", [])
                    for item in graph:
                        if item.get("@type") == "Event":
                            return item
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Event":
                            return item
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _extract_js_variables(self, html: str) -> dict:
        """Extract JavaScript variables like event_postcode, event_id, etc."""
        vars_found = {}
        patterns = {
            "event_id": r"var\s+event_id\s*=\s*(\d+)",
            "event_postcode": r"var\s+event_postcode\s*=\s*['\"]([^'\"]+)['\"]",
            "spaces_max": r"var\s+spaces_max\s*=\s*(\d+)",
            "spaces_remaining": r"var\s+spaces_remaining\s*=\s*(\d+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, html)
            if match:
                vars_found[key] = match.group(1)
        return vars_found

    def _extract_classes(self, soup: BeautifulSoup) -> list[str]:
        """Extract class/ticket names from the page."""
        classes = []
        # Look for class listing divs or definition lists
        for h4 in soup.find_all("h4"):
            text = h4.get_text(strip=True)
            if text and ("class" in text.lower() or re.match(r"^\d", text)):
                classes.append(text)

        # Also look for class descriptions in list items
        if not classes:
            for li in soup.find_all("li"):
                text = li.get_text(strip=True)
                if re.match(r"Class\s+\d", text, re.IGNORECASE):
                    classes.append(text)

        return classes


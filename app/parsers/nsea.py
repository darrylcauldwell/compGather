from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

COMPETITIONS_URL = "https://www.nsea.org.uk/competitions/"

# UK postcode regex
POSTCODE_RE = re.compile(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", re.IGNORECASE)


@register_parser("nsea")
class NSEAParser(BaseParser):
    """Parser for nsea.org.uk — National Schools Equestrian Association."""

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Phase 1: Parse listings table
            competitions = await self._parse_listings(client, url)
            logger.info("NSEA listings: %d competitions from table", len(competitions))

            # Phase 2: Enrich with detail page data (venue name, postcode, deadline)
            enriched = []
            for comp, detail_url in competitions:
                if detail_url:
                    try:
                        comp = await self._enrich_from_detail(client, comp, detail_url)
                    except Exception as e:
                        logger.debug("NSEA: failed to enrich %s: %s", detail_url, e)
                enriched.append(comp)

        logger.info("NSEA: extracted %d competitions total", len(enriched))
        return enriched

    async def _parse_listings(self, client: httpx.AsyncClient, url: str) -> list[tuple[ExtractedCompetition, str | None]]:
        """Parse the competitions listing table."""
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        results: list[tuple[ExtractedCompetition, str | None]] = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue

            # Try 5-column layout: date | name | location | code | status
            if len(tds) >= 5:
                date_text = tds[0].get_text(strip=True)
                name_tag = tds[1].find("a")
                name = name_tag.get_text(strip=True) if name_tag else tds[1].get_text(strip=True)
                detail_url = self._resolve_url(name_tag["href"]) if name_tag and name_tag.get("href") else None
                location = tds[2].get_text(strip=True)
            else:
                # Fallback: fewer columns
                date_text = tds[0].get_text(strip=True)
                name_tag = tds[1].find("a")
                name = name_tag.get_text(strip=True) if name_tag else tds[1].get_text(strip=True)
                detail_url = self._resolve_url(name_tag["href"]) if name_tag and name_tag.get("href") else None
                location = tds[2].get_text(strip=True) if len(tds) > 2 else ""

            if not name or not date_text:
                continue

            date_start, date_end = self._parse_date_cell(date_text)
            if not date_start:
                continue

            # Filter out past events
            if not is_future_event(date_start, date_end):
                continue

            comp = ExtractedCompetition(
                name=name,
                date_start=date_start,
                date_end=date_end,
                venue_name=location if location else "TBC",
                venue_postcode=None,
                discipline="NSEA",
                has_pony_classes=True,  # All NSEA events are school/pony competitions
                classes=[],
                url=detail_url or "https://www.nsea.org.uk/competitions/",
            )
            results.append((comp, detail_url))

        return results

    async def _enrich_from_detail(self, client: httpx.AsyncClient, comp: ExtractedCompetition, url: str) -> ExtractedCompetition:
        """Fetch a detail page to get venue name, postcode, and deadline."""
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text()

        # Extract venue from "The Venue" section
        venue_heading = soup.find("h3", string=re.compile(r"The Venue", re.IGNORECASE))
        if venue_heading:
            next_p = venue_heading.find_next_sibling("p")
            if next_p:
                venue_text = next_p.get_text(separator=", ", strip=True)
                # First line is usually the venue name
                venue_parts = [p.strip() for p in venue_text.split(",") if p.strip()]
                if venue_parts:
                    comp.venue_name = venue_parts[0]

                # Extract postcode from venue address
                postcode_match = POSTCODE_RE.search(venue_text)
                if postcode_match:
                    comp.venue_postcode = postcode_match.group(0).strip()


        # If still no postcode, try the whole page text
        if not comp.venue_postcode:
            postcode_match = POSTCODE_RE.search(page_text)
            if postcode_match:
                comp.venue_postcode = postcode_match.group(0).strip()

        # Extract classes from detail page
        classes = self._extract_classes(soup)
        if classes:
            comp.classes = classes

        return comp

    def _parse_date_cell(self, text: str) -> tuple[str | None, str | None]:
        """Parse date cell: '21 Feb 2026' or '1 Feb 2026 - 28 Feb 2026'."""
        text = text.strip()

        # Try date range first: "1 Feb 2026 - 28 Feb 2026"
        range_match = re.match(
            r"(\d{1,2}\s+\w+\s+\d{4})\s*[-–]\s*(\d{1,2}\s+\w+\s+\d{4})",
            text
        )
        if range_match:
            start = self._parse_single_date(range_match.group(1))
            end = self._parse_single_date(range_match.group(2))
            return start, end

        # Single date: "21 Feb 2026"
        start = self._parse_single_date(text)
        return start, None

    def _parse_single_date(self, text: str) -> str | None:
        """Parse a single date like '21 Feb 2026' into YYYY-MM-DD."""
        text = text.strip()
        # Remove ordinal suffixes
        text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text)
        for fmt in ["%d %b %Y", "%d %B %Y"]:
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _extract_classes(self, soup: BeautifulSoup) -> list[str]:
        """Extract class info from detail page.

        Looks for patterns like 'Class 1', 'Class 2' in headings, tables, and lists.
        """
        classes = []

        # Look for headings with "Class N" pattern
        for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
            text = heading.get_text(strip=True)
            if re.match(r"Class\s+\d", text, re.IGNORECASE):
                classes.append(text)

        # Look in table cells
        if not classes:
            for table in soup.find_all("table"):
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    for td in tds:
                        text = td.get_text(strip=True)
                        if re.match(r"Class\s+\d", text, re.IGNORECASE) and len(text) > 5:
                            classes.append(text)

        # Look in list items
        if not classes:
            for li in soup.find_all("li"):
                text = li.get_text(strip=True)
                if re.match(r"Class\s+\d", text, re.IGNORECASE):
                    classes.append(text)

        return classes

    def _resolve_url(self, href: str) -> str:
        """Resolve a relative URL to absolute."""
        if href.startswith("http"):
            return href
        return f"https://www.nsea.org.uk{href}" if href.startswith("/") else f"https://www.nsea.org.uk/{href}"

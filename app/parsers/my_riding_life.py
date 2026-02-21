from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

BASE_URL = "https://www.myridinglife.com/myridinglife/onlineentries.aspx"

# Postcode in parentheses: "Manor Grange Stud (WF110AZ)"
POSTCODE_RE = re.compile(r"\(([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\)", re.IGNORECASE)

# Non-competition disciplines to skip
SKIP_DISCIPLINES = {"Box Office"}


@register_parser("my_riding_life")
class MyRidingLifeParser(BaseParser):
    """Parser for myridinglife.com — ASP.NET WebForms with postback pagination.

    The online entries page has a table with 8 columns:
    Actions | Event Name | From Date | To Date | Discipline | Location | County | Distance
    25 events per page, ~97 pages, paginated via __doPostBack.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Fetch page 1 to get initial form state and total pages
            resp = await client.get(BASE_URL)
            resp.raise_for_status()
            html = resp.text

            total_pages = self._get_hidden_value(html, "hfTotalPages")
            max_pages = int(total_pages) if total_pages else 1
            logger.info("My Riding Life: %d pages to fetch", max_pages)

            all_competitions: list[ExtractedCompetition] = []
            seen: set[tuple[str, str]] = set()

            # Parse page 1
            comps = self._parse_page(html)
            for c in comps:
                key = (c.name, c.date_start)
                if key not in seen:
                    seen.add(key)
                    all_competitions.append(c)

            # Paginate through remaining pages
            for page in range(2, max_pages + 1):
                try:
                    form_data = self._build_postback_form(html, page)
                    resp = await client.post(BASE_URL, data=form_data)
                    resp.raise_for_status()
                    html = resp.text

                    comps = self._parse_page(html)
                    for c in comps:
                        key = (c.name, c.date_start)
                        if key not in seen:
                            seen.add(key)
                            all_competitions.append(c)

                    if page % 20 == 0:
                        logger.info("MRL: fetched %d/%d pages, %d events",
                                    page, max_pages, len(all_competitions))
                except Exception as e:
                    logger.warning("MRL: page %d failed: %s", page, e)
                    break

        logger.info("My Riding Life: extracted %d competitions", len(all_competitions))
        return all_competitions

    def _parse_page(self, html: str) -> list[ExtractedCompetition]:
        """Parse events from a single page of results."""
        soup = BeautifulSoup(html, "html.parser")
        competitions = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 8:
                continue

            # col 1: Event Name, col 2: From Date, col 3: To Date,
            # col 4: Discipline, col 5: Location, col 6: County
            name = tds[1].get_text(strip=True)
            from_date_text = tds[2].get_text(strip=True)
            to_date_text = tds[3].get_text(strip=True)
            discipline_text = tds[4].get_text(strip=True)
            location_text = tds[5].get_text(strip=True)

            if not name or not from_date_text:
                continue

            # Skip non-competition disciplines
            if discipline_text in SKIP_DISCIPLINES:
                continue

            # Parse dates (DD/MM/YYYY)
            date_start = self._parse_date(from_date_text)
            date_end = self._parse_date(to_date_text)
            if not date_start:
                continue

            if not is_future_event(date_start, date_end):
                continue

            # Extract postcode from location: "Venue Name (AB12 3CD)"
            postcode = None
            pc_match = POSTCODE_RE.search(location_text)
            if pc_match:
                postcode = pc_match.group(1).strip()

            # Venue name is location without the postcode part
            venue_name = POSTCODE_RE.sub("", location_text).strip().rstrip("()")
            if not venue_name or venue_name.lower() in ("uk location", "n/a"):
                venue_name = name

            # Extract event detail URL if available
            event_url = None
            link = tds[1].find("a", href=True)
            if link:
                href = link["href"]
                if href.startswith("http"):
                    event_url = href
                elif href.startswith("/"):
                    event_url = f"https://www.myridinglife.com{href}"
                else:
                    event_url = f"https://www.myridinglife.com/myridinglife/{href}"

            discipline = infer_discipline(name) or discipline_text
            has_pony = detect_pony_classes(name)

            competitions.append(ExtractedCompetition(
                name=name,
                date_start=date_start,
                date_end=date_end if date_end and date_end != date_start else None,
                venue_name=venue_name,
                venue_postcode=postcode,
                discipline=discipline,
                has_pony_classes=has_pony,
                url=event_url or BASE_URL,
            ))

        return competitions

    def _build_postback_form(self, html: str, target_page: int) -> dict:
        """Build ASP.NET postback form data for pagination."""
        return {
            "__EVENTTARGET": "ctl00$mainContent$lnkNextPage",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": self._get_hidden_value(html, "__VIEWSTATE") or "",
            "__VIEWSTATEGENERATOR": self._get_hidden_value(html, "__VIEWSTATEGENERATOR") or "",
            "__EVENTVALIDATION": self._get_hidden_value(html, "__EVENTVALIDATION") or "",
            "ctl00$mainContent$hfCurrentPage": str(target_page - 1),
            "ctl00$mainContent$hfTotalPages": self._get_hidden_value(html, "hfTotalPages") or "",
            "ctl00$mainContent$hfPageSize": self._get_hidden_value(html, "hfPageSize") or "25",
            "ctl00$mainContent$hfStartDate": self._get_hidden_value(html, "hfStartDate") or "",
            "ctl00$mainContent$hfEndDate": self._get_hidden_value(html, "hfEndDate") or "",
        }

    def _get_hidden_value(self, html: str, field_name: str) -> str | None:
        """Extract a hidden form field value."""
        match = re.search(
            rf'name="[^"]*{re.escape(field_name)}"[^>]*value="([^"]*)"', html
        )
        return match.group(1) if match else None

    def _parse_date(self, text: str) -> str | None:
        """Parse DD/MM/YYYY into YYYY-MM-DD."""
        try:
            return datetime.strptime(text.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None

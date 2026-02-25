from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, normalise_postcode
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

BASE_URL = "https://www.myridinglife.com/myridinglife/onlineentries.aspx"

POSTCODE_RE = re.compile(r"\(([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\)", re.IGNORECASE)

_ORG_SUFFIXES_RE = re.compile(
    r"(Riding\s+Club|Pony\s+Club|Equestrian\s+Centre|Equestrian\s+Club"
    r"|RC\b|PC\b)",
    re.IGNORECASE,
)


@register_parser("my_riding_life")
class MyRidingLifeParser(HttpParser):
    """Parser for myridinglife.com — ASP.NET WebForms with postback pagination.

    The online entries page has a table with 8 columns:
    Actions | Event Name | From Date | To Date | Discipline | Location | County | Distance
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            resp = await client.get(BASE_URL)
            resp.raise_for_status()
            html = resp.text

            total_pages = self._get_hidden_value(html, "hfTotalPages")
            max_pages = int(total_pages) if total_pages else 1
            logger.info("My Riding Life: %d pages to fetch", max_pages)

            all_competitions: list[ExtractedEvent] = []
            seen: set[tuple[str, str]] = set()

            comps = self._parse_page(html)
            for c in comps:
                key = (c.name, c.date_start)
                if key not in seen:
                    seen.add(key)
                    all_competitions.append(c)

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
                        logger.info("MRL: fetched %d/%d pages, %d events", page, max_pages, len(all_competitions))
                except Exception as e:
                    logger.warning("MRL: page %d failed: %s", page, e)
                    break

        self._log_result("My Riding Life", len(all_competitions))
        return all_competitions

    def _parse_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        competitions = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 8:
                continue

            name = tds[1].get_text(strip=True)
            from_date_text = tds[2].get_text(strip=True)
            to_date_text = tds[3].get_text(strip=True)
            discipline_text = tds[4].get_text(strip=True)
            location_text = tds[5].get_text(separator=" ", strip=True)

            if not name or not from_date_text:
                continue

            date_start = self._parse_mrl_date(from_date_text)
            date_end = self._parse_mrl_date(to_date_text)
            if not date_start:
                continue

            postcode = None
            pc_match = POSTCODE_RE.search(location_text)
            if pc_match:
                postcode = normalise_postcode(pc_match.group(1).strip())

            venue_name = POSTCODE_RE.sub("", location_text).strip().rstrip("()")
            if not venue_name or venue_name.lower() in ("uk location", "n/a"):
                venue_name = self._extract_org_name(name) or name

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

            discipline = discipline_text if discipline_text else None
            has_pony = detect_pony_classes(name)

            competitions.append(self._build_event(
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

    def _build_postback_form(self, html, target_page):
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

    def _get_hidden_value(self, html, field_name):
        match = re.search(
            rf'name="[^"]*{re.escape(field_name)}"[^>]*value="([^"]*)"', html
        )
        return match.group(1) if match else None

    @staticmethod
    def _extract_org_name(name):
        m = _ORG_SUFFIXES_RE.search(name)
        if m:
            return name[:m.end()].strip()
        if " - " in name:
            return name.split(" - ", 1)[0].strip() or None
        return None

    def _parse_mrl_date(self, text):
        try:
            return datetime.strptime(text.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None

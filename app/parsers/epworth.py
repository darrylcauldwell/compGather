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

VENUE_NAME = "Epworth Equestrian Centre"
VENUE_POSTCODE = "DN9 1LQ"
BASE_URL = "https://www.epworthequestrianltd.com"

# Date pattern: "Sunday 22nd February 2026"
DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})",
    re.IGNORECASE,
)

# Category pages and their associated disciplines
CATEGORY_PAGES = {
    "/whats-on/competitions.html": None,  # mixed — infer from name
    "/competitions/dressage/whats-on.html": "Dressage",
    "/competitions/show-jumping/whats-on.html": "Show Jumping",
    "/competitions/eventing/whats-on.html": "Eventing",
    "/competitions/one-day-event/whats-on.html": "Eventing",
    "/competitions/hunter-trial/whats-on.html": "Hunter Trial",
    "/competitions/arena-eventing/whats-on.html": "Cross Country",
    "/competitions/combined-training/whats-on.html": "Combined Training",
    "/competitions/show-cross/whats-on.html": "Cross Country",
    "/competitions/nsea/whats-on.html": "NSEA",
    "/competitions/trailblazers/whats-on.html": "Show Jumping",
    "/clinics/whats-on.html": "Clinic",
    "/camps/whats-on.html": "Camp",
}


@register_parser("epworth")
class EpworthParser(BaseParser):
    """Parser for epworthequestrianltd.com — Joomla with JEvents calendar.

    Scrapes multiple category pages for comprehensive coverage.
    Events are accordion-style with h4 (date), h5 (title), and hidden detail divs.
    Fixed venue: Epworth Equestrian Centre, DN9 1LQ.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        seen: set[tuple[str, str]] = set()  # (name, date_start) for dedup
        competitions: list[ExtractedCompetition] = []

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Scrape all category pages
            for page_path, discipline in CATEGORY_PAGES.items():
                page_url = f"{BASE_URL}{page_path}"
                try:
                    resp = await client.get(page_url)
                    resp.raise_for_status()
                    page_comps = self._parse_page(resp.text, page_url, discipline)
                    for comp in page_comps:
                        key = (comp.name, comp.date_start)
                        if key not in seen:
                            seen.add(key)
                            competitions.append(comp)
                except Exception as e:
                    logger.debug("Epworth: failed to scrape %s: %s", page_path, e)

            # Also try the originally provided URL if not already covered
            if url and not any(url.endswith(p) for p in CATEGORY_PAGES):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    page_comps = self._parse_page(resp.text, url, None)
                    for comp in page_comps:
                        key = (comp.name, comp.date_start)
                        if key not in seen:
                            seen.add(key)
                            competitions.append(comp)
                except Exception as e:
                    logger.debug("Epworth: failed to scrape source URL %s: %s", url, e)

        logger.info("Epworth: extracted %d competitions from %d category pages",
                     len(competitions), len(CATEGORY_PAGES))
        return competitions

    def _parse_page(self, html: str, page_url: str, page_discipline: str | None) -> list[ExtractedCompetition]:
        """Parse a single category page for events."""
        soup = BeautifulSoup(html, "html.parser")
        jevents = soup.find(id="jevents_body")
        if not jevents:
            return []

        competitions = []
        current_date = None

        # Walk through elements sequentially: h4=date, h5=title, div=details
        for element in jevents.children:
            if not hasattr(element, "name") or element.name is None:
                continue

            if element.name == "h4":
                text = element.get_text(strip=True)
                match = DATE_RE.search(text)
                if match:
                    try:
                        current_date = datetime.strptime(
                            f"{match.group(1)} {match.group(2)} {match.group(3)}",
                            "%d %B %Y"
                        ).strftime("%Y-%m-%d")
                    except ValueError:
                        current_date = None

            elif element.name == "h5" and current_date:
                current_title = element.get_text(strip=True)

                # Skip past events
                if not is_future_event(current_date):
                    continue

                # Parse the detail div that follows (slidetext{N})
                detail_div = None
                for sibling in element.next_siblings:
                    if hasattr(sibling, "name"):
                        if sibling.name == "div" and sibling.get("id", "").startswith("slidetext"):
                            detail_div = sibling
                            break
                        if sibling.name in ("h4", "h5"):
                            break

                classes = []
                if detail_div:
                    classes = self._parse_detail(detail_div)

                has_pony = detect_pony_classes(f"{current_title} {' '.join(classes)}")
                discipline = page_discipline or infer_discipline(current_title)

                competitions.append(ExtractedCompetition(
                    name=current_title,
                    date_start=current_date,
                    venue_name=VENUE_NAME,
                    venue_postcode=VENUE_POSTCODE,
                    discipline=discipline,
                    has_pony_classes=has_pony,
                    classes=classes,
                    url=page_url,
                ))

        return competitions

    def _parse_detail(self, div) -> list[str]:
        """Extract classes from a slidetext detail div."""
        classes = []
        for p in div.find_all("p"):
            text = p.get_text(strip=True)
            if re.match(r"Class\s+\d", text, re.IGNORECASE):
                classes.append(text)
        return classes

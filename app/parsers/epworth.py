from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import SingleVenueParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{4})",
    re.IGNORECASE,
)

CATEGORY_PAGES = {
    "/whats-on/competitions.html": None,
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
class EpworthParser(SingleVenueParser):
    """Parser for epworthequestrianltd.com — Joomla with JEvents calendar.

    Scrapes multiple category pages for comprehensive coverage.
    Single venue: Epworth Equestrian Centre (DN9 1LQ).
    """

    VENUE_NAME = "Epworth Equestrian Centre"
    VENUE_POSTCODE = "DN9 1LQ"
    BASE_URL = "https://www.epworthequestrianltd.com"

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        competitions: list[ExtractedEvent] = []

        async with self._make_client() as client:
            for page_path, discipline in CATEGORY_PAGES.items():
                page_url = f"{self.BASE_URL}{page_path}"
                try:
                    text = await self._fetch_text(client, page_url)
                    competitions.extend(self._parse_page(text, page_url, discipline))
                except Exception as e:
                    logger.debug("Epworth: failed to scrape %s: %s", page_path, e)

            if url and not any(url.endswith(p) for p in CATEGORY_PAGES):
                try:
                    text = await self._fetch_text(client, url)
                    competitions.extend(self._parse_page(text, url, None))
                except Exception as e:
                    logger.debug("Epworth: failed to scrape source URL %s: %s", url, e)

        competitions = self._dedup(competitions)
        self._log_result("Epworth", len(competitions))
        return competitions

    def _parse_page(self, html_text, page_url, page_discipline):
        soup = BeautifulSoup(html_text, "html.parser")
        jevents = soup.find(id="jevents_body")
        if not jevents:
            return []

        results = []
        current_date = None

        for element in jevents.find_all(["h4", "h5"]):
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
                title = element.get_text(strip=True)
                discipline = page_discipline or infer_discipline(title)

                results.append(self._build_event(
                    name=title,
                    date_start=current_date,
                    discipline=discipline,
                    has_pony_classes=detect_pony_classes(title),
                    url=page_url,
                ))

        return results

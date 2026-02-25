from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import PlaywrightParser
from app.parsers.registry import register_parser
from app.parsers.utils import detect_pony_classes, infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

VENUE_NAME = "Newbold Verdon Equestrian Centre"
VENUE_POSTCODE = "LE9 9NE"
EQUUS_HUB_URL = "https://nvec.equusorganiser.com/"

DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"(\d{4})",
    re.IGNORECASE,
)


@register_parser("nvec")
class NVECParser(PlaywrightParser):
    """Parser for Newbold Verdon Equestrian Centre (Equus Organiser SPA).

    Uses Playwright to load the SPA and intercepts the GetEventPartial
    API response which returns server-rendered HTML event cards.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("NVEC: Playwright not available — cannot parse SPA")
            return []

        event_html: str | None = None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()

                async def capture_events(response):
                    nonlocal event_html
                    if "GetEventPartial" in response.url:
                        try:
                            event_html = await response.text()
                        except Exception:
                            pass

                page.on("response", capture_events)
                await page.goto(EQUUS_HUB_URL, wait_until="networkidle", timeout=30000)
            finally:
                await browser.close()

        if not event_html:
            logger.warning("NVEC: no event data received from SPA")
            return []

        competitions = self._parse_event_html(event_html)
        self._log_result("NVEC", len(competitions))
        return competitions

    def _parse_event_html(self, html: str) -> list[ExtractedEvent]:
        soup = BeautifulSoup(html, "html.parser")
        competitions: list[ExtractedEvent] = []
        seen: set[tuple[str, str]] = set()

        for box in soup.find_all("div", class_="box"):
            name_el = box.find(class_="eventName")
            date_el = box.find(class_="eventDate")
            if not name_el or not date_el:
                continue

            title = name_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            date_match = DATE_RE.search(date_el.get_text(strip=True))
            if not date_match:
                continue

            try:
                date_start = datetime.strptime(
                    f"{date_match.group(1)} {date_match.group(2)[:3]} {date_match.group(3)}",
                    "%d %b %Y",
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue

            key = (title, date_start)
            if key in seen:
                continue
            seen.add(key)

            type_el = box.find(class_="eventType")
            type_text = type_el.get_text(strip=True) if type_el else ""
            discipline = infer_discipline(title) or infer_discipline(type_text)

            competitions.append(self._build_event(
                name=title,
                date_start=date_start,
                venue_name=VENUE_NAME,
                venue_postcode=VENUE_POSTCODE,
                discipline=discipline,
                has_pony_classes=detect_pony_classes(title),
                url=EQUUS_HUB_URL,
            ))

        return competitions

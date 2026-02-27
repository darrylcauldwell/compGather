"""Parser for itsplainsailing.com Pony Club branch calendars.

Uses Playwright to render the JavaScript SPA and extract event data.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import PlaywrightParser
from app.parsers.registry import register_parser
from app.parsers.utils import extract_postcode, normalise_venue_name
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

# Validated active Pony Club branches on itsplainsailing.com (19 clubs)
ITS_PLAIN_SAILING_CLUBS = [
    "brayhunt", "kildarehunt", "islandhunt", "killinick", "wexfordhunt",
    "avondhu", "imokilly", "cavan", "louthhunt", "tynagh",
    "clare", "ormond", "northdown", "eastantrim", "eastdown",
    "seskinore", "tpc", "iveaghpc", "killultagh",
]


@register_parser("its_plain_sailing")
class ItsPlainSailingParser(PlaywrightParser):
    """Parser for itsplainsailing.com Pony Club branch calendars.

    Each Pony Club branch has its own calendar at:
    https://itsplainsailing.com/org/{branch-slug}
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("ItsPlainSailing: Playwright not available — cannot parse SPA")
            return []

        seen: set[tuple[str, str, str]] = set()
        competitions: list[ExtractedEvent] = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)

                batch_size = 5
                for i in range(0, len(ITS_PLAIN_SAILING_CLUBS), batch_size):
                    batch = ITS_PLAIN_SAILING_CLUBS[i:i + batch_size]
                    tasks = [
                        self._scrape_club_calendar(browser, slug)
                        for slug in batch
                    ]
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                    for club_slug, result in zip(batch, batch_results):
                        if isinstance(result, Exception):
                            logger.debug("ItsPlainSailing: failed to scrape club %s: %s", club_slug, result)
                            continue
                        for comp in result:
                            key = (comp.name, comp.date_start, comp.venue_name)
                            if key not in seen:
                                seen.add(key)
                                competitions.append(comp)
                        logger.info("ItsPlainSailing: %d events from %s", len(result), club_slug)

                    await asyncio.sleep(0.5)

                await browser.close()

        except Exception as e:
            logger.error("ItsPlainSailing: browser error: %s", e)

        self._log_result("ItsPlainSailing", len(competitions))
        return competitions

    async def _scrape_club_calendar(self, browser, club_slug):
        url = f"https://itsplainsailing.com/org/{club_slug}"
        page = None

        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                await page.wait_for_selector("div.event, div[data-event-id], div.event-row", timeout=3000)
            except Exception:
                logger.debug("ItsPlainSailing: no event elements found on %s (timeout)", club_slug)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            competitions: list[ExtractedEvent] = []

            event_selectors = [
                "div[class*='event-item']",
                "div[class*='card']",
                "div[class*='event-card']",
                "article",
                "div.wow",
            ]

            event_elements = []
            for selector in event_selectors:
                found = soup.select(selector)
                valid = [
                    elem for elem in found
                    if any(ind in elem.get_text().lower() for ind in ["2026", "entries", "competition", "event", "rally", "camp"])
                ]
                if valid:
                    event_elements = valid
                    break

            if not event_elements:
                return []

            for elem in event_elements:
                try:
                    comp = self._parse_event_element(elem, club_slug)
                    if comp:
                        competitions.append(comp)
                except Exception as e:
                    logger.debug("ItsPlainSailing: failed to parse event on %s: %s", club_slug, e)

            return competitions

        except Exception as e:
            logger.debug("ItsPlainSailing: failed to scrape %s: %s", url, e)
            return []
        finally:
            if page:
                await page.close()

    _VENUE_AT_RE = re.compile(
        r"(?:held\s+)?at\s+([A-Z][A-Za-z'\u2019]+(?: [A-Za-z'\u2019]+){0,5})",
    )

    def _parse_event_element(self, elem, club_slug):
        card_text = elem.get_text(separator="\n", strip=True)

        name = None
        for selector in ["h3", "h4", "h5", "[class*='title']", "strong"]:
            title_elem = elem.select_one(selector)
            if title_elem:
                name = title_elem.get_text(strip=True)
                if name and len(name) > 2:
                    break

        if not name:
            lines = [line.strip() for line in card_text.split("\n") if line.strip()]
            for line in lines:
                if len(line) > 5 and line.lower() not in ("entries closed", "entries closing", "entries", "event"):
                    name = line
                    break

        if not name or len(name) < 3:
            return None

        date_start = None
        date_patterns = [
            r"(\d{1,2})\s*([A-Za-z]{3})\s*(\d{4})",
            r"([A-Za-z]{3})\s*(\d{1,2})\s*(\d{4})",
        ]

        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }

        for pattern in date_patterns:
            match = re.search(pattern, card_text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if groups[0].isdigit():
                    day, month_str, year = groups
                else:
                    month_str, day, year = groups

                month_num = month_map.get(month_str.lower()[:3])
                if month_num:
                    try:
                        dt = datetime(int(year), month_num, int(day))
                        date_start = dt.strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        pass

        if not date_start:
            return None

        venue_name = "TBC"
        venue_postcode = extract_postcode(card_text) if card_text else None

        # Extract venue from "at <VenueName>" — require capital letter after "at"
        # to avoid matching times ("at 7pm"), emails ("at x@y"), descriptions ("at our...")
        venue_match = self._VENUE_AT_RE.search(card_text)
        if venue_match:
            raw_venue = venue_match.group(1)
            # Truncate at sentence boundaries (period, dash, newline)
            raw_venue = re.split(r'[.\n]|\s-\s', raw_venue)[0].strip()
            # Reject if it looks like a time, email, or is too long
            if (
                raw_venue
                and not re.match(r'\d', raw_venue)
                and '@' not in raw_venue
                and len(raw_venue) <= 60
            ):
                venue_name = normalise_venue_name(raw_venue)

        final_name = f"{name} ({club_slug})" if club_slug else name

        return self._build_event(
            name=final_name,
            date_start=date_start,
            venue_name=venue_name,
            venue_postcode=venue_postcode,
            url=f"https://itsplainsailing.com/org/{club_slug}",
            description=card_text[:200] if card_text else None,
        )

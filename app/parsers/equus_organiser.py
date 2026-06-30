"""Equus Organiser platform parser.

Many UK grassroots venues run their entries on Equus Organiser, served at
``{subdomain}.equusorganiser.com``. The events page is a SPA that loads its
listing via a ``GetEventPartial`` XHR returning server-rendered HTML cards, so
we render with Playwright, intercept that response, and parse the ``.box`` cards.

The platform logic lives in :class:`EquusOrganiserParser`; each single-venue
tenant is a data-driven subclass registered from ``EQUUS_VENUES`` (harvested and
postcode-verified). Newbold Verdon (``nvec``) extends this base directly.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import PlaywrightParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

# Equus event-date format, e.g. "Monday 5th July 2026".
_DATE_RE = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"(\d{4})",
    re.IGNORECASE,
)


class EquusOrganiserParser(PlaywrightParser):
    """Base for single-venue tenants on the Equus Organiser SPA.

    Subclasses set ``SUBDOMAIN``, ``VENUE_NAME``, ``VENUE_POSTCODE`` and
    optionally ``LAT``/``LNG``.
    """

    SUBDOMAIN: str = ""
    VENUE_NAME: str = ""
    VENUE_POSTCODE: str | None = None
    LAT: float | None = None
    LNG: float | None = None

    @property
    def hub_url(self) -> str:
        return f"https://{self.SUBDOMAIN}.equusorganiser.com/"

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("%s: Playwright not available — cannot parse SPA", self.VENUE_NAME)
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
                # domcontentloaded (not networkidle — some tenants poll forever);
                # the GetEventPartial XHR fires after load, so poll for the
                # handler to capture it (up to ~10s).
                await page.goto(self.hub_url, wait_until="domcontentloaded", timeout=30000)
                for _ in range(20):
                    if event_html:
                        break
                    await page.wait_for_timeout(500)
            finally:
                await browser.close()

        if not event_html:
            logger.warning("%s: no event data received from Equus SPA", self.VENUE_NAME)
            return []

        events = self._parse_event_html(event_html)
        self._log_result(self.VENUE_NAME, len(events))
        return events

    def _parse_event_html(self, html: str) -> list[ExtractedEvent]:
        soup = BeautifulSoup(html, "html.parser")
        events: list[ExtractedEvent] = []
        seen: set[tuple[str, str]] = set()

        for box in soup.find_all("div", class_="box"):
            name_el = box.find(class_="eventName")
            date_el = box.find(class_="eventDate")
            if not name_el or not date_el:
                continue
            title = name_el.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            m = _DATE_RE.search(date_el.get_text(strip=True))
            if not m:
                continue
            try:
                date_start = datetime.strptime(
                    f"{m.group(1)} {m.group(2)[:3]} {m.group(3)}", "%d %b %Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue

            key = (title, date_start)
            if key in seen:
                continue
            seen.add(key)

            type_el = box.find(class_="eventType")
            events.append(
                self._build_event(
                    name=title,
                    date_start=date_start,
                    venue_name=self.VENUE_NAME,
                    venue_postcode=self.VENUE_POSTCODE,
                    latitude=self.LAT,
                    longitude=self.LNG,
                    discipline=type_el.get_text(strip=True) if type_el else None,
                    url=self.hub_url,
                )
            )

        return events


# Single-venue Equus Organiser tenants (harvested + UK-postcode verified). Roving
# organisers and niche/non-ridden tenants are intentionally excluded.
EQUUS_VENUES: list[dict] = [
    {"key": "equus_blidworth", "subdomain": "blidworth", "venue_name": "Blidworth Equestrian Show Centre", "postcode": "NG15 9AL", "lat": 53.075, "lng": -1.135},
    {"key": "equus_breconbedsequestrian", "subdomain": "breconbedsequestrian", "venue_name": "Breconbeds Equestrian", "postcode": "DG11 3NA", "lat": 55.048, "lng": -3.208},
    {"key": "equus_byleyec", "subdomain": "byleyec", "venue_name": "Byley International Show Centre", "postcode": "CW10 9LN", "lat": 53.213, "lng": -2.418},
    {"key": "equus_castlefarmliveryxc", "subdomain": "castlefarmliveryxc", "venue_name": "Castle Farm Livery & Cross Country Equestrian", "postcode": "GL12 8NS", "lat": 51.591, "lng": -2.401},
    {"key": "equus_cockermouth", "subdomain": "cockermouth", "venue_name": "Cockermouth & District Agricultural Show", "postcode": "CA13 0HH", "lat": None, "lng": None},
    {"key": "equus_codhampark", "subdomain": "codhampark", "venue_name": "Codham Park Equestrian", "postcode": "CM7 5JQ", "lat": None, "lng": None},
    {"key": "equus_duftonshow", "subdomain": "duftonshow", "venue_name": "Dufton Agricultural Society", "postcode": "CA16 6DA", "lat": None, "lng": None},
    {"key": "equus_fenlandec", "subdomain": "fenlandec", "venue_name": "Fenland Equestrian Centre", "postcode": "PE14 0RN", "lat": None, "lng": None},
    {"key": "equus_foxtonequestrian", "subdomain": "foxtonequestrian", "venue_name": "Foxton Equestrian", "postcode": "LE16 7RY", "lat": None, "lng": None},
    {"key": "equus_greenhilleventing", "subdomain": "greenhilleventing", "venue_name": "Greenhill Eventing", "postcode": "B93 0AU", "lat": None, "lng": None},
    {"key": "equus_greenlands", "subdomain": "greenlands", "venue_name": "Greenlands' Arenas", "postcode": "CA4 0RR", "lat": None, "lng": None},
    {"key": "equus_hackthornhuntertrials", "subdomain": "hackthornhuntertrials", "venue_name": "Hackthorn Hunter Trials", "postcode": "LN2 3PP", "lat": None, "lng": None},
    {"key": "equus_hirdandpartners", "subdomain": "hirdandpartners", "venue_name": "Hird and Partners @ Speetley", "postcode": "S43 4TA", "lat": None, "lng": None},
    {"key": "equus_horseworld", "subdomain": "horseworld", "venue_name": "Horse World", "postcode": "LN8 3TE", "lat": None, "lng": None},
    {"key": "equus_leicestershirecountyshow", "subdomain": "leicestershirecountyshow", "venue_name": "Leicestershire County Show", "postcode": "LE16 7QB", "lat": None, "lng": None},
    {"key": "equus_loweswater", "subdomain": "loweswater", "venue_name": "Loweswater & Brackenthwaite Agricultural Show", "postcode": "CA13 9UU", "lat": None, "lng": None},
    {"key": "equus_mhl", "subdomain": "mhl", "venue_name": "MHL Equestrian Centre", "postcode": "CA4 8DH", "lat": None, "lng": None},
    {"key": "equus_milton", "subdomain": "milton", "venue_name": "Milton Equestrian", "postcode": "S81 0TP", "lat": None, "lng": None},
    {"key": "equus_nethertonequestrian", "subdomain": "nethertonequestrian", "venue_name": "Netherton Equestrian Centre", "postcode": "PH2 9NE", "lat": None, "lng": None},
    {"key": "equus_strathmorerc", "subdomain": "strathmorerc", "venue_name": "Strathmore & District Riding Club", "postcode": "DD8 3TJ", "lat": None, "lng": None},
    {"key": "equus_thorpemeadows", "subdomain": "thorpemeadows", "venue_name": "Thorpe Meadows Ltd", "postcode": "DN17 4BF", "lat": None, "lng": None},
    {"key": "equus_wexc", "subdomain": "wexc", "venue_name": "Winters Equestrian Cross Country", "postcode": "LN7 6JD", "lat": None, "lng": None},
    {"key": "equus_whitehousefarm", "subdomain": "whitehousefarm", "venue_name": "White House Farm Equestrian", "postcode": "LN6 9DP", "lat": None, "lng": None},
    {"key": "equus_willowbanks", "subdomain": "willowbanks", "venue_name": "Willow Banks Equestrian Centre", "postcode": "LN8 3YR", "lat": None, "lng": None},
]


def _register_equus_venues() -> None:
    """Register one EquusOrganiserParser subclass per tenant in EQUUS_VENUES."""
    for c in EQUUS_VENUES:
        cls = type(
            f"Equus_{c['key']}",
            (EquusOrganiserParser,),
            {
                "SUBDOMAIN": c["subdomain"],
                "VENUE_NAME": c["venue_name"],
                "VENUE_POSTCODE": c.get("postcode"),
                "LAT": c.get("lat"),
                "LNG": c.get("lng"),
                "__doc__": f"Equus Organiser parser for {c['venue_name']}.",
            },
        )
        register_parser(c["key"])(cls)


_register_equus_venues()

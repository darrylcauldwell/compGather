"""Parser for British Horseball Association (BHA) events.

Downloads and parses the BHA calendar PDF from the Sportity CDN.
The PDF URL is discovered by rendering the Wix-based events page
with Playwright, then the PDF is downloaded and parsed with pdfplumber.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

BHA_EVENTS_URL = "https://www.britishhorseball.co.uk/bha-events"

# Match ordinal date ranges: "21st-22nd", "2nd – 3rd", "16th"
_DAY_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:[-–]\s*(\d{1,2})(?:st|nd|rd|th)?)?"
)

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


@register_parser("british_horseball")
class BritishHorseballParser(HttpParser):
    """Parser for British Horseball Association events.

    Discovers the calendar PDF URL from the BHA events page (Wix SPA,
    requires Playwright), downloads the PDF, and parses the event table
    using pdfplumber.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        pdf_url = await self._discover_pdf_url()
        if not pdf_url:
            logger.warning("British Horseball: no PDF URL found on events page")
            return []

        async with self._make_client() as client:
            try:
                resp = await client.get(pdf_url, follow_redirects=True, timeout=30.0)
                resp.raise_for_status()
            except Exception as e:
                logger.warning("British Horseball: failed to download PDF: %s", e)
                return []

        competitions = self._parse_pdf(resp.content)
        self._log_result("British Horseball", len(competitions))
        return competitions

    async def _discover_pdf_url(self) -> str | None:
        """Render the BHA events page with Playwright and find the PDF link."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("British Horseball: Playwright not available")
            return None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(
                    BHA_EVENTS_URL, wait_until="domcontentloaded", timeout=60000
                )
                await page.wait_for_timeout(3000)

                # Look for PDF links in the rendered page
                for link in await page.query_selector_all("a[href*='.pdf']"):
                    href = await link.get_attribute("href")
                    if href and ".pdf" in href.lower():
                        logger.info("British Horseball: found PDF URL: %s", href)
                        return href

                # Fallback: look for Sportity CDN links
                for link in await page.query_selector_all("a[href*='sportity']"):
                    href = await link.get_attribute("href")
                    if href:
                        logger.info("British Horseball: found Sportity URL: %s", href)
                        return href

                logger.warning("British Horseball: no PDF link found on events page")
                return None
            except Exception as exc:
                logger.warning("British Horseball: Playwright failed: %s", exc)
                return None
            finally:
                await browser.close()

    def _parse_pdf(self, pdf_bytes: bytes) -> list[ExtractedEvent]:
        """Parse the BHA calendar PDF and extract events."""
        try:
            import pdfplumber
        except ImportError:
            logger.warning("British Horseball: pdfplumber not available")
            return []

        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception as e:
            logger.warning("British Horseball: failed to open PDF: %s", e)
            return []

        # Determine year from PDF title text
        year = datetime.now().year
        for page in pdf.pages:
            text = page.extract_text() or ""
            m = re.search(r"(20\d{2})\s+BHA\s+Calendar", text)
            if m:
                year = int(m.group(1))
                break

        competitions: list[ExtractedEvent] = []
        seen: set[tuple[str, str]] = set()

        for page in pdf.pages:
            for table in page.extract_tables():
                for comp in self._parse_table(table, year):
                    key = (comp.name, comp.date_start)
                    if key not in seen:
                        seen.add(key)
                        competitions.append(comp)

        return competitions

    def _parse_table(self, rows: list[list], year: int) -> list[ExtractedEvent]:
        """Parse a PDF table into events.

        Table structure:
          [Month, Day, Event, Venue, Details]
        Events span multiple rows — continuation rows have empty day column.
        Separator rows have None in the day column.
        """
        if not rows or len(rows) < 2:
            return []

        data_rows = rows[1:] if rows[0] and rows[0][0] == "Date" else rows

        events: list[ExtractedEvent] = []
        current_month = None
        current_event: dict | None = None

        for row in data_rows:
            if not row or len(row) < 5:
                continue

            month_col = (row[0] or "").strip()
            day_col = (row[1] or "").strip() if row[1] is not None else None
            event_col = (row[2] or "").strip()
            venue_col = (row[3] or "").strip()
            detail_col = (row[4] or "").strip() if row[4] else ""

            if month_col and month_col in MONTHS:
                current_month = month_col

            # New event: day column has an ordinal day value
            if day_col and _DAY_RE.match(day_col):
                if current_event:
                    comp = self._build_from_parts(current_event, year)
                    if comp:
                        events.append(comp)

                current_event = {
                    "day": day_col,
                    "month": current_month,
                    "event_parts": [event_col] if event_col else [],
                    "venue_parts": [venue_col] if venue_col else [],
                    "detail_parts": [detail_col] if detail_col else [],
                }

            # Continuation row: day is empty string
            elif day_col == "" and current_event:
                if event_col:
                    current_event["event_parts"].append(event_col)
                if venue_col:
                    current_event["venue_parts"].append(venue_col)
                if detail_col:
                    current_event["detail_parts"].append(detail_col)

        # Flush last event
        if current_event:
            comp = self._build_from_parts(current_event, year)
            if comp:
                events.append(comp)

        return events

    def _build_from_parts(self, parts: dict, year: int) -> ExtractedEvent | None:
        """Build an ExtractedEvent from accumulated table row parts."""
        month_name = parts.get("month")
        day_text = parts.get("day", "")

        if not month_name or month_name not in MONTHS:
            return None

        month_num = MONTHS[month_name]

        m = _DAY_RE.match(day_text)
        if not m:
            return None

        day_start = int(m.group(1))
        day_end = int(m.group(2)) if m.group(2) else None

        try:
            date_start = datetime(year, month_num, day_start).strftime("%Y-%m-%d")
            date_end = (
                datetime(year, month_num, day_end).strftime("%Y-%m-%d")
                if day_end
                else None
            )
        except ValueError:
            return None

        name = " ".join(parts["event_parts"]).strip()
        venue = " ".join(parts["venue_parts"]).strip()

        if not name:
            return None

        # Skip non-UK events (FIHB events in France, etc.)
        venue_lower = venue.lower()
        if any(
            c in venue_lower
            for c in ["france", "spain", "germany", "italy", "portugal"]
        ):
            return None

        return self._build_event(
            name=name,
            date_start=date_start,
            date_end=date_end if date_end and date_end != date_start else None,
            venue_name=venue if venue else "BHA Venue",
            discipline="Horseball",
            url=BHA_EVENTS_URL,
        )

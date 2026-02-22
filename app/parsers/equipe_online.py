from __future__ import annotations

import logging
import re

import httpx

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.parsers.utils import infer_discipline, is_future_event
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

MEETINGS_API = "https://online.equipe.com/api/v1/meetings"
SCHEDULE_API = "https://online.equipe.com/api/v1/meetings/{id}/schedule"
SHOW_URL = "https://online.equipe.com/shows/{id}"


@register_parser("equipe_online")
class EquipeOnlineParser(BaseParser):
    """Parser for online.equipe.com — JSON API for all GBR competition listings.

    Fetches all disciplines (show jumping, dressage, eventing, etc.) for GBR venues.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Fetch all meetings from the API
            meetings = await self._fetch_meetings(client)
            logger.info("Equipe Online: %d total meetings from API", len(meetings))

            # Filter to GBR, future events (all disciplines)
            relevant = [
                m for m in meetings
                if self._is_relevant(m)
            ]
            logger.info("Equipe Online: %d relevant GBR meetings", len(relevant))

            # Optionally enrich with schedule data for class details
            competitions = []
            for meeting in relevant:
                try:
                    comp = await self._build_competition(client, meeting)
                    if comp:
                        competitions.append(comp)
                except Exception as e:
                    logger.debug("Equipe: failed to build comp for meeting %s: %s", meeting.get("id"), e)

        logger.info("Equipe Online: extracted %d competitions", len(competitions))
        return competitions

    async def _fetch_meetings(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch all meetings from the Equipe API."""
        try:
            resp = await client.get(MEETINGS_API)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error("Equipe Online: API request failed: %s", e)
            return []

    def _is_relevant(self, meeting: dict) -> bool:
        """Filter for GBR events that haven't passed (all disciplines)."""
        # Must be in GBR
        if meeting.get("venue_country", "") != "GBR":
            return False

        # Must not have ended
        end_date = meeting.get("end_on") or meeting.get("start_on", "")
        return is_future_event(meeting.get("start_on", ""), end_date)

    async def _build_competition(self, client: httpx.AsyncClient, meeting: dict) -> ExtractedCompetition | None:
        """Build competition from meeting data, optionally enriched with schedule."""
        meeting_id = meeting.get("id")
        name = meeting.get("display_name") or meeting.get("name", "")
        start_date = meeting.get("start_on", "")
        end_date = meeting.get("end_on", "")

        if not name or not start_date:
            return None

        # Detect pony classes from the meeting metadata
        horse_ponies = meeting.get("horse_ponies", [])
        has_pony = "pony" in horse_ponies

        # Determine discipline from API metadata
        discipline_raw = meeting.get("discipline", "")
        discipline = {
            "show_jumping": "Show Jumping",
            "dressage": "Dressage",
            "eventing": "Eventing",
            "driving": "Driving",
            "endurance": "Endurance",
        }.get(discipline_raw) or infer_discipline(name)

        # Try to get classes from schedule API
        classes = []
        venue_name = self._extract_venue_name(name)
        if not venue_name:
            logger.debug("Equipe: skipping event with no identifiable venue: %s", name)
            return None

        try:
            schedule = await self._fetch_schedule(client, meeting_id)
            if schedule:
                # Extract class names
                for mc in schedule.get("meeting_classes", []):
                    class_name = mc.get("name", "")
                    if class_name:
                        classes.append(class_name)
                # Check for pony classes in class names too
                if not has_pony:
                    class_text = " ".join(classes).lower()
                    has_pony = any(kw in class_text for kw in ["pony", "junior"])
        except Exception as e:
            logger.debug("Equipe: schedule fetch failed for %d: %s", meeting_id, e)

        show_url = SHOW_URL.format(id=meeting_id)

        return ExtractedCompetition(
            name=name,
            date_start=start_date,
            date_end=end_date if end_date and end_date != start_date else None,
            venue_name=venue_name,
            venue_postcode=None,  # Not available from Equipe API
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=classes,
            url=show_url,
        )

    async def _fetch_schedule(self, client: httpx.AsyncClient, meeting_id: int) -> dict | None:
        """Fetch the schedule for a meeting to get class details."""
        try:
            resp = await client.get(SCHEDULE_API.format(id=meeting_id))
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    # Keywords that mark the boundary between venue name and event description
    _VENUE_SPLIT_RE = re.compile(
        r"\b(?:British\s+(?:Dressage|Showjumping|Eventing|Riding)|"
        r"BD\s|BS\s|BE\s|"
        r"Dressage|Showjumping|Show\s+Jumping|Eventing|"
        r"Clear\s+Round|Unaffiliated|Arena\s+Eventing|"
        r"Senior\s+(?:British|BS)|Junior\s+(?:British|BS)|"
        r"Small\s+Pony|Large\s+Pony|Para\s+Winter|"
        r"CAT\s+\d|Premier|Training\s+Show|Dress\s+Down|"
        r"Winter\s+(?:League|Regional|Championship)|"
        r"Summer\s+(?:League|Regional|Championship)|"
        r"National|Regional|Championship)"
        r"|\(\s*(?:P[\s-]|Small|Senior|Junior)"  # BD class codes like (P-AM), (Small Pony...)
        r"|\b\d{1,2}(?:st|nd|rd|th)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"|\b(?:Sat|Sun|Mon|Tue|Wed|Thu|Fri)(?:urday|nday|day|sday|nesday|rsday)?\s+\d",
        re.IGNORECASE,
    )

    def _extract_venue_name(self, name: str) -> str:
        """Extract venue name from Equipe event name.

        Equipe's API packs venue + event type + date into one name field, e.g.:
        'Onley Grounds Senior British Showjumping - 26 Feburary 2026'
        → venue = 'Onley Grounds'
        """
        # Strip trailing parenthesised content that isn't part of the venue
        cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", name)

        m = self._VENUE_SPLIT_RE.search(cleaned)
        if m and m.start() > 3:
            venue = cleaned[: m.start()].strip().rstrip("-:").strip()
            # Must be a plausible place name (not just a generic word)
            if venue and len(venue) > 3:
                return venue
        # No recognisable venue prefix — return None to signal unknown
        return None

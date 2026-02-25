from __future__ import annotations

import logging
import re

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.parsers.utils import infer_discipline
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s+\d[A-Z]{2}\b", re.IGNORECASE)

MEETINGS_API = "https://online.equipe.com/api/v1/meetings"
SCHEDULE_API = "https://online.equipe.com/api/v1/meetings/{id}/schedule"
SHOW_URL = "https://online.equipe.com/shows/{id}"


@register_parser("equipe_online")
class EquipeOnlineParser(HttpParser):
    """Parser for online.equipe.com — JSON API for all GBR competition listings."""

    _org_postcode_cache: dict[str, str | None] = {}

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            meetings = await self._fetch_meetings(client)
            logger.info("Equipe Online: %d total meetings from API", len(meetings))

            relevant = [m for m in meetings if self._is_relevant(m)]
            logger.info("Equipe Online: %d relevant GBR meetings", len(relevant))

            competitions = []
            for meeting in relevant:
                try:
                    comp = await self._build_competition(client, meeting)
                    if comp:
                        competitions.append(comp)
                except Exception as e:
                    logger.debug("Equipe: failed to build comp for meeting %s: %s", meeting.get("id"), e)

        self._log_result("Equipe Online", len(competitions))
        return competitions

    async def _fetch_meetings(self, client):
        try:
            return await self._fetch_json(client, MEETINGS_API)
        except Exception as e:
            logger.error("Equipe Online: API request failed: %s", e)
            return []

    def _is_relevant(self, meeting):
        return meeting.get("venue_country", "") == "GBR"

    async def _build_competition(self, client, meeting):
        meeting_id = meeting.get("id")
        name = meeting.get("display_name") or meeting.get("name", "")
        start_date = meeting.get("start_on", "")
        end_date = meeting.get("end_on", "")

        if not name or not start_date:
            return None

        horse_ponies = meeting.get("horse_ponies", [])
        has_pony = "pony" in horse_ponies

        discipline_raw = meeting.get("discipline", "")
        discipline = {
            "show_jumping": "Show Jumping",
            "dressage": "Dressage",
            "eventing": "Eventing",
            "driving": "Driving",
            "endurance": "Endurance",
        }.get(discipline_raw) or infer_discipline(name)

        classes = []
        venue_name = self._extract_venue_name(name)
        organiser_url = None

        try:
            schedule = await self._fetch_schedule(client, meeting_id)
            if schedule:
                for mc in schedule.get("meeting_classes", []):
                    class_name = mc.get("name", "")
                    if class_name:
                        classes.append(class_name)
                if not has_pony:
                    class_text = " ".join(classes).lower()
                    has_pony = any(kw in class_text for kw in ["pony", "junior"])
                organiser_url = schedule.get("organizer_url") or None
        except Exception as e:
            logger.debug("Equipe: schedule fetch failed for %d: %s", meeting_id, e)

        postcode = None
        if organiser_url:
            postcode = await self._fetch_organiser_postcode(client, organiser_url)

        show_url = SHOW_URL.format(id=meeting_id)

        return self._build_event(
            name=name,
            date_start=start_date,
            date_end=end_date if end_date and end_date != start_date else None,
            venue_name=venue_name,
            venue_postcode=postcode,
            discipline=discipline,
            has_pony_classes=has_pony,
            classes=classes,
            url=show_url,
        )

    async def _fetch_organiser_postcode(self, client, base_url):
        if base_url in self._org_postcode_cache:
            return self._org_postcode_cache[base_url]

        for path in ["", "/contact", "/contact-us", "/find-us"]:
            url = base_url.rstrip("/") + path
            try:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    m = _POSTCODE_RE.search(resp.text)
                    if m:
                        postcode = re.sub(r"\s+", " ", m.group(0).strip().upper())
                        self._org_postcode_cache[base_url] = postcode
                        logger.debug("Equipe: found postcode %s for %s", postcode, base_url)
                        return postcode
            except Exception as e:
                logger.debug("Equipe: organiser fetch failed for %s: %s", url, e)

        self._org_postcode_cache[base_url] = None
        return None

    async def _fetch_schedule(self, client, meeting_id):
        try:
            return await self._fetch_json(client, SCHEDULE_API.format(id=meeting_id))
        except Exception:
            return None

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
        r"|\(\s*(?:P[\s-]|Small|Senior|Junior)"
        r"|\b\d{1,2}(?:st|nd|rd|th)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"|\b(?:Sat|Sun|Mon|Tue|Wed|Thu|Fri)(?:urday|nday|day|sday|nesday|rsday)?\s+\d",
        re.IGNORECASE,
    )

    def _extract_venue_name(self, name):
        cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", name)

        for sep in [" - ", " : ", " | "]:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                venue = parts[0].strip()
                if len(venue) > 3:
                    return venue

        m = self._VENUE_SPLIT_RE.search(cleaned)
        if m and m.start() > 3:
            venue = cleaned[:m.start()].strip().rstrip("-:").strip()
            if venue and len(venue) > 3:
                return venue

        logger.debug("Equipe: could not extract venue from '%s', using placeholder", name)
        return "Tbc"

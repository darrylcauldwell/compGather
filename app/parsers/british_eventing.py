from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.parsers.bases import HttpParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedEvent

logger = logging.getLogger(__name__)

BASE_URL = "https://www.britisheventing.com"

CANCELLED_STATUSES = {"X"}

# These keywords indicate the event is a travelling championship (not a
# fixed-venue event).  Only used as a FALLBACK when the cleaned stem is
# not found in _BE_VENUE_MAP.  \b prevents "ace" matching inside "PALACE".
_NON_VENUE_KEYWORDS = re.compile(
    r"\bchampionship|\bgrassroots|\bace\s|\barena\s+eventing\s+champ",
    re.IGNORECASE,
)

SINGLE_DATE_RE = re.compile(r"^(\d{1,2})\s+(\w{3})\s+(\d{2})$")
RANGE_SAME_MONTH_RE = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})\s+(\w{3})\s+(\d{2})$")
RANGE_CROSS_MONTH_RE = re.compile(r"^(\d{1,2})\s+(\w{3})\s*-\s*(\d{1,2})\s+(\w{3})\s+(\d{2})$")

# ---------------------------------------------------------------------------
# Static venue lookup: cleaned event-name stem → (canonical venue, postcode)
#
# BE event names follow patterns like "TWESELDOWN (2)", "BICTON INTERNATIONAL
# (1)", "BURNHAM MARKET INTERNATIONAL SPONSORED BY BAREFOOT RETREATS".  After
# stripping suffixes we get a stem (e.g. "Tweseldown", "Burnham Market") which
# this map resolves to the real venue name and postcode.
# ---------------------------------------------------------------------------
_BE_VENUE_MAP: dict[str, tuple[str, str]] = {
    # --- Already seeded venues (parser provides postcode for safety) ---
    "Allerton Park": ("Allerton Park", "HG5 0SE"),
    "Aston-Le-Walls": ("Aston Le Walls", "NN11 6RT"),
    "Barbury Castle": ("Barbury Castle", "SN8 1RS"),
    "Bicton": ("Bicton", "EX9 7BL"),
    "Bramham": ("Bramham", "LS23 6ND"),
    "Dauntsey Park": ("Dauntsey Park", "SN15 5JA"),
    "Epworth": ("Epworth", "DN9 1LQ"),
    "Hartpury": ("Hartpury", "GL19 3BE"),
    "Kelsall Hill": ("Kelsall Hill Equestrian Centre", "CW6 0SR"),
    "Moreton": ("Moreton", "DT2 8RF"),
    "Moreton Morrell": ("Moreton Morrell", "CV35 9BL"),
    "Northallerton": ("Northallerton", "DL7 0PQ"),
    "Oasby": ("Oasby", "NG32 3NA"),
    "Pontispool": ("Pontispool", "TA4 1BH"),
    "Poplar Park": ("Poplar Park", "IP12 3NA"),
    "Solihull": ("Solihull Riding Club", "B93 8QE"),
    "Tweseldown": ("Tweseldown", "GU52 8AD"),
    # --- Venues needing name mapping (county/ambiguous stems) ---
    "Lincolnshire": ("Lincolnshire Showground", "LN2 2NA"),
    "Little Gatcombe": ("Little Gatcombe", "GL6 9AT"),
    "Burghley Horse Trials": ("Burghley", "PE9 3JY"),
    "Burghley": ("Burghley", "PE9 3JY"),
    "South Of England": ("South Of England Showground", "RH17 6TL"),
    "Mendip Plains Ston Easton": ("Ston Easton Park", "BA3 4BX"),
    "Scottish Grassroots Eventing Festival Scone Palace": ("Scone Palace", "PH2 6BD"),
    # --- Remaining venues (most already seeded; output matches seed keys/aliases) ---
    "Alnwick Ford": ("Alnwick Ford", "NE65 8EQ"),
    "Ascott Under Wychwood": ("Ascott Under Wychwood", "OX7 6AN"),
    "Askham Bryan College": ("Askham Bryan College", "YO23 3FR"),
    "Badminton": ("Badminton", "GL9 1DD"),
    "Belsay": ("Belsay", "NE20 0DX"),
    "Berkshire College Of Agriculture": ("Berkshire College Of Agriculture", "SL6 6QR"),
    "Bishop Burton": ("Bishop Burton", "HU17 8QG"),
    "Blenheim Palace": ("Blenheim Palace", "OX20 1UL"),
    "Blindley Heath": ("Blindley Heath", "RH7 6JL"),
    "Bovington": ("Bovington", "BH20 6JG"),
    "Bradwall Manor": ("Bradwall Manor", "CW11 1RF"),
    "Breckenbrough": ("Breckenbrough", "YO7 4EL"),
    "Brechin Castle": ("Brechin Castle", "DD9 6SG"),
    "Burgham": ("Burgham", "NE65 9QP"),
    "Burnham Market": ("Burnham Market International", "PE31 8JY"),
    "Chard": ("Chard", "TA20 4BP"),
    "Chepstow At Howick": ("Chepstow At Howick", "NP16 6BL"),
    "Chillington Hall": ("Chillington Hall", "WV8 1RE"),
    "Cirencester Park": ("Cirencester Park", "GL7 6JT"),
    "Cornbury House": ("Cornbury House", "OX7 3EH"),
    "Eland Lodge": ("Eland Lodge", "DE6 5HD"),
    "Farley Hall": ("Farley Hall", "RG7 1TJ"),
    "Forgandenny": ("Forgandenny", "PH2 9EG"),
    "Frickley Park": ("Frickley Hall", "DN5 7BU"),
    "Gatcombe": ("Little Gatcombe", "GL6 9AT"),
    "Kingston Maurward College": ("Kingston Maurward College", "DT2 8PY"),
    "Kirriemuir": ("Kirriemuir", "DD8 5BY"),
    "Larkhill": ("Larkhill", "SP4 8QT"),
    "Little Downham": ("Little Downham", "CB6 2TY"),
    "Littleton Manor": ("Littleton Manor", "RH2 8QZ"),
    "Munstead": ("Munstead", "GU7 1XA"),
    "Oatridge": ("Oatridge", "EH52 6NH"),
    "Offchurch Bury": ("Offchurch Bury", "CV33 9AR"),
    "Osberton": ("Osberton", "S81 0UE"),
    "Oxstalls": ("Oxstalls", "GL6 8HZ"),
    "Penrith": ("Penrith", "CA11 8TZ"),
    "Portman": ("Portman", "SP5 5RP"),
    "Scone Palace": ("Scone Palace", "PH2 6BD"),
    "South Of Scotland": ("South Of Scotland", "DG6 4NH"),
    "Swalcliffe Park": ("Swalcliffe Park", "OX15 5EX"),
    "Tetworth": ("Tetworth", "SG19 2HU"),
    "Thoresby Park": ("Thoresby Park", "NG22 9EP"),
    "Upton House": ("Upton House", "OX15 6HT"),
    "Waverton": ("Waverton", "GL56 9TB"),
    "Wellington": ("Wellington", "RG27 0LJ"),
    "West Wilts": ("West Wilts", "BA14 6QT"),
}


@register_parser("british_eventing")
class BritishEventingParser(HttpParser):
    """Parser for britisheventing.com/search-events.

    Server-rendered table with 7 columns:
    Dates | Name | Classes | Location | Entries Open | Ballot Date | Status

    Uses a static venue lookup (_BE_VENUE_MAP) because BE event names are
    often county names or contain heavy sponsor text that generic cleanup
    cannot resolve.  Every known venue maps to a canonical name + postcode.
    """

    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        async with self._make_client() as client:
            html = await self._fetch_text(client, url)

        soup = BeautifulSoup(html, "html.parser")
        competitions = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 7:
                continue

            date_text = tds[0].get_text(strip=True)
            name = tds[1].get_text(strip=True)
            classes_text = tds[2].get_text(strip=True)
            location = tds[3].get_text(strip=True)
            status = tds[6].get_text(strip=True)

            if not name or not date_text:
                continue
            if status in CANCELLED_STATUSES:
                continue

            date_start, date_end = self._parse_be_date(date_text)
            if not date_start:
                continue

            event_url = None
            link = tds[1].find("a", href=True)
            if link:
                href = link["href"]
                event_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            classes = [c.strip() for c in classes_text.split(",") if c.strip()] if classes_text else []
            venue_name, venue_postcode = self._extract_venue(name, location)

            competitions.append(self._build_event(
                name=name,
                date_start=date_start,
                date_end=date_end if date_end and date_end != date_start else None,
                venue_name=venue_name,
                venue_postcode=venue_postcode,
                discipline="Eventing",
                classes=classes,
                url=event_url or url,
            ))

        self._log_result("British Eventing", len(competitions))
        return competitions

    def _extract_venue(self, name: str, location: str) -> tuple[str, str | None]:
        """Extract venue name and postcode from BE event name.

        Order: clean stem → lookup in map → keyword fallback → raw stem.
        Returns (venue_name, postcode) — postcode may be None for unknown venues.
        """
        # 1. Always clean the stem first
        stem = self._clean_stem(name)

        # 2. If the stem is in the venue map, use the mapped venue
        match = _BE_VENUE_MAP.get(stem)
        if match:
            return match

        # 3. Travelling championships — stem won't be in the map, fall to location
        if _NON_VENUE_KEYWORDS.search(name):
            return (location or "TBC", None)

        # 4. Unknown venue — return cleaned stem as best guess
        return (stem, None) if stem else (location or "TBC", None)

    @staticmethod
    def _clean_stem(name: str) -> str:
        """Strip BE-specific suffixes to get the venue name stem."""
        s = name.strip()
        # Strip " - anything" (sponsor text after dash)
        s = re.sub(r"\s+-\s+.*$", "", s)
        # Strip "SPONSORED BY ..." (without dash separator)
        s = re.sub(r"\s+SPONSORED\s+BY\s+.*$", "", s, flags=re.IGNORECASE)
        # Strip "INCORPORATING ..."
        s = re.sub(r"\s+INCORPORATING\s+.*$", "", s, flags=re.IGNORECASE)
        # Strip "& REGIONAL CHAMPIONSHIP" / "& BE80 CHAMPIONSHIPS" / "REGIONAL & BE80 ..."
        s = re.sub(r"\s+(?:&\s+)?REGIONAL\s*&?\s*(?:BE\d+\s+)?CHAMPIONSHIP\S*.*$", "", s, flags=re.IGNORECASE)
        # Strip "& FESTIVAL OF ..."
        s = re.sub(r"\s+&\s+FESTIVAL\s+OF\s+.*$", "", s, flags=re.IGNORECASE)
        # Strip "& YOUNG HORSE ..."
        s = re.sub(r"\s+&\s+YOUNG\s+HORSE\s+.*$", "", s, flags=re.IGNORECASE)
        # Strip "EVENTING SPRING CARNIVAL" / "EVENTING FESTIVAL ..."
        s = re.sub(r"\s+EVENTING\s+(?:SPRING|AUTUMN)\s+\w+.*$", "", s, flags=re.IGNORECASE)
        # Strip "HORSE TRIALS"
        s = re.sub(r"\s+HORSE\s+TRIALS?$", "", s, flags=re.IGNORECASE)
        # Strip trailing year (e.g. " 2026")
        s = re.sub(r"\s+\d{4}$", "", s)
        # Strip trailing instance number e.g. "(1)", "(2)"
        s = re.sub(r"\s*\(\d+\)\s*$", "", s)
        # Strip trailing "INTERNATIONAL"
        s = re.sub(r"\s+INTERNATIONAL$", "", s, flags=re.IGNORECASE)
        return s.strip().title()

    def _parse_be_date(self, text):
        text = text.strip()

        m = RANGE_CROSS_MONTH_RE.match(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(5)}", "%d %b %y")
                end = datetime.strptime(f"{m.group(3)} {m.group(4)} {m.group(5)}", "%d %b %y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        m = RANGE_SAME_MONTH_RE.match(text)
        if m:
            try:
                start = datetime.strptime(f"{m.group(1)} {m.group(3)} {m.group(4)}", "%d %b %y")
                end = datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%d %b %y")
                return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
            except ValueError:
                pass

        m = SINGLE_DATE_RE.match(text)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %y")
                return dt.strftime("%Y-%m-%d"), None
            except ValueError:
                pass

        return None, None

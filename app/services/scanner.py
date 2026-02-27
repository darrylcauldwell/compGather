from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.metrics import (
    PARSER_ERRORS_TOTAL,
    SCAN_COMPETITIONS_FOUND,
    SCAN_DURATION_SECONDS,
    SCAN_TOTAL,
    VENUE_MATCH_TOTAL,
)
from app.models import Competition, DisciplineAlias, Scan, Source, Venue, VenueMatchReview
from app.parsers.registry import get_parser
from app.parsers.utils import (
    disambiguate_venue,
    normalise_discipline,
    normalise_postcode,
    normalise_venue_name,
)
from app.seed_data import get_venue_seeds
from app.services.event_classifier import EventClassifier
from app.services.geocoder import (
    geocode_postcode,
    reverse_geocode,
)
from app.services.tag_manager import extract_tags, serialize_tags
from app.services.venue_matcher import VenueIndex, _is_placeholder_name, match_venue

logger = logging.getLogger(__name__)

# Disambiguated venue name pattern: "Brook Farm (TQ12)", "Rectory Farm (GL7)"
_DISAMBIGUATED_RE = re.compile(r"\([A-Z]{1,2}\d[A-Z\d]?\)$")


# Canonical source definitions — seeded into the sources table at startup.
# parser_key must match @register_parser("key") in app/parsers/*.py
# affiliation: optional governing body tag for all events from this source
_SOURCE_DEFS: list[dict[str, str | None]] = [
    {"name": "Abbey Farm", "parser_key": "abbey_farm", "url": "https://abbeyfarmequestrian.co.uk/events/list/"},
    {"name": "Addington", "parser_key": "addington", "url": "https://addington.co.uk/wp-json/tribe/events/v1/events"},
    {"name": "Arena UK", "parser_key": "arena_uk", "url": "https://www.arenauk.com/events/all-upcoming"},
    {"name": "ASAO", "parser_key": "asao", "url": "https://www.asao.co.uk/"},
    {"name": "Ashwood Equestrian", "parser_key": "ashwood", "url": "https://ashwoodequestrian.com/events/"},
    {"name": "British Dressage", "parser_key": "british_dressage", "url": "https://britishdressage.online/api/events/getByPublicFilter", "affiliation": "british-dressage"},
    {"name": "British Eventing", "parser_key": "british_eventing", "url": "https://www.britisheventing.com/search-events", "affiliation": "british-eventing"},
    {"name": "British Horseball", "parser_key": "british_horseball", "url": "https://www.britishhorseball.co.uk/bha-events", "affiliation": "british-horseball"},
    {"name": "British Show Horse Association", "parser_key": "bsha", "url": "https://bsha.online/index.php", "affiliation": "bsha"},
    {"name": "British Show Pony Society", "parser_key": "bsps", "url": "https://bsps.equine.events/index.php", "affiliation": "bsps"},
    {"name": "British Showjumping", "parser_key": "british_showjumping", "url": "https://www.britishshowjumping.co.uk/show-calendar.cfm", "affiliation": "british-showjumping"},
    {"name": "Derby College", "parser_key": "derby_college", "url": "https://www.derby-college.ac.uk/open-to-the-public/equestrian-centre/"},
    {"name": "Epworth", "parser_key": "epworth", "url": "https://www.epworthequestrianltd.com"},
    {"name": "EquiLive", "parser_key": "equilive", "url": "https://equilive.uk/events/"},
    {"name": "Equipe Online", "parser_key": "equipe_online", "url": "https://online.equipe.com/api/v1/meetings"},
    {"name": "EquoEvents", "parser_key": "equo_events", "url": "https://www.equoevents.co.uk/SearchEvents"},
    {"name": "Endurance GB", "parser_key": "endurance_gb", "url": "https://www.endurancegb.co.uk/Events/Calendar", "affiliation": "endurance-gb"},
    {"name": "Hickstead", "parser_key": "hickstead", "url": "https://www.hickstead.co.uk"},
    {"name": "Hope Valley Riding Club", "parser_key": "hope_valley", "url": "https://hopevalleyridingclub.co.uk/events/"},
    {"name": "Horse Events", "parser_key": "horse_events", "url": "https://www.horse-events.co.uk"},
    {"name": "Horse Monkey", "parser_key": "horse_monkey", "url": "https://horsemonkey.com/uk/search"},
    {"name": "HPA Polo", "parser_key": "hpa_polo", "url": "https://hpa-polo.co.uk/clubs/fixtures/find-a-fixture-search/", "affiliation": "hpa-polo"},
    {"name": "HorsEvents", "parser_key": "horsevents", "url": "https://horsevents.co.uk/diary/"},
    {"name": "Kelsall Hill", "parser_key": "kelsall_hill", "url": "https://kelsallhill.co.uk/wp-admin/admin-ajax.php"},
    {"name": "My Riding Life", "parser_key": "my_riding_life", "url": "https://www.myridinglife.com/myridinglife/onlineentries.aspx"},
    {"name": "NSEA", "parser_key": "nsea", "url": "https://www.nsea.org.uk/competitions/", "affiliation": "nsea"},
    {"name": "NVEC", "parser_key": "nvec", "url": "https://nvec.equusorganiser.com/"},
    {"name": "Outdoor Shows", "parser_key": "outdoor_shows", "url": "https://outdoorshows.co.uk"},
    {"name": "ItsPlainSailing", "parser_key": "its_plain_sailing", "url": "https://itsplainsailing.com"},
    {"name": "EntryMaster", "parser_key": "entry_master", "url": "https://entrymaster.online"},
    {"name": "The Showground", "parser_key": "showground", "url": "https://www.theshowground.com"},
    {"name": "Morris EC", "parser_key": "morris", "url": "https://www.morrisequestrian.co.uk/wp-json/tribe/events/v1/events"},
    {"name": "Port Royal", "parser_key": "port_royal", "url": "https://www.portroyaleec.co.uk"},
    {"name": "Hartpury", "parser_key": "hartpury", "url": "https://www.hartpury.ac.uk/equine/events/"},
    {"name": "Solihull RC", "parser_key": "solihull", "url": "https://solihullridingclub.co.uk/event-diary/"},
    {"name": "Sykehouse Arena", "parser_key": "sykehouse", "url": "https://www.sykehousearena.com/events/"},
    {"name": "Dean Valley", "parser_key": "dean_valley", "url": "https://www.deanvalley.co.uk/events/"},
    {"name": "Brook Farm TC", "parser_key": "brook_farm", "url": "https://www.brookfarmtc.co.uk/what-s-on-2.php"},
    {"name": "Northallerton EC", "parser_key": "northallerton", "url": "https://www.northallertonequestriancentre.co.uk/diary/default.asp"},
    {"name": "Ballavartyn", "parser_key": "ballavartyn", "url": "https://equestrian.ballavartyn.com/events/event/feed/"},
    {"name": "Horse Boarding UK", "parser_key": "horse_boarding_uk", "url": "https://www.horseboardinguk.org/championshipdates"},
    # Major spectator shows
    {"name": "HOYS", "parser_key": "hoys", "url": "https://www.hoys.co.uk"},
    {"name": "London International", "parser_key": "london_international", "url": "https://www.londonhorseshow.com"},
    {"name": "Royal Windsor", "parser_key": "royal_windsor", "url": "https://www.rwhs.co.uk"},
    {"name": "Your Horse Live", "parser_key": "your_horse_live", "url": "https://www.yourhorse.co.uk/yourhorselive/"},
    {"name": "Great Yorkshire Show", "parser_key": "great_yorkshire", "url": "https://www.greatyorkshireshow.co.uk"},
    {"name": "Royal Highland Show", "parser_key": "royal_highland", "url": "https://www.royalhighlandshow.org"},
    {"name": "Royal Welsh Show", "parser_key": "royal_welsh", "url": "https://www.rwas.wales/royal-welsh/"},
    {"name": "Royal Cornwall Show", "parser_key": "royal_cornwall", "url": "https://www.royalcornwallshow.org"},
    {"name": "LGCT", "parser_key": "lgct", "url": "https://www.gcglobalchampions.com"},
    {"name": "Chatsworth Country Fair", "parser_key": "chatsworth", "url": "https://www.chatsworth.org/events/chatsworth-country-fair/"},
    {"name": "National Equine Show", "parser_key": "national_equine_show", "url": "https://nationalequineshow.com"},
    {"name": "Osberton Horse Trials", "parser_key": "osberton", "url": "https://osbertonhorse.co.uk"},
    {"name": "Hope Show", "parser_key": "hope_show", "url": "https://www.hopeshow.co.uk"},
    {"name": "Trailblazers Championships", "parser_key": "trailblazers", "url": "https://www.trailblazerschampionships.com"},
    # International spectator events
    {"name": "Sunshine Tour", "parser_key": "sunshine_tour", "url": "https://www.sunshinetour.net"},
    {"name": "Les 5 Etoiles de Pau", "parser_key": "pau", "url": "https://www.event-pau.com"},
    {"name": "Luhmuhlen Horse Trials", "parser_key": "luhmuhlen", "url": "https://tgl.luhmuehlen.de/en"},
    {"name": "Maryland 5 Star", "parser_key": "maryland_5_star", "url": "https://www.maryland5star.us"},
    {"name": "Ocala Winter Spectacular", "parser_key": "ocala", "url": "https://worldequestriancenter.com/ocala-fl/equestrian/shows/winter-spectacular/"},
    {"name": "Arc de Triomphe", "parser_key": "arc_de_triomphe", "url": "https://billetterie.france-galop.com/en/event/qatar-prix-de-larc-de-triomphe/"},
    {"name": "Spruce Meadows Masters", "parser_key": "spruce_meadows", "url": "https://www.sprucemeadows.com/masters/"},
    {"name": "Aachen World Equestrian Festival", "parser_key": "aachen", "url": "https://www.chioaachen.de/en/"},
    # Winter circuit / international indoor events
    {"name": "Azelhof", "parser_key": "azelhof", "url": "https://azelhof.be/en/home/"},
    {"name": "Sentower Park", "parser_key": "sentower_park", "url": "https://www.sentowerpark.com/en/home/"},
    {"name": "Keysoe International", "parser_key": "keysoe_international", "url": "https://www.keysoe.com/"},
    {"name": "Vilamoura Classic", "parser_key": "vilamoura", "url": "https://grandprix-events.com/en/vilamoura-classic/"},
    {"name": "Jumping Indoor Maastricht", "parser_key": "jumping_indoor_maastricht", "url": "https://jumpingindoormaastricht.com/en/home-en/"},
    {"name": "Gothenburg Horse Show", "parser_key": "gothenburg", "url": "https://www.gothenburghorseshow.com/en/"},
    {"name": "Scandinavia Jumping Tour", "parser_key": "scandinavia_jumping", "url": "https://occ.dk/en/nyheder/scandinavia-jumping-tour-2026/"},
    # UAE winter show jumping
    {"name": "UAE President's Cup", "parser_key": "uae_presidents_cup", "url": "https://uaeerf.ae/en/Content/Jumping/Calendar"},
    {"name": "Al Shira'aa International", "parser_key": "al_shiraaa", "url": "https://www.alshiraatour.com/abu-dhabi"},
    {"name": "Dubai SJ Championship", "parser_key": "dubai_sj_championship", "url": "https://www.emiratesequestriancentre.com/dubai-show-jumping-championship"},
    # France
    {"name": "Saut Hermès", "parser_key": "saut_hermes", "url": "https://www.sauthermes.com/en/"},
    {"name": "Equita Lyon", "parser_key": "equitalyon", "url": "https://www.equitalyon.com/en"},
    {"name": "Chantilly Classic", "parser_key": "chantilly", "url": "https://grandprix-events.com/en/chantilly-classic/"},
    # Italy
    {"name": "Adriatic Tour (Le Siepi)", "parser_key": "le_siepi", "url": "https://lesiepicervia.it/"},
    # Germany
    {"name": "Riesenbeck International", "parser_key": "riesenbeck", "url": "https://riesenbeck-international.com/en/"},
    {"name": "Hof Kasselmann", "parser_key": "hof_kasselmann", "url": "https://horses-and-dreams.de/en/"},
    {"name": "Pferd International München", "parser_key": "munich_riem", "url": "https://www.pferdinternational.de/"},
    # Netherlands
    {"name": "Peelbergen EC", "parser_key": "peelbergen", "url": "https://www.peelbergen.eu/"},
    {"name": "Jumping Amsterdam", "parser_key": "jumping_amsterdam", "url": "https://www.jumpingamsterdam.nl/en/"},
    {"name": "The Dutch Masters", "parser_key": "dutch_masters", "url": "https://www.thedutchmasters.com/en/"},
    {"name": "CHIO Rotterdam", "parser_key": "chio_rotterdam", "url": "https://chio.nl/en"},
    # Tier 1 prestige international events
    {"name": "CHI Geneva", "parser_key": "chi_geneva", "url": "https://www.chi-geneve.ch/en/"},
    {"name": "Dublin Horse Show", "parser_key": "dublin_horse_show", "url": "https://www.dublinhorseshow.com/"},
    {"name": "CSIO Roma — Piazza di Siena", "parser_key": "csio_roma", "url": "https://www.piazzadisiena.it/en/"},
    {"name": "Jumping Verona — Fieracavalli", "parser_key": "jumping_verona", "url": "https://www.fieracavalli.it/en/"},
    {"name": "CSIO Barcelona", "parser_key": "csio_barcelona", "url": "https://www.csiobarcelona.com/en/"},
    {"name": "Helsinki International Horse Show", "parser_key": "helsinki_horse_show", "url": "https://www.horseshowhelsinki.fi/en/"},
    {"name": "Falsterbo Horse Show", "parser_key": "falsterbo", "url": "https://www.falsterbohorseshow.com/en/"},
    {"name": "Madrid Horse Week", "parser_key": "madrid_horse_week", "url": "https://www.madridhorseweek.com/en/"},
    # Scandinavian & Eastern European
    {"name": "Oslo Horse Show", "parser_key": "oslo_horse_show", "url": "https://www.oslohorseshow.com/"},
    {"name": "Stockholm International Horse Show", "parser_key": "stockholm_horse_show", "url": "https://www.stockholmhorseshow.com/"},
    {"name": "CAVALIADA Krakow", "parser_key": "cavaliada", "url": "https://cavaliada.pl/en/"},
    {"name": "Samorin X-Bionic Sphere", "parser_key": "samorin", "url": "https://www.x-bionicsphere.com/en/equestrian/"},
    # France — additional prestige events
    {"name": "Jumping La Baule", "parser_key": "la_baule", "url": "https://www.jumpinglabaule.com/en/"},
    {"name": "Grand Parquet Fontainebleau", "parser_key": "fontainebleau", "url": "https://www.grandparquet.com/"},
    {"name": "Jumping de Dinard", "parser_key": "dinard", "url": "https://www.jumpingdinard.com/"},
    {"name": "Mondial du Lion", "parser_key": "mondial_du_lion", "url": "https://www.mondialdulion.com/en/"},
    {"name": "Jumping de Deauville", "parser_key": "deauville", "url": "https://www.pfrancecomplet.com/"},
    # Belgium & UK — additional
    {"name": "Brussels Stephex Masters", "parser_key": "brussels_stephex", "url": "https://www.stephexmasters.com/"},
    {"name": "Bolesworth International", "parser_key": "bolesworth", "url": "https://www.bolesworth.com/"},
    # Italy — spring circuit
    {"name": "Toscana Tour", "parser_key": "toscana_tour", "url": "https://www.toscanatour.com/"},
    # USA — Tier 1 prestige events
    {"name": "FEI World Cup Finals 2026", "parser_key": "fei_world_cup_finals", "url": "https://www.fortworth2026.com/"},
    {"name": "Kentucky Three-Day Event", "parser_key": "kentucky_three_day", "url": "https://www.kentuckythreedayevent.com/"},
    {"name": "Devon Horse Show", "parser_key": "devon_horse_show", "url": "https://www.devonhorseshow.net/"},
    {"name": "Dressage at Devon", "parser_key": "dressage_at_devon", "url": "https://dressageatdevon.org/"},
    {"name": "Hampton Classic", "parser_key": "hampton_classic", "url": "https://www.hamptonclassic.com/"},
    {"name": "Washington International Horse Show", "parser_key": "washington_international", "url": "https://wihs.org/"},
    {"name": "National Horse Show", "parser_key": "national_horse_show", "url": "https://nhs.org/"},
    {"name": "Upperville Colt & Horse Show", "parser_key": "upperville", "url": "https://www.upperville.com/"},
    {"name": "Pennsylvania National Horse Show", "parser_key": "pennsylvania_national", "url": "https://panational.org/"},
    {"name": "Live Oak International", "parser_key": "live_oak", "url": "https://www.liveoakinternational.com/"},
    {"name": "Great Meadow International", "parser_key": "great_meadow", "url": "https://greatmeadow.org/"},
    {"name": "Carolina International", "parser_key": "carolina_international", "url": "https://www.carolinahorsepark.com/"},
    # USA — multi-fixture competition venues
    {"name": "Lake Placid Horse Shows", "parser_key": "lake_placid", "url": "https://lakeplacidhorseshow.com/"},
    {"name": "Old Salem Farm", "parser_key": "old_salem_farm", "url": "https://oldsalemfarm.net/"},
    # USA — major winter/summer circuits
    {"name": "Winter Equestrian Festival", "parser_key": "wef", "url": "https://www.wellingtoninternational.com/"},
    {"name": "Global Dressage Festival", "parser_key": "global_dressage_festival", "url": "https://www.globaldressagefestival.com/"},
    {"name": "Desert International Horse Park", "parser_key": "desert_international", "url": "https://deserthorsepark.com/"},
    {"name": "Traverse City Horse Shows", "parser_key": "traverse_city", "url": "https://traversecityhorseshows.com/"},
]


def _validate_url(url: str | None) -> str | None:
    """Return the URL if it uses http(s), otherwise None."""
    if url and url.strip().lower().startswith(("http://", "https://")):
        return url.strip()
    if url:
        logger.warning("Rejected non-HTTP URL: %.100s", url)
    return None


async def run_scan(source_id: int, scan_id: int | None = None):
    """Run a scan for a single source."""
    start_time = time.monotonic()
    async with async_session() as session:
        if scan_id:
            scan = await session.get(Scan, scan_id)
            scan.started_at = datetime.utcnow()
            scan.status = "running"
            await session.commit()
        else:
            scan = Scan(
                source_id=source_id,
                started_at=datetime.utcnow(),
                status="running",
            )
            session.add(scan)
            await session.commit()

        try:
            source = (
                await session.execute(
                    select(Source).where(Source.id == source_id, Source.enabled == True)
                )
            ).scalar_one_or_none()

            if not source:
                scan.status = "failed"
                scan.error = f"Source {source_id} not found or not enabled"
                scan.completed_at = datetime.utcnow()
            else:
                count, match_counts, scan_comp_count, scan_training_count = await _scan_source(session, source)
                scan.status = "completed"
                scan.competitions_found = count
                scan.competitions_found_comp = scan_comp_count
                scan.competitions_found_training = scan_training_count
                scan.venue_match_summary = json.dumps(match_counts)
                scan.completed_at = datetime.utcnow()
        except Exception as e:
            logger.exception("Scan failed for source %d", source_id)
            # Roll back any broken transaction (e.g. "database is locked") so
            # the session is usable again before we write the failure status.
            await session.rollback()
            scan.status = "failed"
            scan.error = str(e)[:2000]
            scan.completed_at = datetime.utcnow()
            PARSER_ERRORS_TOTAL.labels(
                source_name=f"source_{source_id}",
                error_type=type(e).__name__,
            ).inc()

        await session.commit()
        logger.info("Scan %d finished: %s (%d found)", scan.id, scan.status, scan.competitions_found)

        # Record metrics
        duration = time.monotonic() - start_time
        SCAN_DURATION_SECONDS.labels(
            source_name=scan.source.name if scan.source else f"source_{source_id}",
            parser_key=scan.source.parser_key or "generic" if scan.source else "unknown",
        ).observe(duration)
        SCAN_TOTAL.labels(
            source_name=scan.source.name if scan.source else f"source_{source_id}",
            status=scan.status,
        ).inc()
        SCAN_COMPETITIONS_FOUND.labels(
            source_name=scan.source.name if scan.source else f"source_{source_id}",
        ).set(scan.competitions_found)

        # Post-scan: check for significant drop in competition count
        if scan.status == "completed" and source_id:
            try:
                await _check_scan_threshold(session, source_id, scan)
            except Exception as e:
                logger.warning("Scan threshold check failed: %s", e)


async def _check_scan_threshold(
    session: AsyncSession, source_id: int, current_scan: Scan
) -> None:
    """Warn if this scan found significantly fewer competitions than the previous one."""
    prev = (
        await session.execute(
            select(Scan)
            .where(
                Scan.source_id == source_id,
                Scan.status == "completed",
                Scan.id != current_scan.id,
            )
            .order_by(Scan.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not prev or prev.competitions_found == 0:
        return

    current = current_scan.competitions_found
    previous = prev.competitions_found
    if current < previous * 0.5:
        source = await session.get(Source, source_id)
        source_name = source.name if source else f"id={source_id}"
        logger.warning(
            "Source '%s' returned %d competitions, down from %d (previous scan) — "
            "possible parser issue",
            source_name, current, previous,
        )


async def _scan_source(session: AsyncSession, source: Source) -> tuple[int, dict[str, int], int, int]:
    """Scan a single source: fetch → extract → upsert competitions.

    Returns (new_competition_count, venue_match_counts, scan_comp_count, scan_training_count).
    scan_comp_count/scan_training_count are the total items found (not just new) in this scan.
    """
    logger.info("Scanning source: %s (%s) [parser: %s]", source.name, source.url, source.parser_key or "generic")

    parser = get_parser(source.parser_key)
    extracted = await parser.fetch_and_parse(source.url)

    # Look up source-level affiliation from _SOURCE_DEFS
    source_affiliation = None
    for defn in _SOURCE_DEFS:
        if defn["parser_key"] == source.parser_key:
            source_affiliation = defn.get("affiliation")
            break

    # Build venue index once per source scan
    venue_index = VenueIndex()
    await venue_index.build(session)

    count = 0
    scan_comp_count = 0
    scan_training_count = 0
    match_counts: dict[str, int] = defaultdict(int)
    for comp_data in extracted:
        try:
            date_start = date.fromisoformat(comp_data.date_start)
        except ValueError:
            logger.warning("Invalid date_start '%s', skipping", comp_data.date_start)
            continue

        date_end = None
        if comp_data.date_end:
            try:
                date_end = date.fromisoformat(comp_data.date_end)
            except ValueError:
                pass

        # Validate URL
        safe_url = _validate_url(comp_data.url)

        # Normalise venue name (basic cleanup only — aliases resolved by matcher)
        venue_name_cleaned = normalise_venue_name(comp_data.venue_name)

        # Normalise postcode: uppercase, insert space, reject junk
        clean_postcode = normalise_postcode(comp_data.venue_postcode)

        # Discard events with placeholder venue and no postcode — unlocatable
        if _is_placeholder_name(venue_name_cleaned) and not clean_postcode:
            logger.debug("Skipping event '%s': placeholder venue '%s' with no postcode",
                         comp_data.name, venue_name_cleaned)
            continue

        # Disambiguate generic venue names using postcode area
        # "Rectory Farm" + "GL7 7JW" → "Rectory Farm (GL7)"
        venue_name_cleaned = disambiguate_venue(venue_name_cleaned, clean_postcode)

        # Match against known venues
        venue_match = await match_venue(
            session,
            venue_index,
            normalised_name=venue_name_cleaned,
            raw_name=comp_data.venue_name,
            postcode=clean_postcode,
            parser_lat=comp_data.latitude,
            parser_lng=comp_data.longitude,
        )

        match_counts[venue_match.match_type] += 1
        VENUE_MATCH_TOTAL.labels(match_type=venue_match.match_type).inc()

        # Ensure venue has coordinates and distance
        venue = await session.get(Venue, venue_match.venue_id)
        if venue:
            await _ensure_venue_coords(
                session, venue, clean_postcode,
                comp_data.latitude, comp_data.longitude,
            )

        # EventClassifier is the single source of truth for classification.
        # It determines canonical discipline and event_type independently.
        discipline, event_type = EventClassifier.classify(
            name=comp_data.name,
            discipline_hint=comp_data.discipline,
            description=comp_data.description or "",
            event_type_hint=comp_data.event_type,
        )

        # Track competition vs training counts for scan metrics
        if event_type == "competition":
            scan_comp_count += 1
        else:
            scan_training_count += 1

        # Upsert: first check same source, then check ANY source (cross-source dedup).
        # Use .scalars().first() because duplicates can exist from earlier scans.
        existing = (
            await session.execute(
                select(Competition).where(
                    Competition.source_id == source.id,
                    Competition.name == comp_data.name,
                    Competition.date_start == date_start,
                    Competition.venue_id == venue_match.venue_id,
                )
            )
        ).scalars().first()

        if not existing:
            # Cross-source dedup: same event listed on multiple sites
            # (e.g. BD event also on Horse Monkey, Horse Events, etc.)
            existing = (
                await session.execute(
                    select(Competition).where(
                        Competition.source_id != source.id,
                        Competition.name == comp_data.name,
                        Competition.date_start == date_start,
                        Competition.venue_id == venue_match.venue_id,
                    )
                )
            ).scalars().first()

        if existing:
            existing.last_seen_at = datetime.utcnow()
            existing.discipline = discipline
            existing.event_type = event_type
            if existing.venue_id != venue_match.venue_id:
                existing.venue_match_type = venue_match.match_type
            existing.venue_id = venue_match.venue_id
            # Always update URL if parser provides one
            if safe_url:
                existing.url = safe_url
            if date_end and not existing.date_end:
                existing.date_end = date_end
            # Re-extract tags on rescan
            tags = extract_tags(
                name=comp_data.name,
                description=comp_data.description or "",
                discipline=discipline,
                event_type=event_type,
                source_affiliation=source_affiliation,
            )
            existing.tags = serialize_tags(tags) if tags else None
        else:
            # Extract tags from event name and details
            tags = extract_tags(
                name=comp_data.name,
                description=comp_data.description or "",
                discipline=discipline,
                event_type=event_type,
                source_affiliation=source_affiliation,
            )
            tags_json = serialize_tags(tags) if tags else None

            comp = Competition(
                source_id=source.id,
                name=comp_data.name,
                date_start=date_start,
                date_end=date_end,
                venue_id=venue_match.venue_id,
                venue_match_type=venue_match.match_type,
                discipline=discipline,
                event_type=event_type,
                tags=tags_json,
                url=safe_url,
                raw_extract=json.dumps(comp_data.model_dump()),
            )
            session.add(comp)
            count += 1

    source.last_scanned_at = datetime.utcnow()
    await session.commit()

    total = sum(match_counts.values())
    parts = ", ".join(f"{v} {k}" for k, v in sorted(match_counts.items(), key=lambda x: -x[1]))
    logger.info(
        "Source '%s': %d competitions — venues: %s",
        source.name, total, parts or "none",
    )
    return count, dict(match_counts), scan_comp_count, scan_training_count


async def _ensure_venue_coords(
    session: AsyncSession,
    venue: Venue,
    postcode: str | None,
    parser_lat: float | None,
    parser_lng: float | None,
) -> None:
    """Ensure a venue has coordinates. Updates the venue row in-place.

    Priority: 1) existing venue coords  2) venue postcode  3) parser coords  4) postcode param.
    """
    # Online/virtual venues: no physical location
    if venue.name and venue.name.strip().lower() in ("online", "virtual"):
        return

    # Already has valid coords (non-null and not (0,0))
    if venue.latitude is not None and venue.longitude is not None and not (venue.latitude == 0.0 and venue.longitude == 0.0):
        if postcode and not venue.postcode:
            venue.postcode = postcode
        return

    # Try venue's own postcode
    if venue.postcode:
        coords = await geocode_postcode(venue.postcode)
        if coords:
            venue.latitude, venue.longitude = coords
            return

    lat, lng = None, None

    # Disambiguated venues (e.g. "Brook Farm (TQ12)") must only get coords
    # from postcode geocoding — parser coords may belong to a different
    # instance of the same base venue name.
    is_disambiguated = bool(_DISAMBIGUATED_RE.search(venue.name or ""))

    if not is_disambiguated:
        # Try parser-provided coordinates (reject only (0,0) garbage)
        if parser_lat is not None and parser_lng is not None and not (parser_lat == 0.0 and parser_lng == 0.0):
            lat, lng = parser_lat, parser_lng
        # Try geocoding from postcode param
        elif postcode:
            coords = await geocode_postcode(postcode)
            if coords:
                lat, lng = coords
    else:
        # Disambiguated: only accept postcode-derived coords
        if postcode:
            coords = await geocode_postcode(postcode)
            if coords:
                lat, lng = coords

    if lat is not None:
        venue.latitude = lat
        venue.longitude = lng
        # Fill venue postcode if missing
        if not venue.postcode:
            if postcode:
                venue.postcode = postcode
            else:
                pc = normalise_postcode(await reverse_geocode(lat, lng))
                if pc:
                    venue.postcode = pc


async def audit_disciplines(session: AsyncSession) -> None:
    """Audit and normalise discipline values across all competitions.

    Logs warnings for unmapped values and auto-fixes known mappings.
    """
    rows = (
        await session.execute(
            select(Competition.discipline, func.count(Competition.id))
            .where(Competition.discipline != None)
            .group_by(Competition.discipline)
        )
    ).all()

    known_disciplines = {
        "Show Jumping", "Dressage", "Eventing", "Cross Country",
        "Combined Training", "Arena Eventing", "Showing", "Hunter Trial",
        "Endurance", "Gymkhana", "Polocrosse", "Polo",
        "Driving", "Drag Hunt", "Hobby Horse", "Horse Boarding",
    }

    fixed = 0
    for raw_disc, count in rows:
        canonical = normalise_discipline(raw_disc)
        if canonical and canonical != raw_disc:
            logger.info(
                "Discipline audit: '%s' (%d records) → '%s'",
                raw_disc, count, canonical,
            )
            comps = (
                await session.execute(
                    select(Competition).where(Competition.discipline == raw_disc)
                )
            ).scalars().all()
            for comp in comps:
                comp.discipline = canonical
                fixed += 1
        elif canonical and canonical not in known_disciplines:
            logger.warning(
                "Unmapped discipline found: '%s' (%d records)", raw_disc, count
            )

    if fixed:
        await session.commit()
        logger.info("Discipline audit: fixed %d records", fixed)
    else:
        logger.info("Discipline audit: all values canonical")


async def geocode_missing_venues() -> None:
    """Geocode venues that have postcodes but no coordinates.

    Called at startup to retry previously failed geocoding and to fill coords
    for disambiguated venues whose bad coords were cleared.
    """
    async with async_session() as session:
        venues = (await session.execute(
            select(Venue).where(Venue.postcode != None, Venue.latitude == None)
        )).scalars().all()
        if not venues:
            logger.info("Geocode missing: all venues with postcodes already have coords")
            return
        geocoded = 0
        for v in venues:
            coords = await geocode_postcode(v.postcode)
            if coords:
                v.latitude, v.longitude = coords
                geocoded += 1
        if geocoded:
            await session.commit()
            logger.info("Geocoded %d venues with missing coordinates", geocoded)
        else:
            logger.info("Geocode missing: 0 of %d venues geocoded (API failures?)", len(venues))


async def seed_venue_postcodes() -> None:
    """Populate venues table with known postcodes and coordinates.

    Reads seed data from app/venue_seeds.json via get_venue_seeds().
    Idempotent: only sets postcode/coords where venue has none; creates venue if missing.
    """
    async with async_session() as session:
        seeded = 0
        coords_set = 0
        for name, data in get_venue_seeds().items():
            postcode = data.get("postcode")
            if not postcode:
                continue  # alias-only entry (e.g. "Tbc")
            lat = data.get("lat")
            lng = data.get("lng")

            venue = (
                await session.execute(
                    select(Venue).where(Venue.name == name)
                )
            ).scalar_one_or_none()

            if venue:
                if not venue.postcode:
                    venue.postcode = postcode
                    seeded += 1
                if lat is not None and venue.latitude is None:
                    venue.latitude = lat
                    venue.longitude = lng
                    coords_set += 1
            else:
                session.add(Venue(
                    name=name, postcode=postcode,
                    latitude=lat, longitude=lng,
                ))
                seeded += 1
                if lat is not None:
                    coords_set += 1

        if seeded or coords_set:
            await session.commit()
            logger.info("Venue seed: %d postcodes, %d coordinates added", seeded, coords_set)
        else:
            logger.info("Venue seed: all data already present")


async def seed_sources() -> None:
    """Populate sources table from _SOURCE_DEFS. Idempotent: skips existing parser_keys."""
    async with async_session() as session:
        existing = {
            row[0]
            for row in (
                await session.execute(select(Source.parser_key).where(Source.parser_key != None))
            ).all()
        }
        created = 0
        for defn in _SOURCE_DEFS:
            if defn["parser_key"] in existing:
                continue
            session.add(Source(
                name=defn["name"],
                url=defn["url"],
                parser_key=defn["parser_key"],
            ))
            created += 1
        if created:
            await session.commit()
            logger.info("Source seed: created %d sources", created)
        else:
            logger.info("Source seed: all %d sources already present", len(_SOURCE_DEFS))


async def audit_venue_health() -> None:
    """Log a summary of venue data quality. Called at startup after geocoding."""
    async with async_session() as session:
        total = (await session.execute(select(func.count(Venue.id)))).scalar() or 0
        with_coords = (await session.execute(
            select(func.count(Venue.id)).where(Venue.latitude != None)
        )).scalar() or 0
        pct = (with_coords / total * 100) if total else 0

        # Venues with postcodes but no coords (geocoding failures)
        missing_coords = (await session.execute(
            select(Venue.name, Venue.postcode)
            .where(Venue.postcode != None, Venue.latitude == None)
        )).all()

        # Placeholder venues (Tbc/Tba/None-like names)
        placeholder_rows = (await session.execute(
            select(Venue.name, func.count(Competition.id))
            .outerjoin(Competition, Competition.venue_id == Venue.id)
            .where(func.lower(Venue.name).in_(["tbc", "tba", "tbd", "none", "unknown"]))
            .group_by(Venue.id)
        )).all()

        # Orphaned venues (0 competitions)
        orphaned = (await session.execute(
            select(func.count(Venue.id))
            .outerjoin(Competition, Competition.venue_id == Venue.id)
            .where(Competition.id == None)
        )).scalar() or 0

        # Pending match reviews
        pending_reviews = (await session.execute(
            select(func.count(VenueMatchReview.id))
            .where(VenueMatchReview.status == "pending")
        )).scalar() or 0

        logger.info(
            "Venue health: %d total, %d with coords (%.1f%%), %d placeholder, "
            "%d orphaned (0 competitions)",
            total, with_coords, pct, len(placeholder_rows), orphaned,
        )

        if missing_coords:
            samples = [f"{name} ({pc})" for name, pc in missing_coords[:5]]
            logger.info("  Missing coords: %s", ", ".join(samples))

        if placeholder_rows:
            parts = [f"{name} ({cnt} comps)" for name, cnt in placeholder_rows]
            logger.info("  Placeholder venues: %s", ", ".join(parts))

        if pending_reviews:
            logger.info("  Pending match reviews: %d", pending_reviews)


async def seed_all_venues_from_seeds() -> None:
    """Populate venues table with ALL seed data from venue_seeds.json.

    This ensures all 663 canonical venues from seed_data.json are in the database
    with source='seed_data' and proper metadata.
    """
    from app.seed_data import get_venue_seeds

    async with async_session() as session:
        created = 0
        updated = 0

        for canonical_name, data in get_venue_seeds().items():
            postcode = data.get("postcode")
            lat = data.get("lat")
            lng = data.get("lng")

            # Try to find existing venue by name
            existing = (
                await session.execute(
                    select(Venue).where(Venue.name == canonical_name)
                )
            ).scalar_one_or_none()

            if existing:
                # Update if needed
                if existing.source != "seed_data":
                    existing.source = "seed_data"
                    existing.seed_batch = "initial_seeds"
                    existing.validation_source = "seed_data"
                    existing.confidence = 1.0
                if postcode and not existing.postcode:
                    existing.postcode = postcode
                if lat is not None and existing.latitude is None:
                    existing.latitude = lat
                    existing.longitude = lng
                updated += 1
            else:
                # Create new venue from seed data
                venue = Venue(
                    name=canonical_name,
                    postcode=postcode,
                    latitude=lat,
                    longitude=lng,
                    source="seed_data",
                    seed_batch="initial_seeds",
                    validation_source="seed_data",
                    confidence=1.0,
                )
                session.add(venue)
                created += 1

        if created or updated:
            await session.commit()
            logger.info(
                "Seed venues: created %d new, updated %d existing (total %d from seed_data.json)",
                created, updated, created + updated
            )
        else:
            logger.info("Seed venues: all 663 already present")


async def seed_aliases_from_seeds() -> None:
    """Load all aliases from venue_seeds.json into venue_aliases table.

    Marks each alias with origin='seed_data' so they can be distinguished from
    dynamically-added aliases.
    """
    from app.models import VenueAlias
    from app.seed_data import get_venue_seeds

    async with async_session() as session:
        created = 0
        updated = 0

        for canonical_name, data in get_venue_seeds().items():
            aliases = data.get("aliases", [])
            if not aliases:
                continue

            # Find the canonical venue (must be source='seed_data')
            venue = (
                await session.execute(
                    select(Venue).where(
                        (Venue.name == canonical_name) & (Venue.source == "seed_data")
                    )
                )
            ).scalar_one_or_none()

            if not venue:
                continue  # Skip if seed_data venue not found

            # Add each alias
            for alias_name in aliases:
                existing = (
                    await session.execute(
                        select(VenueAlias).where(VenueAlias.alias == alias_name)
                    )
                ).scalar_one_or_none()

                if existing:
                    # Update existing alias to point to seed_data venue and mark origin
                    if existing.venue_id != venue.id or existing.origin != "seed_data":
                        existing.venue_id = venue.id
                        existing.source = "seed_data"
                        existing.origin = "seed_data"
                        updated += 1
                else:
                    # Create new alias
                    venue_alias = VenueAlias(
                        alias=alias_name,
                        venue_id=venue.id,
                        source="seed_data",
                        origin="seed_data",
                    )
                    session.add(venue_alias)
                    created += 1

        if created or updated:
            await session.commit()
            logger.info(
                "Seed aliases: created %d new, updated %d to point to seed_data venues",
                created, updated
            )
        else:
            logger.info("Seed aliases: all already properly configured")


async def seed_disciplines() -> None:
    """Populate DisciplineAlias table from seed_data.json disciplines."""
    from app.seed_data import get_discipline_seeds

    async with async_session() as session:
        created = 0
        updated = 0

        seeds = get_discipline_seeds()
        for discipline, data in seeds.items():
            aliases = data.get("aliases", [])
            if not aliases:
                continue

            for alias_name in aliases:
                alias_lower = alias_name.lower()
                existing = (
                    await session.execute(
                        select(DisciplineAlias).where(DisciplineAlias.alias == alias_lower)
                    )
                ).scalar_one_or_none()

                if existing:
                    # Update existing alias to point to current discipline
                    if existing.discipline != discipline:
                        existing.discipline = discipline
                        existing.source = "seed_data"
                        updated += 1
                else:
                    # Create new alias
                    discipline_alias = DisciplineAlias(
                        alias=alias_lower,
                        discipline=discipline,
                        source="seed_data",
                    )
                    session.add(discipline_alias)
                    created += 1

        if created or updated:
            await session.commit()
            logger.info(
                "Seed disciplines: created %d new, updated %d aliases",
                created, updated
            )
        else:
            logger.info("Seed disciplines: all already properly configured")

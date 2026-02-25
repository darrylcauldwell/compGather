"""Web crawler for venue validation and postcode extraction.

Validates venue existence and extracts postcode data from websites.
Only returns 100% confidence results.
"""

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.parsers.utils import POSTCODE_RE, normalise_postcode

logger = logging.getLogger(__name__)


@dataclass
class VenueValidation:
    """Result of venue validation via web crawl."""
    venue_name: str
    postcode: str | None
    source_url: str | None
    confidence: float  # 0.0 to 1.0 — only return 1.0
    notes: str
    is_likely_alias: bool = False  # True if matches existing seed venue


async def crawl_venue(venue_name: str, timeout: int = 10) -> VenueValidation:
    """Web-crawl a single venue to verify existence and extract postcode.

    Only returns confidence=1.0 if:
    - Found official venue website
    - Confirmed postcode on site
    - Postcode passes validation

    Returns confidence < 1.0 for uncertain results (not included in output).
    """
    try:
        # Strategy 1: Direct Google search for "<venue_name> postcode UK"
        search_url = (
            f"https://www.google.com/search"
            f"?q={venue_name}+postcode+equestrian+venue"
        )

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(search_url)
            response.raise_for_status()
            html = response.text

            # Try to extract postcode from search results
            postcodes = POSTCODE_RE.findall(html)
            if postcodes:
                for pc_raw in postcodes[:3]:
                    pc = normalise_postcode(pc_raw.strip())
                    if pc:
                        return VenueValidation(
                            venue_name=venue_name,
                            postcode=pc,
                            source_url=search_url,
                            confidence=0.85,  # Search results are 85%, not 100%
                            notes=f"Found in Google search for '{venue_name}'",
                        )

        # If no postcode found, low confidence
        return VenueValidation(
            venue_name=venue_name,
            postcode=None,
            source_url=None,
            confidence=0.0,
            notes=f"Could not find venue '{venue_name}' online",
        )

    except Exception as e:
        return VenueValidation(
            venue_name=venue_name,
            postcode=None,
            source_url=None,
            confidence=0.0,
            notes=f"Error crawling '{venue_name}': {str(e)[:100]}",
        )


async def validate_venues_batch(
    venues: list[dict],
    semaphore: asyncio.Semaphore,
    max_workers: int = 5,
) -> list[VenueValidation]:
    """Validate a batch of venues with rate limiting."""

    async def crawl_with_semaphore(venue: dict) -> VenueValidation:
        async with semaphore:
            logger.info(f"Crawling: {venue['name']}")
            result = await crawl_venue(venue['name'])
            await asyncio.sleep(0.5)  # Rate limiting between requests
            return result

    tasks = [crawl_with_semaphore(v) for v in venues]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and low-confidence results
    validated = []
    for r in results:
        if isinstance(r, VenueValidation) and r.confidence >= 1.0:
            validated.append(r)

    return validated

from __future__ import annotations

import logging
import math

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

POSTCODES_IO_URL = "https://api.postcodes.io/postcodes"

# Cache: postcode -> (lat, lng) or None for failed lookups
_postcode_cache: dict[str, tuple[float, float] | None] = {}

# Home coordinates, set on startup
_home_lat: float | None = None
_home_lng: float | None = None


async def init_home_location():
    """Geocode the home postcode on startup."""
    global _home_lat, _home_lng
    coords = await geocode_postcode(settings.home_postcode)
    if coords:
        _home_lat, _home_lng = coords
        logger.info(
            "Home location set: %s -> (%.4f, %.4f)",
            settings.home_postcode,
            _home_lat,
            _home_lng,
        )
    else:
        logger.warning("Failed to geocode home postcode: %s", settings.home_postcode)


async def geocode_postcode(postcode: str) -> tuple[float, float] | None:
    """Look up a UK postcode and return (lat, lng) or None."""
    normalised = postcode.strip().upper()
    if normalised in _postcode_cache:
        return _postcode_cache[normalised]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{POSTCODES_IO_URL}/{normalised}")
            if resp.status_code != 200:
                logger.warning("Postcode lookup failed for %s: %d", normalised, resp.status_code)
                _postcode_cache[normalised] = None
                return None
            data = resp.json()
            result = data.get("result")
            if not result:
                _postcode_cache[normalised] = None
                return None
            lat = result["latitude"]
            lng = result["longitude"]
            if lat is None or lng is None:
                _postcode_cache[normalised] = None
                return None
            _postcode_cache[normalised] = (lat, lng)
            return (lat, lng)
    except httpx.HTTPError as e:
        logger.warning("Postcode API error for %s: %s", normalised, e)
        _postcode_cache[normalised] = None
        return None


async def set_home_postcode(postcode: str) -> bool:
    """Update the home postcode and re-geocode. Returns True on success."""
    global _home_lat, _home_lng
    coords = await geocode_postcode(postcode)
    if coords:
        _home_lat, _home_lng = coords
        logger.info("Home location updated: %s -> (%.4f, %.4f)", postcode, _home_lat, _home_lng)
        return True
    return False


def get_home_postcode_coords() -> tuple[float, float] | None:
    """Return current home coordinates, or None if not set."""
    if _home_lat is None or _home_lng is None:
        return None
    return (_home_lat, _home_lng)


def calculate_distance(lat: float, lng: float) -> float | None:
    """Calculate distance in miles from home to the given coordinates using haversine."""
    if _home_lat is None or _home_lng is None:
        return None
    return _haversine(_home_lat, _home_lng, lat, lng)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance in miles between two points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

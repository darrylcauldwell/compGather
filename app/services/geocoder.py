from __future__ import annotations

import logging
import math

import httpx

logger = logging.getLogger(__name__)

POSTCODES_IO_URL = "https://api.postcodes.io/postcodes"
TERMINATED_IO_URL = "https://api.postcodes.io/terminated_postcodes"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Crown Dependencies not covered by postcodes.io
_CROWN_DEPENDENCY_PREFIXES = ("GY", "JE", "IM")

# UK + Crown Dependencies bounding box (lat 49-61, lng -11 to 2)
_UK_LAT_MIN, _UK_LAT_MAX = 49.0, 61.0
_UK_LNG_MIN, _UK_LNG_MAX = -11.0, 2.0

# Cache: postcode -> (lat, lng) or None for failed lookups
_postcode_cache: dict[str, tuple[float, float] | None] = {}


def _coords_in_uk(lat: float, lng: float) -> bool:
    """Check coordinates fall within the UK/Crown Dependencies bounding box."""
    if lat == 0.0 and lng == 0.0:
        return False
    return _UK_LAT_MIN <= lat <= _UK_LAT_MAX and _UK_LNG_MIN <= lng <= _UK_LNG_MAX


async def geocode_postcode(postcode: str) -> tuple[float, float] | None:
    """Look up a UK postcode and return (lat, lng) or None.

    Tries postcodes.io first (active then terminated), then falls back
    to Nominatim for Crown Dependency postcodes (GY, JE, IM).
    """
    normalised = postcode.strip().upper()
    if normalised in _postcode_cache:
        return _postcode_cache[normalised]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Crown Dependencies: skip postcodes.io, go straight to Nominatim
            if not normalised.startswith(_CROWN_DEPENDENCY_PREFIXES):
                # postcodes.io API expects postcodes without spaces
                postcode_for_api = normalised.replace(" ", "")
                resp = await client.get(f"{POSTCODES_IO_URL}/{postcode_for_api}")
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("result")
                    if result:
                        lat = result["latitude"]
                        lng = result["longitude"]
                        if lat is not None and lng is not None and _coords_in_uk(lat, lng):
                            _postcode_cache[normalised] = (lat, lng)
                            return (lat, lng)

                # Fallback: try terminated postcodes endpoint
                resp = await client.get(f"{TERMINATED_IO_URL}/{postcode_for_api}")
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get("result")
                    if result:
                        lat = result.get("latitude")
                        lng = result.get("longitude")
                        if lat is not None and lng is not None and _coords_in_uk(lat, lng):
                            _postcode_cache[normalised] = (lat, lng)
                            return (lat, lng)

            # Fallback: Nominatim for Crown Dependencies and any other failures
            coords = await _nominatim_postcode(client, normalised)
            if coords and _coords_in_uk(*coords):
                _postcode_cache[normalised] = coords
                return coords

            _postcode_cache[normalised] = None
            return None
    except httpx.HTTPError as e:
        logger.warning("Postcode API error for %s: %s", normalised, e)
        _postcode_cache[normalised] = None
        return None


async def _nominatim_postcode(
    client: httpx.AsyncClient, postcode: str
) -> tuple[float, float] | None:
    """Geocode a postcode via Nominatim (OpenStreetMap). Useful for CI/IoM."""
    try:
        resp = await client.get(
            NOMINATIM_URL,
            params={
                "q": postcode,
                "format": "json",
                "limit": 1,
                # Restrict to British Isles bounding box to avoid false matches
                "viewbox": "-11,49,2,61",
                "bounded": 1,
            },
            headers={"User-Agent": "EquiCalendar/1.0"},
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
                return (lat, lng)
    except Exception as e:
        logger.debug("Nominatim lookup failed for %s: %s", postcode, e)
    return None


async def reverse_geocode(lat: float, lng: float) -> str | None:
    """Look up the nearest UK postcode for given coordinates, or None."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                POSTCODES_IO_URL,
                params={"lat": lat, "lon": lng, "limit": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result")
                if result and len(result) > 0:
                    return result[0]["postcode"]
    except httpx.HTTPError as e:
        logger.warning("Reverse geocode error for (%.4f, %.4f): %s", lat, lng, e)
    return None


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance in miles between two points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

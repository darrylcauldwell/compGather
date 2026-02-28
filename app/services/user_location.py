"""Per-request user location helpers.

Provides stateless postcode geocoding and distance annotation
so that distance is computed per-request from a URL query parameter
rather than stored globally.
"""

from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Venue
from app.services.geocoder import geocode_postcode, haversine

# 1 degree latitude ≈ 69.0 miles
_MI_PER_DEG_LAT = 69.0


async def get_user_coords(postcode: str | None) -> tuple[float, float] | None:
    """Geocode a user-provided postcode, return (lat, lng) or None."""
    if not postcode or not postcode.strip():
        return None
    return await geocode_postcode(postcode.strip())


def bounding_box(
    lat: float, lng: float, max_miles: float
) -> tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lng_min, lng_max) for a distance radius.

    Uses flat-earth approximation with 10% margin for curvature error.
    Accurate enough for UK distances (<500 mi).
    """
    margin = max_miles * 1.1  # 10% safety margin
    dlat = margin / _MI_PER_DEG_LAT
    dlng = margin / (_MI_PER_DEG_LAT * math.cos(math.radians(lat)))
    return (lat - dlat, lat + dlat, lng - dlng, lng + dlng)


async def get_nearby_venue_ids(
    session: AsyncSession,
    user_coords: tuple[float, float],
    max_miles: float,
) -> set[int]:
    """Return venue IDs within a bounding box of max_miles from user_coords.

    Queries the Venue table (~670 rows) with a simple lat/lng range filter.
    """
    lat, lng = user_coords
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, max_miles)
    result = await session.execute(
        select(Venue.id).where(
            Venue.latitude.isnot(None),
            Venue.longitude.isnot(None),
            Venue.latitude >= lat_min,
            Venue.latitude <= lat_max,
            Venue.longitude >= lng_min,
            Venue.longitude <= lng_max,
        )
    )
    return {row[0] for row in result.all()}


def annotate_distances(items, user_coords: tuple[float, float] | None, venue_attr: str = "venue"):
    """Set _computed_distance on each item from its venue's lat/lng.

    Works for both Competition objects (venue_attr="venue") and
    Venue objects (venue_attr=None, reads lat/lng directly).
    """
    if not user_coords:
        return
    user_lat, user_lng = user_coords
    for item in items:
        if venue_attr:
            venue = getattr(item, venue_attr, None)
            if venue is None:
                continue
            lat = venue.latitude
            lng = venue.longitude
        else:
            lat = item.latitude
            lng = item.longitude
        if lat is not None and lng is not None:
            item._computed_distance = haversine(user_lat, user_lng, lat, lng)

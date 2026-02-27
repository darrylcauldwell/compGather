"""Per-request user location helpers.

Provides stateless postcode geocoding and distance annotation
so that distance is computed per-request from a URL query parameter
rather than stored globally.
"""

from __future__ import annotations

from app.services.geocoder import geocode_postcode, haversine


async def get_user_coords(postcode: str | None) -> tuple[float, float] | None:
    """Geocode a user-provided postcode, return (lat, lng) or None."""
    if not postcode or not postcode.strip():
        return None
    return await geocode_postcode(postcode.strip())


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

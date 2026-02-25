#!/usr/bin/env python3
"""Populate missing coordinates for venues using postcode API.

This script:
1. Finds all venues without latitude/longitude
2. Geocodes their postcodes using the existing geocoder service
3. Updates the database with coordinates
4. Marks them as geocoded with appropriate metadata
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session
from app.models import Venue
from app.services.geocoder import geocode_postcode
from sqlalchemy import select


async def populate_coordinates():
    """Find and geocode all venues without coordinates."""
    async with async_session() as session:
        # Find venues without coordinates but with postcode
        venues_to_geocode = (
            await session.execute(
                select(Venue).where(
                    (Venue.latitude.is_(None) | Venue.longitude.is_(None))
                    & Venue.postcode.isnot(None)
                )
            )
        ).scalars().all()

        print(f"Found {len(venues_to_geocode)} venues needing geocoding")

        geocoded = 0
        failed = 0

        for venue in venues_to_geocode:
            try:
                coords = await geocode_postcode(venue.postcode)
                if coords:
                    venue.latitude, venue.longitude = coords
                    venue.validation_source = "postcode_api"
                    venue.last_updated_at = __import__("datetime").datetime.utcnow()
                    geocoded += 1

                    if geocoded % 10 == 0:
                        print(f"  Geocoded {geocoded} venues...")
                else:
                    failed += 1
            except Exception as e:
                print(f"  Error geocoding {venue.name}: {e}")
                failed += 1

        # Save changes
        await session.commit()

        print(f"\n✅ Complete!")
        print(f"   Geocoded: {geocoded} venues")
        print(f"   Failed: {failed} venues")
        print(f"   Total venues in database: {len(venues_to_geocode)}")


if __name__ == "__main__":
    asyncio.run(populate_coordinates())

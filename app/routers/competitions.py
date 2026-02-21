from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import Competition
from app.schemas import CompetitionOut
from app.services.geocoder import calculate_distance, set_home_postcode

router = APIRouter(prefix="/api/competitions", tags=["competitions"])


@router.get("", response_model=list[CompetitionOut])
async def list_competitions(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    max_distance: float | None = Query(None),
    pony_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Competition).order_by(Competition.date_start)

    if date_from:
        stmt = stmt.where(Competition.date_start >= date_from)
    if date_to:
        stmt = stmt.where(Competition.date_start <= date_to)
    if pony_only:
        stmt = stmt.where(Competition.has_pony_classes == True)
    if max_distance is not None:
        stmt = stmt.where(
            Competition.distance_miles != None,
            Competition.distance_miles <= max_distance,
        )

    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/{competition_id}", response_model=CompetitionOut)
async def get_competition(
    competition_id: int, session: AsyncSession = Depends(get_session)
):
    comp = await session.get(Competition, competition_id)
    if not comp:
        raise HTTPException(404, "Competition not found")
    return comp


class PostcodeUpdate(BaseModel):
    postcode: str


@router.post("/update-postcode")
async def update_home_postcode(
    body: PostcodeUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update home postcode and recalculate all competition distances."""
    ok = await set_home_postcode(body.postcode)
    if not ok:
        raise HTTPException(400, "Invalid postcode")
    settings.home_postcode = body.postcode.strip().upper()

    # Recalculate distances for all competitions with coordinates
    result = await session.execute(
        select(Competition).where(Competition.latitude != None)
    )
    comps = result.scalars().all()
    updated = 0
    for comp in comps:
        dist = calculate_distance(comp.latitude, comp.longitude)
        if dist is not None:
            comp.distance_miles = dist
            updated += 1
    await session.commit()

    return {"postcode": body.postcode, "distances_updated": updated}

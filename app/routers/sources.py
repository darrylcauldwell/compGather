from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Source
from app.schemas import SourceCreate, SourceOut, SourceUpdate

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
async def list_sources(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Source).order_by(Source.name))
    return result.scalars().all()


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(data: SourceCreate, session: AsyncSession = Depends(get_session)):
    source = Source(name=data.name, url=data.url, parser_key=data.parser_key)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


@router.put("/{source_id}", response_model=SourceOut)
async def update_source(
    source_id: int, data: SourceUpdate, session: AsyncSession = Depends(get_session)
):
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    if data.name is not None:
        source.name = data.name
    if data.url is not None:
        source.url = data.url
    if data.parser_key is not None:
        source.parser_key = data.parser_key
    if data.enabled is not None:
        source.enabled = data.enabled
    await session.commit()
    await session.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: int, session: AsyncSession = Depends(get_session)):
    source = await session.get(Source, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    await session.delete(source)
    await session.commit()

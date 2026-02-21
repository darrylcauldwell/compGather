from __future__ import annotations

import logging

from app.parsers.base import BaseParser
from app.parsers.registry import register_parser
from app.schemas import ExtractedCompetition
from app.services.extractor import extract_competitions
from app.services.fetcher import fetch_page

logger = logging.getLogger(__name__)


@register_parser("generic")
class GenericParser(BaseParser):
    """LLM-based fallback parser using Ollama extraction."""

    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        html = await fetch_page(url)
        return await extract_competitions(html)

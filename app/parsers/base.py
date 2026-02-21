from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import ExtractedCompetition


class BaseParser(ABC):
    """Base class for all source parsers."""

    @abstractmethod
    async def fetch_and_parse(self, url: str) -> list[ExtractedCompetition]:
        """Fetch page content and return extracted competitions."""
        ...

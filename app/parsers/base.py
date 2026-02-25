from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import ExtractedEvent


class BaseParser(ABC):
    """Base class for all source parsers.

    Parsers are purely extractive - they should extract all raw event data
    without filtering or classification. Classification (determining if an
    event is a competition, training, venue hire, etc.) happens later in
    EventClassifier during the scanning process.
    """

    @abstractmethod
    async def fetch_and_parse(self, url: str) -> list[ExtractedEvent]:
        """Fetch page content and return extracted events.

        Returns a list of raw, unclassified events. All events should be
        extracted regardless of date - filtering happens in the classifier
        and UI layer, not in parsers.
        """
        ...

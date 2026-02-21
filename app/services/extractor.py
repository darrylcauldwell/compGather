from __future__ import annotations

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.schemas import ExtractedCompetition

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract all show jumping competitions from this webpage text.
The current year is {year}. Use this when dates don't include a year.
For each competition return a JSON object with these fields:
- name: competition/show name (string, required)
- date_start: start date as YYYY-MM-DD (string, required)
- date_end: end date as YYYY-MM-DD or null
- venue_name: venue name (string, required)
- venue_postcode: UK postcode if visible, or null
- has_pony_classes: true if pony or junior classes exist
- classes: array of class names/descriptions
- url: link to competition details or null

Return ONLY a JSON array. No explanation.

Webpage text:
{text}"""

MAX_TEXT_LENGTH = 6000


def _clean_html(html: str) -> str:
    """Strip boilerplate from HTML and return meaningful text content.

    Strategy: prefer table content (most competition sites use tables),
    then fall back to main/article content, then full page with boilerplate removed.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                              "noscript", "svg", "img", "link", "meta",
                              "select", "option", "form"]):
        tag.decompose()

    # Strategy 1: Extract table content (most competition pages use tables)
    tables = soup.find_all("table")
    if tables:
        parts = []
        for table in tables:
            table_text = table.get_text(separator=" | ")
            table_text = re.sub(r"\s+", " ", table_text).strip()
            if len(table_text) > 50:  # skip tiny/empty tables
                parts.append(table_text)
        if parts:
            text = "\n\n".join(parts)
            if len(text) > 200:
                logger.info("Extracted %d chars from %d table(s)", len(text), len(parts))
                return _collapse_whitespace(text)

    # Strategy 2: Try main/article content
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    if main:
        text = main.get_text(separator="\n")
        if len(text) > 200:
            logger.info("Extracted %d chars from main/article element", len(text))
            return _collapse_whitespace(text)

    # Strategy 3: Full page with boilerplate removed
    text = soup.get_text(separator="\n")
    return _collapse_whitespace(text)


def _collapse_whitespace(text: str) -> str:
    """Collapse whitespace and remove blank lines."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


async def extract_competitions(html: str) -> list[ExtractedCompetition]:
    """Send cleaned page text to Ollama and parse structured competition data."""
    from datetime import date as _date

    cleaned = _clean_html(html)
    truncated = cleaned[:MAX_TEXT_LENGTH]
    prompt = EXTRACTION_PROMPT.format(text=truncated, year=_date.today().year)

    url = f"{settings.ollama_url}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": 2048},
    }

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            logger.info(
                "Sending %d chars of cleaned text to Ollama (%s) [original HTML: %d chars]",
                len(truncated), settings.ollama_model, len(html),
            )
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            logger.info("Ollama response received (%d chars)", len(result.get("response", "")))
    except httpx.TimeoutException as e:
        logger.error("Ollama request timed out after 600s: %s", e)
        return []
    except httpx.HTTPError as e:
        logger.error("Ollama request failed: %s: %s", type(e).__name__, e)
        return []
    except Exception as e:
        logger.error("Unexpected error calling Ollama: %s: %s", type(e).__name__, e)
        return []

    raw_text = result.get("response", "")
    logger.debug("Raw LLM response: %s", raw_text[:2000])
    return _parse_response(raw_text)


def _repair_json_array(text: str) -> str | None:
    """Try to extract a valid JSON array, repairing truncated output."""
    # Find the opening bracket
    start = text.find("[")
    if start == -1:
        return None

    # Try parsing as-is first (look for complete array)
    end = text.rfind("]")
    if end > start:
        candidate = text[start : end + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Truncated output: find last complete object by looking for last "},"  or "}"
    # and close the array there
    fragment = text[start:]
    last_brace = fragment.rfind("}")
    if last_brace == -1:
        return None

    # Try closing the array after the last complete object
    candidate = fragment[: last_brace + 1] + "]"
    try:
        json.loads(candidate)
        logger.info("Repaired truncated JSON array (cut at char %d)", last_brace)
        return candidate
    except json.JSONDecodeError:
        pass

    # More aggressive: find each "}" and try closing from the end backwards
    for i in range(last_brace, 0, -1):
        if fragment[i] == "}":
            candidate = fragment[: i + 1] + "]"
            try:
                json.loads(candidate)
                logger.info("Repaired truncated JSON array (cut at char %d)", i)
                return candidate
            except json.JSONDecodeError:
                continue

    return None


def _parse_response(text: str) -> list[ExtractedCompetition]:
    """Parse the LLM JSON response into validated competition objects."""
    json_str = _repair_json_array(text)
    if not json_str:
        logger.warning("No valid JSON array found in LLM response: %s", text[:500])
        return []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM JSON: %s — raw: %s", e, text[:500])
        return []

    if not isinstance(data, list):
        logger.warning("LLM response is not a list")
        return []

    valid_fields = set(ExtractedCompetition.model_fields.keys())
    competitions = []
    for item in data:
        try:
            filtered = {k: v for k, v in item.items() if k in valid_fields}
            comp = ExtractedCompetition(**filtered)
            competitions.append(comp)
        except Exception as e:
            logger.warning("Skipping invalid competition entry: %s — data: %s", e, json.dumps(item)[:300])

    logger.info("Extracted %d competitions from LLM response", len(competitions))
    return competitions

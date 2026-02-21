from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.parsers.base import BaseParser

PARSER_REGISTRY: dict[str, type[BaseParser]] = {}


def register_parser(key: str):
    """Decorator to register a parser class under a key."""
    def decorator(cls):
        PARSER_REGISTRY[key] = cls
        return cls
    return decorator


def get_parser(key: str | None) -> BaseParser:
    """Return a parser instance for the given key, or the generic fallback."""
    if key and key in PARSER_REGISTRY:
        return PARSER_REGISTRY[key]()
    from app.parsers.generic import GenericParser
    return GenericParser()


def list_parser_keys() -> list[str]:
    """Return all registered parser keys."""
    return sorted(PARSER_REGISTRY.keys())

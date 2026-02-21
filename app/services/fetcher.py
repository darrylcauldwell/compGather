from __future__ import annotations

import logging

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 500


async def fetch_page(url: str) -> str:
    """Fetch page content. Tries httpx first, falls back to Playwright for JS-heavy pages."""
    html = await _fetch_with_httpx(url)
    if html and len(html) >= MIN_CONTENT_LENGTH:
        logger.info("Fetched %s with httpx (%d chars)", url, len(html))
        return html

    logger.info("httpx returned insufficient content for %s, trying Playwright", url)
    return await _fetch_with_playwright(url)


async def _fetch_with_httpx(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=30.0
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPError as e:
        logger.warning("httpx fetch failed for %s: %s", url, e)
        return None


async def _fetch_with_playwright(url: str) -> str:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=60000)
                html = await page.content()
                logger.info("Fetched %s with Playwright (%d chars)", url, len(html))
                return html
            finally:
                await browser.close()
    except Exception as e:
        logger.warning("Playwright fetch failed for %s: %s", url, e)
        raise RuntimeError(f"Page at {url} requires a JS browser but Playwright is not available: {e}")

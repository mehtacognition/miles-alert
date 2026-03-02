"""Delta.com award search scraper using Playwright.

Searches delta.com with "Shop with Miles" enabled for international
routes from the configured origin airport. Parses first class and
business class award availability.

IMPORTANT: This scraper is for personal use only. It rate-limits
itself to avoid overloading delta.com (5-10 second delays between
searches). Running more than 3x/day is not recommended.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass

from sources.base import AwardDeal

logger = logging.getLogger(__name__)

# Top international destinations from ATL with Delta service
INTERNATIONAL_DESTINATIONS = [
    "LHR",  # London
    "CDG",  # Paris
    "FCO",  # Rome
    "AMS",  # Amsterdam
    "FRA",  # Frankfurt
    "BCN",  # Barcelona
    "MAD",  # Madrid
    "NRT",  # Tokyo Narita
    "HND",  # Tokyo Haneda
    "ICN",  # Seoul
    "CUN",  # Cancun
    "SJU",  # San Juan
    "BOG",  # Bogota
    "LIM",  # Lima
    "GRU",  # Sao Paulo
    "EZE",  # Buenos Aires
    "DUB",  # Dublin
    "MXP",  # Milan
    "ATH",  # Athens
    "SYD",  # Sydney (via partner)
]


def parse_award_results_from_data(
    origin: str, destination: str, results: list[dict]
) -> list[AwardDeal]:
    """Convert parsed result dicts into AwardDeal objects."""
    deals = []
    for r in results:
        deals.append(
            AwardDeal(
                origin=origin,
                destination=destination,
                airline="DL",
                cabin=r["cabin"],
                miles_price=r["miles"],
                seats_available=r.get("seats", 1),
                departure_date=r["date"],
                source="delta_search",
            )
        )
    return deals


def parse_award_results(
    origin: str, destination: str, page_content: str
) -> list[AwardDeal]:
    """Parse delta.com search results HTML for award availability.

    This function must be updated if Delta changes their page structure.
    Returns empty list if parsing fails.
    """
    if not page_content:
        return []

    logger.warning(
        "parse_award_results needs real delta.com HTML structure. "
        "Run integration test to capture and update selectors."
    )
    return []


class DeltaSearchSource:
    """Scrapes delta.com award search using Playwright."""

    def fetch_deals(self, config: dict) -> list[AwardDeal]:
        """Search delta.com for award availability on all target routes."""
        return asyncio.run(self._fetch_deals_async(config))

    async def _fetch_deals_async(self, config: dict) -> list[AwardDeal]:
        """Async implementation of award search."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        origin = config["origin"]
        cabins = config.get("cabins", ["first", "business"])
        excluded = set(config.get("excluded_destinations", []))
        destinations = [d for d in INTERNATIONAL_DESTINATIONS if d not in excluded]

        all_deals = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            for dest in destinations:
                try:
                    logger.info(f"Searching {origin} -> {dest}...")
                    deals = await self._search_route(page, origin, dest, cabins)
                    all_deals.extend(deals)

                    # Rate limit: random 5-10 second delay
                    delay = random.uniform(5, 10)
                    logger.debug(f"Waiting {delay:.1f}s before next search")
                    await asyncio.sleep(delay)

                except Exception as e:
                    logger.warning(f"Failed to search {origin}->{dest}: {e}")
                    continue

            await browser.close()

        logger.info(f"Found {len(all_deals)} total deals across {len(destinations)} routes")
        return all_deals

    async def _search_route(
        self, page, origin: str, destination: str, cabins: list[str]
    ) -> list[AwardDeal]:
        """Search a single route on delta.com.

        NOTE: This method's selectors must be verified against delta.com's
        actual page structure. The implementation below is a scaffold that
        must be refined during integration testing with a real browser.
        """
        url = (
            f"https://www.delta.com/flight-search/search?"
            f"action=findFlights&tripType=ONE_WAY"
            f"&from={origin}&to={destination}"
            f"&departureDate=flexible&shopWithMiles=true"
        )
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        content = await page.content()
        return parse_award_results(origin, destination, content)

"""Enrich award deals with cash prices from Google Flights.

Uses the fast_flights library to look up what the same flight
would cost in cash, enabling cents-per-mile value calculation.

This is optional enrichment -- if it fails, the deal is still
reported without a cash price comparison.
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace

from sources.base import AwardDeal

try:
    from fast_flights import create_filter, get_flights, Passengers
except ImportError:
    create_filter = None
    get_flights = None
    Passengers = None

logger = logging.getLogger(__name__)

CABIN_MAP = {
    "first": "first",
    "business": "business",
}


def _parse_price(price_str: str) -> float | None:
    """Extract numeric price from string like '$4,800'."""
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


def enrich_with_cash_price(deal: AwardDeal) -> AwardDeal:
    """Look up the cash price for this route/date on Google Flights.

    Returns a new AwardDeal with cash_price set, or the original
    deal unchanged if lookup fails.
    """
    try:
        if create_filter is None or get_flights is None:
            logger.warning("fast_flights not installed, skipping cash price enrichment")
            return deal

        flt = create_filter(
            flight_data=[
                {
                    "date": deal.departure_date,
                    "from": deal.origin,
                    "to": deal.destination,
                }
            ],
            trip="one-way",
            seat=CABIN_MAP.get(deal.cabin, "business"),
            passengers=Passengers(adults=1),
        )

        result = get_flights(flt)

        if not result.flights:
            logger.debug(f"No cash flights found for {deal.origin}->{deal.destination}")
            return deal

        prices = [_parse_price(f.price) for f in result.flights]
        valid_prices = [p for p in prices if p is not None]

        if not valid_prices:
            return deal

        cash_price = min(valid_prices)
        logger.info(
            f"Cash price {deal.origin}->{deal.destination}: "
            f"${cash_price:,.0f} ({deal.cabin})"
        )
        return replace(deal, cash_price=cash_price)

    except Exception as e:
        logger.warning(f"Cash price lookup failed for {deal.origin}->{deal.destination}: {e}")
        return deal

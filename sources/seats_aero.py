"""seats.aero Partner API source for award availability.

Queries the seats.aero cached search API for Delta SkyMiles
award availability from the configured origin airport.

Requires a Pro subscription ($9.99/mo) and API key.
Set seats_aero_api_key in config to activate.

API docs: https://developers.seats.aero/reference/cached-search
Rate limit: 1,000 calls/day (resets midnight UTC)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from sources.base import AwardDeal

logger = logging.getLogger(__name__)

API_BASE = "https://seats.aero/partnerapi/search"

# Map our cabin names to seats.aero availability fields
CABIN_FIELDS = {
    "business": {"available": "JAvailable", "mileage": "JMileageCost", "seats": "JRemainingSeats"},
    "first": {"available": "FAvailable", "mileage": "FMileageCost", "seats": "FRemainingSeats"},
}


class SeatsAeroSource:
    """Fetches award availability from seats.aero Partner API."""

    def fetch_deals(self, config: dict) -> list[AwardDeal]:
        """Query seats.aero for award availability."""
        api_key = config.get("seats_aero_api_key")
        if not api_key:
            logger.warning("No seats_aero_api_key in config — skipping seats.aero source")
            return []

        origin = config["origin"]
        cabins = config.get("cabins", ["first", "business"])

        # Search 1-6 months out for award availability
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")

        # Map cabin names to seats.aero format
        cabin_param = ",".join(
            {"first": "first", "business": "business"}.get(c, c)
            for c in cabins
        )

        params = {
            "origin_airport": origin,
            "sources": "delta",
            "cabins": cabin_param,
            "start_date": start_date,
            "end_date": end_date,
            "order_by": "lowest_mileage",
            "take": 500,
        }

        url = f"{API_BASE}?{urlencode(params)}"
        logger.info(f"Querying seats.aero: {origin} -> international ({cabin_param})")

        try:
            req = Request(url, headers={"Partner-Authorization": api_key})
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

                # Log rate limit info
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining:
                    logger.info(f"seats.aero API calls remaining today: {remaining}")

        except Exception as e:
            logger.error(f"seats.aero API request failed: {e}")
            return []

        return self._parse_response(data, origin, cabins)

    def _parse_response(
        self, data: dict, origin: str, cabins: list[str]
    ) -> list[AwardDeal]:
        """Parse seats.aero API response into AwardDeal objects."""
        results = data.get("data", [])
        deals = []

        for item in results:
            destination = item.get("Route", {}).get("DestinationAirport", "")
            date = item.get("Date", "")

            for cabin in cabins:
                fields = CABIN_FIELDS.get(cabin)
                if not fields:
                    continue

                available = item.get(fields["available"], False)
                if not available:
                    continue

                mileage_str = item.get(fields["mileage"], "0")
                try:
                    mileage = int(mileage_str)
                except (ValueError, TypeError):
                    continue

                if mileage <= 0:
                    continue

                seats = item.get(fields["seats"], 0) or 0

                # Determine airline from the cabin-specific airlines field
                airline_key = {"business": "JAirlines", "first": "FAirlines"}.get(cabin, "")
                airline = item.get(airline_key, "DL") or "DL"
                # Take first airline if comma-separated
                airline = airline.split(",")[0].strip()

                deals.append(
                    AwardDeal(
                        origin=origin,
                        destination=destination,
                        airline=airline,
                        cabin=cabin,
                        miles_price=mileage,
                        seats_available=seats,
                        departure_date=date,
                        source="seats_aero",
                    )
                )

        logger.info(f"seats.aero returned {len(deals)} deals from {len(results)} availability records")
        return deals

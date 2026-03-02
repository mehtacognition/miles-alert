"""Data model and source interface for award deals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class DealSource(Protocol):
    """Interface for award deal data sources."""

    def fetch_deals(self, config: dict) -> list[AwardDeal]: ...


@dataclass
class AwardDeal:
    """A single award flight deal."""

    origin: str
    destination: str
    airline: str
    cabin: str  # "first" | "business"
    miles_price: int
    seats_available: int
    departure_date: str  # YYYY-MM-DD
    source: str  # "delta_search" | "seats_aero"
    cash_price: float | None = None

    @property
    def cents_per_mile(self) -> float | None:
        """Calculate redemption value in cents per mile."""
        if self.cash_price is None or self.miles_price <= 0:
            return None
        return (self.cash_price / self.miles_price) * 100

    @property
    def dedup_key(self) -> str:
        """Unique key for deduplication."""
        return f"{self.origin}-{self.destination}-{self.cabin}-{self.departure_date}"

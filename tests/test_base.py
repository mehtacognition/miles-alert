"""Tests for data model and source interface."""
import pytest
from sources.base import AwardDeal, DealSource


def test_award_deal_creation():
    deal = AwardDeal(
        origin="ATL",
        destination="NRT",
        airline="DL",
        cabin="first",
        miles_price=85000,
        seats_available=2,
        departure_date="2026-05-15",
        source="delta_search",
    )
    assert deal.origin == "ATL"
    assert deal.miles_price == 85000
    assert deal.cash_price is None
    assert deal.cents_per_mile is None


def test_award_deal_dedup_key():
    deal = AwardDeal(
        origin="ATL",
        destination="NRT",
        airline="DL",
        cabin="first",
        miles_price=85000,
        seats_available=2,
        departure_date="2026-05-15",
        source="delta_search",
    )
    assert deal.dedup_key == "ATL-NRT-first-2026-05-15"


def test_award_deal_with_cash_price():
    deal = AwardDeal(
        origin="ATL",
        destination="NRT",
        airline="DL",
        cabin="first",
        miles_price=80000,
        seats_available=2,
        departure_date="2026-05-15",
        source="delta_search",
        cash_price=4800.0,
    )
    assert deal.cents_per_mile == pytest.approx(6.0)


def test_deal_source_protocol():
    """DealSource protocol requires fetch_deals method."""
    class FakeSource:
        def fetch_deals(self, config):
            return []

    source = FakeSource()
    assert hasattr(source, "fetch_deals")

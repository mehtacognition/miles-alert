"""Tests for cash price enrichment via Google Flights."""
import pytest
from unittest.mock import patch, MagicMock
from sources.base import AwardDeal
from enrichment import enrich_with_cash_price


def make_deal(**kwargs):
    defaults = dict(
        origin="ATL", destination="NRT", airline="DL",
        cabin="first", miles_price=80000, seats_available=2,
        departure_date="2026-05-15", source="delta_search",
    )
    defaults.update(kwargs)
    return AwardDeal(**defaults)


@patch("enrichment.Passengers", MagicMock())
@patch("enrichment.create_filter")
@patch("enrichment.get_flights")
def test_enrich_success(mock_get_flights, mock_create_filter):
    """Should set cash_price when Google Flights returns results."""
    mock_filter = MagicMock()
    mock_create_filter.return_value = mock_filter

    mock_result = MagicMock()
    mock_flight = MagicMock()
    mock_flight.price = "$4,800"
    mock_result.flights = [mock_flight]
    mock_get_flights.return_value = mock_result

    deal = make_deal()
    enriched = enrich_with_cash_price(deal)
    assert enriched.cash_price == 4800.0


@patch("enrichment.Passengers", MagicMock())
@patch("enrichment.create_filter")
@patch("enrichment.get_flights")
def test_enrich_no_results(mock_get_flights, mock_create_filter):
    """Should leave cash_price as None when no flights found."""
    mock_filter = MagicMock()
    mock_create_filter.return_value = mock_filter
    mock_result = MagicMock()
    mock_result.flights = []
    mock_get_flights.return_value = mock_result

    deal = make_deal()
    enriched = enrich_with_cash_price(deal)
    assert enriched.cash_price is None


@patch("enrichment.create_filter", side_effect=Exception("rate limited"))
def test_enrich_failure_graceful(mock_create_filter):
    """Should return deal unchanged on failure, not raise."""
    deal = make_deal()
    enriched = enrich_with_cash_price(deal)
    assert enriched.cash_price is None

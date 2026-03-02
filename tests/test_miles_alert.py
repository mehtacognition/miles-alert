"""Tests for main entry point."""
import json
import pytest
from unittest.mock import patch, MagicMock
from sources.base import AwardDeal
from miles_alert import run, filter_deals, _send_to_all


@pytest.fixture
def sample_deals():
    return [
        AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "delta_search", 8000.0),
        AwardDeal("ATL", "LHR", "DL", "business", 200000, 1, "2026-06-01", "delta_search", 3000.0),
        AwardDeal("ATL", "CDG", "DL", "first", 50000, 3, "2026-07-10", "delta_search", 5000.0),
    ]


@pytest.fixture
def sample_config():
    return {
        "origin": "ATL",
        "phones": ["+15551234567", "+15559876543"],
        "min_cents_per_mile": 2.0,
        "min_seats": 2,
        "cabins": ["first", "business"],
        "sources": ["delta_search"],
        "excluded_destinations": [],
    }


def test_filter_deals_by_cents_per_mile(sample_deals, sample_config):
    """Should filter out deals below min_cents_per_mile threshold."""
    filtered = filter_deals(sample_deals, sample_config)
    # NRT: 8000/80000*100 = 10.0 cpm (pass)
    # LHR: 3000/200000*100 = 1.5 cpm (fail - below 2.0)
    # CDG: 5000/50000*100 = 10.0 cpm (pass)
    assert len(filtered) == 2
    destinations = {d.destination for d in filtered}
    assert "NRT" in destinations
    assert "CDG" in destinations
    assert "LHR" not in destinations


def test_filter_deals_by_min_seats(sample_deals, sample_config):
    """Should filter out deals with fewer than min_seats."""
    sample_config["min_cents_per_mile"] = 0  # disable cpm filter
    filtered = filter_deals(sample_deals, sample_config)
    # LHR has only 1 seat, min is 2
    assert all(d.seats_available >= 2 for d in filtered)


def test_filter_deals_no_cash_price_passes(sample_config):
    """Deals without cash price should pass filter (can't calculate cpm)."""
    deals = [
        AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "delta_search"),
    ]
    filtered = filter_deals(deals, sample_config)
    assert len(filtered) == 1


def test_filter_deals_by_cabin(sample_config):
    """Should only include configured cabin classes."""
    deals = [
        AwardDeal("ATL", "NRT", "DL", "economy", 25000, 4, "2026-05-15", "delta_search"),
    ]
    filtered = filter_deals(deals, sample_config)
    assert len(filtered) == 0


@patch("miles_alert.send_imessage")
def test_send_to_all_sends_to_both_phones(mock_send):
    """Should send message to all phones in the config."""
    config = {"phones": ["+15551111111", "+15552222222"]}
    _send_to_all(config, "Test deal alert")
    assert mock_send.call_count == 2
    mock_send.assert_any_call("+15551111111", "Test deal alert")
    mock_send.assert_any_call("+15552222222", "Test deal alert")

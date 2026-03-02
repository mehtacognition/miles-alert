"""Tests for main entry point."""
import json
import pytest
from unittest.mock import patch, MagicMock
from sources.base import AwardDeal
from miles_alert import run, filter_deals, _send_to_all, classify_tier, detect_price_drop, is_watchlist_match, build_alert_plan


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


@pytest.fixture
def tier_thresholds():
    return {"exceptional": 5.0, "strong": 3.0, "good": 2.0}


def test_classify_tier_exceptional(tier_thresholds):
    deal = AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "seats_aero", 8000.0)
    # 8000/80000*100 = 10.0 CPM -> exceptional
    assert classify_tier(deal, tier_thresholds) == "exceptional"


def test_classify_tier_strong(tier_thresholds):
    deal = AwardDeal("ATL", "CDG", "DL", "business", 120000, 2, "2026-06-01", "seats_aero", 4800.0)
    # 4800/120000*100 = 4.0 CPM -> strong
    assert classify_tier(deal, tier_thresholds) == "strong"


def test_classify_tier_good(tier_thresholds):
    deal = AwardDeal("ATL", "LHR", "DL", "business", 100000, 2, "2026-07-01", "seats_aero", 2500.0)
    # 2500/100000*100 = 2.5 CPM -> good
    assert classify_tier(deal, tier_thresholds) == "good"


def test_classify_tier_no_cpm_defaults_to_strong(tier_thresholds):
    """Deals without cash price (no CPM) should default to strong tier."""
    deal = AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "seats_aero")
    assert classify_tier(deal, tier_thresholds) == "strong"


def test_is_watchlist_match_hit():
    deal = AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "seats_aero")
    watchlist = [{"destination": "NRT", "cabin": "first"}]
    assert is_watchlist_match(deal, watchlist) is True


def test_is_watchlist_match_wrong_cabin():
    deal = AwardDeal("ATL", "NRT", "DL", "business", 120000, 2, "2026-05-15", "seats_aero")
    watchlist = [{"destination": "NRT", "cabin": "first"}]
    assert is_watchlist_match(deal, watchlist) is False


def test_is_watchlist_match_wrong_destination():
    deal = AwardDeal("ATL", "LHR", "DL", "first", 80000, 2, "2026-05-15", "seats_aero")
    watchlist = [{"destination": "NRT", "cabin": "first"}]
    assert is_watchlist_match(deal, watchlist) is False


def test_is_watchlist_match_empty_watchlist():
    deal = AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "seats_aero")
    assert is_watchlist_match(deal, []) is False


def test_detect_price_drop_found():
    deal = AwardDeal("ATL", "NRT", "DL", "first", 70000, 2, "2026-05-15", "seats_aero")
    state = {
        "ATL-NRT-first-2026-05-15": {"alerted_at": "2026-03-01T10:00:00+00:00", "miles_price": 85000}
    }
    result = detect_price_drop(deal, state)
    assert result is not None
    assert result == 85000  # previous price


def test_detect_price_drop_no_drop():
    """Same or higher price should not trigger a price drop."""
    deal = AwardDeal("ATL", "NRT", "DL", "first", 85000, 2, "2026-05-15", "seats_aero")
    state = {
        "ATL-NRT-first-2026-05-15": {"alerted_at": "2026-03-01T10:00:00+00:00", "miles_price": 85000}
    }
    assert detect_price_drop(deal, state) is None


def test_detect_price_drop_increase():
    """Price increase should not trigger."""
    deal = AwardDeal("ATL", "NRT", "DL", "first", 90000, 2, "2026-05-15", "seats_aero")
    state = {
        "ATL-NRT-first-2026-05-15": {"alerted_at": "2026-03-01T10:00:00+00:00", "miles_price": 85000}
    }
    assert detect_price_drop(deal, state) is None


def test_detect_price_drop_not_in_state():
    """New deal not in state should not trigger price drop."""
    deal = AwardDeal("ATL", "NRT", "DL", "first", 70000, 2, "2026-05-15", "seats_aero")
    assert detect_price_drop(deal, {}) is None


def test_detect_price_drop_no_previous_price():
    """Migrated old state entry with no miles_price should not trigger."""
    deal = AwardDeal("ATL", "NRT", "DL", "first", 70000, 2, "2026-05-15", "seats_aero")
    state = {
        "ATL-NRT-first-2026-05-15": {"alerted_at": "2026-03-01T10:00:00+00:00", "miles_price": None}
    }
    assert detect_price_drop(deal, state) is None


def test_build_alert_plan_separates_tiers():
    """Exceptional deals go to individual alerts, others to digest."""
    deals = [
        AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "seats_aero", 8000.0),   # 10.0 CPM -> exceptional
        AwardDeal("ATL", "CDG", "DL", "business", 120000, 2, "2026-06-14", "seats_aero", 4800.0), # 4.0 CPM -> strong
        AwardDeal("ATL", "FCO", "DL", "business", 95000, 3, "2026-08-03", "seats_aero", 2300.0),  # 2.4 CPM -> good
    ]
    config = {
        "tier_thresholds": {"exceptional": 5.0, "strong": 3.0, "good": 2.0},
        "watchlist": [],
    }
    state = {}
    plan = build_alert_plan(deals, config, state)
    assert len(plan["individual"]) == 1  # NRT exceptional
    assert plan["individual"][0]["deal"].destination == "NRT"
    assert len(plan["digest"]["strong"]) == 1
    assert len(plan["digest"]["good"]) == 1


def test_build_alert_plan_watchlist_sends_individually():
    """Watchlist hits send individually even if only 'good' tier."""
    deals = [
        AwardDeal("ATL", "NRT", "DL", "first", 80000, 2, "2026-05-15", "seats_aero", 2000.0),  # 2.5 CPM -> good
    ]
    config = {
        "tier_thresholds": {"exceptional": 5.0, "strong": 3.0, "good": 2.0},
        "watchlist": [{"destination": "NRT", "cabin": "first"}],
    }
    state = {}
    plan = build_alert_plan(deals, config, state)
    assert len(plan["individual"]) == 1
    assert plan["individual"][0]["watchlist_hit"] is True


def test_build_alert_plan_price_drop():
    """Price drops send individually."""
    deals = [
        AwardDeal("ATL", "NRT", "DL", "first", 70000, 2, "2026-05-15", "seats_aero", 8500.0),
    ]
    config = {
        "tier_thresholds": {"exceptional": 5.0, "strong": 3.0, "good": 2.0},
        "watchlist": [],
    }
    state = {
        "ATL-NRT-first-2026-05-15": {"alerted_at": "2026-03-01T10:00:00+00:00", "miles_price": 85000}
    }
    plan = build_alert_plan(deals, config, state)
    assert len(plan["price_drops"]) == 1
    assert plan["price_drops"][0]["previous_miles"] == 85000


def test_build_alert_plan_dedup_skips_known_deals():
    """Deals already in state (same price) should not appear in digest or individual."""
    deals = [
        AwardDeal("ATL", "NRT", "DL", "first", 85000, 2, "2026-05-15", "seats_aero", 8500.0),  # 10.0 CPM exceptional
    ]
    config = {
        "tier_thresholds": {"exceptional": 5.0, "strong": 3.0, "good": 2.0},
        "watchlist": [],
    }
    state = {
        "ATL-NRT-first-2026-05-15": {"alerted_at": "2026-03-01T10:00:00+00:00", "miles_price": 85000}
    }
    plan = build_alert_plan(deals, config, state)
    assert len(plan["individual"]) == 0
    assert len(plan["price_drops"]) == 0

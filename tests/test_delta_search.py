"""Tests for Delta award search scraper.

These tests mock Playwright interactions. Integration tests
require a real browser and are in tests/test_delta_integration.py.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sources.delta_search import (
    DeltaSearchSource,
    parse_award_results_from_data,
    INTERNATIONAL_DESTINATIONS,
)


def test_international_destinations_list():
    """Should have a curated list of ATL international destinations."""
    assert len(INTERNATIONAL_DESTINATIONS) >= 15
    assert "LHR" in INTERNATIONAL_DESTINATIONS
    assert "NRT" in INTERNATIONAL_DESTINATIONS
    assert "CDG" in INTERNATIONAL_DESTINATIONS


def test_parse_award_results_empty():
    """Empty data returns no deals."""
    deals = parse_award_results_from_data("ATL", "LHR", [])
    assert deals == []


def test_parse_award_results_sample():
    """Parse sample result data."""
    sample_data = [
        {
            "date": "2026-05-15",
            "cabin": "first",
            "miles": 85000,
            "seats": 2,
        }
    ]
    deals = parse_award_results_from_data("ATL", "NRT", sample_data)
    assert len(deals) == 1
    assert deals[0].miles_price == 85000
    assert deals[0].cabin == "first"
    assert deals[0].origin == "ATL"
    assert deals[0].destination == "NRT"
    assert deals[0].source == "delta_search"


def test_delta_search_source_implements_protocol():
    from sources.base import DealSource
    source = DeltaSearchSource()
    assert isinstance(source, DealSource)

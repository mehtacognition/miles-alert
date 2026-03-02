"""Tests for seats.aero API source."""
import json
import pytest
from unittest.mock import patch, MagicMock
from sources.seats_aero import SeatsAeroSource, CABIN_FIELDS


@pytest.fixture
def sample_config():
    return {
        "origin": "ATL",
        "phone": "+15551234567",
        "seats_aero_api_key": "pro_test_key_123",
        "cabins": ["first", "business"],
    }


@pytest.fixture
def sample_api_response():
    return {
        "data": [
            {
                "ID": "abc123",
                "Route": {
                    "OriginAirport": "ATL",
                    "DestinationAirport": "NRT",
                    "DestinationRegion": "Asia",
                    "Source": "delta",
                },
                "Date": "2026-05-15",
                "JAvailable": True,
                "FAvailable": True,
                "JMileageCost": "120000",
                "FMileageCost": "85000",
                "JRemainingSeats": 2,
                "FRemainingSeats": 1,
                "JAirlines": "DL",
                "FAirlines": "KE",
                "Source": "delta",
            },
            {
                "ID": "def456",
                "Route": {
                    "OriginAirport": "ATL",
                    "DestinationAirport": "LHR",
                    "DestinationRegion": "Europe",
                    "Source": "delta",
                },
                "Date": "2026-06-10",
                "JAvailable": True,
                "FAvailable": False,
                "JMileageCost": "75000",
                "FMileageCost": "0",
                "JRemainingSeats": 4,
                "FRemainingSeats": 0,
                "JAirlines": "DL,VS",
                "FAirlines": "",
                "Source": "delta",
            },
            {
                "ID": "ghi789",
                "Route": {
                    "OriginAirport": "ATL",
                    "DestinationAirport": "CDG",
                    "DestinationRegion": "Europe",
                    "Source": "delta",
                },
                "Date": "2026-07-01",
                "JAvailable": False,
                "FAvailable": False,
                "JMileageCost": "0",
                "FMileageCost": "0",
                "JRemainingSeats": 0,
                "FRemainingSeats": 0,
                "JAirlines": "",
                "FAirlines": "",
                "Source": "delta",
            },
        ],
        "count": 3,
        "hasMore": False,
    }


def test_seats_aero_implements_protocol():
    from sources.base import DealSource
    source = SeatsAeroSource()
    assert isinstance(source, DealSource)


def test_parse_response_extracts_deals(sample_api_response, sample_config):
    source = SeatsAeroSource()
    deals = source._parse_response(
        sample_api_response, "ATL", ["first", "business"]
    )

    # NRT: both first (85K) and business (120K) available
    # LHR: only business (75K) available
    # CDG: nothing available
    assert len(deals) == 3

    nrt_first = [d for d in deals if d.destination == "NRT" and d.cabin == "first"]
    assert len(nrt_first) == 1
    assert nrt_first[0].miles_price == 85000
    assert nrt_first[0].seats_available == 1
    assert nrt_first[0].airline == "KE"

    nrt_biz = [d for d in deals if d.destination == "NRT" and d.cabin == "business"]
    assert len(nrt_biz) == 1
    assert nrt_biz[0].miles_price == 120000
    assert nrt_biz[0].seats_available == 2

    lhr_biz = [d for d in deals if d.destination == "LHR" and d.cabin == "business"]
    assert len(lhr_biz) == 1
    assert lhr_biz[0].miles_price == 75000
    assert lhr_biz[0].seats_available == 4
    assert lhr_biz[0].airline == "DL"  # first airline from "DL,VS"


def test_parse_response_skips_unavailable(sample_api_response, sample_config):
    source = SeatsAeroSource()
    deals = source._parse_response(
        sample_api_response, "ATL", ["first", "business"]
    )

    # CDG has nothing available, LHR has no first
    cdg_deals = [d for d in deals if d.destination == "CDG"]
    assert len(cdg_deals) == 0

    lhr_first = [d for d in deals if d.destination == "LHR" and d.cabin == "first"]
    assert len(lhr_first) == 0


def test_no_api_key_returns_empty():
    source = SeatsAeroSource()
    config = {"origin": "ATL", "phone": "+15551234567"}
    deals = source.fetch_deals(config)
    assert deals == []


@patch("sources.seats_aero.urlopen")
def test_fetch_deals_calls_api(mock_urlopen, sample_config, sample_api_response):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(sample_api_response).encode()
    mock_resp.headers = {}
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_resp

    source = SeatsAeroSource()
    deals = source.fetch_deals(sample_config)

    assert len(deals) == 3
    mock_urlopen.assert_called_once()

    # Verify the request URL contains expected params
    call_args = mock_urlopen.call_args[0][0]
    assert "origin_airport=ATL" in call_args.full_url
    assert "sources=delta" in call_args.full_url
    assert call_args.headers["Partner-authorization"] == "pro_test_key_123"


@patch("sources.seats_aero.urlopen", side_effect=Exception("network error"))
def test_fetch_deals_handles_api_error(mock_urlopen, sample_config):
    source = SeatsAeroSource()
    deals = source.fetch_deals(sample_config)
    assert deals == []


def test_all_deals_have_source_seats_aero(sample_api_response):
    source = SeatsAeroSource()
    deals = source._parse_response(sample_api_response, "ATL", ["first", "business"])
    for deal in deals:
        assert deal.source == "seats_aero"

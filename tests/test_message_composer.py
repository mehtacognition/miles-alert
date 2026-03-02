"""Tests for alert message composition."""
from sources.base import AwardDeal
from message_composer import compose_alert


def test_compose_alert_with_cash_price():
    deal = AwardDeal(
        origin="ATL",
        destination="NRT",
        airline="DL",
        cabin="first",
        miles_price=80000,
        seats_available=2,
        departure_date="2026-05-15",
        source="delta_search",
        cash_price=8200.0,
    )
    msg = compose_alert(deal)
    assert "ATL" in msg
    assert "NRT" in msg
    assert "First Class" in msg
    assert "80,000" in msg
    assert "2 seats" in msg
    assert "$8,200" in msg
    assert "10.2" in msg  # cents per mile


def test_compose_alert_without_cash_price():
    deal = AwardDeal(
        origin="ATL",
        destination="LHR",
        airline="DL",
        cabin="business",
        miles_price=120000,
        seats_available=3,
        departure_date="2026-06-10",
        source="delta_search",
    )
    msg = compose_alert(deal)
    assert "ATL" in msg
    assert "LHR" in msg
    assert "Business" in msg
    assert "120,000" in msg
    assert "delta.com" in msg
    assert "$" not in msg

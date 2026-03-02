"""Tests for alert message composition."""
from sources.base import AwardDeal
from message_composer import compose_alert, compose_digest, compose_price_drop


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


def test_compose_alert_with_tier_exceptional():
    deal = AwardDeal(
        origin="ATL", destination="NRT", airline="DL", cabin="first",
        miles_price=80000, seats_available=2, departure_date="2026-05-15",
        source="seats_aero", cash_price=8000.0,
    )
    msg = compose_alert(deal, tier="exceptional")
    assert "EXCEPTIONAL" in msg


def test_compose_alert_with_watchlist():
    deal = AwardDeal(
        origin="ATL", destination="NRT", airline="DL", cabin="first",
        miles_price=80000, seats_available=2, departure_date="2026-05-15",
        source="seats_aero", cash_price=8000.0,
    )
    msg = compose_alert(deal, tier="exceptional", watchlist_hit=True)
    assert "EXCEPTIONAL" in msg
    assert "WATCHLIST" in msg


def test_compose_alert_with_watchlist_only():
    deal = AwardDeal(
        origin="ATL", destination="NRT", airline="DL", cabin="first",
        miles_price=80000, seats_available=2, departure_date="2026-05-15",
        source="seats_aero",
    )
    msg = compose_alert(deal, tier="good", watchlist_hit=True)
    assert "WATCHLIST HIT" in msg
    assert "EXCEPTIONAL" not in msg


def test_compose_alert_no_tier_backward_compat():
    """Calling compose_alert without tier should still work."""
    deal = AwardDeal(
        origin="ATL", destination="NRT", airline="DL", cabin="first",
        miles_price=80000, seats_available=2, departure_date="2026-05-15",
        source="seats_aero",
    )
    msg = compose_alert(deal)
    assert "ATL" in msg
    assert "NRT" in msg


def test_compose_digest():
    deals_by_tier = {
        "strong": [
            AwardDeal("ATL", "CDG", "DL", "business", 120000, 2, "2026-06-14", "seats_aero", 4800.0),
        ],
        "good": [
            AwardDeal("ATL", "FCO", "DL", "business", 95000, 3, "2026-08-03", "seats_aero", 2300.0),
        ],
        "no_cpm": [
            AwardDeal("ATL", "ICN", "DL", "first", 90000, 2, "2026-09-10", "seats_aero"),
        ],
    }
    msg = compose_digest(deals_by_tier, exceptional_count=1, watchlist_count=0)
    assert "Digest" in msg
    assert "STRONG" in msg
    assert "GOOD" in msg
    assert "No CPM" in msg
    assert "CDG" in msg
    assert "FCO" in msg
    assert "ICN" in msg
    assert "1" in msg  # exceptional count reference


def test_compose_digest_empty():
    """Empty digest should return None (no message to send)."""
    deals_by_tier = {"strong": [], "good": [], "no_cpm": []}
    result = compose_digest(deals_by_tier, exceptional_count=0, watchlist_count=0)
    assert result is None


def test_compose_price_drop():
    deal = AwardDeal(
        origin="ATL", destination="NRT", airline="DL", cabin="first",
        miles_price=70000, seats_available=2, departure_date="2026-05-15",
        source="seats_aero", cash_price=8500.0,
    )
    msg = compose_price_drop(deal, previous_miles=85000)
    assert "PRICE DROP" in msg
    assert "85,000" in msg
    assert "70,000" in msg
    assert "ATL" in msg
    assert "NRT" in msg


def test_compose_price_drop_no_cash_price():
    deal = AwardDeal(
        origin="ATL", destination="NRT", airline="DL", cabin="first",
        miles_price=70000, seats_available=2, departure_date="2026-05-15",
        source="seats_aero",
    )
    msg = compose_price_drop(deal, previous_miles=85000)
    assert "PRICE DROP" in msg
    assert "$" not in msg

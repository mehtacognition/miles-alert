# Smarter Alerts + Deal Radar — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deal quality tiers, daily digest, route watchlist, price drop re-alerts, and update schedule to noon/8pm.

**Architecture:** Tier classification happens after enrichment, before sending. The main `run()` loop becomes: fetch → enrich → filter → classify tiers → check watchlist → detect price drops → batch into digest vs individual alerts → send. State format extends from `{key: timestamp}` to `{key: {alerted_at, miles_price}}` with backward-compat migration.

**Tech Stack:** Pure Python, no new dependencies. pytest for tests.

---

### Task 1: Extend State Format in config.py

**Files:**
- Modify: `config.py:49-65` (load_state, save_state)
- Test: `tests/test_config.py`

**Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_load_state_new_format(tmp_config_dir):
    """New state format with miles_price should load correctly."""
    state_file = tmp_config_dir / "sent_alerts.json"
    state_file.write_text(json.dumps({
        "ATL-NRT-first-2026-05-15": {
            "alerted_at": "2026-03-01T10:00:00+00:00",
            "miles_price": 85000
        }
    }))
    state = load_state()
    assert "ATL-NRT-first-2026-05-15" in state
    entry = state["ATL-NRT-first-2026-05-15"]
    assert entry["alerted_at"] == "2026-03-01T10:00:00+00:00"
    assert entry["miles_price"] == 85000


def test_load_state_migrates_old_format(tmp_config_dir):
    """Old state format (plain timestamp string) should migrate to new format."""
    state_file = tmp_config_dir / "sent_alerts.json"
    state_file.write_text(json.dumps({
        "ATL-NRT-first-2026-05-15": "2026-03-01T10:00:00+00:00"
    }))
    state = load_state()
    entry = state["ATL-NRT-first-2026-05-15"]
    assert entry["alerted_at"] == "2026-03-01T10:00:00+00:00"
    assert entry["miles_price"] is None


def test_load_state_prunes_old_entries_new_format(tmp_config_dir):
    """Pruning should work with new state format."""
    state_file = tmp_config_dir / "sent_alerts.json"
    state_file.write_text(json.dumps({
        "old-deal": {"alerted_at": "2025-01-01T00:00:00+00:00", "miles_price": 80000},
        "recent-deal": {"alerted_at": "2026-02-28T00:00:00+00:00", "miles_price": 90000},
    }))
    state = load_state()
    assert "old-deal" not in state
    assert "recent-deal" in state
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && source venv/bin/activate && python -m pytest tests/test_config.py -v -k "new_format or migrates_old or prunes_old_entries_new"`

Expected: FAIL — old `load_state` returns plain strings, not dicts.

**Step 3: Implement state format migration**

Update `load_state()` in `config.py` to handle both formats:

```python
def load_state():
    """Load sent alert state. Prunes entries older than STATE_PRUNE_DAYS.

    State format: {dedup_key: {"alerted_at": iso_timestamp, "miles_price": int|None}}
    Migrates old format (plain timestamp string) automatically.
    """
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE) as f:
        data = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=STATE_PRUNE_DAYS)
    pruned = {}
    for key, value in data.items():
        # Migrate old format: plain timestamp string -> new dict format
        if isinstance(value, str):
            value = {"alerted_at": value, "miles_price": None}
        elif value is None:
            value = {"alerted_at": None, "miles_price": None}

        ts = value.get("alerted_at")
        if ts is None:
            pruned[key] = value
        else:
            alert_time = datetime.fromisoformat(ts)
            if alert_time > cutoff:
                pruned[key] = value
    return pruned
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_config.py -v`

Expected: ALL PASS. Existing tests should also pass since old format gets migrated.

**Step 5: Add config defaults for tier_thresholds and watchlist**

Update `load_config()` in `config.py` — add these two lines after the existing `setdefault` calls:

```python
    config.setdefault("tier_thresholds", {"exceptional": 5.0, "strong": 3.0, "good": 2.0})
    config.setdefault("watchlist", [])
```

**Step 6: Write test for new config defaults**

Add to `tests/test_config.py`:

```python
def test_load_config_defaults_tier_thresholds(tmp_config_dir):
    """Config should have tier_thresholds defaults."""
    config_file = tmp_config_dir / "config.json"
    config_file.write_text(json.dumps({
        "origin": "ATL",
        "phones": ["+15551234567"],
    }))
    config = load_config()
    assert config["tier_thresholds"] == {"exceptional": 5.0, "strong": 3.0, "good": 2.0}
    assert config["watchlist"] == []
```

**Step 7: Run all config tests**

Run: `cd ~/miles-alert && python -m pytest tests/test_config.py -v`

Expected: ALL PASS.

**Step 8: Commit**

```bash
cd ~/miles-alert && git add config.py tests/test_config.py && git commit -m "feat: extend state format with miles_price and add tier/watchlist config defaults"
```

---

### Task 2: Deal Tier Classification

**Files:**
- Modify: `miles_alert.py` (add `classify_tier` function)
- Test: `tests/test_miles_alert.py`

**Step 1: Write the failing tests**

Add to `tests/test_miles_alert.py`:

```python
from miles_alert import classify_tier


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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v -k "classify_tier"`

Expected: FAIL — `classify_tier` does not exist.

**Step 3: Implement classify_tier**

Add to `miles_alert.py`:

```python
def classify_tier(deal: AwardDeal, thresholds: dict) -> str:
    """Classify a deal into a quality tier based on cents-per-mile.

    Returns: "exceptional", "strong", or "good".
    Deals without CPM data default to "strong".
    """
    cpm = deal.cents_per_mile
    if cpm is None:
        return "strong"
    if cpm >= thresholds["exceptional"]:
        return "exceptional"
    if cpm >= thresholds["strong"]:
        return "strong"
    return "good"
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v -k "classify_tier"`

Expected: ALL PASS.

**Step 5: Commit**

```bash
cd ~/miles-alert && git add miles_alert.py tests/test_miles_alert.py && git commit -m "feat: add deal quality tier classification"
```

---

### Task 3: Watchlist Matching

**Files:**
- Modify: `miles_alert.py` (add `is_watchlist_match` function)
- Test: `tests/test_miles_alert.py`

**Step 1: Write the failing tests**

Add to `tests/test_miles_alert.py`:

```python
from miles_alert import is_watchlist_match


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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v -k "watchlist"`

Expected: FAIL — `is_watchlist_match` does not exist.

**Step 3: Implement is_watchlist_match**

Add to `miles_alert.py`:

```python
def is_watchlist_match(deal: AwardDeal, watchlist: list[dict]) -> bool:
    """Check if a deal matches any entry in the route watchlist."""
    for entry in watchlist:
        if deal.destination == entry["destination"] and deal.cabin == entry["cabin"]:
            return True
    return False
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v -k "watchlist"`

Expected: ALL PASS.

**Step 5: Commit**

```bash
cd ~/miles-alert && git add miles_alert.py tests/test_miles_alert.py && git commit -m "feat: add route watchlist matching"
```

---

### Task 4: Price Drop Detection

**Files:**
- Modify: `miles_alert.py` (add `detect_price_drop` function)
- Test: `tests/test_miles_alert.py`

**Step 1: Write the failing tests**

Add to `tests/test_miles_alert.py`:

```python
from miles_alert import detect_price_drop


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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v -k "price_drop"`

Expected: FAIL — `detect_price_drop` does not exist.

**Step 3: Implement detect_price_drop**

Add to `miles_alert.py`:

```python
def detect_price_drop(deal: AwardDeal, state: dict) -> int | None:
    """Check if a deal's miles price dropped since last alert.

    Returns the previous miles price if a drop is detected, None otherwise.
    """
    entry = state.get(deal.dedup_key)
    if entry is None:
        return None
    prev_price = entry.get("miles_price")
    if prev_price is None:
        return None
    if deal.miles_price < prev_price:
        return prev_price
    return None
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v -k "price_drop"`

Expected: ALL PASS.

**Step 5: Commit**

```bash
cd ~/miles-alert && git add miles_alert.py tests/test_miles_alert.py && git commit -m "feat: add price drop detection"
```

---

### Task 5: Message Composer — Tier Labels, Digest, and Price Drop

**Files:**
- Modify: `message_composer.py`
- Test: `tests/test_message_composer.py`

**Step 1: Write the failing tests**

Add to `tests/test_message_composer.py`:

```python
from message_composer import compose_alert, compose_digest, compose_price_drop


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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_message_composer.py -v`

Expected: FAIL — `compose_digest`, `compose_price_drop` don't exist; `compose_alert` doesn't accept `tier`/`watchlist_hit` params.

**Step 3: Implement updated message_composer.py**

Replace `message_composer.py` with:

```python
"""Compose iMessage alert text for award deals."""
from datetime import datetime
from sources.base import AwardDeal

CABIN_DISPLAY = {
    "first": "First Class",
    "business": "Business / Delta One",
}


def compose_alert(deal: AwardDeal, tier: str | None = None, watchlist_hit: bool = False) -> str:
    """Format an award deal as a readable iMessage alert."""
    # Build header label
    labels = []
    if tier == "exceptional":
        labels.append("\u2b50 EXCEPTIONAL")
    if watchlist_hit:
        labels.append("\ud83c\udfaf WATCHLIST HIT" if not labels else "\ud83c\udfaf WATCHLIST")

    if labels:
        header = " + ".join(labels) + " \u2014 Delta Miles Deal"
    else:
        header = "Delta Miles Deal Alert"

    cabin_name = CABIN_DISPLAY.get(deal.cabin, deal.cabin.title())
    miles_fmt = f"{deal.miles_price:,}"

    lines = [
        header,
        f"{deal.origin} \u2192 {deal.destination} - {cabin_name}",
        f"{miles_fmt} miles \u00d7 {deal.seats_available} seats",
    ]

    if deal.cash_price is not None and deal.cents_per_mile is not None:
        cash_fmt = f"${deal.cash_price:,.0f}"
        cpm = f"{deal.cents_per_mile:.1f}"
        lines.append(f"Cash price: {cash_fmt} = {cpm} cents/mile")

    lines.append(f"Date: {deal.departure_date}")
    lines.append(f"Book: delta.com")

    return "\n".join(lines)


def _format_deal_line(deal: AwardDeal) -> str:
    """Format a single deal as a compact one-liner for the digest."""
    cabin_short = {"first": "First", "business": "Biz"}.get(deal.cabin, deal.cabin)
    miles_fmt = f"{deal.miles_price // 1000}K"
    cpm_str = f" | {deal.cents_per_mile:.1f} CPM" if deal.cents_per_mile is not None else ""
    return (
        f"\u2022 {deal.origin}\u2192{deal.destination} {cabin_short} "
        f"{miles_fmt} mi \u00d7 {deal.seats_available} seats"
        f"{cpm_str} | {deal.departure_date}"
    )


def compose_digest(
    deals_by_tier: dict[str, list[AwardDeal]],
    exceptional_count: int,
    watchlist_count: int,
) -> str | None:
    """Compose a daily digest message grouping deals by tier.

    Returns None if there are no deals to include in the digest.
    """
    strong = deals_by_tier.get("strong", [])
    good = deals_by_tier.get("good", [])
    no_cpm = deals_by_tier.get("no_cpm", [])

    total = len(strong) + len(good) + len(no_cpm)
    if total == 0:
        return None

    now = datetime.now().strftime("%b %-d, %-I:%M %p")
    summary_parts = []
    if exceptional_count:
        summary_parts.append(f"{exceptional_count} \u2b50 Exceptional sent separately")
    if watchlist_count:
        summary_parts.append(f"{watchlist_count} \ud83c\udfaf Watchlist sent separately")
    summary_extra = f" ({', '.join(summary_parts)})" if summary_parts else ""

    lines = [
        f"Delta Miles Digest \u2014 {now}",
        f"{total + exceptional_count + watchlist_count} deals found{summary_extra}",
    ]

    if strong:
        lines.append("")
        lines.append("STRONG (3.0+ CPM):")
        for deal in strong:
            lines.append(_format_deal_line(deal))

    if good:
        lines.append("")
        lines.append("GOOD (2.0+ CPM):")
        for deal in good:
            lines.append(_format_deal_line(deal))

    if no_cpm:
        lines.append("")
        lines.append("No CPM available:")
        for deal in no_cpm:
            lines.append(_format_deal_line(deal))

    return "\n".join(lines)


def compose_price_drop(deal: AwardDeal, previous_miles: int) -> str:
    """Format a price drop alert."""
    cabin_name = CABIN_DISPLAY.get(deal.cabin, deal.cabin.title())
    prev_fmt = f"{previous_miles:,}"
    now_fmt = f"{deal.miles_price:,}"

    lines = [
        f"\ud83d\udcc9 PRICE DROP \u2014 Delta Miles Deal",
        f"{deal.origin} \u2192 {deal.destination} - {cabin_name}",
        f"Was: {prev_fmt} miles \u2192 Now: {now_fmt} miles",
    ]

    if deal.cash_price is not None and deal.cents_per_mile is not None:
        cash_fmt = f"${deal.cash_price:,.0f}"
        cpm = f"{deal.cents_per_mile:.1f}"
        lines.append(f"Cash price: {cash_fmt} = {cpm} cents/mile")

    lines.append(f"{deal.seats_available} seats | Date: {deal.departure_date}")
    lines.append(f"Book: delta.com")

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_message_composer.py -v`

Expected: ALL PASS.

**Step 5: Commit**

```bash
cd ~/miles-alert && git add message_composer.py tests/test_message_composer.py && git commit -m "feat: add tier labels, digest format, and price drop messages"
```

---

### Task 6: Restructure run() Loop

**Files:**
- Modify: `miles_alert.py` (rewrite `run()`)
- Test: `tests/test_miles_alert.py`

**Step 1: Write integration-level tests for the new run loop**

Add to `tests/test_miles_alert.py`:

```python
from miles_alert import classify_tier, is_watchlist_match, detect_price_drop, build_alert_plan


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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v -k "build_alert_plan"`

Expected: FAIL — `build_alert_plan` does not exist.

**Step 3: Implement build_alert_plan and restructured run()**

Add `build_alert_plan` to `miles_alert.py`:

```python
def build_alert_plan(deals: list[AwardDeal], config: dict, state: dict) -> dict:
    """Classify deals and build an alert plan.

    Returns dict with keys:
        individual: list of {"deal": AwardDeal, "tier": str, "watchlist_hit": bool}
        digest: {"strong": [...], "good": [...], "no_cpm": [...]}
        price_drops: list of {"deal": AwardDeal, "previous_miles": int}
    """
    thresholds = config["tier_thresholds"]
    watchlist = config.get("watchlist", [])

    individual = []
    digest = {"strong": [], "good": [], "no_cpm": []}
    price_drops = []

    for deal in deals:
        # Check for price drop first (applies to already-seen deals)
        prev_price = detect_price_drop(deal, state)
        if prev_price is not None:
            price_drops.append({"deal": deal, "previous_miles": prev_price})
            continue

        # Skip already-alerted deals
        if deal.dedup_key in state:
            continue

        tier = classify_tier(deal, thresholds)
        watchlist_hit = is_watchlist_match(deal, watchlist)

        # Exceptional or watchlist hits send individually
        if tier == "exceptional" or watchlist_hit:
            individual.append({"deal": deal, "tier": tier, "watchlist_hit": watchlist_hit})
        else:
            # Bucket into digest by tier
            if deal.cents_per_mile is None:
                digest["no_cpm"].append(deal)
            elif tier == "strong":
                digest["strong"].append(deal)
            else:
                digest["good"].append(deal)

    return {"individual": individual, "digest": digest, "price_drops": price_drops}
```

Then update `run()` to use the new plan:

```python
def run():
    """Main run loop."""
    setup_logging()
    logging.info("Starting miles alert...")

    config = {}
    try:
        config = load_config()
        state = load_state()

        sources = get_sources(config)
        all_deals = []
        for source in sources:
            try:
                deals = source.fetch_deals(config)
                all_deals.extend(deals)
            except Exception as e:
                logging.error(f"Source {type(source).__name__} failed: {e}")

        logging.info(f"Found {len(all_deals)} raw deals")

        enriched = []
        for deal in all_deals:
            enriched.append(enrich_with_cash_price(deal))

        filtered = filter_deals(enriched, config)
        logging.info(f"{len(filtered)} deals pass filters")

        plan = build_alert_plan(filtered, config, state)

        new_alerts = 0

        # Send individual alerts (exceptional + watchlist)
        for item in plan["individual"]:
            deal = item["deal"]
            try:
                message = compose_alert(deal, tier=item["tier"], watchlist_hit=item["watchlist_hit"])
                _send_to_all(config, message)
                state[deal.dedup_key] = {
                    "alerted_at": datetime.now(timezone.utc).isoformat(),
                    "miles_price": deal.miles_price,
                }
                save_state(state)
                new_alerts += 1
                logging.info(f"Individual alert: {deal.dedup_key} (tier={item['tier']}, watchlist={item['watchlist_hit']})")
            except Exception as e:
                logging.error(f"Failed to send alert for {deal.dedup_key}: {e}")
                _notify_error(config, f"Miles Alert: failed to send alert. Check logs.")

        # Send price drop alerts
        for item in plan["price_drops"]:
            deal = item["deal"]
            try:
                message = compose_price_drop(deal, previous_miles=item["previous_miles"])
                _send_to_all(config, message)
                state[deal.dedup_key] = {
                    "alerted_at": datetime.now(timezone.utc).isoformat(),
                    "miles_price": deal.miles_price,
                }
                save_state(state)
                new_alerts += 1
                logging.info(f"Price drop alert: {deal.dedup_key}")
            except Exception as e:
                logging.error(f"Failed to send price drop for {deal.dedup_key}: {e}")
                _notify_error(config, f"Miles Alert: failed to send alert. Check logs.")

        # Send digest
        digest_msg = compose_digest(
            plan["digest"],
            exceptional_count=len(plan["individual"]),
            watchlist_count=sum(1 for i in plan["individual"] if i["watchlist_hit"]),
        )
        if digest_msg:
            try:
                _send_to_all(config, digest_msg)
                # Mark digest deals as alerted
                for tier_deals in plan["digest"].values():
                    for deal in tier_deals:
                        state[deal.dedup_key] = {
                            "alerted_at": datetime.now(timezone.utc).isoformat(),
                            "miles_price": deal.miles_price,
                        }
                save_state(state)
                digest_count = sum(len(v) for v in plan["digest"].values())
                new_alerts += digest_count
                logging.info(f"Digest sent with {digest_count} deals")
            except Exception as e:
                logging.error(f"Failed to send digest: {e}")
                _notify_error(config, f"Miles Alert: failed to send digest. Check logs.")

        logging.info(f"Miles alert complete. {new_alerts} new alerts sent.")

    except Exception as e:
        logging.error(f"Miles alert failed: {e}", exc_info=True)
        now_local = datetime.now().strftime("%-I:%M %p")
        _notify_error(config, f"Miles Alert failed at {now_local}. Check logs.")
        raise
```

Also update the imports at the top of `miles_alert.py`:

```python
from message_composer import compose_alert, compose_digest, compose_price_drop
```

**Step 4: Run all tests**

Run: `cd ~/miles-alert && python -m pytest tests/ -v`

Expected: ALL PASS.

**Step 5: Commit**

```bash
cd ~/miles-alert && git add miles_alert.py tests/test_miles_alert.py && git commit -m "feat: restructure run loop with alert plan, digest, and price drops"
```

---

### Task 7: Update config.example.json and Launchd Plist

**Files:**
- Modify: `config.example.json`
- Modify: `com.milesalert.daily.plist`

**Step 1: Update config.example.json**

Replace contents with:

```json
{
  "origin": "ATL",
  "phones": ["+1XXXXXXXXXX", "+1YYYYYYYYYY"],
  "min_cents_per_mile": 2.0,
  "min_seats": 2,
  "cabins": ["first", "business"],
  "sources": ["seats_aero"],
  "seats_aero_api_key": "pro_YOUR_API_KEY_HERE",
  "excluded_destinations": [],
  "watchlist": [
    {"destination": "NRT", "cabin": "first"}
  ],
  "tier_thresholds": {
    "exceptional": 5.0,
    "strong": 3.0,
    "good": 2.0
  }
}
```

**Step 2: Update plist schedule to noon and 8 PM**

In `com.milesalert.daily.plist`, change the `StartCalendarInterval` entries:
- First entry: Hour 12, Minute 0
- Second entry: Hour 20, Minute 0

**Step 3: Run full test suite**

Run: `cd ~/miles-alert && python -m pytest tests/ -v`

Expected: ALL PASS (no test changes, just config/plist).

**Step 4: Commit**

```bash
cd ~/miles-alert && git add config.example.json com.milesalert.daily.plist && git commit -m "chore: update config example with watchlist/tiers, change schedule to noon and 8pm"
```

---

### Task 8: Final Integration Verification

**Step 1: Run full test suite**

Run: `cd ~/miles-alert && python -m pytest tests/ -v --tb=short`

Expected: ALL PASS.

**Step 2: Verify no import errors**

Run: `cd ~/miles-alert && python -c "from miles_alert import run, classify_tier, is_watchlist_match, detect_price_drop, build_alert_plan; print('All imports OK')"`

Expected: `All imports OK`

**Step 3: Commit any remaining changes**

If any fixups needed, commit them. Otherwise this is a verification-only step.

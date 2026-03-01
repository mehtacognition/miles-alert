# Miles Alert Agent — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated agent that monitors Delta SkyMiles award availability from ATL to international destinations, calculates cents-per-mile value, and sends iMessage alerts for high-value first class / Delta One deals.

**Architecture:** Pluggable data source pattern — Phase 1 uses Playwright to scrape delta.com award search; Phase 2 adds seats.aero API. Google Flights enrichment via fast_flights for cash price comparison. Same scheduling/notification pattern as flight-texter.

**Tech Stack:** Python 3.12+, Playwright (playwright-stealth), fast_flights, launchd, iMessage via AppleScript

---

### Task 1: Project Scaffold and Config Module

**Files:**
- Create: `~/miles-alert/config.py`
- Create: `~/miles-alert/tests/test_config.py`
- Create: `~/miles-alert/requirements.txt`

**Step 1: Create requirements.txt**

```
playwright
fast-flights
pytest
```

**Step 2: Write the failing tests for config module**

```python
"""Tests for config loading and state management."""
import json
import pytest
from pathlib import Path
from config import (
    load_config,
    load_state,
    save_state,
    ensure_config_dir,
    CONFIG_DIR,
)


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch):
    """Redirect config dir to temp path."""
    monkeypatch.setattr("config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr("config.STATE_FILE", tmp_path / "sent_alerts.json")
    monkeypatch.setattr("config.LOG_DIR", tmp_path / "logs")
    return tmp_path


def test_load_config_missing_file(tmp_config_dir):
    with pytest.raises(FileNotFoundError):
        load_config()


def test_load_config_valid(tmp_config_dir):
    config_file = tmp_config_dir / "config.json"
    config_file.write_text(json.dumps({
        "origin": "ATL",
        "phone": "+15551234567",
        "min_cents_per_mile": 2.0,
        "min_seats": 2,
        "cabins": ["first", "business"],
        "sources": ["delta_search"],
    }))
    config = load_config()
    assert config["origin"] == "ATL"
    assert config["min_cents_per_mile"] == 2.0


def test_load_config_missing_required_field(tmp_config_dir):
    config_file = tmp_config_dir / "config.json"
    config_file.write_text(json.dumps({"origin": "ATL"}))
    with pytest.raises(ValueError, match="phone"):
        load_config()


def test_load_state_empty(tmp_config_dir):
    state = load_state()
    assert state == {}


def test_load_state_valid(tmp_config_dir):
    state_file = tmp_config_dir / "sent_alerts.json"
    state_file.write_text(json.dumps({
        "ATL-NRT-first-2026-05-15": "2026-03-01T10:00:00+00:00"
    }))
    state = load_state()
    assert "ATL-NRT-first-2026-05-15" in state


def test_load_state_prunes_old_entries(tmp_config_dir):
    state_file = tmp_config_dir / "sent_alerts.json"
    state_file.write_text(json.dumps({
        "old-deal": "2025-01-01T00:00:00+00:00",
        "recent-deal": "2026-02-28T00:00:00+00:00",
    }))
    state = load_state()
    assert "old-deal" not in state
    assert "recent-deal" in state


def test_save_state(tmp_config_dir):
    save_state({"deal-1": "2026-03-01T10:00:00+00:00"})
    state_file = tmp_config_dir / "sent_alerts.json"
    data = json.loads(state_file.read_text())
    assert "deal-1" in data


def test_ensure_config_dir(tmp_config_dir):
    log_dir = tmp_config_dir / "logs"
    ensure_config_dir()
    assert log_dir.exists()
```

**Step 3: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_config.py -v`
Expected: FAIL — config module not found

**Step 4: Implement config.py**

```python
"""Configuration and state management for miles-alert."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "miles-alert"
CONFIG_FILE = CONFIG_DIR / "config.json"
STATE_FILE = CONFIG_DIR / "sent_alerts.json"
LOG_DIR = CONFIG_DIR / "logs"

REQUIRED_FIELDS = ["origin", "phone"]
STATE_PRUNE_DAYS = 14


def ensure_config_dir():
    """Create config and log directories if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    """Load configuration from JSON file.

    Required fields: origin, phone
    Optional: min_cents_per_mile (2.0), min_seats (2),
              cabins (["first", "business"]),
              sources (["delta_search"]),
              seats_aero_api_key (null),
              excluded_destinations ([])
    """
    ensure_config_dir()
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Config not found at {CONFIG_FILE}\n"
            f"Create it with at least: origin, phone"
        )
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    for field in REQUIRED_FIELDS:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")

    # Defaults
    config.setdefault("min_cents_per_mile", 2.0)
    config.setdefault("min_seats", 2)
    config.setdefault("cabins", ["first", "business"])
    config.setdefault("sources", ["delta_search"])
    config.setdefault("seats_aero_api_key", None)
    config.setdefault("excluded_destinations", [])
    return config


def load_state():
    """Load sent alert state. Prunes entries older than STATE_PRUNE_DAYS."""
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE) as f:
        data = json.load(f)

    cutoff = datetime.now(timezone.utc) - timedelta(days=STATE_PRUNE_DAYS)
    pruned = {}
    for key, ts in data.items():
        if ts is None:
            pruned[key] = ts
        else:
            alert_time = datetime.fromisoformat(ts)
            if alert_time > cutoff:
                pruned[key] = ts
    return pruned


def save_state(state):
    """Save alert state to disk."""
    ensure_config_dir()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
```

**Step 5: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_config.py -v`
Expected: All 8 tests PASS

**Step 6: Commit**

```bash
cd ~/miles-alert && git init
git add config.py tests/test_config.py requirements.txt
git commit -m "feat: add config and state management module"
```

---

### Task 2: Data Model and Source Interface

**Files:**
- Create: `~/miles-alert/sources/__init__.py`
- Create: `~/miles-alert/sources/base.py`
- Create: `~/miles-alert/tests/test_base.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_base.py -v`
Expected: FAIL — sources.base not found

**Step 3: Implement sources/base.py**

```python
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
```

**Step 4: Create `~/miles-alert/sources/__init__.py`**

```python
```

(empty file)

**Step 5: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_base.py -v`
Expected: All 4 tests PASS

**Step 6: Commit**

```bash
git add sources/ tests/test_base.py
git commit -m "feat: add AwardDeal data model and DealSource protocol"
```

---

### Task 3: iMessage Module

**Files:**
- Create: `~/miles-alert/imessage.py`
- Create: `~/miles-alert/tests/test_imessage.py`

**Step 1: Write the failing tests**

```python
"""Tests for iMessage sending."""
from unittest.mock import patch, MagicMock
import pytest
from imessage import send_imessage


@patch("imessage.subprocess.run")
def test_send_imessage_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    result = send_imessage("+15551234567", "Test message")
    assert result is True
    mock_run.assert_called_once()


@patch("imessage.subprocess.run")
def test_send_imessage_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stderr="AppleScript error")
    with pytest.raises(RuntimeError, match="Failed to send"):
        send_imessage("+15551234567", "Test message")


@patch("imessage.subprocess.run")
def test_send_imessage_escapes_quotes(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    send_imessage("+15551234567", 'Message with "quotes"')
    call_args = mock_run.call_args[0][0]
    # The AppleScript string should have escaped quotes
    script = call_args[2]  # osascript -e <script>
    assert '\\"' in script or "quotes" in script
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_imessage.py -v`
Expected: FAIL — imessage module not found

**Step 3: Implement imessage.py**

```python
"""Send iMessages via AppleScript."""
import subprocess


def send_imessage(phone_number: str, message: str) -> bool:
    """Send an iMessage to the given phone number.

    Raises RuntimeError if sending fails.
    """
    escaped_message = message.replace('"', '\\"')
    escaped_phone = phone_number.replace('"', '\\"')

    applescript = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{escaped_phone}" of targetService
        send "{escaped_message}" to targetBuddy
    end tell
    '''

    result = subprocess.run(
        ["osascript", "-e", applescript],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to send iMessage: {result.stderr}")

    return True
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_imessage.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add imessage.py tests/test_imessage.py
git commit -m "feat: add iMessage sending module"
```

---

### Task 4: Message Composer

**Files:**
- Create: `~/miles-alert/message_composer.py`
- Create: `~/miles-alert/tests/test_message_composer.py`

**Step 1: Write the failing tests**

```python
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
    # No cash price info
    assert "$" not in msg
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_message_composer.py -v`
Expected: FAIL

**Step 3: Implement message_composer.py**

```python
"""Compose iMessage alert text for award deals."""
from sources.base import AwardDeal

CABIN_DISPLAY = {
    "first": "First Class",
    "business": "Business / Delta One",
}


def compose_alert(deal: AwardDeal) -> str:
    """Format an award deal as a readable iMessage alert."""
    cabin_name = CABIN_DISPLAY.get(deal.cabin, deal.cabin.title())
    miles_fmt = f"{deal.miles_price:,}"

    lines = [
        f"Delta Miles Deal Alert",
        f"{deal.origin} -> {deal.destination} - {cabin_name}",
        f"{miles_fmt} miles x {deal.seats_available} seats",
    ]

    if deal.cash_price is not None and deal.cents_per_mile is not None:
        cash_fmt = f"${deal.cash_price:,.0f}"
        cpm = f"{deal.cents_per_mile:.1f}"
        lines.append(f"Cash price: {cash_fmt} = {cpm} cents/mile")

    lines.append(f"Date: {deal.departure_date}")
    lines.append(f"Book: delta.com")

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_message_composer.py -v`
Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add message_composer.py tests/test_message_composer.py
git commit -m "feat: add alert message composer"
```

---

### Task 5: Delta Award Search Scraper (Playwright)

**Files:**
- Create: `~/miles-alert/sources/delta_search.py`
- Create: `~/miles-alert/tests/test_delta_search.py`

This is the most complex task. We use Playwright to:
1. Navigate to delta.com flexible date search
2. Toggle "Shop with Miles"
3. Search each target route from ATL
4. Parse results for first/business availability

**Step 1: Write the failing tests**

```python
"""Tests for Delta award search scraper.

These tests mock Playwright interactions. Integration tests
require a real browser and are in tests/test_delta_integration.py.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sources.delta_search import (
    DeltaSearchSource,
    parse_award_results,
    INTERNATIONAL_DESTINATIONS,
)


def test_international_destinations_list():
    """Should have a curated list of ATL international destinations."""
    assert len(INTERNATIONAL_DESTINATIONS) >= 15
    assert "LHR" in INTERNATIONAL_DESTINATIONS
    assert "NRT" in INTERNATIONAL_DESTINATIONS
    assert "CDG" in INTERNATIONAL_DESTINATIONS


def test_parse_award_results_empty():
    """Empty HTML returns no deals."""
    deals = parse_award_results("ATL", "LHR", "")
    assert deals == []


def test_parse_award_results_sample():
    """Parse a sample result structure.

    Note: The exact HTML structure must be verified against delta.com
    and this test updated accordingly during implementation.
    """
    # This test will be refined once we capture real delta.com HTML
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


def test_delta_search_source_implements_protocol():
    from sources.base import DealSource
    source = DeltaSearchSource()
    assert isinstance(source, DealSource)
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_delta_search.py -v`
Expected: FAIL

**Step 3: Implement sources/delta_search.py**

```python
"""Delta.com award search scraper using Playwright.

Searches delta.com with "Shop with Miles" enabled for international
routes from the configured origin airport. Parses first class and
business class award availability.

IMPORTANT: This scraper is for personal use only. It rate-limits
itself to avoid overloading delta.com (5-10 second delays between
searches). Running more than 3x/day is not recommended.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass

from sources.base import AwardDeal

logger = logging.getLogger(__name__)

# Top international destinations from ATL with Delta service
INTERNATIONAL_DESTINATIONS = [
    "LHR",  # London
    "CDG",  # Paris
    "FCO",  # Rome
    "AMS",  # Amsterdam
    "FRA",  # Frankfurt
    "BCN",  # Barcelona
    "MAD",  # Madrid
    "NRT",  # Tokyo Narita
    "HND",  # Tokyo Haneda
    "ICN",  # Seoul
    "CUN",  # Cancun
    "SJU",  # San Juan
    "BOG",  # Bogota
    "LIM",  # Lima
    "GRU",  # Sao Paulo
    "EZE",  # Buenos Aires
    "DUB",  # Dublin
    "MXP",  # Milan
    "ATH",  # Athens
    "SYD",  # Sydney (via partner)
]


def parse_award_results_from_data(
    origin: str, destination: str, results: list[dict]
) -> list[AwardDeal]:
    """Convert parsed result dicts into AwardDeal objects."""
    deals = []
    for r in results:
        deals.append(
            AwardDeal(
                origin=origin,
                destination=destination,
                airline="DL",
                cabin=r["cabin"],
                miles_price=r["miles"],
                seats_available=r.get("seats", 1),
                departure_date=r["date"],
                source="delta_search",
            )
        )
    return deals


def parse_award_results(
    origin: str, destination: str, page_content: str
) -> list[AwardDeal]:
    """Parse delta.com search results HTML for award availability.

    This function must be updated if Delta changes their page structure.
    Returns empty list if parsing fails.
    """
    # NOTE: The exact selectors and parsing logic must be determined
    # by inspecting delta.com's actual award search results page.
    # This is a placeholder that will be filled during integration testing.
    #
    # Expected structure (to be verified):
    # - Calendar/list view shows dates with mileage prices
    # - Each result has cabin class, miles required, seats
    # - "Shop with Miles" toggle changes price display
    if not page_content:
        return []

    logger.warning(
        "parse_award_results needs real delta.com HTML structure. "
        "Run integration test to capture and update selectors."
    )
    return []


class DeltaSearchSource:
    """Scrapes delta.com award search using Playwright."""

    def fetch_deals(self, config: dict) -> list[AwardDeal]:
        """Search delta.com for award availability on all target routes."""
        return asyncio.run(self._fetch_deals_async(config))

    async def _fetch_deals_async(self, config: dict) -> list[AwardDeal]:
        """Async implementation of award search."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        origin = config["origin"]
        cabins = config.get("cabins", ["first", "business"])
        excluded = set(config.get("excluded_destinations", []))
        destinations = [d for d in INTERNATIONAL_DESTINATIONS if d not in excluded]

        all_deals = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            for dest in destinations:
                try:
                    logger.info(f"Searching {origin} -> {dest}...")
                    deals = await self._search_route(page, origin, dest, cabins)
                    all_deals.extend(deals)

                    # Rate limit: random 5-10 second delay
                    delay = random.uniform(5, 10)
                    logger.debug(f"Waiting {delay:.1f}s before next search")
                    await asyncio.sleep(delay)

                except Exception as e:
                    logger.warning(f"Failed to search {origin}->{dest}: {e}")
                    continue

            await browser.close()

        logger.info(f"Found {len(all_deals)} total deals across {len(destinations)} routes")
        return all_deals

    async def _search_route(
        self, page, origin: str, destination: str, cabins: list[str]
    ) -> list[AwardDeal]:
        """Search a single route on delta.com.

        NOTE: This method's selectors must be verified against delta.com's
        actual page structure. The implementation below is a scaffold that
        must be refined during integration testing with a real browser.
        """
        # Navigate to delta.com search
        url = (
            f"https://www.delta.com/flight-search/search?"
            f"action=findFlights&tripType=ONE_WAY"
            f"&from={origin}&to={destination}"
            f"&departureDate=flexible&shopWithMiles=true"
        )
        await page.goto(url, wait_until="networkidle", timeout=30000)

        # Wait for results to load
        await page.wait_for_timeout(3000)

        # Get page content for parsing
        content = await page.content()
        return parse_award_results(origin, destination, content)
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_delta_search.py -v`
Expected: 4 tests PASS (unit tests with mocks only)

**Step 5: Commit**

```bash
git add sources/delta_search.py tests/test_delta_search.py
git commit -m "feat: add Delta award search scraper scaffold with Playwright"
```

**Step 6: Integration testing session (manual)**

After the scaffold is built, run an interactive integration test:

```bash
cd ~/miles-alert
source venv/bin/activate
playwright install chromium
python -c "
import asyncio
from playwright.async_api import async_playwright

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible browser
        page = await browser.new_page()
        await page.goto(
            'https://www.delta.com/flight-search/search?'
            'action=findFlights&tripType=ONE_WAY'
            '&from=ATL&to=NRT&shopWithMiles=true',
            wait_until='networkidle',
            timeout=60000
        )
        input('Press Enter after page loads and you see results...')
        content = await page.content()
        with open('/tmp/delta_search_sample.html', 'w') as f:
            f.write(content)
        print('Saved to /tmp/delta_search_sample.html')
        await browser.close()

asyncio.run(capture())
"
```

Use the captured HTML to:
1. Identify CSS selectors for award prices, cabin classes, seat counts
2. Update `parse_award_results()` with real selectors
3. Update `test_parse_award_results_sample()` with real HTML snippets

---

### Task 6: Google Flights Cash Price Enrichment

**Files:**
- Create: `~/miles-alert/enrichment.py`
- Create: `~/miles-alert/tests/test_enrichment.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_enrichment.py -v`
Expected: FAIL

**Step 3: Implement enrichment.py**

```python
"""Enrich award deals with cash prices from Google Flights.

Uses the fast_flights library to look up what the same flight
would cost in cash, enabling cents-per-mile value calculation.

This is optional enrichment — if it fails, the deal is still
reported without a cash price comparison.
"""
from __future__ import annotations

import logging
import re
from dataclasses import replace

from sources.base import AwardDeal

logger = logging.getLogger(__name__)

# Cabin class mapping for fast_flights
CABIN_MAP = {
    "first": "first",
    "business": "business",
}


def _parse_price(price_str: str) -> float | None:
    """Extract numeric price from string like '$4,800'."""
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


def enrich_with_cash_price(deal: AwardDeal) -> AwardDeal:
    """Look up the cash price for this route/date on Google Flights.

    Returns a new AwardDeal with cash_price set, or the original
    deal unchanged if lookup fails.
    """
    try:
        from fast_flights import create_filter, get_flights, Passengers

        flt = create_filter(
            flight_data=[
                {
                    "date": deal.departure_date,
                    "from": deal.origin,
                    "to": deal.destination,
                }
            ],
            trip="one-way",
            seat=CABIN_MAP.get(deal.cabin, "business"),
            passengers=Passengers(adults=1),
        )

        result = get_flights(flt)

        if not result.flights:
            logger.debug(f"No cash flights found for {deal.origin}->{deal.destination}")
            return deal

        # Use the cheapest cash price
        prices = [_parse_price(f.price) for f in result.flights]
        valid_prices = [p for p in prices if p is not None]

        if not valid_prices:
            return deal

        cash_price = min(valid_prices)
        logger.info(
            f"Cash price {deal.origin}->{deal.destination}: "
            f"${cash_price:,.0f} ({deal.cabin})"
        )
        return replace(deal, cash_price=cash_price)

    except Exception as e:
        logger.warning(f"Cash price lookup failed for {deal.origin}->{deal.destination}: {e}")
        return deal
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_enrichment.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add enrichment.py tests/test_enrichment.py
git commit -m "feat: add Google Flights cash price enrichment"
```

---

### Task 7: Main Entry Point

**Files:**
- Create: `~/miles-alert/miles_alert.py`
- Create: `~/miles-alert/tests/test_miles_alert.py`
- Create: `~/miles-alert/tests/__init__.py`

**Step 1: Write the failing tests**

```python
"""Tests for main entry point."""
import json
import pytest
from unittest.mock import patch, MagicMock
from sources.base import AwardDeal
from miles_alert import run, filter_deals


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
        "phone": "+15551234567",
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
```

**Step 2: Run tests to verify they fail**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v`
Expected: FAIL

**Step 3: Implement miles_alert.py**

```python
#!/usr/bin/env python3
"""Miles Alert — Delta SkyMiles award deal finder and alerter."""

import logging
from datetime import datetime, timezone

from config import load_config, load_state, save_state, LOG_DIR, ensure_config_dir
from sources.base import AwardDeal
from sources.delta_search import DeltaSearchSource
from enrichment import enrich_with_cash_price
from message_composer import compose_alert
from imessage import send_imessage


def setup_logging():
    """Configure logging to file and console."""
    ensure_config_dir()
    log_file = LOG_DIR / f"miles_alert_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )


def _notify_error(config: dict, message: str):
    """Send error notification to self via iMessage. Fails silently."""
    phone = config.get("phone")
    if not phone:
        return
    try:
        send_imessage(phone, message)
    except Exception as e:
        logging.warning(f"Could not send error notification: {e}")


def get_sources(config: dict) -> list:
    """Instantiate configured data sources."""
    sources = []
    for name in config.get("sources", ["delta_search"]):
        if name == "delta_search":
            sources.append(DeltaSearchSource())
        elif name == "seats_aero":
            try:
                from sources.seats_aero import SeatsAeroSource
                sources.append(SeatsAeroSource())
            except ImportError:
                logging.warning("seats_aero source not available")
        else:
            logging.warning(f"Unknown source: {name}")
    return sources


def filter_deals(deals: list[AwardDeal], config: dict) -> list[AwardDeal]:
    """Filter deals based on config thresholds."""
    min_cpm = config.get("min_cents_per_mile", 2.0)
    min_seats = config.get("min_seats", 2)
    cabins = set(config.get("cabins", ["first", "business"]))

    filtered = []
    for deal in deals:
        # Cabin filter
        if deal.cabin not in cabins:
            continue

        # Seats filter
        if deal.seats_available < min_seats:
            continue

        # Cents-per-mile filter (skip if no cash price available)
        if deal.cents_per_mile is not None and deal.cents_per_mile < min_cpm:
            continue

        filtered.append(deal)

    return filtered


def run():
    """Main run loop."""
    setup_logging()
    logging.info("Starting miles alert...")

    config = {}
    try:
        config = load_config()
        state = load_state()

        # Fetch deals from all configured sources
        sources = get_sources(config)
        all_deals = []
        for source in sources:
            try:
                deals = source.fetch_deals(config)
                all_deals.extend(deals)
            except Exception as e:
                logging.error(f"Source {type(source).__name__} failed: {e}")

        logging.info(f"Found {len(all_deals)} raw deals")

        # Enrich with cash prices
        enriched = []
        for deal in all_deals:
            enriched.append(enrich_with_cash_price(deal))

        # Filter
        filtered = filter_deals(enriched, config)
        logging.info(f"{len(filtered)} deals pass filters")

        # Deduplicate and alert
        new_alerts = 0
        for deal in filtered:
            if deal.dedup_key in state:
                logging.debug(f"Already alerted: {deal.dedup_key}")
                continue

            try:
                message = compose_alert(deal)
                send_imessage(config["phone"], message)
                state[deal.dedup_key] = datetime.now(timezone.utc).isoformat()
                save_state(state)
                new_alerts += 1
                logging.info(f"Alerted: {deal.dedup_key}")
            except Exception as e:
                logging.error(f"Failed to send alert for {deal.dedup_key}: {e}")
                _notify_error(config, f"Miles Alert: failed to send alert. Check logs.")

        logging.info(f"Miles alert complete. {new_alerts} new alerts sent.")

    except Exception as e:
        logging.error(f"Miles alert failed: {e}", exc_info=True)
        now_local = datetime.now().strftime("%-I:%M %p")
        _notify_error(config, f"Miles Alert failed at {now_local}. Check logs.")
        raise


if __name__ == "__main__":
    run()
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/miles-alert && python -m pytest tests/test_miles_alert.py -v`
Expected: All 4 tests PASS

**Step 5: Run all tests**

Run: `cd ~/miles-alert && python -m pytest tests/ -v`
Expected: All tests PASS (config + base + imessage + composer + delta_search + enrichment + main)

**Step 6: Commit**

```bash
git add miles_alert.py tests/test_miles_alert.py tests/__init__.py
git commit -m "feat: add main entry point with filtering, dedup, and alerting"
```

---

### Task 8: Launchd Plist and Config Template

**Files:**
- Create: `~/miles-alert/com.milesalert.daily.plist`
- Create: `~/miles-alert/config.example.json`

**Step 1: Create the launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.milesalert.daily</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/miles-alert/venv/bin/python3</string>
        <string>/Users/YOUR_USERNAME/miles-alert/miles_alert.py</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>7</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>12</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>18</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/.config/miles-alert/logs/launchd_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/.config/miles-alert/logs/launchd_stderr.log</string>

    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

**Step 2: Create config template**

```json
{
  "origin": "ATL",
  "phone": "+1XXXXXXXXXX",
  "min_cents_per_mile": 2.0,
  "min_seats": 2,
  "cabins": ["first", "business"],
  "sources": ["delta_search"],
  "seats_aero_api_key": null,
  "excluded_destinations": []
}
```

**Step 3: Commit**

```bash
git add com.milesalert.daily.plist config.example.json
git commit -m "feat: add launchd plist and config template"
```

---

### Task 9: Setup, venv, and Manual Test

**Step 1: Create venv and install dependencies**

```bash
cd ~/miles-alert
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**Step 2: Create real config**

```bash
mkdir -p ~/.config/miles-alert
cp config.example.json ~/.config/miles-alert/config.json
# Edit with real phone number
```

**Step 3: Run all tests**

```bash
cd ~/miles-alert && source venv/bin/activate
python -m pytest tests/ -v
```
Expected: All tests PASS

**Step 4: Manual integration test**

```bash
python miles_alert.py
```

Observe:
- Logs to console and `~/.config/miles-alert/logs/`
- Searches delta.com routes (will likely need selector refinement)
- Attempts cash price enrichment
- Sends iMessage alerts for any deals found

**Step 5: Install launchd plist**

```bash
# Replace YOUR_USERNAME with actual username
sed "s/YOUR_USERNAME/$(whoami)/g" com.milesalert.daily.plist > ~/Library/LaunchAgents/com.milesalert.daily.plist
launchctl load ~/Library/LaunchAgents/com.milesalert.daily.plist
```

**Step 6: Commit any selector/parsing fixes from integration testing**

```bash
git add -A
git commit -m "fix: refine delta.com selectors from integration testing"
```

---

### Task 10 (Phase 2, Future): seats.aero API Source

**Files:**
- Create: `~/miles-alert/sources/seats_aero.py`
- Create: `~/miles-alert/tests/test_seats_aero.py`

This task is deferred until the user subscribes to seats.aero Pro.

**Implementation notes for when ready:**
- API endpoint: `https://api.seats.aero/partnerapi/search`
- Auth header: `Partner-Authorization: <api_key>`
- Query params: `origin_airport=ATL&sources=delta&cabins=business,first&order_by=lowest_mileage`
- Response: JSON with `YMileageCost`, `JMileageCost`, `FMileageCost`, `JAvailable`, `FAvailable`
- Rate limit: 1,000 calls/day with Pro
- To activate: add `seats_aero_api_key` to config, add `"seats_aero"` to `sources` list

---

## Summary

| Task | What | Tests |
|------|------|-------|
| 1 | Config + state management | 8 |
| 2 | AwardDeal model + DealSource protocol | 4 |
| 3 | iMessage module | 3 |
| 4 | Message composer | 2 |
| 5 | Delta search scraper (Playwright) | 4 |
| 6 | Cash price enrichment (Google Flights) | 3 |
| 7 | Main entry point + filtering | 4 |
| 8 | Launchd plist + config template | 0 |
| 9 | Setup + manual integration test | 0 |
| 10 | seats.aero API (Phase 2, deferred) | — |

**Total: 9 tasks, ~28 tests, ~8 files**

**Critical path:** Task 5 (Delta scraper) requires interactive integration testing to capture real delta.com HTML and determine CSS selectors. All other tasks can proceed from the plan directly.

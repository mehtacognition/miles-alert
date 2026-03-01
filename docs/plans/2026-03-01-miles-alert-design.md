# Miles Alert Agent — Design Document

_2026-03-01_

## Problem

User has millions of Delta SkyMiles but struggles to use them effectively. International first class and Delta One deals from ATL appear and disappear quickly. Need automated monitoring and alerting when high-value redemption opportunities arise.

## Requirements

- Track **First Class + Delta One** award availability from **ATL to all international destinations**
- Alert when **cents-per-mile value exceeds threshold** (default 2.0¢/mile)
- Filter for **2+ seats available** (traveling as a pair)
- Deliver alerts via **iMessage**
- Start free, design for easy upgrade to paid data sources

## Architecture

```
[Data Sources]              [Agent Core]              [Delivery]
                       ┌──────────────────┐
Delta Deals Page ─────►│  Fetch & Parse   │
(free, Phase 1)        │       ↓          │
                       │  Enrich (cash $) │──────► iMessage
seats.aero API ───────►│       ↓          │
(Pro, Phase 2)         │  Filter & Score  │
                       │       ↓          │
Google Flights ───────►│  Dedup & Alert   │
(cash price enrichment)└──────────────────┘
                              ↑
                    Config + State Files
                    (~/.config/miles-alert/)
```

## Data Model

```python
@dataclass
class AwardDeal:
    origin: str              # "ATL"
    destination: str         # "NRT"
    airline: str             # "DL"
    cabin: str               # "first" | "business"
    miles_price: int         # 85000
    seats_available: int     # 2
    departure_date: str      # "2026-05-15"
    source: str              # "delta_deals" | "seats_aero"
    cash_price: float | None     # filled by enrichment
    cents_per_mile: float | None # calculated
```

## Data Sources

### Phase 1: Delta SkyMiles Award Deals Page (Free)
- Scrape delta.com/flight-deals/skymiles-award-deals
- Parse flash sale listings for ATL international routes
- Limited to Delta-promoted deals but catches major flash sales

### Phase 2: seats.aero Partner API ($9.99/mo)
- Query cached availability: origin=ATL, sources=delta, cabins=business,first
- Filter for 2+ seats, sort by lowest mileage
- 1,000 API calls/day included with Pro
- Just add API key to config to activate

### Cash Price Enrichment: Google Flights via fast_flights
- Look up cash price for same route/date
- Calculate cents_per_mile = cash_price / (miles_price / 100)
- Optional — alert still fires if enrichment fails, just without ¢/mile

## Filtering

Configurable thresholds in config.json:
- `min_cents_per_mile`: 2.0 (default) — only alert on above-average value
- `min_seats`: 2 — must have 2+ seats for couple travel
- `cabins`: ["first", "business"]
- `excluded_destinations`: [] — opt-out specific airports

## Deduplication

State file at `~/.config/miles-alert/state.json`:
- Maps `{route_date_cabin: ISO_timestamp}`
- Auto-prunes entries older than 14 days
- Prevents re-alerting on same deal within window

## Alert Format

```
✈️ Delta Miles Deal Alert
ATL → NRT (Tokyo) — First Class
85,000 miles × 2 seats
Cash price: $8,200 → 4.8¢/mile 🔥
Dates: May 15-22, 2026
Book: delta.com
```

## Configuration

`~/.config/miles-alert/config.json`:
```json
{
  "origin": "ATL",
  "phone": "...",
  "min_cents_per_mile": 2.0,
  "min_seats": 2,
  "cabins": ["first", "business"],
  "sources": ["delta_deals"],
  "seats_aero_api_key": null,
  "excluded_destinations": []
}
```

## Scheduling

launchd plist running 3x daily (7 AM, 12 PM, 6 PM).
Award deals don't change by the minute — 3x/day catches flash sales before expiry.

## Project Structure

```
~/miles-alert/
├── miles_alert.py          # main entry point
├── sources/
│   ├── base.py             # DealSource protocol + AwardDeal dataclass
│   ├── delta_deals.py      # scrapes Delta deals page
│   └── seats_aero.py       # seats.aero API (Phase 2)
├── enrichment.py           # Google Flights cash price lookup
├── imessage.py             # iMessage via AppleScript
├── config.py               # load config + state
├── tests/
├── com.milesalert.daily.plist
└── venv/
```

## Patterns Reused from flight-texter

- iMessage delivery via AppleScript subprocess
- JSON config at ~/.config/ (XDG pattern)
- JSON state file with auto-pruning dedup
- launchd scheduling with calendar intervals
- Error self-notification to self_reminder_phone
- Logging to ~/.config/miles-alert/logs/

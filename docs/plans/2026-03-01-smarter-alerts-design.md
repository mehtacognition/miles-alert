# Smarter Alerts + Deal Radar — Design Doc

_Date: 2026-03-01_

## Motivation

miles-alert's core differentiators over seats.aero Pro are CPM value filtering and multi-recipient iMessage alerts. This enhancement makes each alert more useful so you can make faster decisions from plain text alone, and adds personalization (watchlist) and timeliness (price drops).

## Features

### 1. Deal Quality Tiers

Each deal is classified by cents-per-mile value:

| Tier | CPM Range | Behavior |
|---|---|---|
| Exceptional | 5.0+ | Individual iMessage alert immediately |
| Strong | 3.0–4.99 | Included in daily digest |
| Good | 2.0–2.99 | Included in daily digest |
| Below threshold | < 2.0 | Filtered out (same as today) |

- Tier label appears in alert text (e.g. "EXCEPTIONAL Delta Miles Deal")
- Thresholds configurable via `tier_thresholds` in config (optional, sensible defaults)
- Deals without CPM (enrichment failed) are treated as Strong tier — included in digest but not sent as Exceptional

### 2. Daily Digest

Batches results into a single digest message per run instead of individual alerts for every deal.

Format:
```
Delta Miles Digest — Mar 1, 12:00 PM
3 deals found (1 Exceptional sent separately)

STRONG (3.0+ CPM):
- ATL->CDG Business 120K mi x 2 seats | 3.8 CPM | Jun 14
- ATL->LHR First 180K mi x 2 seats | 3.2 CPM | Jul 20

GOOD (2.0+ CPM):
- ATL->FCO Business 95K mi x 3 seats | 2.4 CPM | Aug 3

No CPM available:
- ATL->ICN First 90K mi x 2 seats | Sep 10
```

Behavior:
- Exceptional deals send individually, not in digest
- If only Exceptional deals exist, no digest sent
- If no deals at all, silent run (no message)
- Dedup still applies across digests

### 3. Route Watchlist

Specific routes of interest defined in config. Watchlist matches always send individual alerts regardless of tier.

Config:
```json
{
  "watchlist": [
    {"destination": "NRT", "cabin": "first"},
    {"destination": "CDG", "cabin": "business"}
  ]
}
```

- Watchlist hits tagged with "WATCHLIST HIT" in alert text
- A deal can be both Exceptional and watchlist — sends once with both labels
- Watchlist hits noted in digest summary line
- Optional — omitting watchlist from config changes nothing

### 4. Price Drop Re-Alerts

Re-alerts when a previously-seen route drops in miles cost.

Extended state format:
```json
{
  "ATL-NRT-first-2026-09-15": {
    "alerted_at": "2026-03-01T12:00:00Z",
    "miles_price": 85000
  }
}
```

- Only re-alerts on drops, not increases
- Updates stored price after re-alerting (further drops trigger again)
- Price drop alerts always send individually
- Comparison uses miles price only (not CPM)
- Same 14-day auto-prune applies
- Backward-compat migration for old state format (plain timestamp -> dict)

### 5. Schedule + Origin Changes

- Launchd plist updated to 12:00 PM and 8:00 PM (was 9 AM / 6 PM)
- Origin stays as `"origin": "ATL"` — edit to `"BOM"` when visiting family, edit back on return

## Files Changed

| File | Change |
|---|---|
| `miles_alert.py` | Tier classification, digest batching, watchlist check, price drop detection. Restructured run() loop. |
| `message_composer.py` | New: `compose_digest()`, `compose_price_drop()`. Updated: `compose_alert()` with tier label. |
| `config.py` | New defaults: `tier_thresholds`, `watchlist`. Extended state format. Backward-compat state migration. |
| `config.example.json` | Add `watchlist` and `tier_thresholds` examples. |
| `com.milesalert.daily.plist` | Schedule: 12:00 PM and 8:00 PM. |
| `tests/` | New and updated tests for all above. |

## What Stays the Same

- seats.aero as sole data source
- iMessage delivery via AppleScript
- Google Flights cash price enrichment (optional, graceful fallback)
- `AwardDeal` dataclass (`sources/base.py`) unchanged
- Multi-recipient sending, error self-notification
- 14-day state pruning
- No new dependencies

## Config After Changes

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

Both `watchlist` and `tier_thresholds` are optional with sensible defaults.

#!/usr/bin/env python3
"""Miles Alert — Delta SkyMiles award deal finder and alerter."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import load_config, load_state, save_state, LOG_DIR, ensure_config_dir
from sources.base import AwardDeal
from sources.delta_search import DeltaSearchSource
from enrichment import enrich_with_cash_price
from message_composer import compose_alert, compose_digest, compose_price_drop
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


def _send_to_all(config: dict, message: str):
    """Send a message to all configured phone numbers."""
    phones = config.get("phones", [])
    for phone in phones:
        try:
            send_imessage(phone, message)
        except Exception as e:
            logging.error(f"Failed to send to {phone}: {e}")


def _notify_error(config: dict, message: str):
    """Send error notification to first phone only. Fails silently."""
    phones = config.get("phones", [])
    if not phones:
        return
    try:
        send_imessage(phones[0], message)
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
        if deal.cabin not in cabins:
            continue
        if deal.seats_available < min_seats:
            continue
        if deal.cents_per_mile is not None and deal.cents_per_mile < min_cpm:
            continue
        filtered.append(deal)

    return filtered


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


def is_watchlist_match(deal: AwardDeal, watchlist: list[dict]) -> bool:
    """Check if a deal matches any entry in the route watchlist."""
    for entry in watchlist:
        if deal.destination == entry["destination"] and deal.cabin == entry["cabin"]:
            return True
    return False


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


if __name__ == "__main__":
    run()

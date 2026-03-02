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
        if deal.cabin not in cabins:
            continue
        if deal.seats_available < min_seats:
            continue
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

"""Compose iMessage alert text for award deals."""
from __future__ import annotations

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
    lines.append("Book: delta.com")

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
        "\ud83d\udcc9 PRICE DROP \u2014 Delta Miles Deal",
        f"{deal.origin} \u2192 {deal.destination} - {cabin_name}",
        f"Was: {prev_fmt} miles \u2192 Now: {now_fmt} miles",
    ]

    if deal.cash_price is not None and deal.cents_per_mile is not None:
        cash_fmt = f"${deal.cash_price:,.0f}"
        cpm = f"{deal.cents_per_mile:.1f}"
        lines.append(f"Cash price: {cash_fmt} = {cpm} cents/mile")

    lines.append(f"{deal.seats_available} seats | Date: {deal.departure_date}")
    lines.append("Book: delta.com")

    return "\n".join(lines)

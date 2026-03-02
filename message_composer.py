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

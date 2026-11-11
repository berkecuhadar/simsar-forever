"""What it costs to sell one unit on the auction house."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Fees:
    ah_cut: float
    deposit_rate: float
    auction_hours: int
    max_relists: float
    cut_source: str = "config"
    deposit_source: str = "config"
    min_deposit: float = 0          # copper per listing
    listing_size: float = 1         # units in a typical listing


def from_config(cfg, measured=None):
    eco = cfg["economy"]
    measured = measured or {}
    cut, cut_src = eco["ah_cut"], "config"
    if measured.get("ah_cut") is not None:
        cut, cut_src = measured["ah_cut"], f"measured ({measured['ah_cut_samples']} sales)"
    hours = eco["auction_hours"]
    rate, floor, rate_src = eco["deposit_rate"], eco["min_deposit"], "config"
    by_hours = measured.get("deposit_rates") or {}
    m = by_hours.get(hours)
    if not m and by_hours:
        # Use the duration you actually post with when the configured one has no measurements.
        hours, m = max(by_hours.items(), key=lambda kv: kv[1]["samples"])
    if m:
        parts = []
        if m.get("rate") is not None:
            rate = m["rate"]
            parts.append("rate")
        if m.get("min_deposit") is not None:
            floor = m["min_deposit"]
            parts.append("minimum")
        if parts:
            rate_src = f"measured {' and '.join(parts)} from {m['samples']} posts of {hours}h"
    return Fees(cut, rate, hours, eco["max_relists"], cut_src, rate_src, floor, eco["listing_size"])


def deposit(vendor_sell, fees):
    """Deposit for listing one unit: the larger of the rate on the vendor price and this unit's share
    of the per-listing minimum. None when neither is known."""
    share = fees.min_deposit / max(fees.listing_size, 1)
    if vendor_sell is None:
        return share or None
    return max(vendor_sell * fees.deposit_rate, share)


def listings_per_sale(sale_rate, fees):
    """How many times a unit is listed, on average, before it sells.
    A sale rate of 0.25 means one listing in four sells, so four listings per sale."""
    if not sale_rate or sale_rate <= 0:
        return fees.max_relists
    return min(1 / sale_rate, fees.max_relists)


def net_per_sale(price, vendor_sell, sale_rate, fees):
    """Money kept from one sale at `price`: price minus the AH cut minus deposits lost on the
    listings that expired first. The deposit of the listing that sells is refunded."""
    if price is None:
        return None
    lost = (deposit(vendor_sell, fees) or 0) * (listings_per_sale(sale_rate, fees) - 1)
    return price * (1 - fees.ah_cut) - lost

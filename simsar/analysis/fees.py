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


def from_config(cfg, measured=None):
    eco = cfg["economy"]
    measured = measured or {}
    cut, cut_src = eco["ah_cut"], "config"
    if measured.get("ah_cut") is not None:
        cut, cut_src = measured["ah_cut"], f"measured ({measured['ah_cut_samples']} sales)"
    rate, rate_src = eco["deposit_rate"], "config"
    m = (measured.get("deposit_rates") or {}).get(eco["auction_hours"])
    if m:
        rate, rate_src = m["rate"], f"measured ({m['samples']} posts)"
    return Fees(cut, rate, eco["auction_hours"], eco["max_relists"], cut_src, rate_src)


def deposit(vendor_sell, fees):
    """Deposit for listing one unit. Unknown vendor price -> None."""
    if vendor_sell is None:
        return None
    return vendor_sell * fees.deposit_rate


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

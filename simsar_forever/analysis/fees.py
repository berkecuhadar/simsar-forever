"""What the auction house keeps from a sale."""

from dataclasses import dataclass

# Faction auction houses (Alliance, Horde) keep 5% of the sale price, the neutral one 15%.
CUTS = {"faction": 0.05, "neutral": 0.15}


@dataclass(frozen=True)
class Fees:
    ah_cut: float
    auction_house: str = "faction"
    cut_source: str = "faction auction house"


def from_config(cfg, measured=None):
    eco = cfg["economy"]
    house = eco["auction_house"]
    if eco.get("ah_cut") is not None:
        return Fees(eco["ah_cut"], house, "config")
    return Fees(CUTS[house], house, f"{house} auction house")


def net_per_sale(price, fees):
    """Money kept from one sale at `price` after the auction house cut."""
    if price is None:
        return None
    return price * (1 - fees.ah_cut)

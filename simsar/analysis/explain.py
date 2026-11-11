"""Plain-language commentary for one item."""

from ..money import fmt
from .market import FLAGS


def _pct(x):
    return f"{abs(x) * 100:.0f}%"


def item(it, fees, cfg):
    s = []
    pn, ref, spd = it.get("price_now"), it.get("reference"), it.get("my_sales_per_day")
    ref_name = ("its long-term (60 day) average" if cfg["analysis"]["reference_price"] == "historical"
                else "its usual price over the last two weeks")
    src = {"auctionator": "your Auctionator scan", "tsm_min_buyout": "TSM's latest scan",
           "tsm_market": "TSM market value (no listing seen)"}.get(it.get("price_src"), "unknown source")
    if pn:
        s.append(f"The cheapest listing is {fmt(pn)}, from {src}.")

    d = it.get("disc_ref")
    if d is not None:
        if d < -0.15:
            s.append(f"That is {_pct(d)} below {ref_name} ({fmt(ref)}). Prices tend to drift back toward their "
                     "usual level, so this can be a buying chance, but check why it is cheap "
                     "(a flood of supply, a single odd listing, a new source).")
        elif d > 0.20:
            s.append(f"That is {_pct(d)} above {ref_name} ({fmt(ref)}). Buying at a high is risky; "
                     "if you hold some, it may be a good time to sell.")
        else:
            s.append(f"It is close to {ref_name} ({fmt(ref)}).")
    hd = it.get("disc_hist")
    if hd is not None and cfg["analysis"]["reference_price"] != "historical" and hd < -0.4:
        s.append(f"TSM's 60-day average is much higher ({fmt(it.get('historical'))}). On a new server that "
                 "average still includes launch-week prices, which rarely come back.")

    region = it.get("sold_per_day_region")
    if region is None or region == 0:
        s.append("TSM has no recorded sales for this item in the region. Anything you buy may be hard to sell.")
    else:
        s.append(f"About {region:,.1f} sell per day across the region. With your settings "
                 f"({cfg['economy']['realm_share']:.0%} of that on your realm, of which you win "
                 f"{cfg['economy']['market_share']:.0%}) expect to sell about {spd:,.1f} a day.")
        if it.get("turnover_day"):
            s.append(f"Roughly {fmt(it['turnover_day'])} changes hands for it on your realm each day.")

    sr = it.get("sale_rate")
    if sr is not None:
        s.append(f"Sale rate {sr:.0%}: about {it['listings_per_sale']:.1f} listings per sale. "
                 "Each listing that expires loses its deposit, which is already subtracted below.")

    net = it.get("net_sell")
    if net is not None and it.get("sell_price"):
        s.append(f"Selling one at {fmt(it['sell_price'])} leaves you {fmt(net)} after the "
                 f"{fees.ah_cut:.0%} auction cut and expected deposit losses.")

    fp = it.get("flip_profit")
    if fp is not None:
        if fp > 0:
            s.append(f"Buying at {fmt(pn)} and reselling at the usual price of {fmt(it['sell_ref'])} would make "
                     f"about {fmt(fp)} per unit ({it['flip_margin']:.0%}). This assumes the price comes back and "
                     "that you wait for buyers.")
        else:
            s.append("Buying it to resell does not pay at current prices.")

    vol = it.get("volatility")
    if vol is not None:
        level = "low" if vol < 0.08 else "moderate" if vol < 0.2 else "high"
        s.append(f"Price swings are {level} (typical deviation {vol:.0%} of the price) over the last "
                 f"{cfg['analysis']['history_days']} days.")
    elif it.get("n_points"):
        s.append(f"Only {it['n_points']} price points so far; volatility is not shown until there are "
                 f"{cfg['analysis']['min_points_volatility']}.")
    tr = it.get("trend")
    if tr is not None and abs(tr) >= 0.005:
        s.append(f"Trend: {'rising' if tr > 0 else 'falling'} about {_pct(tr)} per day.")

    for f in it.get("flags", []):
        if f not in ("not_live", "low_confidence"):
            s.append(f"Warning: {FLAGS[f].lower()}.")
    return s

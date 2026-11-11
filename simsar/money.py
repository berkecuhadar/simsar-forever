def fmt(copper):
    """12345 -> '1g 23s 45c'. Prices are stored in copper (1 gold = 100 silver = 10,000 copper)."""
    if copper is None:
        return "-"
    sign = "-" if copper < 0 else ""
    c = int(round(abs(copper)))
    g, rest = divmod(c, 10000)
    s, c = divmod(rest, 100)
    parts = []
    if g:
        parts.append(f"{g:,}g")
    if s or (g and c):
        parts.append(f"{s}s")
    if c or not parts:
        parts.append(f"{c}c")
    return sign + " ".join(parts)

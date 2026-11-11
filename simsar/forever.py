"""WoW Forever regions, realms and auction house slugs as TSM publishes them.

TSM only has realm files for the faction auction houses (`<realm>-<faction>`); the bare realm slug
returns 404. Checked against public-data.tradeskillmaster.com in November 2026.
"""

GAME_TYPE = "forever"

REALM_TYPES = {
    "normal": "Normal (PvE)",
    "pvp": "PvP",
    "roleplay": "Roleplay",
    "roleplay-pvp": "Roleplay PvP",
}

REGIONS = {
    "us": {"label": "Americas (US)", "realms": ["normal", "pvp", "roleplay", "roleplay-pvp"]},
    "eu": {"label": "Europe (EU)", "realms": ["normal", "pvp", "roleplay", "roleplay-pvp"]},
    "tw": {"label": "Taiwan (TW)", "realms": ["normal", "pvp"]},
    "kr": {"label": "Korea (KR)", "realms": ["normal", "pvp"]},
}

FACTIONS = {"alliance": "Alliance", "horde": "Horde"}


def slug(realm_type, faction):
    return f"{realm_type}-{faction}"


def parse_slug(value):
    """'roleplay-pvp-horde' -> ('roleplay-pvp', 'horde'); None if it is not a Forever AH slug."""
    if not value:
        return None
    for faction in FACTIONS:
        suffix = f"-{faction}"
        if value.endswith(suffix) and value[: -len(suffix)] in REALM_TYPES:
            return value[: -len(suffix)], faction
    return None


def valid(region, realm):
    if region not in REGIONS:
        return False
    if realm is None:
        return True
    parsed = parse_slug(realm)
    return bool(parsed) and parsed[0] in REGIONS[region]["realms"]


def label(region, realm):
    reg = REGIONS.get(region, {}).get("label", region)
    parsed = parse_slug(realm)
    if not parsed:
        return f"{reg}, region only"
    return f"{reg} - {REALM_TYPES[parsed[0]]} - {FACTIONS[parsed[1]]}"


def catalog():
    return {
        "regions": [{"key": k, "label": v["label"], "realms": v["realms"]} for k, v in REGIONS.items()],
        "realm_types": REALM_TYPES,
        "factions": FACTIONS,
    }

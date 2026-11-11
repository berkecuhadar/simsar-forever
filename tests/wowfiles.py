"""Helpers that write files the way the WoW client does."""

import cbor2


def lua_quote(data):
    # The client escapes exactly these bytes inside SavedVariables strings.
    out = bytearray(b'"')
    for b in data:
        if b == 10:
            out += b"\\n"
        elif b == 13:
            out += b"\\r"
        elif b == 0:
            out += b"\\000"
        elif b == 34:
            out += b'\\"'
        elif b == 92:
            out += b"\\\\"
        else:
            out.append(b)
    out += b'"'
    return bytes(out)


def _bytes_keys(value):
    if isinstance(value, dict):
        if not value:
            return []
        return {str(k).encode(): _bytes_keys(v) for k, v in value.items()}
    return value


def auctionator_file(realms, db_version=8, extra=b""):
    """realms: {realm: {db_key: {"m": .., "h": {day: p}, "l": {..}, "a": {..}}}}"""
    parts = [b"\nAUCTIONATOR_CONFIG = {\n[\"autoscan_2\"] = false,\n}\n",
             b"AUCTIONATOR_SAVEDVARS = {\n[\"TimeOfLastBrowseScan\"] = 1794091937,\n}\n",
             b"AUCTIONATOR_PRICE_DATABASE = {\n[\"__dbversion\"] = %d,\n" % db_version]
    for realm, items in realms.items():
        blob = cbor2.dumps(_bytes_keys(items))
        parts.append(b'["' + realm.encode() + b'"] = ' + lua_quote(blob) + b",\n")
    parts.append(b"}\n")
    parts.append(extra)
    return b"".join(parts)

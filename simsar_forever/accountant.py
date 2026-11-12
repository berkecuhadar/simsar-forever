"""Import the gold history of the Accountant Classic addon, when it is installed.

Accountant Classic keeps a per day, per character, per category record of gold earned and spent
(`Accountant_ClassicHistory`). Simsar Forever reads it so the ledger reaches back to before its own
addon started recording. Only the data is read; no code from Accountant Classic is used.

    Accountant_ClassicHistory.chars["<realm>|<name>-<server>"] = {
      name, money, days = { [YYYYMMDD] = { <CATEGORY> = { i, o, ni, no }, bal = <gold at day end> } } }
    Accountant_ClassicHistory.recent = { { t, a, k = <CATEGORY>, c = <char key> }, ... }
"""

from pathlib import Path

from . import lua
from .addon_import import _int, _items, import_ledger

FILE = "Accountant_Classic.lua"

# Accountant Classic category -> Simsar Forever category. Its AH income is money from sale mails.
CATEGORIES = {
    "MERCH": "VENDOR", "REPAIRS": "REPAIR", "MAIL": "MAIL", "QUEST": "QUEST", "LOOT": "LOOT",
    "TRAIN": "TRAINING", "TAXI": "TAXI", "TRADE": "TRADE", "BANK": "BANK", "GUILD": "GUILD",
    "BARBER": "BARBER", "WARBAND": "TRANSFER", "OTHER": "OTHER", "TRANSMO": "OTHER", "LFG": "OTHER",
    "GARRISON": "OTHER",
}


def category(raw, amount):
    if raw == "AH":
        return "AH_SALE" if amount > 0 else "AH"
    return CATEGORIES.get(raw, "OTHER")


def char_key(acc_key, info):
    """'CAMWOW EU5 Realm 1 PvE|Bolulu-Karahaci' -> 'Bolulu-CAMWOW EU5 Realm 1 PvE' (the addon's key)."""
    realm, _, who = str(acc_key).partition("|")
    name = (info.get("name") if isinstance(info, dict) else None) or who
    return f"{str(name).split('-')[0]}-{realm}"


def import_file(conn, path):
    saved = lua.load(Path(path))
    history = saved.get("Accountant_ClassicHistory")
    if not isinstance(history, dict):
        return {"ok": False, "error": "Accountant_ClassicHistory is missing (Accountant Classic too old?)"}
    keys, days, tx = {}, 0, 0
    for acc_key, info in _items(history.get("chars")):
        if not isinstance(info, dict):
            continue
        key = keys[str(acc_key)] = char_key(acc_key, info)
        ledger_days, balance = {}, {}
        for day, bucket in _items(info.get("days")):
            if not _int(day) or not isinstance(bucket, dict):
                continue
            cats = {}
            for raw, e in bucket.items():
                if not (isinstance(raw, str) and raw.isupper() and isinstance(e, dict)):
                    continue
                for amount, field, count in ((_int(e.get("i")) or 0, "i", _int(e.get("ni")) or 0),
                                             (-(_int(e.get("o")) or 0), "o", _int(e.get("no")) or 0)):
                    if not amount:
                        continue
                    c = cats.setdefault(category(raw, amount), {"i": 0, "o": 0, "n": 0})
                    c[field] += abs(amount)
                    c["n"] += count
            ledger_days[int(day)] = cats
            if _int(bucket.get("bal")) is not None:
                balance[int(day)] = int(bucket["bal"])
            days += 1
        import_ledger(conn, key, {"days": ledger_days}, balance, "accountant")
    recent = {}
    for _, r in _items(history.get("recent")):
        if isinstance(r, dict) and str(r.get("c")) in keys and _int(r.get("a")):
            recent.setdefault(keys[str(r["c"])], []).append(
                {"t": r.get("t"), "a": r["a"], "k": category(r.get("k"), r["a"]), "z": r.get("s")})
            tx += 1
    for key, rows in recent.items():
        import_ledger(conn, key, {"recent": rows}, None, "accountant")
    conn.commit()
    return {"ok": True, "characters": len(keys), "days": days, "transactions": tx}

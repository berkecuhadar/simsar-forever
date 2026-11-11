"""Find WoW Forever installs, accounts and Auctionator realms on this computer."""

import json
import os
import string
import sys
from pathlib import Path

from . import auctionator, lua

FOREVER_FOLDER = "_forever_"
COMMON_SUBPATHS = [
    "World of Warcraft",
    "Games/World of Warcraft",
    "Program Files (x86)/World of Warcraft",
    "Program Files/World of Warcraft",
    "Blizzard/World of Warcraft",
    "Battle.net/World of Warcraft",
]


def _registry_paths():
    if sys.platform != "win32":
        return []
    import winreg
    out = []
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\World of Warcraft", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\World of Warcraft", "InstallLocation"),
    ]
    for hive, key, value in keys:
        try:
            with winreg.OpenKey(hive, key) as k:
                out.append(Path(winreg.QueryValueEx(k, value)[0]))
        except OSError:
            continue
    return out


def _battlenet_paths():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    cfg = Path(appdata) / "Battle.net" / "Battle.net.config"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    path = (((data.get("Client") or {}).get("Install") or {}).get("DefaultInstallPath"))
    return [Path(path) / "World of Warcraft", Path(path)] if path else []


def _drives():
    if sys.platform == "win32":
        return [Path(f"{d}:/") for d in string.ascii_uppercase if os.path.exists(f"{d}:/")]
    return [Path("/"), Path.home(), Path("/Applications")]


def _root_candidates():
    seen, out = set(), []

    def add(p):
        try:
            key = str(p.resolve()).lower()
        except OSError:
            return
        if key not in seen:
            seen.add(key)
            out.append(p)

    for p in _registry_paths() + _battlenet_paths():
        # The registry usually points at a flavor folder such as _retail_; its parent is the root.
        add(p.parent if p.name.startswith("_") and p.name.endswith("_") else p)
    for drive in _drives():
        for sub in COMMON_SUBPATHS:
            add(drive / sub)
        try:
            for entry in os.scandir(drive):
                if entry.is_dir() and "warcraft" in entry.name.lower():
                    add(Path(entry.path))
        except OSError:
            continue
    return out


def accounts(game_dir):
    base = Path(game_dir) / "WTF" / "Account"
    out = []
    if not base.is_dir():
        return out
    for entry in sorted(base.iterdir()):
        sv = entry / "SavedVariables"
        if not sv.is_dir():
            continue
        ato = sv / "Auctionator.lua"
        out.append({
            "name": entry.name,
            "has_auctionator": ato.exists(),
            "auctionator_mtime": int(ato.stat().st_mtime) if ato.exists() else None,
            "has_simsar_export": (sv / "SimsarExport.lua").exists(),
        })
    return out


def auctionator_realms(game_dir, account):
    path = Path(game_dir) / "WTF" / "Account" / account / "SavedVariables" / "Auctionator.lua"
    if not path.exists():
        return []
    try:
        _, realms = auctionator.read_price_database(lua.load(path))
    except (auctionator.AuctionatorFormatError, ValueError):
        return []
    return [{"key": k, "items": sum(isinstance(v, dict) for v in data.values())} for k, data in realms.items()]


def describe(game_dir):
    """What is in a candidate game folder. Accepts the root or the _forever_ folder itself."""
    p = Path(game_dir)
    if p.name != FOREVER_FOLDER and (p / FOREVER_FOLDER).is_dir():
        p = p / FOREVER_FOLDER
    flavor = None
    try:
        flavor = (p / ".flavor.info").read_text(encoding="utf-8", errors="replace").split()[-1]
    except (OSError, IndexError):
        pass
    addons = p / "Interface" / "AddOns"
    toc = auctionator.read_toc(addons / "Auctionator" / "Auctionator.toc")
    return {
        "path": str(p),
        "exists": p.is_dir(),
        "is_forever": p.name == FOREVER_FOLDER,
        "flavor": flavor,
        "has_wtf": (p / "WTF").is_dir(),
        "auctionator_version": toc.get("Version"),
        "simsar_export_installed": (addons / "SimsarExport" / "SimsarExport.toc").exists(),
        "accounts": accounts(p),
    }


def find_installs():
    found = []
    for root in _root_candidates():
        target = root / FOREVER_FOLDER if root.name != FOREVER_FOLDER else root
        if target.is_dir():
            found.append(describe(target))
    return found

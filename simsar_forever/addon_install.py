import shutil
from pathlib import Path

from . import auctionator

NAME = "SimsarForever"
SOURCE = Path(__file__).resolve().parents[1] / "addon" / NAME
# Earlier builds shipped the addon under these names. Their SavedVariables files stay where they are
# and are still imported, so removing the old folder loses nothing.
LEGACY_NAMES = ("SimsarForeverExport", "SimsarExport")
# Written by the dashboard; an update must not replace today's data with the empty copy.
KEEP = ("SimsarForeverData.lua",)


class InstallError(RuntimeError):
    pass


def shipped_version():
    return auctionator.read_toc(SOURCE / f"{NAME}.toc").get("Version")


def install(game_dir):
    """Copy the Simsar Forever addon into <game_dir>/Interface/AddOns. Returns the target folder."""
    if not game_dir:
        raise InstallError("no game folder is set")
    addons = Path(game_dir) / "Interface" / "AddOns"
    if not addons.is_dir():
        raise InstallError(f"{addons} does not exist; is this the WoW Forever folder?")
    if not SOURCE.is_dir():
        raise InstallError(f"addon source not found at {SOURCE}")
    target = addons / NAME
    target.mkdir(exist_ok=True)
    for src in SOURCE.iterdir():
        if src.is_file() and not (src.name in KEEP and (target / src.name).exists()):
            shutil.copy2(src, target / src.name)
    for name in LEGACY_NAMES:
        old = addons / name
        title = auctionator.read_toc(old / f"{name}.toc").get("Title", "")
        if old.is_dir() and title.startswith("Simsar"):
            shutil.rmtree(old)
    return target

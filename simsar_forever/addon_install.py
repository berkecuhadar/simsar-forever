import shutil
from pathlib import Path

from . import auctionator

SOURCE = Path(__file__).resolve().parents[1] / "addon" / "SimsarForeverExport"
# Earlier builds shipped the addon under this name.
LEGACY_NAMES = ("SimsarExport",)


class InstallError(RuntimeError):
    pass


def shipped_version():
    return auctionator.read_toc(SOURCE / "SimsarForeverExport.toc").get("Version")


def install(game_dir):
    """Copy SimsarForeverExport into <game_dir>/Interface/AddOns. Returns the target folder."""
    if not game_dir:
        raise InstallError("no game folder is set")
    addons = Path(game_dir) / "Interface" / "AddOns"
    if not addons.is_dir():
        raise InstallError(f"{addons} does not exist; is this the WoW Forever folder?")
    if not SOURCE.is_dir():
        raise InstallError(f"addon source not found at {SOURCE}")
    target = addons / "SimsarForeverExport"
    shutil.copytree(SOURCE, target, dirs_exist_ok=True)
    for name in LEGACY_NAMES:
        old = addons / name
        title = auctionator.read_toc(old / f"{name}.toc").get("Title", "")
        if old.is_dir() and title.startswith("Simsar"):
            shutil.rmtree(old)
    return target

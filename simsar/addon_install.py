import shutil
from pathlib import Path

from . import auctionator

SOURCE = Path(__file__).resolve().parents[1] / "addon" / "SimsarExport"


class InstallError(RuntimeError):
    pass


def shipped_version():
    return auctionator.read_toc(SOURCE / "SimsarExport.toc").get("Version")


def install(game_dir):
    """Copy SimsarExport into <game_dir>/Interface/AddOns. Returns the target folder."""
    if not game_dir:
        raise InstallError("no game folder is set")
    addons = Path(game_dir) / "Interface" / "AddOns"
    if not addons.is_dir():
        raise InstallError(f"{addons} does not exist; is this the WoW Forever folder?")
    if not SOURCE.is_dir():
        raise InstallError(f"addon source not found at {SOURCE}")
    target = addons / "SimsarExport"
    shutil.copytree(SOURCE, target, dirs_exist_ok=True)
    return target

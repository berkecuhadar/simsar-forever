"""Bring the database up to date: TSM downloads and SavedVariables imports."""

import logging
import threading
import time
from pathlib import Path

from . import addon_import, auctionator, db, tsm
from .analysis import alerts
from .analysis.engine import bump_data_version

log = logging.getLogger("simsar_forever")


def fetch_tsm(cfg, conn, session=None):
    reports = tsm.fetch(cfg, conn, session=session)
    if any(r.get("new_rows") for r in reports):
        db.prune(conn, cfg["storage"]["retain_days"])
        bump_data_version(conn)
    return reports


def _file_state(path):
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return [int(st.st_mtime), st.st_size]


def auctionator_path(cfg):
    sv = auctionator.saved_variables_dir(cfg)
    return sv / "Auctionator.lua" if sv else None


def addon_path(cfg):
    sv = auctionator.saved_variables_dir(cfg)
    return sv / "SimsarForeverExport.lua" if sv else None


def import_auctionator(cfg, conn, force=False):
    path = auctionator_path(cfg)
    if path is None:
        return {"ok": False, "skipped": True, "error": "wow.game_dir is not set or the account folder was not found"}
    state = _file_state(path)
    if state is None:
        return {"ok": False, "error": f"{path} does not exist yet; scan the auction house and /reload"}
    if not force and state == db.get_meta(conn, "ato_file_state"):
        return {"ok": True, "unchanged": True}

    toc = auctionator.read_toc(auctionator.addon_dir(cfg) / "Auctionator.toc")
    addon_version = toc.get("Version")
    warnings = []
    prev_version = db.get_meta(conn, "ato_addon_version")
    if prev_version and addon_version and prev_version != addon_version:
        warnings.append(f"Auctionator was updated from {prev_version} to {addon_version}. "
                        "Simsar Forever checked the file format; see below if anything changed.")
    try:
        rep = auctionator.import_file(conn, path, cfg)
    except (auctionator.AuctionatorFormatError, ValueError) as e:
        warnings.append(f"Auctionator import failed: {e}")
        db.set_meta(conn, "ato_warnings", warnings)
        db.set_meta(conn, "ato_file_state", state)
        result = {"ok": False, "error": str(e), "addon_version": addon_version}
        db.log_fetch(conn, "auctionator", False, result)
        return result

    prev_fp = db.get_meta(conn, "ato_fingerprint")
    if prev_fp and prev_fp != rep["fingerprint"]:
        warnings.append("Auctionator's data layout changed since the last import "
                        f"(fingerprint {prev_fp} -> {rep['fingerprint']}). Numbers may be off until Simsar Forever is updated.")
    if rep["unknown_fields"]:
        warnings.append(f"Auctionator entries contain unknown fields: {', '.join(rep['unknown_fields'])}.")
    rep.update(ok=True, addon_version=addon_version, path=str(path))
    for key, value in (("ato_addon_version", addon_version), ("ato_fingerprint", rep["fingerprint"]),
                       ("ato_file_state", state), ("ato_warnings", warnings), ("ato_last_import", rep)):
        db.set_meta(conn, key, value)
    db.log_fetch(conn, "auctionator", True, rep)
    bump_data_version(conn)
    return rep


def import_addon(cfg, conn, force=False):
    path = addon_path(cfg)
    if path is None:
        return {"ok": False, "skipped": True}
    state = _file_state(path)
    if state is None:
        return {"ok": False, "missing": True}
    if not force and state == db.get_meta(conn, "addon_file_state"):
        return {"ok": True, "unchanged": True}
    try:
        rep = addon_import.import_file(conn, path)
        rep["ok"] = True
    except (addon_import.AddonFormatError, ValueError) as e:
        rep = {"ok": False, "error": str(e)}
    db.set_meta(conn, "addon_file_state", state)
    db.set_meta(conn, "addon_last_import", rep)
    db.log_fetch(conn, "addon", rep["ok"], rep)
    if rep["ok"]:
        bump_data_version(conn)
    return rep


def refresh_all(cfg, conn, force=False):
    return {
        "tsm": fetch_tsm(cfg, conn),
        "auctionator": import_auctionator(cfg, conn, force),
        "addon": import_addon(cfg, conn, force),
    }


class Background:
    """Polls TSM every tsm.check_minutes and SavedVariables every wow.watch_seconds."""

    def __init__(self, cfg, conn, engine):
        self.cfg, self.conn, self.engine = cfg, conn, engine
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="simsar-forever-refresh", daemon=True)
        self.lock = threading.Lock()

    def start(self):
        self.thread.start()

    def _run(self):
        next_tsm = 0
        while not self.stop.is_set():
            try:
                with self.lock:
                    if time.time() >= next_tsm:
                        fetch_tsm(self.cfg, self.conn)
                        next_tsm = time.time() + self.cfg["tsm"]["check_minutes"] * 60
                    import_auctionator(self.cfg, self.conn)
                    import_addon(self.cfg, self.conn)
                    self.check_alerts()
            except Exception:
                log.exception("background refresh failed")
            self.stop.wait(self.cfg["wow"]["watch_seconds"])

    def check_alerts(self):
        if db.get_meta(self.conn, "demo"):
            return
        result = self.engine.result()
        if db.get_meta(self.conn, "alerts_version") == db.get_meta(self.conn, "data_version"):
            return
        alerts.store(self.conn, alerts.generate(result["items"], result["crafts"], self.cfg))
        db.set_meta(self.conn, "alerts_version", db.get_meta(self.conn, "data_version"))

    def refresh_now(self):
        with self.lock:
            out = refresh_all(self.cfg, self.conn, force=True)
            self.check_alerts()
            return out

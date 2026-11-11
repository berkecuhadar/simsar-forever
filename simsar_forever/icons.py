"""Item and coin icons from Blizzard's render CDN, cached on disk.

The game tells addons an icon's file id (132913), while render.worldofwarcraft.com serves icons by
file name (inv_fabric_wool_03). The community listfile (github.com/wowdev/wow-listfile) maps one to
the other; Simsar Forever downloads it once and keeps only the icon rows.
"""

import json
import logging
import re
import threading
from pathlib import Path

import requests

from . import __version__

log = logging.getLogger("simsar_forever")

LISTFILE_URL = "https://github.com/wowdev/wow-listfile/releases/latest/download/community-listfile.csv"
RENDER_URL = "https://render.worldofwarcraft.com/us/icons/56/{name}.jpg"
HEADERS = {"User-Agent": f"simsar-forever/{__version__} (personal market dashboard)"}
COINS = {"gold": "inv_misc_coin_01", "silver": "inv_misc_coin_03", "copper": "inv_misc_coin_05"}
_ICON_LINE = re.compile(r"^(\d+);interface/icons/([^/;]+)\.blp$", re.IGNORECASE)
_NAME = re.compile(r"^[a-z0-9_\-]+$")


class Icons:
    def __init__(self, data_dir, enabled=True):
        self.dir = Path(data_dir) / "icons"
        self.names_path = Path(data_dir) / "icon-names.json"
        self.enabled = enabled
        self._names = None
        self._lock = threading.Lock()
        self._loading = False
        self.status = "idle"

    def names(self):
        """{file_id: name}, or None while the map is not available yet."""
        if self._names is None and self.names_path.exists():
            try:
                self._names = {int(k): v for k, v in json.loads(self.names_path.read_text()).items()}
            except (OSError, ValueError):
                self._names = None
        return self._names

    def ensure_names(self):
        """Start the one-off listfile download in the background if the map is missing."""
        if not self.enabled or self.names() is not None or self._loading:
            return
        self._loading = True
        threading.Thread(target=self._download_names, name="simsar-forever-icons", daemon=True).start()

    def _download_names(self):
        self.status = "downloading"
        try:
            names = {}
            with requests.get(LISTFILE_URL, headers=HEADERS, stream=True, timeout=60) as r:
                r.raise_for_status()
                for raw in r.iter_lines():
                    m = _ICON_LINE.match(raw.decode("utf-8", "replace"))
                    if m:
                        names[int(m.group(1))] = m.group(2).lower()
            self.names_path.parent.mkdir(parents=True, exist_ok=True)
            self.names_path.write_text(json.dumps(names))
            self._names = names
            self.status = f"ready ({len(names)} icons)"
        except (requests.RequestException, OSError) as e:
            log.warning("icon name download failed: %s", e)
            self.status = f"failed: {e}"
        finally:
            self._loading = False

    def path_for_name(self, name):
        name = name.lower()
        if not _NAME.match(name):
            return None
        target = self.dir / f"{name}.jpg"
        if target.exists():
            return target
        if not self.enabled:
            return None
        with self._lock:
            if target.exists():
                return target
            try:
                r = requests.get(RENDER_URL.format(name=name), headers=HEADERS, timeout=15)
            except requests.RequestException:
                return None
            if r.status_code != 200 or not r.content.startswith(b"\xff\xd8"):
                return None
            self.dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(r.content)
            return target

    def path_for_id(self, file_id):
        names = self.names()
        if names is None:
            self.ensure_names()
            return None
        name = names.get(int(file_id))
        return self.path_for_name(name) if name else None

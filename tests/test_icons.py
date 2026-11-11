import pytest

from simsar_forever import icons


class Resp:
    def __init__(self, status, content=b"", lines=()):
        self.status_code, self.content, self._lines = status, content, lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_listfile_rows_become_an_icon_map(tmp_path, monkeypatch):
    lines = [b"132913;interface/icons/inv_fabric_wool_03.blp", b"12;world/maps/x.adt",
             b"134252;Interface/Icons/INV_Misc_LeatherScrap_02.blp"]
    monkeypatch.setattr(icons.requests, "get", lambda *a, **k: Resp(200, lines=lines))
    ic = icons.Icons(tmp_path)
    ic._download_names()
    assert ic.names() == {132913: "inv_fabric_wool_03", 134252: "inv_misc_leatherscrap_02"}
    assert icons.Icons(tmp_path).names() == ic.names()          # cached on disk


def test_icons_are_fetched_once_and_cached(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, **k):
        calls.append(url)
        return Resp(200, content=b"\xff\xd8 jpeg")

    monkeypatch.setattr(icons.requests, "get", fake_get)
    ic = icons.Icons(tmp_path)
    ic._names = {132913: "inv_fabric_wool_03"}
    p = ic.path_for_id(132913)
    assert p.read_bytes() == b"\xff\xd8 jpeg" and ic.path_for_id(132913) == p
    assert calls == ["https://render.worldofwarcraft.com/us/icons/56/inv_fabric_wool_03.jpg"]
    assert ic.path_for_name("../evil") is None


def test_disabled_icons_never_download(tmp_path, monkeypatch):
    monkeypatch.setattr(icons.requests, "get", lambda *a, **k: pytest.fail("no network"))
    assert icons.Icons(tmp_path, enabled=False).path_for_name("inv_misc_coin_01") is None

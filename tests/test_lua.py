import pytest

from simsar import lua


def test_globals_and_basic_values():
    src = b'''
A = {
  ["name"] = "Light Leather",
  ["count"] = 12,
  ["price"] = 3.5,
  ["neg"] = -4,
  ["hex"] = 0x1F,
  ["yes"] = true,
  ["no"] = false,
  ["gone"] = nil,
}
B = "plain"
'''
    out = lua.loads(src)
    assert out["A"] == {"name": "Light Leather", "count": 12, "price": 3.5, "neg": -4,
                        "hex": 31, "yes": True, "no": False, "gone": None}
    assert out["B"] == "plain"


def test_sequences_become_lists_and_sparse_tables_stay_dicts():
    out = lua.loads(b'X = { "a", "b", { 1, 2 }, }\nY = { [1] = "a", [3] = "c" }\nZ = {}')
    assert out["X"] == ["a", "b", [1, 2]]
    assert out["Y"] == {1: "a", 3: "c"}
    assert out["Z"] == {}


def test_bare_name_keys_and_semicolons():
    out = lua.loads(b"T = { a = 1; b = { c = 'x' } }")
    assert out["T"] == {"a": 1, "b": {"c": "x"}}


def test_escapes():
    out = lua.loads(rb'S = "q\"b\\n\nt\tz\065\x41\
end"')
    assert out["S"] == 'q"b\\n\nt\tzAA\nend'


def test_binary_string_round_trips():
    raw = bytes(range(256))
    escaped = bytearray()
    for b in raw:
        if b == 34:
            escaped += b'\\"'
        elif b == 92:
            escaped += b"\\\\"
        elif b == 10:
            escaped += b"\\n"
        elif b == 13:
            escaped += b"\\r"
        elif b == 0:
            escaped += b"\\0"
        else:
            escaped.append(b)
    out = lua.loads(b'B = "' + bytes(escaped) + b'"')
    assert lua.to_bytes(out["B"]) == raw


def test_comments_and_long_strings():
    out = lua.loads(b"-- header\nA = [[\nline]] --[[ block\ncomment ]]\nB = [==[x]]y]==]")
    assert out == {"A": "line", "B": "x]]y"}


def test_utf8_bom_and_utf8_text():
    out = lua.loads("﻿N = \"Şimşek\"".encode("utf-8"))
    assert out["N"] == "Şimşek"


def test_errors_report_line():
    with pytest.raises(lua.LuaParseError, match="line 2"):
        lua.loads(b"A = 1\nB = {")

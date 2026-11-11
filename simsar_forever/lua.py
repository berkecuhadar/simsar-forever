"""Reader for WoW SavedVariables files.

Only the data subset of Lua is supported: assignments of tables, strings, numbers, booleans
and nil to global names. Nothing is executed.

Strings are decoded as UTF-8 with surrogateescape, so binary payloads (Auctionator stores CBOR
blobs in strings) survive the round trip: ``s.encode("utf-8", "surrogateescape")`` gives back
the exact bytes the game wrote.
"""

import re


class LuaParseError(ValueError):
    pass


_NUMBER = re.compile(
    rb"-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|inf|nan)"
)
_NAME = re.compile(rb"[A-Za-z_][A-Za-z_0-9]*")
_SIMPLE_ESCAPES = {
    ord("a"): 7, ord("b"): 8, ord("f"): 12, ord("n"): 10, ord("r"): 13,
    ord("t"): 9, ord("v"): 11, ord("\\"): 92, ord('"'): 34, ord("'"): 39, 10: 10,
}


def to_bytes(s):
    return s.encode("utf-8", "surrogateescape")


class _Parser:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.n = len(data)

    def error(self, msg):
        line = self.data.count(b"\n", 0, self.pos) + 1
        raise LuaParseError(f"{msg} at line {line}")

    def skip(self):
        data, n = self.data, self.n
        while self.pos < n:
            c = data[self.pos]
            if c in b" \t\r\n":
                self.pos += 1
            elif data.startswith(b"--", self.pos):
                m = re.compile(rb"--\[(=*)\[").match(data, self.pos)
                if m:
                    end = data.find(b"]" + m.group(1) + b"]", m.end())
                    self.pos = n if end < 0 else end + len(m.group(1)) + 2
                else:
                    end = data.find(b"\n", self.pos)
                    self.pos = n if end < 0 else end + 1
            else:
                break

    def peek(self):
        self.skip()
        return self.data[self.pos] if self.pos < self.n else None

    def expect(self, ch):
        if self.peek() != ord(ch):
            self.error(f"expected {ch!r}")
        self.pos += 1

    def string(self):
        data = self.data
        quote = data[self.pos]
        self.pos += 1
        out = bytearray()
        while True:
            if self.pos >= self.n:
                self.error("unterminated string")
            c = data[self.pos]
            if c == quote:
                self.pos += 1
                return out.decode("utf-8", "surrogateescape")
            if c != 92:
                out.append(c)
                self.pos += 1
                continue
            nxt = data[self.pos + 1] if self.pos + 1 < self.n else None
            if nxt in _SIMPLE_ESCAPES:
                out.append(_SIMPLE_ESCAPES[nxt])
                self.pos += 2
            elif nxt == 13:
                out.append(10)
                self.pos += 3 if data[self.pos + 2:self.pos + 3] == b"\n" else 2
            elif nxt is not None and 48 <= nxt <= 57:
                m = re.compile(rb"\d{1,3}").match(data, self.pos + 1)
                value = int(m.group())
                if value > 255:
                    self.error("decimal escape out of range")
                out.append(value)
                self.pos = m.end()
            elif nxt == ord("x"):
                out.append(int(data[self.pos + 2:self.pos + 4], 16))
                self.pos += 4
            elif nxt == ord("z"):
                self.pos += 2
                while self.pos < self.n and data[self.pos] in b" \t\r\n":
                    self.pos += 1
            elif nxt == ord("u"):
                end = data.index(b"}", self.pos)
                out += chr(int(data[self.pos + 3:end], 16)).encode("utf-8")
                self.pos = end + 1
            else:
                self.error(f"bad escape \\{chr(nxt) if nxt else ''}")

    def long_string(self):
        m = re.compile(rb"\[(=*)\[").match(self.data, self.pos)
        close = b"]" + m.group(1) + b"]"
        end = self.data.find(close, m.end())
        if end < 0:
            self.error("unterminated long string")
        body = self.data[m.end():end]
        if body.startswith(b"\r\n"):
            body = body[2:]
        elif body.startswith(b"\n"):
            body = body[1:]
        self.pos = end + len(close)
        return body.decode("utf-8", "surrogateescape")

    def value(self):
        c = self.peek()
        if c is None:
            self.error("unexpected end of file")
        if c in b"\"'":
            return self.string()
        if c == ord("{"):
            return self.table()
        if c == ord("[") and self.data[self.pos + 1:self.pos + 2] in (b"[", b"="):
            return self.long_string()
        m = _NUMBER.match(self.data, self.pos)
        if m and (c in b"-.0123456789" or m.group() in (b"inf", b"nan")):
            self.pos = m.end()
            return _to_number(m.group())
        m = _NAME.match(self.data, self.pos)
        if m:
            self.pos = m.end()
            word = m.group()
            if word == b"true":
                return True
            if word == b"false":
                return False
            if word == b"nil":
                return None
            self.error(f"unexpected name {word.decode(errors='replace')!r}")
        self.error(f"unexpected character {chr(c)!r}")

    def table(self):
        self.expect("{")
        result = {}
        index = 1
        while True:
            c = self.peek()
            if c == ord("}"):
                self.pos += 1
                break
            if c == ord("[") and self.data[self.pos + 1:self.pos + 2] not in (b"[", b"="):
                self.pos += 1
                key = self.value()
                self.expect("]")
                self.expect("=")
                result[key] = self.value()
            else:
                m = _NAME.match(self.data, self.pos)
                after = None
                if m and m.group() not in (b"true", b"false", b"nil"):
                    save = self.pos
                    self.pos = m.end()
                    after = self.peek()
                    if after == ord("="):
                        self.pos += 1
                        result[m.group().decode()] = self.value()
                    else:
                        self.pos = save
                        after = None
                if after is None:
                    result[index] = self.value()
                    index += 1
            c = self.peek()
            if c in (ord(","), ord(";")):
                self.pos += 1
            elif c != ord("}"):
                self.error("expected ',' or '}'")
        return _maybe_list(result)

    def file(self):
        out = {}
        while self.peek() is not None:
            m = _NAME.match(self.data, self.pos)
            if not m:
                self.error("expected a global assignment")
            self.pos = m.end()
            self.expect("=")
            out[m.group().decode()] = self.value()
        return out


def _to_number(raw):
    text = raw.decode()
    if text.lstrip("-").lower().startswith("0x"):
        return int(text, 16)
    if text.lstrip("-") in ("inf", "nan"):
        return float(text)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return float(text)


def _maybe_list(table):
    if table and all(type(k) is int for k in table) and sorted(table) == list(range(1, len(table) + 1)):
        return [table[i] for i in range(1, len(table) + 1)]
    return table


def loads(data):
    if isinstance(data, str):
        data = data.encode("utf-8", "surrogateescape")
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return _Parser(data).file()


def load(path):
    with open(path, "rb") as f:
        return loads(f.read())

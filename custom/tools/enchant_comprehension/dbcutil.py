#!/usr/bin/env python3
"""Minimal WDBC read/write helpers for Classic 1.12 DBC files."""
import struct
from pathlib import Path


class DBC:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.records = []  # list[list[int]] unsigned 32-bit fields
        self.strings = b"\x00"
        self.field_count = 0
        self.record_size = 0
        if path:
            self.load(path)

    def load(self, path):
        data = Path(path).read_bytes()
        magic, recs, fields, recsize, strsize = struct.unpack_from("<4s4I", data, 0)
        if magic != b"WDBC":
            raise ValueError(f"bad magic {magic} in {path}")
        self.field_count = fields
        self.record_size = recsize
        n = recsize // 4
        assert n == fields
        off = 20
        self.records = []
        for i in range(recs):
            self.records.append(list(struct.unpack_from("<" + "I" * n, data, off)))
            off += recsize
        self.strings = data[off : off + strsize]
        if not self.strings.endswith(b"\x00"):
            self.strings += b"\x00"
        if self.strings[:1] != b"\x00":
            self.strings = b"\x00" + self.strings

    def get_string(self, offset):
        if offset <= 0 or offset >= len(self.strings):
            return ""
        end = self.strings.find(b"\x00", offset)
        if end < 0:
            end = len(self.strings)
        return self.strings[offset:end].decode("utf-8", "replace")

    def add_string(self, text):
        raw = text.encode("utf-8") + b"\x00"
        # reuse existing
        idx = self.strings.find(raw)
        if idx >= 0:
            return idx
        off = len(self.strings)
        self.strings += raw
        return off

    def by_id(self, id_field=0):
        return {r[id_field]: r for r in self.records}

    def max_id(self, id_field=0):
        return max((r[id_field] for r in self.records), default=0)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        recs = len(self.records)
        fields = self.field_count
        recsize = self.record_size
        strings = self.strings
        if not strings.endswith(b"\x00"):
            strings += b"\x00"
        header = struct.pack("<4s4I", b"WDBC", recs, fields, recsize, len(strings))
        body = b"".join(struct.pack("<" + "I" * fields, *r) for r in self.records)
        path.write_bytes(header + body + strings)

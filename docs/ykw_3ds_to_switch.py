#!/usr/bin/env python3
"""Convert a Yo-kai Watch 1 (3DS) save into a Switch save container.

A known-good fresh Switch save is bundled as the default template. The converter
keeps Switch-only/platform metadata and transplants the portable game-state
sections from the 3DS save. Inputs are never modified.

This is an independently produced, experimental save converter.  Keep backups.

The save cipher and prime table are adapted from ``yw_save``:
Copyright (c) 2016 togenyan, used under the MIT License. Permission is hereby
granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies, and to
permit persons to whom the Software is furnished to do so, subject to the
following conditions: the above copyright notice and this permission notice
shall be included in all copies or substantial portions of the Software. THE
SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import argparse
import binascii
import os
from pathlib import Path
import struct
import sys
import tempfile


APP_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = APP_DIR / "assets" / "switch_fresh_template.yw"

ODD_PRIMES = (
    3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83,89,97,
    101,103,107,109,113,127,131,137,139,149,151,157,163,167,173,179,181,191,
    193,197,199,211,223,227,229,233,239,241,251,257,263,269,271,277,281,283,
    293,307,311,313,317,331,337,347,349,353,359,367,373,379,383,389,397,401,
    409,419,421,431,433,439,443,449,457,461,463,467,479,487,491,499,503,509,
    521,523,541,547,557,563,569,571,577,587,593,599,601,607,613,617,619,631,
    641,643,647,653,659,661,673,677,683,691,701,709,719,727,733,739,743,751,
    757,761,769,773,787,797,809,811,821,823,827,829,839,853,857,859,863,877,
    881,883,887,907,911,919,929,937,941,947,953,967,971,977,983,991,997,1009,
    1013,1019,1021,1031,1033,1039,1049,1051,1061,1063,1069,1087,1091,1093,
    1097,1103,1109,1117,1123,1129,1151,1153,1163,1171,1181,1187,1193,1201,
    1213,1217,1223,1229,1231,1237,1249,1259,1277,1279,1283,1289,1291,1297,
    1301,1303,1307,1319,1321,1327,1361,1367,1373,1381,1399,1409,1423,1427,
    1429,1433,1439,1447,1451,1453,1459,1471,1481,1483,1487,1489,1493,1499,
    1511,1523,1531,1543,1549,1553,1559,1567,1571,1579,1583,1597,1601,1607,
    1609,1613,1619,1621,
)


class SaveError(Exception):
    pass


class XorShift:
    def __init__(self, seed: int):
        self.s = [0x6C078966, 0xDD5254A5, 0xB9523B81, 0x03DF95B3]
        if seed:
            for i in range(3):
                seed ^= seed >> 30
                seed = (seed * 0x6C078965 + i + 1) & 0xFFFFFFFF
                self.s[i] = seed

    def next(self, modulus: int) -> int:
        x, y = self.s[0], self.s[3]
        self.s[0], self.s[1], self.s[2] = self.s[1], self.s[2], self.s[3]
        x ^= (x << 11) & 0xFFFFFFFF
        x ^= x >> 8
        y ^= y >> 19
        self.s[3] = (x ^ y) & 0xFFFFFFFF
        return self.s[3] % modulus if modulus else self.s[3]


def crypt_body(data: bytes, seed: int) -> bytes:
    rng = XorShift(seed)
    table = list(range(256))
    for _ in range(0x1000):
        value = rng.next(0x10000)
        r1, r2 = value & 0xFF, value >> 8
        if r1 != r2:
            a, b = table[r1], table[r2]
            table[a], table[b] = table[b], table[a]
    out = bytearray(len(data))
    key_a = 0
    for i, value in enumerate(data):
        if not i & 0xFF:
            key_a = ODD_PRIMES[table[(i >> 8) & 0xFF]]
        out[i] = value ^ table[(key_a * (i + 1)) & 0xFF]
    return bytes(out)


def decrypt_save(raw: bytes, label: str) -> bytes:
    if len(raw) < 20:
        raise SaveError(f"{label}: file is too short")
    stored_crc, seed = struct.unpack_from("<II", raw, len(raw) - 8)
    actual_crc = binascii.crc32(raw[:-8]) & 0xFFFFFFFF
    if stored_crc != actual_crc:
        raise SaveError(f"{label}: bad encrypted CRC32 (not a supported .yw save?)")
    return crypt_body(raw[:-8], seed) + raw[-8:]


def encrypt_save(clear: bytes, seed: int) -> bytes:
    if len(clear) < 8:
        raise SaveError("internal error: clear save is too short")
    raw = bytearray(crypt_body(clear[:-8], seed) + b"\0" * 8)
    struct.pack_into("<I", raw, len(raw) - 8, binascii.crc32(raw[:-8]) & 0xFFFFFFFF)
    struct.pack_into("<I", raw, len(raw) - 4, seed)
    return bytes(raw)


def chunk(chunk_type: int, payload: bytes, footer: bytes = b"\xff\xfe\x00\x00") -> bytes:
    return b"\xfe\xff\x00\x00" + struct.pack("<I", (len(payload) << 8) | chunk_type) + payload + footer


def parse_container(clear: bytes, label: str) -> tuple[bytes, dict[int, tuple[bytes, bytes]], bytes]:
    if len(clear) < 20 or clear[:2] != b"\xfe\xff" or clear[4] != 0xF1:
        raise SaveError(f"{label}: unsupported clear-save header")
    outer_size = struct.unpack_from("<I", clear, 4)[0] >> 8
    outer_end = 8 + outer_size
    if outer_end + 12 != len(clear):
        raise SaveError(f"{label}: inconsistent outer size")
    pos = 8
    pieces: list[tuple[int, bytes, bytes]] = []
    while pos < outer_end:
        if clear[pos:pos+2] != b"\xfe\xff":
            raise SaveError(f"{label}: malformed chunk at 0x{pos:x}")
        value = struct.unpack_from("<I", clear, pos + 4)[0]
        kind, size = value & 0xFF, value >> 8
        end = pos + 8 + size
        pieces.append((kind, clear[pos+8:end], clear[end:end+4]))
        pos = end + 4
    if [p[0] for p in pieces] != [0xF2, 0xF3]:
        raise SaveError(f"{label}: expected F2/F3 top-level chunks")
    f3 = pieces[1][1]
    sections: dict[int, tuple[bytes, bytes]] = {}
    pos = 0
    while pos < len(f3):
        if f3[pos:pos+2] != b"\xfe\xff":
            raise SaveError(f"{label}: malformed game-state section")
        value = struct.unpack_from("<I", f3, pos + 4)[0]
        kind, size = value & 0xFF, value >> 8
        end = pos + 8 + size
        if kind in sections or end + 4 > len(f3):
            raise SaveError(f"{label}: invalid section {kind:02x}")
        sections[kind] = (f3[pos+8:end], f3[end:end+4])
        pos = end + 4
    return pieces[0][1], sections, pieces[0][2]


def switch_name(name: bytes) -> bytes:
    text = name.split(b"\0", 1)[0].decode("utf-8", "replace")
    # The Switch release stores Latin player names as full-width uppercase UTF-8.
    text = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text.upper())
    return text.encode("utf-8")[:31]


def expand_yokai_roster(source: bytes, template: bytes) -> bytes:
    """Expand 241 YW1 roster records from 3DS (0x5c) to Switch (0x7c).

    Switch increased the nickname field from 16 to 48 bytes.  Copying the
    section as a flat prefix therefore misaligns every owned Yo-kai after the
    first record.
    """
    old_size, new_size = 0x5C, 0x7C
    if len(source) % old_size or len(template) % new_size:
        raise SaveError("section 07 has an unsupported roster layout")
    if len(source) // old_size != len(template) // new_size:
        raise SaveError("3DS and Switch roster slot counts do not match")
    result = bytearray()
    for pos in range(0, len(source), old_size):
        old_record = source[pos:pos+old_size]
        raw_name = old_record[8:24].split(b"\0", 1)[0]
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            name = raw_name.decode("cp932", "replace")
        encoded_name = name.encode("utf-8")[:47]
        result += old_record[:8]
        result += encoded_name + b"\0" * (48 - len(encoded_name))
        result += old_record[24:]
    return bytes(result)


def expand_parallel_flags(source: bytes, template: bytes) -> bytes:
    """Expand section 0C's four parallel flag tables from 59 to 102 bytes."""
    old_width, new_width, table_count = 59, 102, 4
    if len(source) != old_width * table_count or len(template) != new_width * table_count:
        raise SaveError("section 0C has an unsupported flag-table layout")
    result = bytearray(template)
    for table in range(table_count):
        old_start = table * old_width
        new_start = table * new_width
        result[new_start:new_start+old_width] = source[old_start:old_start+old_width]
    return bytes(result)


def verify_migration(old_meta: bytes, old_sections: dict[int, tuple[bytes, bytes]],
                     new_clear: bytes) -> None:
    """Fail closed if a portable save-data domain was lost or misaligned."""
    new_meta, new_sections, _ = parse_container(new_clear, "converted save")
    if new_meta[0x04:0x14] != old_meta[0x04:0x14]:
        raise SaveError("internal verification failed: player transform")
    if new_meta[0x14:0x18] != old_meta[0x14:0x18]:
        raise SaveError("internal verification failed: playtime")
    if new_meta[0x146] != old_meta[0x44] or new_meta[0x14C] != old_meta[0x44]:
        raise SaveError("internal verification failed: watch rank")
    for kind in (1, 2, 3, 8, 13, 14):
        if new_sections[kind][0] != old_sections[kind][0]:
            raise SaveError(f"internal verification failed: section {kind:02X}")
    old_0b = old_sections[11][0]
    if new_sections[11][0][:len(old_0b)] != old_0b:
        raise SaveError("internal verification failed: section 0B")
    old_0c, new_0c = old_sections[12][0], new_sections[12][0]
    for table in range(4):
        if new_0c[table*102:table*102+59] != old_0c[table*59:(table+1)*59]:
            raise SaveError(f"internal verification failed: section 0C table {table}")
    expected_roster = expand_yokai_roster(old_sections[7][0], new_sections[7][0])
    if new_sections[7][0] != expected_roster:
        raise SaveError("internal verification failed: Yo-kai roster")


def convert(three_ds_raw: bytes, template_raw: bytes, *, fresh_seed: bool = True) -> bytes:
    old = decrypt_save(three_ds_raw, "3DS save")
    template = decrypt_save(template_raw, "Switch template")
    old_meta, old_sections, _ = parse_container(old, "3DS save")
    new_meta, new_sections, meta_footer = parse_container(template, "Switch template")

    if len(three_ds_raw) != 0x96E0:
        raise SaveError(f"3DS save: expected 0x96e0 bytes, got 0x{len(three_ds_raw):x}")
    if len(template_raw) != 0xB9CC:
        raise SaveError(f"Switch template: expected 0xb9cc bytes, got 0x{len(template_raw):x}")
    expected = {1,2,3,7,8,11,12,13,14,15,16}
    if set(old_sections) != expected or set(new_sections) != expected:
        raise SaveError("section layout does not match the supported Yo-kai Watch 1 saves")

    # Retain platform-owned Switch metadata, but carry over the visible identity.
    meta = bytearray(new_meta)
    # The leading transform is shared by both versions: player position and
    # facing/orientation. It must travel with the map identifier below.
    meta[0x04:0x14] = old_meta[0x04:0x14]
    name = switch_name(old_meta[24:40])
    meta[32:64] = b"\0" * 32
    meta[32:32+len(name)] = name
    meta[96:104] = old_meta[56:64]  # current map/room identifier
    meta[0x14:0x18] = old_meta[0x14:0x18]  # accumulated playtime, in seconds
    watch_rank = old_meta[0x44]
    if watch_rank > 5:
        raise SaveError(f"3DS save: invalid watch rank value {watch_rank}")
    # E=0, D=1, C=2, B=3, A=4, S=5. Switch keeps two mirrored copies;
    # updating only one causes the game to retain/fall back to the old rank.
    meta[0x146] = watch_rank
    meta[0x14C] = watch_rank

    # Portable domains:
    #   01: records plus persistent world/event flags (chests/interactables)
    #   02: active story/objective state
    #   03: inventory, equipment, and key items
    #   07: owned Yo-kai roster (record expansion required)
    #   08: party/formation and related records
    #   0B: fixed-layout state with additional Switch capacity
    #   0C: four persistent indexed-state tables (table expansion required)
    #   0D: records/settings state
    #   0E: same-sized opaque game-state/RNG block
    # Sections 0F and 10 are retained from Switch. In both supplied Switch
    # samples they are entirely empty, while 0F has 3DS-only data; transferring
    # that block would introduce unsupported handheld-only state.
    portable = {1,2,3,7,8,11,12,13,14}
    built = []
    for kind in new_sections:
        dst, footer = new_sections[kind]
        if kind in portable:
            src = old_sections[kind][0]
            if kind == 7:
                payload = expand_yokai_roster(src, dst)
            elif kind == 12:
                payload = expand_parallel_flags(src, dst)
            elif len(src) > len(dst):
                raise SaveError(f"section {kind:02x} will not fit the Switch layout")
            else:
                payload = src + dst[len(src):]
        else:
            payload = dst
        built.append(chunk(kind, payload, footer))

    f3 = b"".join(built)
    body = chunk(0xF2, bytes(meta), meta_footer) + chunk(0xF3, f3, b"\xff\xfe\x00\x00")
    clear = chunk(0xF1, body, b"\xff\xfe\x00\x00") + b"\0" * 8
    verify_migration(old_meta, old_sections, clear)
    seed = int.from_bytes(os.urandom(4), "little") if fresh_seed else struct.unpack_from("<I", template_raw, len(template_raw)-4)[0]
    return encrypt_save(clear, seed)


def atomic_write(path: Path, data: bytes, force: bool) -> None:
    if path.exists() and not force:
        raise SaveError(f"output already exists: {path} (use --force to replace it)")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try: os.unlink(tmp_name)
        except FileNotFoundError: pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a Yo-kai Watch 1 3DS save for Nintendo Switch")
    parser.add_argument("three_ds_save", type=Path, help="3DS game*.yw save")
    parser.add_argument("output", type=Path, help="converted Switch .yw output")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE,
                        help="optional custom fresh Switch template")
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    parser.add_argument("--keep-template-seed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = convert(args.three_ds_save.read_bytes(), args.template.read_bytes(), fresh_seed=not args.keep_template_seed)
        # Full post-write-equivalent validation before touching the destination.
        clear = decrypt_save(result, "converted save")
        parse_container(clear, "converted save")
        atomic_write(args.output, result, args.force)
    except (OSError, SaveError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Created {args.output} ({len(result)} bytes). Keep backups of both original saves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

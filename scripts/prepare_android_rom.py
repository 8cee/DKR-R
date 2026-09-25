#!/usr/bin/env python3
"""Normalize and verify a user-owned Diddy Kong Racing US ROM."""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

EXPECTED = {
    "v77": "0cb115d8716dbbc2922fda38e533b9fe63bb9670",
    "v80": "6d96743d46f8c0cd0edb0ec5600b003c89b93755",
}
EXPECTED_SIZE = 12 * 1024 * 1024


def canonicalize(data: bytearray) -> str:
    if len(data) != EXPECTED_SIZE:
        raise ValueError(
            f"DKR retail ROM must be exactly {EXPECTED_SIZE} bytes; got {len(data)}"
        )
    magic = bytes(data[:4])
    if magic == bytes.fromhex("80371240"):
        return "z64"
    if magic == bytes.fromhex("37804012"):
        for index in range(0, len(data), 2):
            data[index], data[index + 1] = data[index + 1], data[index]
        return "v64"
    if magic == bytes.fromhex("40123780"):
        for index in range(0, len(data), 4):
            data[index:index + 4] = reversed(data[index:index + 4])
        return "n64"
    raise ValueError(f"Unrecognized N64 ROM byte order: {magic.hex().upper()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, choices=sorted(EXPECTED))
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()

    data = bytearray(args.input.read_bytes())
    source_order = canonicalize(data)
    digest = hashlib.sha1(data).hexdigest()
    expected = EXPECTED[args.revision]
    if digest != expected:
        raise ValueError(
            f"Normalized ROM SHA-1 is {digest}; DKR US {args.revision} requires {expected}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"[OK] DKR US {args.revision}: {source_order} -> canonical z64")
    print(f"[OK] SHA-1: {digest}")
    print(f"[OK] Private local build ROM: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

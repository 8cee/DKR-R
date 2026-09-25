#!/usr/bin/env python3
"""Build an N64Recomp symbol context from DKR's pinned decomp symbol metadata.

This avoids compiling the DKR N64 ELF. The checked-in decomp symbol list
provides the CPU function boundaries; N64Recomp reads each function's words
straight from the user's canonical ROM.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

SYMBOL_RE = re.compile(
    r"^([A-Za-z_.$][\w.$]*)\s*=\s*(0x[0-9A-Fa-f]+);"
)
TEXT_COMMENT_RE = re.compile(r"^//.*\.text\b")
UCODE_COMMENT_RE = re.compile(r"^//\s*ucode_text\b")

ROM_BASE = 0x1000
VRAM_BASE = 0x80000400


def toml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def parse_functions(symbols_path: pathlib.Path) -> tuple[list[tuple[str, int]], int]:
    functions: list[tuple[str, int]] = []
    in_text = False
    ucode_start: int | None = None

    for raw in symbols_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if TEXT_COMMENT_RE.match(line):
            in_text = True
            continue
        if UCODE_COMMENT_RE.match(line):
            in_text = False
            continue

        match = SYMBOL_RE.match(line)
        if match is None:
            continue

        name = match.group(1)
        address = int(match.group(2), 16)

        if name == "aspMainTextStart":
            ucode_start = address
            break

        if name == "entrypoint" or in_text:
            if address < VRAM_BASE:
                continue
            functions.append((name, address))

    if not functions:
        raise ValueError(f"No DKR CPU text functions found in {symbols_path}")
    if functions[0] != ("entrypoint", VRAM_BASE):
        raise ValueError(
            f"Expected entrypoint at 0x{VRAM_BASE:08X}, got {functions[0]}"
        )
    if ucode_start is None:
        raise ValueError("Could not locate aspMainTextStart / CPU text end")

    addresses = [address for _, address in functions]
    if addresses != sorted(addresses):
        raise ValueError("DKR text symbols are not monotonically increasing")
    if len(addresses) != len(set(addresses)):
        raise ValueError("DKR text symbols contain duplicate function addresses")
    if ucode_start <= addresses[-1]:
        raise ValueError("RSP microcode boundary overlaps CPU text")

    return functions, ucode_start


def merge_policy_functions(
    policy_path: pathlib.Path, functions: list[tuple[str, int]]
) -> tuple[list[tuple[str, int]], dict[str, int]]:
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("schemaVersion") != 1:
        raise ValueError("Unsupported DKR Patch Pipeline policy schema")

    by_name = {name: address for name, address in functions}
    by_address = {address: name for name, address in functions}
    explicit_sizes: dict[str, int] = {}

    for entry in policy.get("manualFunctions", []):
        name = str(entry["name"])
        address = int(str(entry["vram"]), 0)
        size = int(str(entry["size"]), 0)
        explicit_sizes[name] = size

        existing = by_name.get(name)
        if existing is not None:
            if existing != address:
                raise ValueError(
                    f"Manual function {name} address mismatch: "
                    f"symbols=0x{existing:08X}, policy=0x{address:08X}"
                )
            continue

        collision = by_address.get(address)
        if collision is not None:
            raise ValueError(
                f"Manual function {name} collides with {collision} "
                f"at 0x{address:08X}"
            )
        functions.append((name, address))
        by_name[name] = address
        by_address[address] = name

    # The decomp symbol list includes a small number of named internal text
    # labels. When the Patch Pipeline supplies an authoritative manual function
    # span, discard any other symbol strictly inside that span; the ELF path
    # would expose the containing function, not the interior label.
    manual_spans = [
        (
            str(entry["name"]),
            int(str(entry["vram"]), 0),
            int(str(entry["size"]), 0),
        )
        for entry in policy.get("manualFunctions", [])
    ]
    filtered: list[tuple[str, int]] = []
    for name, address in functions:
        interior_owner = next(
            (
                owner
                for owner, start, size in manual_spans
                if name != owner and start < address < start + size
            ),
            None,
        )
        if interior_owner is None:
            filtered.append((name, address))
    functions = filtered

    for entry in policy.get("functionSizes", []):
        explicit_sizes[str(entry["name"])] = int(str(entry["size"]), 0)

    functions.sort(key=lambda item: item[1])
    names = {name for name, _ in functions}
    required: set[str] = set()
    for entry in policy.get("manualFunctions", []):
        required.add(str(entry["name"]))
    for entry in policy.get("functionSizes", []):
        required.add(str(entry["name"]))
    for entry in policy.get("instructionPatches", []):
        required.add(str(entry["function"]))
    for entry in policy.get("functionHooks", []):
        required.add(str(entry["function"]))
    # Stubs and renamed functions must correspond to CPU functions. Ignored
    # entries may also name RSP microcode/data boundary symbols, which are
    # deliberately outside this CPU-only context.
    for key in ("stubs", "renamed"):
        for entry in policy.get(key, []):
            required.add(str(entry["name"]))

    missing = sorted(required.difference(names))
    if missing:
        raise ValueError(
            "Pinned symbol metadata is missing policy function(s): "
            + ", ".join(missing)
        )
    return functions, explicit_sizes


def write_context(
    output: pathlib.Path,
    functions: list[tuple[str, int]],
    text_end: int,
    explicit_sizes: dict[str, int],
) -> None:
    section_size = text_end - VRAM_BASE
    rom_end = ROM_BASE + section_size
    entries: list[str] = []

    for index, (name, address) in enumerate(functions):
        next_address = (
            functions[index + 1][1]
            if index + 1 < len(functions)
            else text_end
        )
        derived_size = next_address - address
        size = explicit_sizes.get(name, derived_size)
        if size <= 0 or size % 4:
            raise ValueError(f"Invalid size for {name}: 0x{size:X}")
        if address + size > text_end:
            raise ValueError(
                f"Function {name} extends beyond CPU text: "
                f"0x{address + size:08X} > 0x{text_end:08X}"
            )
        # Exact policy sizes may intentionally be smaller than the distance to
        # the next symbol, but they may never overlap a distinct next function.
        if size > derived_size:
            raise ValueError(
                f"Explicit size for {name} overlaps the next function: "
                f"0x{size:X} > 0x{derived_size:X}"
            )
        entries.append(
            "    { name = %s, vram = 0x%08X, size = 0x%X },"
            % (toml_quote(name), address, size)
        )

    content = (
        "# Generated from pinned DKR decomp metadata.\n"
        "# No ROM bytes or extracted game assets are stored in this file.\n"
        "[[section]]\n"
        'name = ".main"\n'
        f"rom = 0x{ROM_BASE:08X}\n"
        f"vram = 0x{VRAM_BASE:08X}\n"
        f"size = 0x{section_size:X}\n"
        "functions = [\n"
        + "\n".join(entries)
        + "\n]\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    print(
        f"[OK] {len(functions)} CPU functions, "
        f"ROM 0x{ROM_BASE:X}-0x{rom_end:X}, "
        f"VRAM 0x{VRAM_BASE:08X}-0x{text_end:08X}"
    )
    print(f"[OK] N64Recomp symbol context: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", required=True, type=pathlib.Path)
    parser.add_argument("--policy", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()

    functions, text_end = parse_functions(args.symbols)
    functions, explicit_sizes = merge_policy_functions(args.policy, functions)
    write_context(args.output, functions, text_end, explicit_sizes)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

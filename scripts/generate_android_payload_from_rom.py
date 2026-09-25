#!/usr/bin/env python3
"""Generate one DKR CPU payload from a canonical ROM and pinned symbol metadata."""
from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SYMBOL_CONTEXT_TOOL = ROOT / "scripts" / "generate_dkr_symbol_context.py"
CONFIG_TOOL = ROOT / "scripts" / "generate_recomp_config.py"
RUNTIME = ROOT / "runtime-recomp"

SYMBOL_RE = re.compile(r"^([A-Za-z_.$][\w.$]*)\s*=\s*(0x[0-9A-Fa-f]+);")


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def find_symbol(path: pathlib.Path, name: str) -> int:
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SYMBOL_RE.match(raw.strip())
        if match and match.group(1) == name:
            return int(match.group(2), 16)
    raise RuntimeError(f"Symbol {name} was not found in {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, choices=("v77", "v80"))
    parser.add_argument("--rom", required=True, type=pathlib.Path)
    parser.add_argument("--decomp-root", required=True, type=pathlib.Path)
    parser.add_argument("--n64recomp", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()

    symbols = (
        args.decomp_root
        / "ver"
        / "symbols"
        / f"symbol_addrs.us.{args.revision}.txt"
    )
    policy = RUNTIME / f"dkr.us.{args.revision}.recomp-policy.json"
    if not symbols.is_file():
        raise RuntimeError(f"Pinned DKR symbols are missing: {symbols}")
    if not policy.is_file():
        raise RuntimeError(f"DKR recomp policy is missing: {policy}")
    if not args.n64recomp.is_file():
        raise RuntimeError(f"N64Recomp executable is missing: {args.n64recomp}")

    workspace = ROOT / "build" / "android-recomp" / args.revision
    context = workspace / "symbols.toml"
    config = workspace / "recomp.toml"

    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)

    run([
        sys.executable,
        str(SYMBOL_CONTEXT_TOOL),
        "--symbols", str(symbols),
        "--policy", str(policy),
        "--output", str(context),
    ])

    mainproc = find_symbol(symbols, "mainproc")
    run([
        sys.executable,
        str(CONFIG_TOOL),
        "--policy", str(policy),
        "--symbols-file", str(context),
        "--rom", str(args.rom.resolve()),
        "--output-functions", str(args.output.resolve()),
        "--entrypoint", f"0x{mainproc:08X}",
        "--output", str(config),
    ])

    run([str(args.n64recomp.resolve()), str(config.resolve())])

    sources = list(args.output.rglob("*.c")) + list(args.output.rglob("*.cpp"))
    funcs = list(args.output.rglob("funcs.h"))
    if not sources or not funcs:
        raise RuntimeError(
            f"N64Recomp did not produce a usable {args.revision} payload"
        )

    print(
        f"[OK] DKR US {args.revision}: {len(sources)} generated CPU source files"
    )
    print(f"[OK] Payload: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

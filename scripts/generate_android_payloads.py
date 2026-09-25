#!/usr/bin/env python3
"""Generate DKR-R v77/v80 CPU payloads for a local Android full-runtime build.

The ROM and ELF inputs stay local. This script only writes N64Recomp-generated
C/C++ sources to the requested output directories.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_TOOL = ROOT / "scripts" / "generate_recomp_config.py"
RUNTIME = ROOT / "runtime-recomp"


def run(command: list[str], *, capture: bool = False) -> str:
    print("+", " ".join(command))
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout, file=sys.stderr)
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        )
    return (result.stdout or "").strip()


def resolve_mainproc(nm: str, elf: pathlib.Path) -> str:
    output = run([nm, "-n", "--defined-only", str(elf)], capture=True)
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1] == "mainproc":
            return "0x" + parts[0].upper().lstrip("0X")
    raise RuntimeError(f"Could not resolve mainproc in ELF: {elf}")


def use_mdebug(readelf: str | None, elf: pathlib.Path) -> bool:
    if not readelf:
        return False
    output = run([readelf, "-S", "-W", str(elf)], capture=True)
    return ".mdebug" in output


def generate(
    *,
    revision: str,
    elf: pathlib.Path,
    rom: pathlib.Path,
    output: pathlib.Path,
    policy: pathlib.Path,
    n64recomp: pathlib.Path,
    nm: str,
    readelf: str | None,
) -> None:
    if not elf.is_file():
        raise RuntimeError(f"{revision} ELF does not exist: {elf}")
    if not rom.is_file():
        raise RuntimeError(f"{revision} ROM does not exist: {rom}")
    if not policy.is_file():
        raise RuntimeError(f"{revision} recomp policy does not exist: {policy}")

    entrypoint = resolve_mainproc(nm, elf)
    mdebug = use_mdebug(readelf, elf)
    config = output.parent / f"{revision}.android.toml"

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(CONFIG_TOOL),
        "--policy",
        str(policy),
        "--elf",
        str(elf),
        "--rom",
        str(rom),
        "--output-functions",
        str(output),
        "--entrypoint",
        entrypoint,
        "--output",
        str(config),
    ]
    if mdebug:
        command.append("--use-mdebug")
    run(command)

    print(f"[{revision}] mainproc: {entrypoint}")
    print(f"[{revision}] .mdebug: {mdebug}")
    run([str(n64recomp), str(config)])

    sources = list(output.rglob("*.c")) + list(output.rglob("*.cpp"))
    if not sources or not any(path.name == "funcs.h" for path in output.rglob("funcs.h")):
        raise RuntimeError(
            f"{revision} N64Recomp completed without a usable generated payload: {output}"
        )
    print(f"[OK] {revision}: {len(sources)} generated source files -> {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n64recomp", required=True, type=pathlib.Path)
    parser.add_argument("--v77-elf", required=True, type=pathlib.Path)
    parser.add_argument("--v77-rom", required=True, type=pathlib.Path)
    parser.add_argument("--v80-elf", type=pathlib.Path)
    parser.add_argument("--v80-rom", type=pathlib.Path)
    parser.add_argument(
        "--output-root",
        type=pathlib.Path,
        default=ROOT / "build" / "android-generated",
    )
    parser.add_argument(
        "--nm",
        default="mips-linux-gnu-nm",
        help="MIPS nm executable used to resolve mainproc",
    )
    parser.add_argument(
        "--readelf",
        default="mips-linux-gnu-readelf",
        help="MIPS readelf executable used to detect .mdebug; pass an empty string to disable",
    )
    args = parser.parse_args()

    if not args.n64recomp.is_file():
        raise RuntimeError(f"N64Recomp executable does not exist: {args.n64recomp}")
    if shutil.which(args.nm) is None:
        raise RuntimeError(f"nm executable was not found on PATH: {args.nm}")
    readelf = args.readelf or None
    if readelf and shutil.which(readelf) is None:
        raise RuntimeError(f"readelf executable was not found on PATH: {readelf}")

    output_root = args.output_root.resolve()
    generate(
        revision="v77",
        elf=args.v77_elf.resolve(),
        rom=args.v77_rom.resolve(),
        output=output_root / "v77",
        policy=RUNTIME / "dkr.us.v77.recomp-policy.json",
        n64recomp=args.n64recomp.resolve(),
        nm=args.nm,
        readelf=readelf,
    )
    if (args.v80_elf is None) != (args.v80_rom is None):
        raise RuntimeError("--v80-elf and --v80-rom must be supplied together")
    if args.v80_elf is not None:
        generate(
            revision="v80",
            elf=args.v80_elf.resolve(),
            rom=args.v80_rom.resolve(),
            output=output_root / "v80",
            policy=RUNTIME / "dkr.us.v80.recomp-policy.json",
            n64recomp=args.n64recomp.resolve(),
            nm=args.nm,
            readelf=readelf,
        )

    print("")
    print("[OK] Android CPU payload generation complete.")
    print(f"v77: {output_root / 'v77'}")
    if args.v80_elf is not None:
        print(f"v80: {output_root / 'v80'}")
    else:
        print("v80: not generated (v77-only Android build)")
    print("No ROM bytes were copied into the generated output directories.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

# Windows ROM-to-APK build

This is the shortest full Android build path on Windows. It does **not** require WSL or Ubuntu.

The pinned N64Recomp revision can translate DKR directly from the user's ROM when supplied with a function-symbol context. DKR-R generates that context from the pinned DKR decomp repository's checked-in US symbol metadata, so compiling the original N64 ELF is not required for the Android build.

## US v1.0 / v77

Run in PowerShell:

    .\scripts\Build-Android-From-Rom.ps1 -RomV77 "C:\path\to\Diddy Kong Racing.z64"

The script validates and normalizes z64/v64/n64 byte order, requires the exact US v1.0 SHA-1, generates the v77 CPU payload, and builds the ARM64 APK.

## Optional Rev A / v80 support

    .\scripts\Build-Android-From-Rom.ps1 -RomV77 "C:\path\to\DKR-US-1.0.z64" -RomV80 "C:\path\to\DKR-US-1.1.z64"

Accepted SHA-1 values after byte-order normalization:

- US v1.0 / v77: `0cb115d8716dbbc2922fda38e533b9fe63bb9670`
- US Rev A / v80: `6d96743d46f8c0cd0edb0ec5600b003c89b93755`

## What stays private

The ROM is never committed and is never packaged into the APK. Canonical local copies are placed under the ignored `build/android-roms/` directory only to feed N64Recomp. Generated CPU C/C++ sources are placed under `build/android-generated/`, which is also ignored.

The symbol context contains names, addresses and derived function sizes from the pinned open-source decomp metadata; it contains no ROM bytes or extracted game assets.

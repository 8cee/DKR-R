# Full Android runtime build

## Recommended Windows path

For a normal Android build, start directly from your legally obtained DKR US
v1.0 ROM. No WSL/Ubuntu or separately built N64 ELF is required:

```powershell
.\scripts\Build-Android-From-Rom.ps1 -RomV77 "C:\path\to\Diddy Kong Racing.z64"
```

Add `-RomV80` only if Rev A support is wanted in the same APK.

The ROM-direct pipeline uses the pinned DKR decomp's checked-in symbol metadata
to build an N64Recomp symbol context, then N64Recomp reads the CPU instructions
from the locally validated ROM. ROM bytes never enter Git or the APK.

The public Android workflow deliberately stays ROM-free. It validates the
Android/NDK/RT64/N64ModernRuntime integration without embedding Diddy Kong
Racing game data.

A full local build consumes the N64Recomp CPU source directories that DKR-R's
existing runtime-preparation tooling generated from the user's own legally
obtained ROM(s). Those generated payload directories remain local and are not
added to Git.

## Build

From PowerShell:

```powershell
.\scripts\Build-Android-Full.ps1 \
  -GeneratedV77 C:\path\to\RecompiledFuncs-v77

# Optional Rev A support:
.\scripts\Build-Android-Full.ps1 \
  -GeneratedV77 C:\path\to\RecompiledFuncs-v77 \
  -GeneratedV80 C:\path\to\RecompiledFuncs-v80
```

Use `-Configuration Release` for a release APK.

The script:

1. validates the required v77 source tree and optional v80 source tree contain code and `funcs.h`;
2. detects the Android SDK and, when `sdkmanager` is available, ensures API 35, build-tools 35.0.0, NDK 27.2.12479018 and CMake 3.22.1 are installed;
3. prepares every revision pinned in `dependencies.lock.json`;
4. applies the checksummed dependency patch manifest;
5. builds RT64's host-side `file_to_c` with the resolved host CMake;
6. enables `DKR_ANDROID_FULL_RUNTIME`;
7. passes the generated v77 directory and optional v80 directory into the Android CMake build;
8. uses a project Gradle wrapper when available, a system Gradle when installed, or downloads and SHA-256-verifies the pinned Gradle 8.10.2 distribution into the ignored build cache;
9. builds the ARM64 APK.

The complete runtime is linked through the Android-safe `DKRPortGame` static
target and enters through `DkrSdlActivity -> DKRAndroidHostMain -> DkrMain`.
ROM selection at runtime uses Android's Storage Access Framework and DKR-R's
native v77/v80 hash validation.

ROM files and extracted game assets are never copied into the repository or
packaged into the APK.

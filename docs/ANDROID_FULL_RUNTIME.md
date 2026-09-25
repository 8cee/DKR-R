# Full Android runtime build

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
  -GeneratedV77 C:\path\to\RecompiledFuncs-v77 \
  -GeneratedV80 C:\path\to\RecompiledFuncs-v80
```

Use `-Configuration Release` for a release APK.

The script:

1. validates that both generated source trees contain code and `funcs.h`;
2. prepares every revision pinned in `dependencies.lock.json`;
3. applies the checksummed dependency patch manifest;
4. builds RT64's host-side `file_to_c`;
5. enables `DKR_ANDROID_FULL_RUNTIME`;
6. passes the two generated CPU directories into the Android CMake build;
7. builds the ARM64 APK.

The complete runtime is linked through the Android-safe `DKRPortGame` static
target and enters through `DkrSdlActivity -> DKRAndroidHostMain -> DkrMain`.
ROM selection at runtime uses Android's Storage Access Framework and DKR-R's
native v77/v80 hash validation.

ROM files and extracted game assets are never copied into the repository or
packaged into the APK.

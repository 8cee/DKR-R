# Android runtime integration plan

The APK/bootstrap is deliberately independent of the desktop launcher while the native runtime is ported.

## Reusable DKR-R systems

The existing runtime already provides:

- exact ROM identity for US v1.0 (v77) and US Rev A/v1.1 (v80), including z64/v64/n64 normalization and XXH3 validation;
- save manager and controller-pak import/export;
- custom tracks and legacy mod launch;
- controller assignment/mapping policies and SDL3 input client;
- widescreen, presentation and texture-pack policies;
- N64ModernRuntime/librecomp registration and generated CPU/RSP payloads.

Android should call these systems rather than fork their formats.

## Android bridge milestones

1. **Bootstrap (implemented)**: Gradle APK, ARM64 JNI library, private storage, ROM import, controller-event capture, mod catalog.
2. **ROM handoff (partially implemented)**: Java performs safe container/header/size screening. Final acceptance must call the existing native `rom::inspect` so only the known XXH3 identities `0x68512C37A6FDA951` and `0xB55D4348B9AB07F5` launch.
3. **Runtime library**: refactor the desktop `DkrMain` orchestration into a platform-neutral entry function callable from JNI. Keep desktop `main/WinMain` as thin wrappers.
4. **Platform backend**: implement Android lifecycle/window/audio/input in `runtime_platform`, using the Activity/ANativeWindow and Android-safe SDL3 facilities where appropriate.
5. **Renderer**: build an Android Vulkan path. RT64 must be validated dependency-by-dependency; desktop SDL2/window assumptions cannot simply be linked into the APK.
6. **Lifecycle**: Activity pause/resume, focus loss, audio suspension, surface recreation and clean shutdown must map to the runtime thread.
7. **Saves/mods**: configure the existing save manager under the app-private directory. Keep librecomp `.nrm` mods distinct from DKR-R custom tracks and Android catalog packages.
8. **Packaging**: stage only freely redistributable runtime assets. Never package a ROM or extracted Nintendo/Rare assets.

## Current storage

`/data/user/0/com.eightcee.dkrrecomp/files/`

contains `roms/`, `saves/`, `cache/`, `logs/`, `screenshots/`, `custom-tracks/` and `mods/`.

The Android catalog installer is designed for HTTPS downloads, SHA-256 verification, archive-size limits, zip-slip rejection, staging, atomic activation and rollback of the previous installed version.

# DKR-R Android port

The `android` branch contains the Android/ARM64 port layer for DKR-R.

## Current milestone

The first milestone intentionally separates the Android application shell from the desktop runtime so CI can produce an installable APK while runtime dependencies are ported incrementally.

Implemented:

- Android application id: `com.eightcee.dkrrecomp`
- ARM64-v8a native library
- app-private ROM, saves, cache, and mod directories
- Storage Access Framework ROM import
- HTTP mod-catalog bootstrap
- Android GitHub Actions APK build
- no copyrighted ROM/game data in the repository or APK

Planned runtime integration:

1. validate supported DKR ROM revisions and hashes;
2. make N64ModernRuntime build under the Android NDK;
3. bring SDL3 Android input/lifecycle integration online;
4. select an Android-capable Vulkan rendering path and integrate RT64-compatible functionality where portable;
5. expose runtime launch/pause/resume through JNI;
6. connect controller, touch overlay, save management, graphics settings and mods.

## Local build

Open the `android/` directory in Android Studio, install SDK 35 + NDK, and build the app module.

GitHub Actions also builds a debug APK from the `android` branch.

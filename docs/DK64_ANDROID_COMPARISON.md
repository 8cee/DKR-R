# DK64 Android comparison

Reference implementation: `8cee/dk64-recomp-android`.

DKR-R should reuse the proven Android architecture where the underlying
runtime contracts match, while keeping DKR-R's own save, mod, launcher,
netplay, controller and custom-track systems authoritative.

## Patterns to carry over

- Native-first launch instead of a permanent Java setup frontend.
- Android Storage Access Framework bridged into native menus through JNI.
- ARM64-only NDK build and 16 KiB ELF page alignment.
- Android lifecycle gate around renderer presentation.
- Native crash logging before Android tombstones.
- External controllers plus a virtual N64 touch pad.
- Patch pinned dependencies at the Android boundary; do not edit vendored
  upstream trees directly.
- Host code-generation phase followed by NDK/Gradle APK phase.
- Optional custom Vulkan driver support only after the base Vulkan backend is
  stable on DKR-R.

## DKR-specific differences

- DKR-R already owns ROM v77/v80 inspection and z64/v64/n64 normalization.
- DKR-R already owns Adventure EEPROM and Controller Pak import/export/bundles.
- DKR-R has custom tracks and legacy mod launch semantics that must remain
  separate from librecomp .nrm content.
- DKR-R has netplay save isolation and manifest rules that Android must not
  bypass.

## Runtime entry

`DkrMain(int argc, char** argv)` is now declared as the platform-neutral
launcher/runtime entry. Desktop still wraps it with `main/WinMain`; Android
will call the same entry from its native activity/SDL layer.

# Android SAF bridge

DKR-R Android now includes a non-blocking native-to-Java Storage Access
Framework bridge modeled after the proven design in `8cee/dk64-recomp-android`.

Native runtime code can call:

`dkr::android::filedialog::request(kind, callback)`

The bridge posts the Android DocumentsUI picker on the Java UI thread. The
selected input is copied into app-private cache under `cache/saf-inbox/`, then
its normal filesystem path is published back to native code. The callback is
not invoked from JNI; `process_pending()` dispatches it later from the native
frame/update context. This avoids blocking a render/UI thread across
Activity pause/resume.

The current bridge supports staged inputs for ROMs, Adventure saves, DKR-R save
bundles, Controller Pak images and mod packages. Native DKR-R menu integration
will consume this bridge once the full launcher/runtime is linked into the APK.

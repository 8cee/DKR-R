#pragma once

#include <functional>
#include <string>

namespace dkr::android::filedialog {

enum class Kind {
    Rom = 0,
    AdventureSave = 1,
    SaveBundle = 2,
    ControllerPak = 3,
    ModPackage = 4,
    TexturePack = 5,
    CrtFilter = 6,
    ControllerMappings = 7,
    AdventureSaveExport = 20,
    SaveBundleExport = 21,
    ControllerMappingsExport = 22,
};

using Callback = std::function<void(bool ok, const std::string& staged_path)>;

// Non-blocking single-slot Android SAF request. The Java side stages selected
// input into app-private cache and publishes a normal filesystem path.
bool request(Kind kind, Callback callback);

// Export a private staging file through ACTION_CREATE_DOCUMENT. Java copies the
// file into the selected content:// destination and reports completion back
// through the same single-slot callback state.
bool request_export(Kind kind, const std::string& source_path,
                    const std::string& suggested_name, Callback callback);

// Call from the native frame/update loop once the DKR-R launcher is linked.
void process_pending();

// Installed from MainActivity.nativeBridgeInit on the Java UI thread.
void set_java_vm(void* vm);

} // namespace dkr::android::filedialog

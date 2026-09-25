#include "android_paths.hpp"

#include <mutex>
#include <system_error>

namespace dkr::android {
namespace {
std::mutex g_mutex;
Paths g_paths;
}

void configure_paths(std::filesystem::path files,
                     std::filesystem::path external_files) {
    std::scoped_lock lock(g_mutex);
    g_paths.files = std::move(files);
    g_paths.external_files = std::move(external_files);

    std::error_code error;
    for (const auto& dir : {
            g_paths.saves(), g_paths.mods(), g_paths.cache(), g_paths.logs(),
            g_paths.custom_tracks(), g_paths.files / "roms",
            g_paths.files / "save-backups", g_paths.files / "screenshots"}) {
        std::filesystem::create_directories(dir, error);
        error.clear();
    }
}

Paths paths() {
    std::scoped_lock lock(g_mutex);
    return g_paths;
}

} // namespace dkr::android

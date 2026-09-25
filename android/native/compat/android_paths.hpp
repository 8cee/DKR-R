#pragma once

#include <filesystem>

namespace dkr::android {

struct Paths {
    std::filesystem::path files;
    std::filesystem::path external_files;

    [[nodiscard]] std::filesystem::path config() const { return files; }
    [[nodiscard]] std::filesystem::path saves() const { return files / "saves"; }
    [[nodiscard]] std::filesystem::path mods() const { return files / "mods"; }
    [[nodiscard]] std::filesystem::path cache() const { return files / "cache"; }
    [[nodiscard]] std::filesystem::path logs() const { return files / "logs"; }
    [[nodiscard]] std::filesystem::path custom_tracks() const { return files / "custom-tracks"; }
};

void configure_paths(std::filesystem::path files,
                     std::filesystem::path external_files = {});
[[nodiscard]] Paths paths();

} // namespace dkr::android

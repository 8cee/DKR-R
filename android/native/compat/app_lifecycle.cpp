#include "app_lifecycle.hpp"

#include <atomic>

namespace dkr::android::lifecycle {
namespace {
std::atomic<bool> g_resumed{false};
std::atomic<bool> g_surface_available{false};
}

void set_resumed(bool value) {
    g_resumed.store(value, std::memory_order_release);
}

void set_surface_available(bool value) {
    g_surface_available.store(value, std::memory_order_release);
}

bool resumed() {
    return g_resumed.load(std::memory_order_acquire);
}

bool surface_available() {
    return g_surface_available.load(std::memory_order_acquire);
}

bool presentation_allowed() {
    return resumed() && surface_available();
}

} // namespace dkr::android::lifecycle

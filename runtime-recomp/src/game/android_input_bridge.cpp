#include "android_input_bridge.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <mutex>

namespace dkr::runtime::android_input {
namespace {

constexpr std::uint16_t kButtonA = 0x8000;
constexpr std::uint16_t kButtonB = 0x4000;
constexpr std::uint16_t kButtonZ = 0x2000;
constexpr std::uint16_t kButtonStart = 0x1000;
constexpr std::uint16_t kDpadUp = 0x0800;
constexpr std::uint16_t kDpadDown = 0x0400;
constexpr std::uint16_t kDpadLeft = 0x0200;
constexpr std::uint16_t kDpadRight = 0x0100;
constexpr std::uint16_t kButtonL = 0x0020;
constexpr std::uint16_t kButtonR = 0x0010;
constexpr std::uint16_t kCUp = 0x0008;
constexpr std::uint16_t kCDown = 0x0004;
constexpr std::uint16_t kCLeft = 0x0002;
constexpr std::uint16_t kCRight = 0x0001;

// Android KeyEvent gamepad constants. Keep these numeric here so this runtime
// source stays independent from Java/NDK framework headers.
constexpr int kKeyDpadUp = 19;
constexpr int kKeyDpadDown = 20;
constexpr int kKeyDpadLeft = 21;
constexpr int kKeyDpadRight = 22;
constexpr int kKeyButtonA = 96;
constexpr int kKeyButtonB = 97;
constexpr int kKeyButtonX = 99;
constexpr int kKeyButtonY = 100;
constexpr int kKeyButtonL1 = 102;
constexpr int kKeyButtonR1 = 103;
constexpr int kKeyButtonL2 = 104;
constexpr int kKeyButtonR2 = 105;
constexpr int kKeyButtonStart = 108;

std::mutex g_mutex;
constexpr std::size_t kControllerCount = 4;

struct ControllerState {
    int device_id = -1;
    std::array<bool, 512> keys{};
    float left_x = 0.0F;
    float left_y = 0.0F;
    float right_x = 0.0F;
    float right_y = 0.0F;
    float left_trigger = 0.0F;
    float right_trigger = 0.0F;
};

std::array<ControllerState, kControllerCount> g_controllers{};

ControllerState* controller_for_device(int device_id, bool create) {
    if (device_id < 0) return nullptr;
    for (auto& controller : g_controllers) {
        if (controller.device_id == device_id) return &controller;
    }
    if (!create) return nullptr;
    for (auto& controller : g_controllers) {
        if (controller.device_id < 0) {
            controller = {};
            controller.device_id = device_id;
            return &controller;
        }
    }
    return nullptr;
}

float shaped(float value) {
    constexpr float deadzone = 0.14F;
    value = std::clamp(value, -1.0F, 1.0F);
    const float magnitude = std::abs(value);
    if (magnitude <= deadzone) return 0.0F;
    const float normalized = (magnitude - deadzone) / (1.0F - deadzone);
    return std::copysign(std::clamp(normalized, 0.0F, 1.0F), value);
}

bool key(const ControllerState& controller, int code) {
    return code >= 0 &&
           code < static_cast<int>(controller.keys.size()) &&
           controller.keys[static_cast<std::size_t>(code)];
}

} // namespace

void set_key(int device_id, int android_key_code, bool pressed) {
    if (android_key_code < 0 || android_key_code >= 512) return;
    std::scoped_lock lock(g_mutex);
    ControllerState* controller = controller_for_device(device_id, true);
    if (controller == nullptr) return;
    controller->keys[static_cast<std::size_t>(android_key_code)] = pressed;
}

void set_axes(int device_id, float left_x, float left_y,
              float right_x, float right_y,
              float left_trigger, float right_trigger) {
    std::scoped_lock lock(g_mutex);
    ControllerState* controller = controller_for_device(device_id, true);
    if (controller == nullptr) return;
    controller->left_x = left_x;
    controller->left_y = left_y;
    controller->right_x = right_x;
    controller->right_y = right_y;
    controller->left_trigger = std::clamp(left_trigger, 0.0F, 1.0F);
    controller->right_trigger = std::clamp(right_trigger, 0.0F, 1.0F);
}

void remove_device(int device_id) {
    std::scoped_lock lock(g_mutex);
    for (auto& controller : g_controllers) {
        if (controller.device_id == device_id) {
            controller = {};
            return;
        }
    }
}

void clear() {
    std::scoped_lock lock(g_mutex);
    g_controllers = {};
}

Sample sample(std::size_t player) {
    std::scoped_lock lock(g_mutex);
    Sample out{};
    if (player >= g_controllers.size()) return out;
    const ControllerState& controller = g_controllers[player];
    if (controller.device_id < 0) return out;

    if (key(controller, kKeyButtonA)) out.buttons |= kButtonA;
    if (key(controller, kKeyButtonX)) out.buttons |= kButtonB;
    if (key(controller, kKeyButtonStart)) out.buttons |= kButtonStart;
    if (key(controller, kKeyDpadUp)) out.buttons |= kDpadUp;
    if (key(controller, kKeyDpadDown)) out.buttons |= kDpadDown;
    if (key(controller, kKeyDpadLeft)) out.buttons |= kDpadLeft;
    if (key(controller, kKeyDpadRight)) out.buttons |= kDpadRight;
    if (key(controller, kKeyButtonL1)) out.buttons |= kButtonL;
    if (key(controller, kKeyButtonR1)) out.buttons |= kButtonR;

    if (controller.left_trigger > 0.50F ||
        key(controller, kKeyButtonL2)) {
        out.buttons |= kButtonZ;
    }

    const float rx = shaped(controller.right_x);
    const float ry = shaped(controller.right_y);
    if (ry < -0.50F) out.buttons |= kCUp;
    if (ry > 0.50F) out.buttons |= kCDown;
    if (rx < -0.50F) out.buttons |= kCLeft;
    if (rx > 0.50F) out.buttons |= kCRight;

    if (key(controller, kKeyButtonY)) out.buttons |= kCUp;
    if (key(controller, kKeyButtonB)) out.buttons |= kCRight;
    if (key(controller, kKeyButtonR2) ||
        controller.right_trigger > 0.50F) {
        out.buttons |= kCDown;
    }

    out.stick_x = shaped(controller.left_x);
    out.stick_y = -shaped(controller.left_y);
    return out;
}

} // namespace dkr::runtime::android_input

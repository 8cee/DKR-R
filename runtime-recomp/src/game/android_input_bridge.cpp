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
std::array<bool, 512> g_keys{};
float g_left_x = 0.0F;
float g_left_y = 0.0F;
float g_right_x = 0.0F;
float g_right_y = 0.0F;
float g_left_trigger = 0.0F;
float g_right_trigger = 0.0F;

float shaped(float value) {
    constexpr float deadzone = 0.14F;
    value = std::clamp(value, -1.0F, 1.0F);
    const float magnitude = std::abs(value);
    if (magnitude <= deadzone) return 0.0F;
    const float normalized = (magnitude - deadzone) / (1.0F - deadzone);
    return std::copysign(std::clamp(normalized, 0.0F, 1.0F), value);
}

bool key(int code) {
    return code >= 0 && code < static_cast<int>(g_keys.size()) &&
           g_keys[static_cast<std::size_t>(code)];
}

} // namespace

void set_key(int android_key_code, bool pressed) {
    if (android_key_code < 0 ||
        android_key_code >= static_cast<int>(g_keys.size())) return;
    std::scoped_lock lock(g_mutex);
    g_keys[static_cast<std::size_t>(android_key_code)] = pressed;
}

void set_axes(float left_x, float left_y, float right_x, float right_y,
              float left_trigger, float right_trigger) {
    std::scoped_lock lock(g_mutex);
    g_left_x = left_x;
    g_left_y = left_y;
    g_right_x = right_x;
    g_right_y = right_y;
    g_left_trigger = std::clamp(left_trigger, 0.0F, 1.0F);
    g_right_trigger = std::clamp(right_trigger, 0.0F, 1.0F);
}

void clear() {
    std::scoped_lock lock(g_mutex);
    g_keys.fill(false);
    g_left_x = g_left_y = g_right_x = g_right_y = 0.0F;
    g_left_trigger = g_right_trigger = 0.0F;
}

Sample sample() {
    std::scoped_lock lock(g_mutex);
    Sample out{};

    // Match DKR-R's default SDL controller policy.
    if (key(kKeyButtonA)) out.buttons |= kButtonA;
    if (key(kKeyButtonX)) out.buttons |= kButtonB;
    if (key(kKeyButtonStart)) out.buttons |= kButtonStart;
    if (key(kKeyDpadUp)) out.buttons |= kDpadUp;
    if (key(kKeyDpadDown)) out.buttons |= kDpadDown;
    if (key(kKeyDpadLeft)) out.buttons |= kDpadLeft;
    if (key(kKeyDpadRight)) out.buttons |= kDpadRight;
    if (key(kKeyButtonL1)) out.buttons |= kButtonL;
    if (key(kKeyButtonR1)) out.buttons |= kButtonR;

    // DKR-R desktop defaults map Z to the left trigger. Keep L2 key fallback
    // for controllers that expose digital trigger buttons instead of axes.
    if (g_left_trigger > 0.50F || key(kKeyButtonL2)) out.buttons |= kButtonZ;

    const float rx = shaped(g_right_x);
    const float ry = shaped(g_right_y);
    if (ry < -0.50F) out.buttons |= kCUp;
    if (ry > 0.50F) out.buttons |= kCDown;
    if (rx < -0.50F) out.buttons |= kCLeft;
    if (rx > 0.50F) out.buttons |= kCRight;

    // Face-button fallbacks make controllers without a useful right stick
    // practical on phones/handhelds without changing the primary mapping.
    if (key(kKeyButtonY)) out.buttons |= kCUp;
    if (key(kKeyButtonB)) out.buttons |= kCRight;
    if (key(kKeyButtonR2) || g_right_trigger > 0.50F) out.buttons |= kCDown;

    out.stick_x = shaped(g_left_x);
    // Android joystick Y is negative upward; DKR-R expects positive upward.
    out.stick_y = -shaped(g_left_y);
    return out;
}

} // namespace dkr::runtime::android_input

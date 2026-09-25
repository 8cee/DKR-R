#pragma once

#include <cstdint>

namespace dkr::runtime::android_input {

struct Sample {
    std::uint16_t buttons = 0;
    float stick_x = 0.0F;
    float stick_y = 0.0F;
};

void set_key(int android_key_code, bool pressed);
void set_axes(float left_x, float left_y, float right_x, float right_y,
              float left_trigger, float right_trigger);
void clear();
[[nodiscard]] Sample sample();

} // namespace dkr::runtime::android_input

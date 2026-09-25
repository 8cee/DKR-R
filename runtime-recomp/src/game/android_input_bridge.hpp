#pragma once

#include <cstddef>
#include <cstdint>

namespace dkr::runtime::android_input {

struct Sample {
    std::uint16_t buttons = 0;
    float stick_x = 0.0F;
    float stick_y = 0.0F;
};

void set_key(int device_id, int android_key_code, bool pressed);
void set_axes(int device_id, float left_x, float left_y,
              float right_x, float right_y,
              float left_trigger, float right_trigger);
void remove_device(int device_id);
void clear();
[[nodiscard]] Sample sample(std::size_t player);
[[nodiscard]] Sample sample_touch();

} // namespace dkr::runtime::android_input

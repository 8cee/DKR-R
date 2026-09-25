#pragma once

namespace dkr::android::lifecycle {

void set_resumed(bool resumed);
void set_surface_available(bool available);
[[nodiscard]] bool resumed();
[[nodiscard]] bool surface_available();
[[nodiscard]] bool presentation_allowed();

} // namespace dkr::android::lifecycle

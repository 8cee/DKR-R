#pragma once

namespace dkr::android {

#if defined(__ANDROID__)
void request_app_restart();
#else
inline void request_app_restart() {}
#endif

} // namespace dkr::android

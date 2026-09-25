cmake_minimum_required(VERSION 3.22.1)
project(dkr_android LANGUAGES C CXX)

set(ANDROID_COMPAT_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../../native/compat")

add_library(dkr_android SHARED
    dkr_android.cpp
    "${ANDROID_COMPAT_DIR}/android_paths.cpp"
    "${ANDROID_COMPAT_DIR}/app_lifecycle.cpp"
    "${ANDROID_COMPAT_DIR}/crash_handler.cpp"
    "${ANDROID_COMPAT_DIR}/file_bridge.cpp"
)

target_compile_features(dkr_android PRIVATE cxx_std_20)
target_include_directories(dkr_android PRIVATE "${ANDROID_COMPAT_DIR}")
target_link_libraries(dkr_android PRIVATE android log)

# Match the robust Android packaging used by the DK64 port and Android's
# modern 16 KiB page-size expectations.
target_link_options(dkr_android PRIVATE "-Wl,-z,max-page-size=16384")

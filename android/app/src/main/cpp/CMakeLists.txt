cmake_minimum_required(VERSION 3.22.1)
project(dkr_android LANGUAGES C CXX)

include(FetchContent)

set(SDL2_VERSION "2.30.8" CACHE STRING "SDL2 version for Android")
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)
set(SDL_TEST OFF CACHE BOOL "" FORCE)
set(SDL2_DISABLE_SDL2MAIN ON CACHE BOOL "" FORCE)
set(SDL2_DISABLE_INSTALL ON CACHE BOOL "" FORCE)

FetchContent_Declare(sdl2
    URL https://github.com/libsdl-org/SDL/releases/download/release-${SDL2_VERSION}/SDL2-${SDL2_VERSION}.tar.gz
    URL_HASH SHA256=380c295ea76b9bd72d90075793971c8bcb232ba0a69a9b14da4ae8f603350058
)
FetchContent_MakeAvailable(sdl2)

set(ANDROID_COMPAT_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../../native/compat")

add_library(dkr_android_compat STATIC
    "${ANDROID_COMPAT_DIR}/android_paths.cpp"
    "${ANDROID_COMPAT_DIR}/app_lifecycle.cpp"
    "${ANDROID_COMPAT_DIR}/crash_handler.cpp"
    "${ANDROID_COMPAT_DIR}/file_bridge.cpp"
)
target_compile_features(dkr_android_compat PRIVATE cxx_std_20)
target_include_directories(dkr_android_compat PUBLIC "${ANDROID_COMPAT_DIR}")
target_link_libraries(dkr_android_compat PUBLIC android log)

add_library(dkr_runtime_platform_android STATIC
    "${DKR_RUNTIME_GAME_DIR}/runtime_platform.cpp"
    "${DKR_RUNTIME_GAME_DIR}/android_input_bridge.cpp"
)
target_compile_features(dkr_runtime_platform_android PRIVATE cxx_std_20)
target_compile_definitions(dkr_runtime_platform_android PRIVATE
    DKR_RUNTIME_HAS_RT64=0
    DKR_RUNTIME_HAS_SDL3_INPUT_HOST=0
)
target_include_directories(dkr_runtime_platform_android PRIVATE
    "${DKR_RUNTIME_GAME_DIR}"
    "${sdl2_SOURCE_DIR}/include"
)
target_link_libraries(dkr_runtime_platform_android PRIVATE SDL2-static android log)

# Compile a dependency-light slice of the real DKR-R runtime with the NDK on
# every APK build. This catches Android portability regressions before RT64 and
# the generated recomp payload are brought into the Android link.
set(DKR_RUNTIME_GAME_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../../../runtime-recomp/src/game")
add_library(dkr_runtime_portability_probe STATIC
    "${DKR_RUNTIME_GAME_DIR}/runtime_support.cpp"
    "${DKR_RUNTIME_GAME_DIR}/dkr_save_codec.cpp"
    "${DKR_RUNTIME_GAME_DIR}/save_manager.cpp"
    "${DKR_RUNTIME_GAME_DIR}/android_input_bridge.cpp"
)
target_compile_features(dkr_runtime_portability_probe PRIVATE cxx_std_20)
target_include_directories(dkr_runtime_portability_probe PRIVATE "${DKR_RUNTIME_GAME_DIR}")
target_link_libraries(dkr_runtime_portability_probe PRIVATE android log)

add_library(dkr_android SHARED dkr_android.cpp)
target_compile_features(dkr_android PRIVATE cxx_std_20)
target_include_directories(dkr_android PRIVATE "${DKR_RUNTIME_GAME_DIR}")
target_link_libraries(dkr_android PRIVATE dkr_android_compat dkr_runtime_portability_probe dkr_runtime_platform_android)

# Match the robust Android packaging used by the DK64 port and Android's
# modern 16 KiB page-size expectations.
target_link_options(dkr_android PRIVATE "-Wl,-z,max-page-size=16384")

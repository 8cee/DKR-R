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
# Keep the vendored SDLActivity Java contract in lock-step with the native
# SDL2 release. A mismatch compiles successfully but aborts at runtime.
set(SDL_JAVA_ACTIVITY "${CMAKE_CURRENT_LIST_DIR}/../java/org/libsdl/app/SDLActivity.java")
file(READ "${SDL_JAVA_ACTIVITY}" _dkr_sdl_java)
foreach(_component MAJOR MINOR MICRO)
    string(REGEX MATCH "SDL_${_component}_VERSION *= *([0-9]+)"
           _match "${_dkr_sdl_java}")
    if(NOT _match)
        message(FATAL_ERROR
            "Vendored SDLActivity.java does not expose SDL_${_component}_VERSION")
    endif()
    set(DKR_SDL_JAVA_${_component} "${CMAKE_MATCH_1}")
endforeach()
string(REPLACE "." ";" _dkr_sdl_native_parts "${SDL2_VERSION}")
list(GET _dkr_sdl_native_parts 0 DKR_SDL_NATIVE_MAJOR)
list(GET _dkr_sdl_native_parts 1 DKR_SDL_NATIVE_MINOR)
list(GET _dkr_sdl_native_parts 2 DKR_SDL_NATIVE_MICRO)
if(NOT (DKR_SDL_JAVA_MAJOR STREQUAL DKR_SDL_NATIVE_MAJOR
    AND DKR_SDL_JAVA_MINOR STREQUAL DKR_SDL_NATIVE_MINOR
    AND DKR_SDL_JAVA_MICRO STREQUAL DKR_SDL_NATIVE_MICRO))
    message(FATAL_ERROR
        "SDL Java ${DKR_SDL_JAVA_MAJOR}.${DKR_SDL_JAVA_MINOR}.${DKR_SDL_JAVA_MICRO} "
        "does not match native SDL ${SDL2_VERSION}")
endif()
message(STATUS "SDL Java vendored matches native SDL ${SDL2_VERSION}")

FetchContent_MakeAvailable(sdl2)

# RT64's pinned build still discovers SDL2 through find_package(). Export the
# in-tree Android SDL target through a tiny package config so RT64, plume and
# their children resolve exactly the same headers/library.
set(DKR_FAKE_SDL2_DIR "${CMAKE_BINARY_DIR}/fake-sdl2")
file(MAKE_DIRECTORY "${DKR_FAKE_SDL2_DIR}")
file(WRITE "${DKR_FAKE_SDL2_DIR}/SDL2Config.cmake" "
if(NOT TARGET SDL2::SDL2)
  add_library(SDL2::SDL2 INTERFACE IMPORTED GLOBAL)
  set_target_properties(SDL2::SDL2 PROPERTIES
    INTERFACE_LINK_LIBRARIES SDL2-static
    INTERFACE_INCLUDE_DIRECTORIES \"${sdl2_SOURCE_DIR}/include\")
endif()
set(SDL2_FOUND TRUE)
set(SDL2_INCLUDE_DIRS \"${sdl2_SOURCE_DIR}/include\")
set(SDL2_LIBRARIES SDL2-static)
")
set(SDL2_DIR "${DKR_FAKE_SDL2_DIR}" CACHE PATH "" FORCE)
set(SDL2_INCLUDE_DIRS "${sdl2_SOURCE_DIR}/include" CACHE STRING "" FORCE)
set(SDL2_LIBRARIES SDL2-static CACHE STRING "" FORCE)

set(ANDROID_COMPAT_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../../native/compat")
set(DKR_RUNTIME_GAME_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../../../runtime-recomp/src/game")
set(DKR_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../../../")
set(DKR_ANDROID_NMR_DIR "${DKR_REPO_ROOT}/extern/n64-modern-runtime")
set(DKR_ANDROID_RT64_DIR "${DKR_REPO_ROOT}/extern/rt64")
set(RT64_HOST_FILE_TO_C "" CACHE FILEPATH "Host file_to_c executable for Android RT64 cross-build")
option(DKR_ANDROID_BUILD_RT64_PROBE
       "Configure and compile the pinned RT64 renderer in the Android APK build"
       ON)
option(DKR_ANDROID_BUILD_NMR_PROBE
       "Configure and compile pinned N64ModernRuntime targets in the Android APK build"
       ON)
option(DKR_ANDROID_FULL_RUNTIME
       "Link the complete generated DKR-R runtime into libdkr_android.so"
       OFF)
set(DKR_ANDROID_GENERATED_V77 "" CACHE PATH
    "User-generated N64Recomp CPU source directory for DKR US v1.0")
set(DKR_ANDROID_GENERATED_V80 "" CACHE PATH
    "User-generated N64Recomp CPU source directory for DKR US Rev A/v1.1")

add_library(dkr_android_compat STATIC
    "${ANDROID_COMPAT_DIR}/android_paths.cpp"
    "${ANDROID_COMPAT_DIR}/app_lifecycle.cpp"
    "${ANDROID_COMPAT_DIR}/crash_handler.cpp"
    "${ANDROID_COMPAT_DIR}/app_restart.cpp"
)
set_target_properties(dkr_android_compat PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(dkr_android_compat PRIVATE cxx_std_20)
target_include_directories(dkr_android_compat PUBLIC "${ANDROID_COMPAT_DIR}")
target_link_libraries(dkr_android_compat PUBLIC android log)

add_library(dkr_android_input STATIC
    "${DKR_RUNTIME_GAME_DIR}/android_input_bridge.cpp"
)
set_target_properties(dkr_android_input PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(dkr_android_input PRIVATE cxx_std_20)
target_include_directories(dkr_android_input PUBLIC "${DKR_RUNTIME_GAME_DIR}")

if(NOT DKR_ANDROID_FULL_RUNTIME)
add_library(dkr_runtime_platform_android STATIC
    "${DKR_RUNTIME_GAME_DIR}/runtime_platform.cpp"
)
target_compile_features(dkr_runtime_platform_android PRIVATE cxx_std_20)
target_compile_definitions(dkr_runtime_platform_android PRIVATE
    DKR_RUNTIME_HAS_RT64=0
    DKR_RUNTIME_HAS_SDL3_INPUT_HOST=0
)
target_include_directories(dkr_runtime_platform_android PRIVATE
    "${DKR_RUNTIME_GAME_DIR}"
    "${DKR_ANDROID_NMR_DIR}/ultramodern/include"
    "${DKR_ANDROID_NMR_DIR}/thirdparty"
    "${DKR_ANDROID_NMR_DIR}/thirdparty/concurrentqueue"
    "${DKR_ANDROID_NMR_DIR}/thirdparty/sse2neon"
    "${DKR_ANDROID_NMR_DIR}/N64Recomp/include"
    "${sdl2_SOURCE_DIR}/include"
    "${ANDROID_COMPAT_DIR}"
)
target_link_libraries(dkr_runtime_platform_android PRIVATE dkr_android_input SDL2-static android log)
endif()

if(DKR_ANDROID_BUILD_NMR_PROBE AND NOT DKR_ANDROID_FULL_RUNTIME)
    if(NOT EXISTS "${DKR_ANDROID_NMR_DIR}/CMakeLists.txt")
        message(FATAL_ERROR
            "Pinned N64ModernRuntime checkout is missing. Run "
            "scripts/bootstrap_dependencies.py --only n64-modern-runtime first.")
    endif()

    add_subdirectory("${DKR_ANDROID_NMR_DIR}" "${CMAKE_BINARY_DIR}/n64-modern-runtime-android")
endif()

if(DKR_ANDROID_BUILD_RT64_PROBE AND NOT DKR_ANDROID_FULL_RUNTIME)
    if(NOT EXISTS "${DKR_ANDROID_RT64_DIR}/CMakeLists.txt")
        message(FATAL_ERROR
            "Pinned RT64 checkout is missing. Run scripts/bootstrap_dependencies.py "
            "--only rt64 and scripts/apply-dependency-patches.sh first.")
    endif()
    if(NOT RT64_HOST_FILE_TO_C OR NOT EXISTS "${RT64_HOST_FILE_TO_C}")
        message(FATAL_ERROR
            "RT64_HOST_FILE_TO_C must point to the host-built file_to_c executable.")
    endif()

    set(RT64_STATIC TRUE CACHE BOOL "" FORCE)
    set(RT64_SDL_WINDOW_VULKAN TRUE CACHE BOOL "" FORCE)
    set(PLUME_SDL_VULKAN_ENABLED TRUE CACHE BOOL "" FORCE)
    add_compile_definitions(HLSL_CPU)
    add_subdirectory("${DKR_ANDROID_RT64_DIR}" "${CMAKE_BINARY_DIR}/rt64-android")

    if(TARGET rt64)
        target_include_directories(rt64 PRIVATE
            "${sdl2_SOURCE_DIR}/include"
            "${ANDROID_COMPAT_DIR}"
        )
    endif()

endif()

if(DKR_ANDROID_FULL_RUNTIME)
    add_library(dkr_android_nfd_stub STATIC
        "${CMAKE_CURRENT_LIST_DIR}/nfd_android_stub.cpp"
    )
    set_target_properties(dkr_android_nfd_stub PROPERTIES
        POSITION_INDEPENDENT_CODE ON)
    target_include_directories(dkr_android_nfd_stub PRIVATE
        "${DKR_ANDROID_RT64_DIR}/src/contrib/nativefiledialog-extended/src/include"
    )

    if(DKR_ANDROID_GENERATED_V77 STREQUAL "")
        message(FATAL_ERROR
            "DKR_ANDROID_FULL_RUNTIME requires DKR_ANDROID_GENERATED_V77. "
            "Generate the v77 payload from your own legally obtained ROM.")
    endif()
    if(NOT EXISTS "${DKR_ANDROID_GENERATED_V77}")
        message(FATAL_ERROR "The generated DKR v77 CPU source directory does not exist.")
    endif()
    if(NOT DKR_ANDROID_GENERATED_V80 STREQUAL "" AND
       NOT EXISTS "${DKR_ANDROID_GENERATED_V80}")
        message(FATAL_ERROR "The generated DKR v80 CPU source directory does not exist.")
    endif()

    # The production runtime owns N64ModernRuntime, RT64, netplay and all DKR
    # source lists in this mode. Disable desktop-only helpers/tests and use the
    # Android-safe static DKRPortGame target provided by runtime-recomp.
    set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
    set(DKR_RUNTIME_BUILD_GENERATED ON CACHE BOOL "" FORCE)
    set(DKR_RUNTIME_BUILD_RT64 ON CACHE BOOL "" FORCE)
    set(DKR_RUNTIME_BUILD_SDL3_INPUT_HOST OFF CACHE BOOL "" FORCE)
    set(DKR_NETPLAY_WEBRTC OFF CACHE BOOL "" FORCE)
    set(DKR_GENERATED_SOURCE_V77 "${DKR_ANDROID_GENERATED_V77}" CACHE PATH "" FORCE)
    if(DKR_ANDROID_GENERATED_V80 STREQUAL "")
        set(DKR_RUNTIME_BUILD_V80_PAYLOAD OFF CACHE BOOL "" FORCE)
        set(DKR_GENERATED_SOURCE_V80 "" CACHE PATH "" FORCE)
    else()
        set(DKR_RUNTIME_BUILD_V80_PAYLOAD ON CACHE BOOL "" FORCE)
        set(DKR_GENERATED_SOURCE_V80 "${DKR_ANDROID_GENERATED_V80}" CACHE PATH "" FORCE)
    endif()
    set(DKR_GENERATED_RSP_SOURCE
        "${DKR_REPO_ROOT}/runtime-recomp/RecompiledRSP" CACHE PATH "" FORCE)
    set(DKRPORT_ROOT "${DKR_REPO_ROOT}" CACHE PATH "" FORCE)

    add_subdirectory(
        "${DKR_REPO_ROOT}/runtime-recomp"
        "${CMAKE_BINARY_DIR}/dkr-full-runtime"
    )
    if(TARGET DKRPortGame)
        target_include_directories(DKRPortGame PRIVATE
            "${ANDROID_COMPAT_DIR}"
            "${DKR_ANDROID_RT64_DIR}/src/contrib/nativefiledialog-extended/src/include"
        )
        # DKRPortGame directly calls Android lifecycle/SAF/input bridge symbols.
        # Express that dependency on the target itself so LLD can order static
        # archives correctly when DKRPortGame is folded into libdkr_android.so.
        target_link_libraries(DKRPortGame PRIVATE
            dkr_android_compat
            dkr_android_input
        )
    endif()
endif()

if(NOT DKR_ANDROID_FULL_RUNTIME)
# Compile a dependency-light slice of the real DKR-R runtime with the NDK on
# every APK build. This catches Android portability regressions before RT64 and
# the generated recomp payload are brought into the Android link.
add_library(dkr_runtime_portability_probe STATIC
    "${DKR_RUNTIME_GAME_DIR}/runtime_support.cpp"
    "${DKR_RUNTIME_GAME_DIR}/dkr_save_codec.cpp"
    "${DKR_RUNTIME_GAME_DIR}/save_manager.cpp"
    "${DKR_RUNTIME_GAME_DIR}/startup_performance.cpp"
    "${DKR_RUNTIME_GAME_DIR}/rom_revision.cpp"
)
target_compile_features(dkr_runtime_portability_probe PRIVATE cxx_std_20)
target_include_directories(dkr_runtime_portability_probe PRIVATE
    "${DKR_RUNTIME_GAME_DIR}"
    "${DKR_ANDROID_RT64_DIR}/src/contrib"
)
target_link_libraries(dkr_runtime_portability_probe PRIVATE android log)

endif()

add_library(dkr_android SHARED
    dkr_android.cpp
    "${ANDROID_COMPAT_DIR}/file_bridge.cpp"
)
target_compile_features(dkr_android PRIVATE cxx_std_20)
target_compile_definitions(dkr_android PRIVATE
    DKR_ANDROID_FULL_RUNTIME=$<BOOL:${DKR_ANDROID_FULL_RUNTIME}>
)
target_include_directories(dkr_android PRIVATE "${DKR_RUNTIME_GAME_DIR}")
target_link_libraries(dkr_android PRIVATE
    dkr_android_compat
    dkr_android_input
)
if(DKR_ANDROID_FULL_RUNTIME)
    target_link_libraries(dkr_android PRIVATE DKRPortGame dkr_android_nfd_stub)
else()
    target_link_libraries(dkr_android PRIVATE
        dkr_runtime_portability_probe
        dkr_runtime_platform_android
    )
    if(DKR_ANDROID_BUILD_NMR_PROBE)
        target_link_libraries(dkr_android PRIVATE ultramodern librecomp)
    endif()
endif()
if(DKR_ANDROID_BUILD_RT64_PROBE AND NOT DKR_ANDROID_FULL_RUNTIME)
    target_link_libraries(dkr_android PRIVATE rt64)
endif()

# Match the robust Android packaging used by the DK64 port and Android's
# modern 16 KiB page-size expectations.
target_link_options(dkr_android PRIVATE "-Wl,-z,max-page-size=16384")

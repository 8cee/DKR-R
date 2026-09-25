#include <jni.h>
#include <array>
#include <filesystem>
#include <mutex>
#include <string>

#include "android_paths.hpp"
#include "app_lifecycle.hpp"
#include "crash_handler.hpp"

namespace {
std::mutex g_input_mutex;
std::array<bool, 512> g_buttons{};
struct Axes { float lx=0, ly=0, rx=0, ry=0, lt=0, rt=0; } g_axes;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeBootstrap(
        JNIEnv* env, jclass, jstring filesDir) {
    const char* raw = env->GetStringUTFChars(filesDir, nullptr);
    std::string files = raw ? raw : "";
    if (raw) env->ReleaseStringUTFChars(filesDir, raw);

    try {
        dkr::android::install_crash_handler();
        dkr::android::configure_paths(files);
        dkr::android::lifecycle::set_resumed(true);
        dkr::android::lifecycle::set_surface_available(true);
        return env->NewStringUTF("ready");
    } catch (const std::exception& e) {
        return env->NewStringUTF(e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeVersion(JNIEnv* env, jclass) {
    return env->NewStringUTF("dkr-android-bootstrap/0.3");
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeSetResumed(
        JNIEnv*, jclass, jboolean resumed) {
    dkr::android::lifecycle::set_resumed(resumed == JNI_TRUE);
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeSetButton(
        JNIEnv*, jclass, jint key, jboolean pressed) {
    if (key < 0 || key >= static_cast<jint>(g_buttons.size())) return;
    std::scoped_lock lock(g_input_mutex);
    g_buttons[static_cast<size_t>(key)] = pressed == JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeSetAxis(
        JNIEnv*, jclass, jfloat lx, jfloat ly, jfloat rx, jfloat ry,
        jfloat lt, jfloat rt) {
    std::scoped_lock lock(g_input_mutex);
    g_axes = {lx, ly, rx, ry, lt, rt};
}

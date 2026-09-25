#include <jni.h>
#include <cstdio>
#include <filesystem>
#include <string>

#include "android_paths.hpp"
#include "app_lifecycle.hpp"
#include "crash_handler.hpp"
#include "save_manager.hpp"
#include "runtime_support.hpp"
#include "android_input_bridge.hpp"

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeBootstrap(
        JNIEnv* env, jclass, jstring filesDir) {
    const char* raw = env->GetStringUTFChars(filesDir, nullptr);
    std::string files = raw ? raw : "";
    if (raw) env->ReleaseStringUTFChars(filesDir, raw);

    try {
        dkr::android::install_crash_handler();
        dkr::android::configure_paths(files);
        dkr::runtime::saves::configure(files);
        dkr::runtime::support::configure(files);
        dkr::android::lifecycle::set_resumed(true);
        dkr::android::lifecycle::set_surface_available(true);
        return env->NewStringUTF("ready");
    } catch (const std::exception& e) {
        return env->NewStringUTF(e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeVersion(JNIEnv* env, jclass) {
    return env->NewStringUTF("dkr-android-bootstrap/0.5");
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeSetResumed(
        JNIEnv*, jclass, jboolean resumed) {
    const bool is_resumed = resumed == JNI_TRUE;
    dkr::android::lifecycle::set_resumed(is_resumed);
    if (!is_resumed) {
        dkr::runtime::android_input::clear();
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeSetButton(
        JNIEnv*, jclass, jint key, jboolean pressed) {
    dkr::runtime::android_input::set_key(
        static_cast<int>(key), pressed == JNI_TRUE);
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeSetAxis(
        JNIEnv*, jclass, jfloat lx, jfloat ly, jfloat rx, jfloat ry,
        jfloat lt, jfloat rt) {
    dkr::runtime::android_input::set_axes(lx, ly, rx, ry, lt, rt);
}


extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeSaveStatus(JNIEnv* env, jclass) {
    const auto info = dkr::runtime::saves::adventure_info();
    std::string status = "Native save manager: ";
    if (!info.exists) {
        status += "no Adventure save yet";
    } else if (!info.valid) {
        status += "Adventure save exists but is invalid";
    } else {
        status += "Adventure save valid (" + std::to_string(info.size) + " bytes)";
    }

    int valid_paks = 0;
    for (int channel = 0; channel < dkr::runtime::saves::kControllerPakCount; ++channel) {
        const auto pak = dkr::runtime::saves::controller_pak_info(channel);
        if (pak.exists && pak.valid) ++valid_paks;
    }
    status += "; valid Controller Paks: " + std::to_string(valid_paks);
    return env->NewStringUTF(status.c_str());
}


namespace {
jstring SaveTransferResult(JNIEnv* env, bool ok, const std::string& error) {
    const std::string text = ok ? "OK" : "ERR:" + error;
    return env->NewStringUTF(text.c_str());
}
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeImportSaveFile(
        JNIEnv* env, jclass, jint kind, jint channel, jstring sourcePath) {
    const char* raw = env->GetStringUTFChars(sourcePath, nullptr);
    const std::filesystem::path source = raw ? raw : "";
    if (raw) env->ReleaseStringUTFChars(sourcePath, raw);

    std::string error;
    bool ok = false;
    switch (kind) {
    case 0:
        ok = dkr::runtime::saves::import_adventure(source, error);
        break;
    case 1:
        ok = dkr::runtime::saves::import_bundle(source, error);
        break;
    case 2:
        ok = dkr::runtime::saves::import_controller_pak(
            static_cast<int>(channel), source, error);
        break;
    default:
        error = "Unknown save import kind.";
        break;
    }
    return SaveTransferResult(env, ok, error);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeExportSaveFile(
        JNIEnv* env, jclass, jint kind, jint channel, jstring destinationPath) {
    const char* raw = env->GetStringUTFChars(destinationPath, nullptr);
    const std::filesystem::path destination = raw ? raw : "";
    if (raw) env->ReleaseStringUTFChars(destinationPath, raw);

    std::string error;
    bool ok = false;
    switch (kind) {
    case 0:
        ok = dkr::runtime::saves::export_adventure(destination, error);
        break;
    case 1:
        ok = dkr::runtime::saves::export_bundle(destination, error);
        break;
    case 2:
        ok = dkr::runtime::saves::export_controller_pak(
            static_cast<int>(channel), destination, error);
        break;
    default:
        error = "Unknown save export kind.";
        break;
    }
    return SaveTransferResult(env, ok, error);
}


extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeInputStatus(JNIEnv* env, jclass) {
    const auto sample = dkr::runtime::android_input::sample();
    char buffer[160]{};
    std::snprintf(buffer, sizeof(buffer),
                  "N64 input buttons=0x%04X stick=(%.2f, %.2f)",
                  static_cast<unsigned>(sample.buttons),
                  static_cast<double>(sample.stick_x),
                  static_cast<double>(sample.stick_y));
    return env->NewStringUTF(buffer);
}


extern "C" int DKRAndroidHostMain(int argc, char** argv) {
    try {
        if (argc > 1 && argv != nullptr && argv[1] != nullptr) {
            dkr::android::configure_paths(argv[1]);
            dkr::runtime::saves::configure(argv[1]);
            dkr::runtime::support::configure(argv[1]);
        }
        dkr::android::install_crash_handler();
        dkr::android::lifecycle::set_resumed(true);
        dkr::android::lifecycle::set_surface_available(true);
        return 0;
    } catch (...) {
        return 1;
    }
}

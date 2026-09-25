#include <jni.h>
#include <filesystem>
#include <string>

namespace fs = std::filesystem;

static std::string g_files_dir;

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeBootstrap(
        JNIEnv* env, jclass, jstring filesDir) {
    const char* raw = env->GetStringUTFChars(filesDir, nullptr);
    g_files_dir = raw ? raw : "";
    if (raw) env->ReleaseStringUTFChars(filesDir, raw);

    try {
        fs::create_directories(fs::path(g_files_dir) / "roms");
        fs::create_directories(fs::path(g_files_dir) / "saves");
        fs::create_directories(fs::path(g_files_dir) / "mods" / "translations");
        fs::create_directories(fs::path(g_files_dir) / "mods" / "textures");
        fs::create_directories(fs::path(g_files_dir) / "mods" / "characters");
        fs::create_directories(fs::path(g_files_dir) / "mods" / "tracks");
        fs::create_directories(fs::path(g_files_dir) / "mods" / "gameplay");
        fs::create_directories(fs::path(g_files_dir) / "mods" / "ui");
        fs::create_directories(fs::path(g_files_dir) / "cache");
        return env->NewStringUTF("ready");
    } catch (const std::exception& e) {
        return env->NewStringUTF(e.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeVersion(JNIEnv* env, jclass) {
    return env->NewStringUTF("dkr-android-bootstrap/0.1");
}

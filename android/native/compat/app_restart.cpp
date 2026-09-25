#include "app_restart.hpp"

#if defined(__ANDROID__)

#include <android/log.h>
#include <jni.h>

#include <mutex>

namespace dkr::android {
namespace {

constexpr const char* kTag = "DKR-R";
std::mutex g_mutex;
JavaVM* g_vm = nullptr;
jclass g_activity_class = nullptr;
jmethodID g_restart_method = nullptr;

bool cache_restart(JNIEnv* env, jclass clazz) {
    if (env == nullptr || clazz == nullptr) return false;
    jmethodID method =
        env->GetStaticMethodID(clazz, "handleNativeAppRestart", "()V");
    if (method == nullptr) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return false;
    }
    jclass global = static_cast<jclass>(env->NewGlobalRef(clazz));
    if (global == nullptr) return false;

    std::scoped_lock lock(g_mutex);
    if (g_activity_class != nullptr) env->DeleteGlobalRef(g_activity_class);
    g_activity_class = global;
    g_restart_method = method;
    env->GetJavaVM(&g_vm);
    return g_vm != nullptr;
}

} // namespace

void request_app_restart() {
    JavaVM* vm = nullptr;
    jclass clazz = nullptr;
    jmethodID method = nullptr;
    {
        std::scoped_lock lock(g_mutex);
        vm = g_vm;
        clazz = g_activity_class;
        method = g_restart_method;
    }
    if (vm == nullptr || clazz == nullptr || method == nullptr) {
        __android_log_print(ANDROID_LOG_WARN, kTag,
                            "Restart requested before Java restart bridge initialization");
        return;
    }

    JNIEnv* env = nullptr;
    bool attached = false;
    if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
        if (vm->AttachCurrentThread(&env, nullptr) != JNI_OK) return;
        attached = true;
    }

    env->CallStaticVoidMethod(clazz, method);
    if (env->ExceptionCheck()) {
        env->ExceptionDescribe();
        env->ExceptionClear();
    }

    if (attached) vm->DetachCurrentThread();
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_DkrSdlActivity_nativeRestartInit(
        JNIEnv* env, jclass clazz) {
    if (!cache_restart(env, clazz)) {
        __android_log_print(ANDROID_LOG_WARN, kTag,
                            "Could not initialize Android restart bridge");
    }
}

} // namespace dkr::android

#endif

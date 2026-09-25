#include "file_bridge.hpp"

#if defined(__ANDROID__)

#include <android/log.h>
#include <jni.h>

#include <mutex>
#include <utility>

namespace dkr::android::filedialog {
namespace {

constexpr const char* kTag = "DKR-R";
enum class State { Idle, Waiting, Result };

std::mutex g_mutex;
JavaVM* g_vm = nullptr;
jclass g_main_class = nullptr;
jmethodID g_request_method = nullptr;
jmethodID g_export_method = nullptr;
State g_state = State::Idle;
Kind g_kind = Kind::Rom;
bool g_ok = false;
std::string g_payload;
Callback g_callback;

bool cache_activity(JNIEnv* env, jclass activity_class) {
    if (env == nullptr || activity_class == nullptr) return false;

    jclass global =
        static_cast<jclass>(env->NewGlobalRef(activity_class));
    if (global == nullptr) return false;

    jmethodID method =
        env->GetStaticMethodID(global, "requestNativeFilePicker", "(I)Z");
    if (method == nullptr) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        env->DeleteGlobalRef(global);
        __android_log_print(ANDROID_LOG_ERROR, kTag,
                            "SAF bridge: active Activity lacks requestNativeFilePicker(I)Z");
        return false;
    }

    jmethodID export_method = env->GetStaticMethodID(
        global, "requestNativeExport",
        "(ILjava/lang/String;Ljava/lang/String;)Z");
    if (export_method == nullptr && env->ExceptionCheck()) {
        // The temporary MainActivity bootstrap does not need native exports.
        // DkrSdlActivity provides this method once the full runtime is active.
        env->ExceptionClear();
    }

    std::scoped_lock lock(g_mutex);
    if (g_main_class != nullptr) {
        env->DeleteGlobalRef(g_main_class);
    }
    g_main_class = global;
    g_request_method = method;
    g_export_method = export_method;
    return true;
}

bool call_java(Kind kind) {
    JavaVM* vm = nullptr;
    {
        std::scoped_lock lock(g_mutex);
        vm = g_vm;
    }
    if (vm == nullptr) return false;

    JNIEnv* env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
        if (vm->AttachCurrentThread(&env, nullptr) != JNI_OK) return false;
    }
    {
        std::scoped_lock lock(g_mutex);
        if (g_main_class == nullptr || g_request_method == nullptr) {
            __android_log_print(ANDROID_LOG_ERROR, kTag,
                                "SAF bridge: no active Activity registered");
            return false;
        }
    }

    jclass cls = nullptr;
    jmethodID method = nullptr;
    {
        std::scoped_lock lock(g_mutex);
        cls = g_main_class;
        method = g_request_method;
    }

    jboolean accepted = env->CallStaticBooleanMethod(
            cls, method, static_cast<jint>(kind));
    if (env->ExceptionCheck()) {
        env->ExceptionDescribe();
        env->ExceptionClear();
        return false;
    }
    return accepted == JNI_TRUE;
}


bool call_java_export(Kind kind, const std::string& source_path,
                      const std::string& suggested_name) {
    JavaVM* vm = nullptr;
    {
        std::scoped_lock lock(g_mutex);
        vm = g_vm;
    }
    if (vm == nullptr) return false;

    JNIEnv* env = nullptr;
    bool attached = false;
    if (vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6) != JNI_OK) {
        if (vm->AttachCurrentThread(&env, nullptr) != JNI_OK) return false;
        attached = true;
    }

    jclass cls = nullptr;
    jmethodID method = nullptr;
    {
        std::scoped_lock lock(g_mutex);
        cls = g_main_class;
        method = g_export_method;
    }
    if (cls == nullptr || method == nullptr) {
        if (attached) vm->DetachCurrentThread();
        return false;
    }

    jstring source = env->NewStringUTF(source_path.c_str());
    jstring name = env->NewStringUTF(suggested_name.c_str());
    const jboolean accepted = env->CallStaticBooleanMethod(
        cls, method, static_cast<jint>(kind), source, name);
    env->DeleteLocalRef(source);
    env->DeleteLocalRef(name);
    if (env->ExceptionCheck()) {
        env->ExceptionDescribe();
        env->ExceptionClear();
        if (attached) vm->DetachCurrentThread();
        return false;
    }
    if (attached) vm->DetachCurrentThread();
    return accepted == JNI_TRUE;
}

} // namespace

void set_java_vm(void* vm) {
    std::scoped_lock lock(g_mutex);
    g_vm = static_cast<JavaVM*>(vm);
}

bool request(Kind kind, Callback callback) {
    Callback rejected;
    {
        std::scoped_lock lock(g_mutex);
        if (g_state != State::Idle) {
            rejected = std::move(callback);
        } else {
            g_state = State::Waiting;
            g_kind = kind;
            g_ok = false;
            g_payload.clear();
            g_callback = std::move(callback);
        }
    }

    if (rejected) {
        rejected(false, {});
        return false;
    }

    if (call_java(kind)) return true;

    Callback failed;
    {
        std::scoped_lock lock(g_mutex);
        g_state = State::Idle;
        failed = std::move(g_callback);
        g_callback = nullptr;
    }
    if (failed) failed(false, {});
    return false;
}


bool request_export(Kind kind, const std::string& source_path,
                    const std::string& suggested_name, Callback callback) {
    Callback rejected;
    {
        std::scoped_lock lock(g_mutex);
        if (g_state != State::Idle) {
            rejected = std::move(callback);
        } else {
            g_state = State::Waiting;
            g_kind = kind;
            g_ok = false;
            g_payload.clear();
            g_callback = std::move(callback);
        }
    }
    if (rejected) {
        rejected(false, {});
        return false;
    }
    if (call_java_export(kind, source_path, suggested_name)) return true;

    Callback failed;
    {
        std::scoped_lock lock(g_mutex);
        g_state = State::Idle;
        failed = std::move(g_callback);
        g_callback = nullptr;
    }
    if (failed) failed(false, {});
    return false;
}

void process_pending() {
    Callback callback;
    bool ok = false;
    std::string payload;
    {
        std::scoped_lock lock(g_mutex);
        if (g_state != State::Result) return;
        callback = std::move(g_callback);
        ok = g_ok;
        payload = std::move(g_payload);
        g_callback = nullptr;
        g_payload.clear();
        g_state = State::Idle;
    }
    if (callback) callback(ok, payload);
}

namespace {
void BridgeInit(JNIEnv* env, jclass activity_class) {
    JavaVM* vm = nullptr;
    if (env->GetJavaVM(&vm) == JNI_OK && vm != nullptr) {
        set_java_vm(vm);
        cache_activity(env, activity_class);
    }
}

void PublishPickedFile(JNIEnv* env, jint kind, jboolean ok, jstring payload) {
    const char* raw = payload ? env->GetStringUTFChars(payload, nullptr) : nullptr;
    {
        std::scoped_lock lock(g_mutex);
        if (g_state == State::Waiting && static_cast<int>(g_kind) == kind) {
            g_ok = ok == JNI_TRUE;
            g_payload = raw ? raw : "";
            g_state = State::Result;
        }
    }
    if (raw) env->ReleaseStringUTFChars(payload, raw);
}
} // namespace

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeBridgeInit(
        JNIEnv* env, jclass activity_class) {
    BridgeInit(env, activity_class);
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeOnFilePicked(
        JNIEnv* env, jclass, jint kind, jboolean ok, jstring payload) {
    PublishPickedFile(env, kind, ok, payload);
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_DkrSdlActivity_nativeBridgeInit(
        JNIEnv* env, jclass activity_class) {
    BridgeInit(env, activity_class);
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_DkrSdlActivity_nativeOnFilePicked(
        JNIEnv* env, jclass, jint kind, jboolean ok, jstring payload) {
    PublishPickedFile(env, kind, ok, payload);
}

} // namespace dkr::android::filedialog

#else

namespace dkr::android::filedialog {
void set_java_vm(void*) {}
bool request(Kind, Callback callback) {
    if (callback) callback(false, {});
    return false;
}
bool request_export(Kind, const std::string&, const std::string&, Callback callback) {
    if (callback) callback(false, {});
    return false;
}
void process_pending() {}
} // namespace dkr::android::filedialog

#endif

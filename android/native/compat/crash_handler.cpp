#include "crash_handler.hpp"

#if defined(__ANDROID__)
#include <android/log.h>
#include <csignal>
#include <cstdlib>
#include <exception>

namespace {
void signal_handler(int signal_number) {
    __android_log_print(ANDROID_LOG_FATAL, "DKR-R-Crash",
                        "native fatal signal=%d", signal_number);
    std::signal(signal_number, SIG_DFL);
    std::raise(signal_number);
}

void terminate_handler() {
    __android_log_print(ANDROID_LOG_FATAL, "DKR-R-Crash",
                        "std::terminate called");
    std::abort();
}
}

namespace dkr::android {
void install_crash_handler() {
    for (int sig : {SIGSEGV, SIGABRT, SIGFPE, SIGILL}) {
        std::signal(sig, signal_handler);
    }
    std::set_terminate(terminate_handler);
}
}
#else
namespace dkr::android {
void install_crash_handler() {}
}
#endif

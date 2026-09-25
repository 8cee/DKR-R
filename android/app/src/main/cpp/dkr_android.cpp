#include <jni.h>
#include <cstdio>
#include <filesystem>
#include <string>
#include <set>
#include <chrono>
#include <thread>

#include "android_paths.hpp"
#include "app_lifecycle.hpp"
#include "crash_handler.hpp"
#include "save_manager.hpp"
#include "runtime_support.hpp"
#include "rom_revision.hpp"
#include "game_main.hpp"
#include "android_input_bridge.hpp"
#if DKR_ANDROID_FULL_RUNTIME
#include "runtime_ui.hpp"
#include "custom_tracks.hpp"
#include "runtime_texture_packs.hpp"
#include "mods/legacy_mod_library.hpp"
#endif

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
        JNIEnv*, jclass, jint device, jint key, jboolean pressed) {
    dkr::runtime::android_input::set_key(
        static_cast<int>(device), static_cast<int>(key),
        pressed == JNI_TRUE);
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeSetAxis(
        JNIEnv*, jclass, jint device,
        jfloat lx, jfloat ly, jfloat rx, jfloat ry,
        jfloat lt, jfloat rt) {
    dkr::runtime::android_input::set_axes(
        static_cast<int>(device), lx, ly, rx, ry, lt, rt);
}


extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeRemoveDevice(
        JNIEnv*, jclass, jint device) {
    dkr::runtime::android_input::remove_device(static_cast<int>(device));
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeToggleOverlay(
        JNIEnv*, jclass) {
#if DKR_ANDROID_FULL_RUNTIME
    dkr::runtime::ui::toggle_overlay();
#endif
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_eightcee_dkrrecomp_ControllerBridge_nativeOverlayVisible(
        JNIEnv*, jclass) {
#if DKR_ANDROID_FULL_RUNTIME
    return dkr::runtime::ui::overlay_visible() ? JNI_TRUE : JNI_FALSE;
#else
    return JNI_FALSE;
#endif
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
    const auto sample = dkr::runtime::android_input::sample(0);
    char buffer[160]{};
    std::snprintf(buffer, sizeof(buffer),
                  "N64 input buttons=0x%04X stick=(%.2f, %.2f)",
                  static_cast<unsigned>(sample.buttons),
                  static_cast<double>(sample.stick_x),
                  static_cast<double>(sample.stick_y));
    return env->NewStringUTF(buffer);
}


extern "C" int DKRAndroidHostMain(int argc, char** argv) {
    const char* files_dir =
        argc > 1 && argv != nullptr && argv[1] != nullptr ? argv[1] : "";
    const char* external_files_dir =
        argc > 2 && argv != nullptr && argv[2] != nullptr ? argv[2] : "";

    try {
        dkr::android::configure_paths(files_dir, external_files_dir);
        dkr::runtime::saves::configure(files_dir);
        dkr::runtime::support::configure(files_dir);
        dkr::android::install_crash_handler();
        dkr::android::lifecycle::set_resumed(true);

#if DKR_ANDROID_FULL_RUNTIME
        // SDLActivity's argv[1]/argv[2] are Android storage paths, not DKR-R
        // desktop positional arguments. Rebuild the command line explicitly so
        // DkrMain sees a config directory and no ROM, which opens its launcher.
        char program[] = "DKR-R";
        char config_option[] = "--config";
        char* runtime_argv[] = {
            program,
            config_option,
            const_cast<char*>(files_dir),
            nullptr
        };
        return DkrMain(3, runtime_argv);
#else
        return 0;
#endif
    } catch (...) {
        return 1;
    }
}


extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_DkrSdlActivity_nativeHostResumed(
        JNIEnv*, jclass, jboolean resumed) {
    const bool active = resumed == JNI_TRUE;
    dkr::android::lifecycle::set_resumed(active);
    if (!active) {
        dkr::runtime::android_input::clear();
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_eightcee_dkrrecomp_DkrSdlActivity_nativeSurfaceState(
        JNIEnv*, jclass, jboolean available) {
    dkr::android::lifecycle::set_surface_available(available == JNI_TRUE);
}


extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_MainActivity_nativeInspectRom(
        JNIEnv* env, jclass, jstring path) {
    const char* raw = env->GetStringUTFChars(path, nullptr);
    const std::filesystem::path rom_path = raw ? raw : "";
    if (raw) env->ReleaseStringUTFChars(path, raw);

    const auto identity = dkr::runtime::rom::inspect(rom_path);
    const std::string description = dkr::runtime::rom::describe(identity);
    const std::string result =
        std::string(identity.supported() ? "OK\n" : "ERR\n") + description;
    return env->NewStringUTF(result.c_str());
}


extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_CatalogModNative_nativeActivate(
        JNIEnv* env, jclass, jstring targetValue, jstring archiveValue,
        jstring filesDirValue, jstring expectedIdValue) {
    const char* targetRaw = env->GetStringUTFChars(targetValue, nullptr);
    const char* archiveRaw = env->GetStringUTFChars(archiveValue, nullptr);
    const char* filesRaw = env->GetStringUTFChars(filesDirValue, nullptr);
    const char* expectedRaw = env->GetStringUTFChars(expectedIdValue, nullptr);
    const std::string target = targetRaw ? targetRaw : "";
    const std::filesystem::path archive = archiveRaw ? archiveRaw : "";
    const std::filesystem::path files = filesRaw ? filesRaw : "";
    const std::string expected_id = expectedRaw ? expectedRaw : "";
    if (targetRaw) env->ReleaseStringUTFChars(targetValue, targetRaw);
    if (archiveRaw) env->ReleaseStringUTFChars(archiveValue, archiveRaw);
    if (filesRaw) env->ReleaseStringUTFChars(filesDirValue, filesRaw);
    if (expectedRaw) env->ReleaseStringUTFChars(expectedIdValue, expectedRaw);

#if DKR_ANDROID_FULL_RUNTIME
    try {
        if (target == "custom-track") {
            dkr::runtime::custom_tracks::scan(files / "custom-tracks");
            dkr::runtime::custom_tracks::InstallOutcome outcome;
            std::string error;
            if (!dkr::runtime::custom_tracks::install(archive, error, &outcome)) {
                const std::string result = "ERR\n" + error;
                return env->NewStringUTF(result.c_str());
            }

            std::string detail = "Custom track activated.";
            if (!outcome.hd_pack_archive.empty()) {
                dkr::runtime::texture_packs::configure(files);
                dkr::runtime::texture_packs::TrackPackOwner owner{
                    outcome.track_id, outcome.hd_pack_digest};
                std::string status;
                if (!dkr::runtime::texture_packs::import_archive(
                        outcome.hd_pack_archive, status, {}, &owner)) {
                    detail += " HD texture pack was not activated: " + status;
                } else if (!status.empty()) {
                    detail += " " + status;
                }
            }
            dkr::runtime::custom_tracks::discard_install_temp(outcome.temp_root);
            const std::string result = "OK\n" + outcome.track_id + "\n" + detail;
            return env->NewStringUTF(result.c_str());
        }

        if (target == "texture-pack") {
            dkr::runtime::texture_packs::configure(files);
            std::set<std::string> before;
            for (const auto& pack : dkr::runtime::texture_packs::snapshot(true)) {
                before.insert(pack.id);
            }

            std::string status;
            if (!dkr::runtime::texture_packs::import_archive(archive, status)) {
                const std::string result = "ERR\n\n" + status;
                return env->NewStringUTF(result.c_str());
            }

            std::string imported_id;
            std::int64_t newest = -1;
            for (const auto& pack : dkr::runtime::texture_packs::snapshot(true)) {
                if (!before.contains(pack.id) && pack.imported_at_unix_seconds >= newest) {
                    imported_id = pack.id;
                    newest = pack.imported_at_unix_seconds;
                }
            }
            if (imported_id.empty()) {
                const auto packs = dkr::runtime::texture_packs::snapshot(true);
                for (const auto& pack : packs) {
                    if (pack.imported_at_unix_seconds >= newest) {
                        imported_id = pack.id;
                        newest = pack.imported_at_unix_seconds;
                    }
                }
            }
            if (imported_id.empty()) {
                return env->NewStringUTF("ERR\n\nTexture pack imported but its managed ID could not be resolved.");
            }

            const std::string detail =
                status.empty() ? std::string("Texture pack activated.") : status;
            const std::string result = "OK\n" + imported_id + "\n" + detail;
            return env->NewStringUTF(result.c_str());
        }

        if (target == "legacy-track" || target == "legacy-character") {
            const auto root = files / "mods" / "legacy";
            const auto rom = files / "roms" / "dkr.rom";
            if (!std::filesystem::is_regular_file(rom)) {
                return env->NewStringUTF("ERR\n\nSelect a supported DKR ROM before importing a legacy mod.");
            }

            dkr::mods::ModLibrary library;
            library.configure(root, {});
            auto wait_for_idle = [&]() {
                for (unsigned tick = 0; tick < 3000; ++tick) {
                    library.tick();
                    if (!library.snapshot().busy) return true;
                    std::this_thread::sleep_for(std::chrono::milliseconds(10));
                }
                return false;
            };
            if (!wait_for_idle()) {
                return env->NewStringUTF("ERR\n\nLegacy mod library refresh timed out.");
            }

            const auto before = library.snapshot();
            const bool character = target == "legacy-character";
            std::set<std::string> before_ids;
            const auto before_catalog = character ? before.characters : before.tracks;
            if (before_catalog) {
                for (const auto& item : before_catalog->tracks) before_ids.insert(item.id);
            }

            if (!library.import_file(archive, {rom})) {
                return env->NewStringUTF("ERR\n\nLegacy import could not be started.");
            }
            if (!wait_for_idle()) {
                library.cancel();
                return env->NewStringUTF("ERR\n\nLegacy import timed out.");
            }
            const auto imported = library.snapshot();
            if (!imported.succeeded) {
                const std::string result = "ERR\n\n" +
                    (imported.result.empty() ? std::string("Legacy import failed.") : imported.result);
                return env->NewStringUTF(result.c_str());
            }

            const auto catalog = character ? imported.characters : imported.tracks;
            if (!catalog) return env->NewStringUTF("ERR\n\nLegacy import catalogue is unavailable.");

            std::string native_id;
            if (!expected_id.empty()) {
                for (const auto& item : catalog->tracks) {
                    if (item.id == expected_id) {
                        native_id = expected_id;
                        break;
                    }
                }
            }
            if (native_id.empty()) {
                for (const auto& item : catalog->tracks) {
                    if (!before_ids.contains(item.id)) {
                        if (!native_id.empty() && native_id != item.id) {
                            return env->NewStringUTF("ERR\n\nLegacy package produced multiple new items; install them from DKR-R's Mods / Hacks page.");
                        }
                        native_id = item.id;
                    }
                }
            }
            if (native_id.empty()) {
                return env->NewStringUTF("ERR\n\nNo new reviewed legacy item was identified.");
            }

            const auto kind = character
                ? dkr::mods::TrackCatalog::Kind::Character
                : dkr::mods::TrackCatalog::Kind::Track;
            if (!library.set_enabled(kind, native_id, true)) {
                return env->NewStringUTF("ERR\n\nPrepared legacy item could not be enabled.");
            }
            if (!wait_for_idle()) {
                library.cancel();
                return env->NewStringUTF("ERR\n\nLegacy activation timed out.");
            }
            const auto enabled = library.snapshot();
            if (!enabled.succeeded) {
                const std::string result = "ERR\n" + native_id + "\n" +
                    (enabled.result.empty() ? std::string("Legacy activation failed.") : enabled.result);
                return env->NewStringUTF(result.c_str());
            }
            const std::string result = "OK\n" + native_id + "\n" +
                (character ? "Legacy character prepared and enabled." : "Legacy track prepared and enabled.");
            return env->NewStringUTF(result.c_str());
        }

        return env->NewStringUTF("ERR\n\nUnsupported catalog activation target.");
    } catch (const std::exception& e) {
        const std::string result = std::string("ERR\n") + e.what();
        return env->NewStringUTF(result.c_str());
    }
#else
    (void)target;
    (void)archive;
    (void)files;
    (void)expected_id;
    return env->NewStringUTF("ERR\n\nCatalog activation requires a full-runtime APK.");
#endif
}


extern "C" JNIEXPORT jstring JNICALL
Java_com_eightcee_dkrrecomp_CatalogModNative_nativeDeactivate(
        JNIEnv* env, jclass, jstring targetValue, jstring nativeIdValue,
        jstring filesDirValue) {
    const char* targetRaw = env->GetStringUTFChars(targetValue, nullptr);
    const char* idRaw = env->GetStringUTFChars(nativeIdValue, nullptr);
    const char* filesRaw = env->GetStringUTFChars(filesDirValue, nullptr);
    const std::string target = targetRaw ? targetRaw : "";
    const std::string native_id = idRaw ? idRaw : "";
    const std::filesystem::path files = filesRaw ? filesRaw : "";
    if (targetRaw) env->ReleaseStringUTFChars(targetValue, targetRaw);
    if (idRaw) env->ReleaseStringUTFChars(nativeIdValue, idRaw);
    if (filesRaw) env->ReleaseStringUTFChars(filesDirValue, filesRaw);

#if DKR_ANDROID_FULL_RUNTIME
    try {
        if (target == "custom-track") {
            dkr::runtime::custom_tracks::scan(files / "custom-tracks");
            std::string error;
            if (!dkr::runtime::custom_tracks::uninstall(native_id, error)) {
                const std::string result = "ERR\n" + native_id + "\n" + error;
                return env->NewStringUTF(result.c_str());
            }
            dkr::runtime::texture_packs::configure(files);
            std::string pack_status;
            dkr::runtime::texture_packs::forget_track_pack(native_id, pack_status);
            const std::string result = "OK\n" + native_id +
                "\nCustom track removed from DKR-R's managed library.";
            return env->NewStringUTF(result.c_str());
        }

        if (target == "texture-pack") {
            dkr::runtime::texture_packs::configure(files);
            std::string status;
            if (!dkr::runtime::texture_packs::delete_managed(native_id, status)) {
                const std::string result = "ERR\n" + native_id + "\n" + status;
                return env->NewStringUTF(result.c_str());
            }
            const std::string result = "OK\n" + native_id + "\n" +
                (status.empty() ? std::string("Texture pack removed.") : status);
            return env->NewStringUTF(result.c_str());
        }

        if (target == "legacy-track" || target == "legacy-character") {
            dkr::mods::ModLibrary library;
            library.configure(files / "mods" / "legacy", {});
            auto wait_for_idle = [&]() {
                for (unsigned tick = 0; tick < 3000; ++tick) {
                    library.tick();
                    if (!library.snapshot().busy) return true;
                    std::this_thread::sleep_for(std::chrono::milliseconds(10));
                }
                return false;
            };
            if (!wait_for_idle()) return env->NewStringUTF("ERR\n\nLegacy mod library refresh timed out.");

            const auto kind = target == "legacy-character"
                ? dkr::mods::TrackCatalog::Kind::Character
                : dkr::mods::TrackCatalog::Kind::Track;
            if (!library.remove(kind, native_id)) {
                return env->NewStringUTF("ERR\n\nLegacy mod removal could not be started.");
            }
            if (!wait_for_idle()) {
                library.cancel();
                return env->NewStringUTF("ERR\n\nLegacy mod removal timed out.");
            }
            const auto removed = library.snapshot();
            if (!removed.succeeded) {
                const std::string result = "ERR\n" + native_id + "\n" +
                    (removed.result.empty() ? std::string("Legacy mod removal failed.") : removed.result);
                return env->NewStringUTF(result.c_str());
            }
            const std::string result = "OK\n" + native_id + "\n" +
                (target == "legacy-character"
                    ? "Legacy character removed from DKR-R's managed library."
                    : "Legacy track removed from DKR-R's managed library.");
            return env->NewStringUTF(result.c_str());
        }

        return env->NewStringUTF("ERR\n\nUnsupported catalog deactivation target.");
    } catch (const std::exception& e) {
        const std::string result = std::string("ERR\n") + native_id + "\n" + e.what();
        return env->NewStringUTF(result.c_str());
    }
#else
    (void)target;
    (void)native_id;
    (void)files;
    return env->NewStringUTF("ERR\n\nCatalog deactivation requires a full-runtime APK.");
#endif
}

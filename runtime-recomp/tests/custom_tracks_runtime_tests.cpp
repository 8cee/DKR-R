#include "custom_tracks.hpp"
#include "game_payload.hpp"
#include "revision_addresses.hpp"
#include "recomp.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <vector>

extern "C" void dkr_custom_tracks_auto_boot(std::uint8_t*, recomp_context*);
extern "C" void dkr_custom_tracks_prepare_vehicle(std::uint8_t*, recomp_context*);

namespace tracks = dkr::runtime::custom_tracks;
namespace addresses = dkr::runtime::revision_addresses;
namespace {
dkr::runtime::GamePayload payload{};
bool payload_available = true;
unsigned unlocks = 0;
unsigned stage = 0;
int vehicle = 0;
unsigned allowed = 1;
int saved_vehicle = -1;
std::array<int, 8> committed{};
gpr addr(std::uint32_t value) { return static_cast<std::int32_t>(value); }
bool rev80() { return addresses::selected_revision() == dkr::runtime::rom::Revision::UsV80; }

// Guest-call substitutes check prerequisites at the real host boundary. The
// native AI algorithm itself remains untouched; these checks catch a missing
// commit, wrong revision table, uninitialised players or a clobbered context.
void controller(std::uint8_t* rdram, recomp_context* ctx) {
    assert(stage++ == 0 && ctx->r4 == 0);
    MEM_W(0, addr(addresses::NumberOfActivePlayers)) = 1;
    for (int i = 0; i < 4; ++i) MEM_B(i, addr(addresses::ActivePlayersArray)) = i == 0;
    ctx->r4 = 999;
}
void inputs(std::uint8_t*, recomp_context*) { assert(stage++ == 1); }
void time_trial(std::uint8_t* rdram, recomp_context* ctx) {
    assert(stage++ == 2 && ctx->r4 == 0);
    assert(MEM_W(0, addr(addresses::TracksMode)) == 1);
}
void drumstick(std::uint8_t*, recomp_context* ctx) { ctx->r2 = unlocks & 1; }
void tt(std::uint8_t*, recomp_context* ctx) { ctx->r2 = unlocks & 2; }
void ai(std::uint8_t* rdram, recomp_context* ctx) {
    assert(stage++ == 3 && ctx->r4 == 1);
    const std::uint32_t tables77[] = {0x800DFDD0, 0x800DFE40, 0x800DFEC0, 0x800DFF40};
    const std::uint32_t tables80[] = {0x800E0350, 0x800E03C0, 0x800E0440, 0x800E04C0};
    assert(static_cast<std::uint32_t>(MEM_W(0, addr(rev80() ? 0x8012696C : 0x801263CC))) ==
           (rev80() ? tables80 : tables77)[unlocks]);
    assert(MEM_W(0, addr(addresses::NumberOfActivePlayers)) == 1);
    assert(MEM_W(0, addr(addresses::NumberOfReadyPlayers)) == 1);
    for (int i = 0; i < 4; ++i)
        assert(MEM_B(i, addr(addresses::CharacterSelectStatus)) == (i == 0 ? 2 : 0));
    assert(MEM_B(0, addr(addresses::CharacterIdSlots)) == 9);
    for (int i = 1; i < 8; ++i) MEM_B(i, addr(addresses::CharacterIdSlots)) = i - 1;
    ctx->r2 = 999;
}
void headers(std::uint8_t* rdram, recomp_context*) {
    assert(stage++ == 4);
    for (int i = 0; i < 8; ++i) committed[i] = MEM_B(i, addr(addresses::CharacterIdSlots));
}
void default_vehicle(std::uint8_t*, recomp_context* ctx) {
    assert(ctx->r4 == static_cast<gpr>(tracks::track_override()));
    ctx->r2 = vehicle;
    ctx->r4 = 999;
}
void usable(std::uint8_t*, recomp_context* ctx) {
    assert(ctx->r4 == static_cast<gpr>(tracks::track_override()));
    ctx->r2 = allowed;
}
void save_vehicle(std::uint8_t*, recomp_context* ctx) { saved_vehicle = static_cast<int>(ctx->r4); }
}
namespace dkr::runtime {
const GamePayload* active_payload() { return payload_available ? &payload : nullptr; }
}

int main() {
    const auto root = std::filesystem::temp_directory_path() /
        ("dkr-track-lab-runtime-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    const auto folder = root / "tracks" / "test.dkrmap";
    std::filesystem::create_directories(folder);
    std::ofstream(folder / "manifest.json") <<
        R"({"schemaVersion":1,"id":"test","name":"Test","adds":[{"section":"LEVEL_HEADERS","file":"header.bin"}]})";
    std::string header(196, '\0');
    header[0x37] = 73; // Inherit Ancient Lake's retail object maps.
    header[0xBB] = 5;
    std::ofstream(folder / "header.bin", std::ios::binary) << header;
    tracks::scan(root / "tracks");
    const std::int32_t retail[] = {0, 196, -1};
    assert(!tracks::build_extended_table(tracks::Section::LevelHeaders, retail).empty());
    tracks::arm_track_override("test");
    assert(tracks::track_override() == 1);

    payload.titlescreen_controller_assign = controller;
    payload.input_assign_players = inputs;
    payload.unlock_drumstick = drumstick;
    payload.unlock_tt = tt;
    payload.charselect_assign_ai = ai;
    payload.init_racer_headers = headers;
    payload.set_time_trial_enabled = time_trial;
    payload.leveltable_vehicle_default = default_vehicle;
    payload.leveltable_vehicle_usable = usable;
    payload.set_level_default_vehicle = save_vehicle;
    std::vector<std::uint8_t> memory(8 * 1024 * 1024);
    auto* rdram = memory.data();

    for (const auto revision : {dkr::runtime::rom::Revision::UsV77, dkr::runtime::rom::Revision::UsV80}) {
        assert(addresses::select(revision));
        for (unlocks = 0; unlocks < 4; ++unlocks) {
            std::fill(memory.begin(), memory.end(), 0xA5);
            stage = 0;
            committed.fill(0);
            tracks::set_auto_boot(false);
            tracks::set_auto_boot(true);
            recomp_context context{};
            context.r2 = 123;
            context.r4 = 456;
            context.r29 = 0x80400000;
            auto expected = context;
            // An unavailable guest payload must not consume the one-shot.
            payload_available = false;
            dkr_custom_tracks_auto_boot(rdram, &context);
            assert(std::memcmp(&context, &expected, sizeof(context)) == 0 && stage == 0);
            payload_available = true;
            dkr_custom_tracks_auto_boot(rdram, &context);
            expected.r2 = 0x201;
            assert(std::memcmp(&context, &expected, sizeof(context)) == 0);
            assert(stage == 5 && committed[0] == 9);
            for (int i = 1; i < 8; ++i) assert(committed[i] == i - 1);
            assert(MEM_W(0, addr(rev80() ? 0x80123A80 : 0x80123500)) == 0);
            // This is a HUD byte, not gGameNumPlayers; never overwrite it.
            assert(static_cast<unsigned char>(MEM_B(0, addr(addresses::NumberOfGameplayPlayers))) == 0xA5);
            const auto booted = memory;
            dkr_custom_tracks_auto_boot(rdram, &context);
            assert(memory == booted && stage == 5);
        }
        // Cars, hovercraft and planes replace stale selections on every load,
        // including restarts and multiplayer tests; the roster stays intact.
        MEM_W(0, addr(addresses::GameMode)) = 0;
        for (vehicle = 0; vehicle < 3; ++vehicle) {
            for (int players = 1; players <= 4; ++players) {
                recomp_context context{};
                context.r4 = tracks::track_override();
                context.r5 = players - 1;
                context.r6 = 3;
                context.r7 = 99;
                auto expected = context;
                expected.r7 = vehicle;
                for (int i = 0; i < 4; ++i) MEM_B(i, addr(addresses::PlayerSelectVehicle)) = 99;
                dkr_custom_tracks_prepare_vehicle(rdram, &context);
                assert(std::memcmp(&context, &expected, sizeof(context)) == 0);
                assert(saved_vehicle == vehicle);
                for (int i = 0; i < 4; ++i)
                    assert(MEM_B(i, addr(addresses::PlayerSelectVehicle)) == (i < players ? vehicle : 99));
                const auto prepared = memory;
                dkr_custom_tracks_prepare_vehicle(rdram, &context);
                assert(memory == prepared);
            }
        }
        // Debug vehicles remain load arguments, never indices into the three
        // normal vehicle records; AI selections use an allowed normal vehicle.
        vehicle = 7;
        allowed = 4;
        recomp_context context{};
        context.r4 = tracks::track_override();
        dkr_custom_tracks_prepare_vehicle(rdram, &context);
        assert(context.r7 == 7 && MEM_B(0, addr(addresses::PlayerSelectVehicle)) == 2);

        // Unrelated levels, menu-style player counts and disarmed testing must
        // leave both guest memory and every register untouched.
        for (int inactive = 0; inactive < 4; ++inactive) {
            context.r4 = inactive == 0 ? 0 : 1;
            context.r5 = inactive == 1 ? static_cast<gpr>(-1) : 0;
            if (inactive == 2) tracks::arm_track_override("");
            if (inactive == 3) {
                tracks::arm_track_override("test");
                MEM_W(0, addr(addresses::GameMode)) = 1; // menu preview with racers
            }
            const auto before = memory;
            const auto registers = context;
            dkr_custom_tracks_prepare_vehicle(rdram, &context);
            assert(memory == before && std::memcmp(&context, &registers, sizeof(context)) == 0);
        }
        tracks::arm_track_override("test");
    }
    tracks::set_auto_boot(false);
    tracks::arm_track_override("");
    std::filesystem::remove_all(root);
    std::puts("[test][track-lab-runtime] both revisions PASS");
}

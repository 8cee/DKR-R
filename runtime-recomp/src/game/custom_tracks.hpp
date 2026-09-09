#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

// Project-owned custom track support.
//
// DKR reaches every level through one indirection that is entirely data
// driven, so added tracks need no instruction patching:
//
//   gTempAssetTable = asset_table_load(ASSET_LEVEL_HEADERS_TABLE);
//   for (i = 0; gTempAssetTable[i] != -1; i++) {}   // count, then i--
//   if (levelId >= i) { /* retail range check, derived from the table */ }
//   offset = gTempAssetTable[levelId];
//   size   = gTempAssetTable[levelId + 1] - offset; // size BY DIFFERENCE
//   asset_load(ASSET_LEVEL_HEADERS, dest, offset, size);
//
// Two consequences drive this module:
//
//   * Publishing a longer table before the -1 terminator grows the level
//     count, the retail range check and gGlobalLevelTable together. A header
//     whose `world` field exceeds the retail maximum also grows
//     gNumberOfWorlds, because level_global_init derives it as a running max.
//
//   * Because size comes from the difference between consecutive entries, a
//     custom offset cannot be an arbitrary token: overwriting the retail end
//     offset would corrupt the size of the LAST retail entry. Custom offsets
//     therefore begin exactly AT the retail end offset and advance by exact
//     entry sizes, so the payload behaves as though appended to the section:
//
//       retail : [o0, o1, ..., o(n-1), oEnd, -1]                 -> n entries
//       result : [o0, o1, ..., o(n-1), oEnd, oEnd+s0, ..., E, -1] -> n+K
//
//     Retail arithmetic is untouched (o(n-1)'s size is still oEnd - o(n-1)),
//     custom entry j sits at table index n+j, and `offset >= oEnd` is the
//     discriminator that routes a load to a mod payload instead of the ROM.
namespace dkr::runtime::custom_tracks {

// Sections a custom track can contribute to. Each has a parallel `_TABLE`
// section in DKR's asset LUT; the table is what this module rewrites.
enum class Section {
    LevelHeaders,
    LevelObjectMaps,
    LevelNames,
    LevelModels,
};

// A level owns two object maps, and init_track spawns from both:
//
//   init_track(geometry, skybox, players, vehicle, entrance,
//              header->collectables,   // 0x36 - coins, balloons, items
//              header->unkBA);         // 0xBA - checkpoints, spawns, cameras
//
// They are the same asset section, so a track that replaces objects has to say
// which of the two a payload is. Merging them loses that split: structural
// objects would spawn with the collectable flag while the retail structure map
// kept spawning alongside.
enum class MapSlot {
    None,          // not an object map
    Structure,     // header 0xBA
    Collectables,  // header 0x36
};

struct Entry {
    Section section = Section::LevelHeaders;
    MapSlot slot = MapSlot::None;
    // Position among this section's added entries, in manifest order. The
    // resulting level id is the retail count plus this ordinal, resolved at
    // table-build time and reported back through resolved_level_id().
    std::uint32_t ordinal = 0;
    std::vector<std::uint8_t> bytes;
};

struct Track {
    std::string id;
    std::string name;
    std::string author;
    std::filesystem::path source;
    std::vector<Entry> entries;
    bool enabled = true;
};

// Scans `directory` for *.dkrmap archives and parses their manifests. Invalid
// archives are reported and skipped; one bad mod never prevents startup.
void scan(const std::filesystem::path& directory);

// Where scan() last looked. The importer copies into it, so the install
// location is decided in one place rather than repeated in the UI.
[[nodiscard]] std::filesystem::path directory();

// An second directory, chosen by the author, scanned in place alongside the
// install directory. Copying is right for a track you want to keep; it is
// wrong while authoring, where the folder the exporter writes to should simply
// be the folder the game reads. Point this at that folder and a re-export is
// picked up by a rescan with no copy step at all.
//
// Persisted beside the settings so it survives a restart. Empty disables it.
void set_working_directory(const std::filesystem::path& directory);
[[nodiscard]] std::filesystem::path working_directory();

// Copies a *.dkrmap directory into the install location and rescans. Returns
// false with a reason in `error` when the source is not a track.
bool install(const std::filesystem::path& source, std::string& error);

// Returns a snapshot. The UI thread reads this while an authoring reload can
// be replacing the backing vector, so a reference would dangle.
[[nodiscard]] std::vector<Track> tracks();
[[nodiscard]] std::size_t enabled_count();
void set_enabled(const std::string& id, bool enabled);

// Re-reads every archive from disk. Paired with the retail restart path this
// is the authoring hot-reload: save in the editor, restart the track, race the
// new geometry without leaving the process.
void reload();

// Level id assigned to a track's header after the last table build, or -1
// when the track is disabled or contributes no header.
[[nodiscard]] std::int32_t resolved_level_id(const std::string& track_id);

// Track Lab: force every level load to resolve to one level id, so an author
// can reach a track without walking the retail menus for it.
//
// DKR already owns this path. get_track_id_to_load() returns gTrackIdToLoad
// whenever tracks mode or gTrackSpecifiedWithTrackIdToLoad is set, and the
// retail Track Select and Trophy Race both drive it. The override reuses that
// return value instead of introducing a second way to choose a level.
//
// The override is deliberately sticky rather than one-shot: paired with the
// retail L+Z restart it gives an authoring loop where the same track reloads
// on every restart. Pass kNoTrackOverride to return to retail selection.
// The override is armed by track identity, not by level id, because the id a
// track receives is only known once the extended table has been built - which
// happens on the first level load, long after the launcher has drawn its list.
// Resolution is therefore deferred to the moment the game asks.
inline constexpr std::int32_t kNoTrackOverride = -1;

void arm_track_override(std::string track_id);   // empty string disarms
[[nodiscard]] std::string armed_track_id();
[[nodiscard]] std::int32_t track_override();

// Auto boot: skip the logos, title, file select and character select and drop
// straight into the armed track.
//
// This does not fabricate a load. mode_menu already starts a level whenever
// menu_loop returns MENU_RESULT_FLAGS_200 with a map id in its low bits, so
// auto boot returns exactly that result and lets retail run its own sequence:
// vehicle default, entrance, cutscene, game mode and load_level_game.
//
// It fires once per launch. Restarting in place with L+Z keeps reloading the
// same track, while quitting still returns to the menus rather than trapping
// the player in a loop they cannot leave.
void set_auto_boot(bool enabled);
[[nodiscard]] bool auto_boot_enabled();

// Returns true exactly once while auto boot is armed, then disarms it.
[[nodiscard]] bool consume_auto_boot();

// Builds the replacement table for `section` from the retail table (terminated
// by -1). Returns an empty vector when nothing is added, meaning the caller
// must publish the retail table unchanged.
[[nodiscard]] std::vector<std::int32_t> build_extended_table(
    Section section, const std::int32_t* retail_table);

// Resolves an offset produced by build_extended_table. Returns nullptr when
// the offset belongs to the ROM or does not cover `size` bytes, in which case
// the caller must fall back to the retail loader.
[[nodiscard]] const std::uint8_t* payload_for(
    Section section, std::uint32_t offset, std::int32_t size);

// A level header names its object map by index, and that index only exists once
// the extended object-map table has been built. Given a custom entry in `from`
// at `offset`, this returns the index the same track's entry received in `to`,
// so a header can be fixed up as it is served instead of asking the author to
// write a number they cannot know.
//
// Returns -1 when the offset is not custom, when the track contributes nothing
// to `to`, or when `to`'s table has not been built yet.
// `slot` selects between a section's two payloads where one exists; pass
// MapSlot::None for sections that have only one.
[[nodiscard]] std::int32_t sibling_index(Section from, std::uint32_t offset,
                                          Section to, MapSlot slot);

} // namespace dkr::runtime::custom_tracks

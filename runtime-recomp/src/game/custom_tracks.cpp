#include "custom_tracks.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <mutex>
#include <utility>

#include <json/json.hpp>
#include <unordered_map>

namespace {

using dkr::runtime::custom_tracks::Entry;
using dkr::runtime::custom_tracks::MapSlot;
using dkr::runtime::custom_tracks::Section;
using dkr::runtime::custom_tracks::Track;

constexpr std::size_t kSectionCount = 4U;

std::size_t section_slot(Section section) {
    return static_cast<std::size_t>(section);
}

// Per-section state captured during the most recent table build. `end_offset`
// is the retail section's end offset, which doubles as the base of the custom
// range and therefore as the ROM/mod discriminator.
// One added entry's span and the index it received, kept so a header can be
// pointed at the object map its own track supplied.
struct AddedEntry {
    std::string track_id;
    dkr::runtime::custom_tracks::MapSlot slot =
        dkr::runtime::custom_tracks::MapSlot::None;
    std::uint32_t offset = 0;   // absolute section offset
    std::uint32_t size = 0;
    std::uint32_t index = 0;    // index assigned within this section
};

struct SectionState {
    bool built = false;
    std::uint32_t end_offset = 0;
    std::vector<std::uint8_t> blob;      // enabled payloads, concatenated
    std::uint32_t retail_count = 0;
    std::vector<AddedEntry> added;
};

// Track Lab's armed track, by manifest id. Guarded by g_mutex because
// resolving it reads the same table that build_extended_table writes; the
// lookup happens once per level load, so the lock is never contended.
std::string g_armed_track;
bool g_auto_boot = false;

std::mutex g_mutex;
std::vector<Track> g_tracks;
std::array<SectionState, kSectionCount> g_sections{};
std::unordered_map<std::string, std::int32_t> g_resolved_level_ids;
std::filesystem::path g_directory;
std::filesystem::path g_working_directory;

// Rescanning replaces the track list, and the section blobs a live level is
// reading are built from it. A rescan requested while a level is loaded is
// therefore deferred to the next table build, which is a level-load boundary.
bool g_rescan_pending = false;

// Entries of one section, in a stable order: track order as scanned, then
// manifest order within a track. The resulting level ids must not shift
// between builds within a session, or a mid-session reload would move a track
// out from under a level id the game is already holding.
std::vector<const Entry*> enabled_entries(Section section) {
    std::vector<const Entry*> result;
    for (const Track& track : g_tracks) {
        if (!track.enabled) {
            continue;
        }
        for (const Entry& entry : track.entries) {
            if (entry.section == section) {
                result.push_back(&entry);
            }
        }
    }
    return result;
}

const Track* track_owning(Section section, const Entry* entry) {
    for (const Track& track : g_tracks) {
        for (const Entry& candidate : track.entries) {
            if (&candidate == entry && candidate.section == section) {
                return &track;
            }
        }
    }
    return nullptr;
}

} // namespace

namespace dkr::runtime::custom_tracks {

// Defined below; assumes g_mutex is already held.
void scan_locked(const std::filesystem::path& directory);

std::vector<Track> tracks() {
    std::scoped_lock lock(g_mutex);
    return g_tracks;
}

std::size_t enabled_count() {
    std::scoped_lock lock(g_mutex);
    return static_cast<std::size_t>(std::count_if(
        g_tracks.begin(), g_tracks.end(),
        [](const Track& track) { return track.enabled; }));
}

void set_enabled(const std::string& id, bool enabled) {
    std::scoped_lock lock(g_mutex);
    for (Track& track : g_tracks) {
        if (track.id == id) {
            track.enabled = enabled;
        }
    }
}

std::int32_t resolved_level_id(const std::string& track_id) {
    std::scoped_lock lock(g_mutex);
    const auto found = g_resolved_level_ids.find(track_id);
    return found == g_resolved_level_ids.end() ? -1 : found->second;
}

void arm_track_override(std::string track_id) {
    std::scoped_lock lock(g_mutex);
    if (g_armed_track == track_id) {
        return;
    }
    g_armed_track = std::move(track_id);
    if (g_armed_track.empty()) {
        std::fprintf(stderr, "[custom-tracks] track override cleared\n");
    } else {
        std::fprintf(stderr, "[custom-tracks] track override armed: %s\n",
                     g_armed_track.c_str());
    }
}

std::string armed_track_id() {
    std::scoped_lock lock(g_mutex);
    return g_armed_track;
}

void set_auto_boot(bool enabled) {
    std::scoped_lock lock(g_mutex);
    if (g_auto_boot == enabled) {
        return;
    }
    g_auto_boot = enabled;
    std::fprintf(stderr, "[custom-tracks] auto boot %s\n",
                 enabled ? "enabled" : "disabled");
}

bool auto_boot_enabled() {
    std::scoped_lock lock(g_mutex);
    return g_auto_boot;
}

bool consume_auto_boot() {
    std::scoped_lock lock(g_mutex);
    if (!g_auto_boot) {
        return false;
    }
    g_auto_boot = false;
    std::fprintf(stderr, "[custom-tracks] auto boot fired\n");
    return true;
}

std::int32_t track_override() {
    std::scoped_lock lock(g_mutex);
    if (g_armed_track.empty()) {
        return kNoTrackOverride;
    }
    // Resolved late on purpose: the id only exists once build_extended_table
    // has run, so arming in the launcher and racing later both work.
    const auto found = g_resolved_level_ids.find(g_armed_track);
    return found == g_resolved_level_ids.end() ? kNoTrackOverride
                                                : found->second;
}

std::vector<std::int32_t> build_extended_table(
    Section section, const std::int32_t* retail_table) {
    std::scoped_lock lock(g_mutex);

    // A rescan asked for while a level was live waits here. This is a level
    // load, so replacing the track list now cannot disturb anything that is
    // already running.
    if (g_rescan_pending) {
        std::fprintf(stderr, "[custom-tracks] applying deferred rescan\n");
        scan_locked(g_directory);
    }

    std::vector<std::int32_t> result;
    if (retail_table == nullptr) {
        return result;
    }

    // Retail layout is [o0 .. o(n-1), oEnd, -1]: count the entries ahead of
    // the terminator, then drop one, exactly as level_global_init does. The
    // dropped slot is the end offset that sizes the final retail entry.
    std::uint32_t counted = 0;
    constexpr std::uint32_t kSanityLimit = 4096U;
    while (counted < kSanityLimit && retail_table[counted] != -1) {
        ++counted;
    }
    if (counted == 0 || counted >= kSanityLimit) {
        std::fprintf(stderr,
                     "[custom-tracks] refusing an unterminated asset table\n");
        return result;
    }
    const std::uint32_t retail_count = counted - 1U;

    const std::vector<const Entry*> entries = enabled_entries(section);
    SectionState& state = g_sections[section_slot(section)];
    state.retail_count = retail_count;
    state.end_offset = static_cast<std::uint32_t>(retail_table[retail_count]);
    state.blob.clear();
    state.added.clear();

    if (section == Section::LevelHeaders) {
        // Drop every previously resolved id before reassigning. Without this a
        // track that has since been disabled would keep reporting the level id
        // it held in an earlier build, and the UI would offer to launch an
        // index the rebuilt table no longer defines.
        g_resolved_level_ids.clear();
    }
    state.built = true;

    if (entries.empty()) {
        // Nothing added: the caller publishes the retail table unchanged.
        return result;
    }

    // Retail offsets are copied verbatim, INCLUDING the end offset, which
    // becomes the first custom entry's offset. That keeps the last retail
    // entry's size (oEnd - o(n-1)) exactly as authored.
    result.assign(retail_table, retail_table + retail_count + 1U);

    std::uint32_t running = state.end_offset;
    for (std::uint32_t ordinal = 0; ordinal < entries.size(); ++ordinal) {
        const Entry* entry = entries[ordinal];
        const Track* owner = track_owning(section, entry);
        const std::uint32_t entry_size =
            static_cast<std::uint32_t>(entry->bytes.size());

        state.added.push_back(AddedEntry{
            owner == nullptr ? std::string{} : owner->id,
            entry->slot,
            running, entry_size, retail_count + ordinal});

        state.blob.insert(state.blob.end(), entry->bytes.begin(),
                          entry->bytes.end());
        running += entry_size;
        result.push_back(static_cast<std::int32_t>(running));

        if (section == Section::LevelHeaders && owner != nullptr) {
            g_resolved_level_ids[owner->id] =
                static_cast<std::int32_t>(retail_count + ordinal);
        }
    }
    result.push_back(-1);

    std::fprintf(stderr,
                 "[custom-tracks] section %zu: %u retail + %zu added\n",
                 section_slot(section), retail_count, entries.size());
    return result;
}

const std::uint8_t* payload_for(Section section, std::uint32_t offset,
                                 std::int32_t size) {
    std::scoped_lock lock(g_mutex);
    const SectionState& state = g_sections[section_slot(section)];
    if (!state.built || size <= 0 || offset < state.end_offset) {
        return nullptr; // Retail range: the ROM loader owns it.
    }
    const std::uint64_t relative =
        static_cast<std::uint64_t>(offset) - state.end_offset;
    if (relative + static_cast<std::uint64_t>(size) > state.blob.size()) {
        std::fprintf(stderr,
                     "[custom-tracks] rejecting out-of-range custom read\n");
        return nullptr;
    }
    return state.blob.data() + relative;
}

std::int32_t sibling_index(Section from, std::uint32_t offset, Section to,
                            MapSlot slot) {
    std::scoped_lock lock(g_mutex);
    const SectionState& source = g_sections[section_slot(from)];
    const SectionState& target = g_sections[section_slot(to)];
    if (!source.built || !target.built) {
        return -1;
    }
    for (const AddedEntry& entry : source.added) {
        if (offset < entry.offset || offset >= entry.offset + entry.size) {
            continue;
        }
        if (entry.track_id.empty()) {
            return -1;
        }
        for (const AddedEntry& sibling : target.added) {
            if (sibling.track_id == entry.track_id && sibling.slot == slot) {
                return static_cast<std::int32_t>(sibling.index);
            }
        }
        return -1; // The track supplies nothing for that section and slot.
    }
    return -1; // Not a custom offset.
}

} // namespace dkr::runtime::custom_tracks


namespace {

const std::unordered_map<std::string, Section>& section_names() {
    static const std::unordered_map<std::string, Section> names{
        {"LEVEL_HEADERS", Section::LevelHeaders},
        {"LEVEL_OBJECT_MAPS", Section::LevelObjectMaps},
        {"LEVEL_NAMES", Section::LevelNames},
        {"LEVEL_MODELS", Section::LevelModels},
    };
    return names;
}

bool read_file(const std::filesystem::path& path,
               std::vector<std::uint8_t>& bytes) {
    std::error_code code;
    const auto size = std::filesystem::file_size(path, code);
    if (code || size == 0 || size > (16U * 1024U * 1024U)) {
        return false;
    }
    std::FILE* file = std::fopen(path.string().c_str(), "rb");
    if (file == nullptr) {
        return false;
    }
    bytes.resize(static_cast<std::size_t>(size));
    const std::size_t read = std::fread(bytes.data(), 1, bytes.size(), file);
    std::fclose(file);
    return read == bytes.size();
}

// Parses one unpacked track. `.dkrmap` archives are unpacked into this form by
// the importer; the directory form is also what an author edits in place, so
// reload() can pick up an editor's save without a repack.
bool parse_track(const std::filesystem::path& root, Track& track,
                 std::string& error) {
    std::vector<std::uint8_t> manifest_bytes;
    if (!read_file(root / "manifest.json", manifest_bytes)) {
        error = "manifest.json is missing or unreadable";
        return false;
    }

    nlohmann::json manifest = nlohmann::json::parse(
        manifest_bytes.begin(), manifest_bytes.end(), nullptr, false);
    if (manifest.is_discarded() || !manifest.is_object()) {
        error = "manifest.json is not valid JSON";
        return false;
    }
    if (manifest.value("schemaVersion", 0) != 1) {
        error = "unsupported schemaVersion";
        return false;
    }

    track.id = manifest.value("id", std::string{});
    track.name = manifest.value("name", track.id);
    track.author = manifest.value("author", std::string{});
    track.source = root;
    if (track.id.empty()) {
        error = "manifest.json has no id";
        return false;
    }

    const auto adds = manifest.find("adds");
    if (adds == manifest.end() || !adds->is_array() || adds->empty()) {
        error = "manifest.json adds nothing";
        return false;
    }
    for (const auto& item : *adds) {
        const auto named =
            section_names().find(item.value("section", std::string{}));
        if (named == section_names().end()) {
            error = "unknown section in adds";
            return false;
        }
        Entry entry;
        entry.section = named->second;

        // A level spawns from two object maps with different roles, so a
        // payload for that section has to say which one it is. Refusing the
        // ambiguous case is deliberate: a merged map silently spawns
        // checkpoints and spawn points as collectables while the retail
        // structure map keeps running alongside it.
        if (entry.section == Section::LevelObjectMaps) {
            const std::string slot = item.value("slot", std::string{});
            if (slot == "structure") {
                entry.slot = MapSlot::Structure;
            } else if (slot == "collectables") {
                entry.slot = MapSlot::Collectables;
            } else {
                error = slot.empty()
                    ? "a LEVEL_OBJECT_MAPS entry needs \"slot\": "
                      "\"structure\" or \"collectables\""
                    : "unknown object map slot \"" + slot + "\"";
                return false;
            }
        }
        const std::string file = item.value("file", std::string{});
        // Keep payloads inside the track directory: a manifest must not be
        // able to name an arbitrary path on the user's machine.
        if (file.empty() || file.find("..") != std::string::npos ||
            std::filesystem::path(file).is_absolute()) {
            error = "adds entry has an unsafe file path";
            return false;
        }
        if (!read_file(root / file, entry.bytes)) {
            error = "could not read " + file;
            return false;
        }
        track.entries.push_back(std::move(entry));
    }

    // A header carries 0 in both object map fields, because the real indices
    // are assigned at load. That is only safe when both are patched: 0 is a
    // valid index, not "no map", so an unpatched field makes the game spawn
    // some other level's layer over this track - which hangs it. Refuse the
    // package rather than let it load and freeze.
    const Entry* header = nullptr;
    for (const Entry& entry : track.entries) {
        if (entry.section == Section::LevelHeaders) {
            header = &entry;
        }
    }
    if (header != nullptr) {
        const auto supplies = [&track](MapSlot slot) {
            return std::any_of(track.entries.begin(), track.entries.end(),
                               [slot](const Entry& e) {
                                   return e.section ==
                                              Section::LevelObjectMaps &&
                                          e.slot == slot;
                               });
        };
        // Reading the authored value matters: a header carrying a real retail
        // index needs no payload and is perfectly valid. Only a zero is
        // dangerous, and only when nothing will overwrite it.
        const auto field_at = [header](std::size_t offset) -> int {
            if (header->bytes.size() < offset + 2U) {
                return -1; // Too short to contain it; nothing to judge.
            }
            return (header->bytes[offset] << 8) | header->bytes[offset + 1];
        };
        struct Check { std::size_t offset; MapSlot slot; const char* name; };
        for (const Check& check : {Check{0x36, MapSlot::Collectables,
                                         "collectables"},
                                   Check{0xBA, MapSlot::Structure,
                                         "structure"}}) {
            if (field_at(check.offset) == 0 && !supplies(check.slot)) {
                error = std::string("the header leaves its ") + check.name +
                        " object map at 0 and the track supplies none; 0 is "
                        "object map 0, not \"no map\", so the game would spawn "
                        "another level's objects";
                return false;
            }
        }
    }
    return true;
}

} // namespace

namespace dkr::runtime::custom_tracks {

namespace {

std::filesystem::path working_setting_file() {
    // Beside the install directory, so it lives with the rest of the
    // configuration rather than in the tracks folder it points away from.
    return g_directory.empty()
        ? std::filesystem::path{}
        : g_directory.parent_path() / "custom-tracks-path.txt";
}

// Appends every *.dkrmap in one directory. Called for the install directory
// and, when set, for the author's working directory.
void scan_one(const std::filesystem::path& directory, const char* label) {
    std::error_code code;
    if (directory.empty() ||
        !std::filesystem::is_directory(directory, code)) {
        return;
    }
    for (const auto& item :
         std::filesystem::directory_iterator(directory, code)) {
        if (!item.is_directory() || item.path().extension() != ".dkrmap") {
            continue;
        }
        Track track;
        std::string error;
        if (!parse_track(item.path(), track, error)) {
            std::fprintf(stderr, "[custom-tracks] skipped %s: %s\n",
                         item.path().filename().string().c_str(),
                         error.c_str());
            continue;
        }
        // Ids key every cross-reference: which level a track resolves to, and
        // which object map a header is pointed at. Two tracks sharing one id
        // make those lookups pick an arbitrary winner, so a header can end up
        // aimed at the other copy's maps. Importing a track that is also being
        // watched in a working folder produces exactly that pair, so refuse
        // the duplicate rather than load it.
        const auto clash = std::find_if(
            g_tracks.begin(), g_tracks.end(),
            [&track](const Track& existing) {
                return existing.id == track.id;
            });
        if (clash != g_tracks.end()) {
            std::fprintf(stderr,
                         "[custom-tracks] skipped %s: id \"%s\" is already "
                         "loaded from %s\n",
                         item.path().filename().string().c_str(),
                         track.id.c_str(),
                         clash->source.string().c_str());
            continue;
        }

        std::fprintf(stderr, "[custom-tracks] loaded %s by %s (%s)\n",
                     track.name.c_str(),
                     track.author.empty() ? "unknown" : track.author.c_str(),
                     label);
        g_tracks.push_back(std::move(track));
    }
}

} // namespace

void scan(const std::filesystem::path& directory) {
    std::scoped_lock lock(g_mutex);
    scan_locked(directory);
}

void scan_locked(const std::filesystem::path& directory) {
    g_rescan_pending = false;
    g_directory = directory;
    g_tracks.clear();
    g_resolved_level_ids.clear();

    // Restore the author's working directory before scanning so a restart
    // keeps reading wherever they pointed it.
    if (g_working_directory.empty()) {
        std::vector<std::uint8_t> stored;
        if (read_file(working_setting_file(), stored) && !stored.empty()) {
            std::string text(stored.begin(), stored.end());
            while (!text.empty() &&
                   (text.back() == '\n' || text.back() == '\r')) {
                text.pop_back();
            }
            g_working_directory = std::filesystem::u8path(text);
        }
    }

    scan_one(directory, "installed");
    if (g_working_directory != directory) {
        scan_one(g_working_directory, "working folder");
    }
}

void set_working_directory(const std::filesystem::path& directory) {
    {
        std::scoped_lock lock(g_mutex);
        g_working_directory = directory;
        const std::filesystem::path setting = working_setting_file();
        if (!setting.empty()) {
            std::error_code code;
            if (directory.empty()) {
                std::filesystem::remove(setting, code);
            } else {
                const auto utf8 = directory.u8string();
                const std::string text(utf8.begin(), utf8.end());
                std::ofstream out(setting, std::ios::binary);
                out.write(text.data(),
                          static_cast<std::streamsize>(text.size()));
            }
        }
        std::fprintf(stderr, "[custom-tracks] working folder %s\n",
                     directory.empty() ? "cleared"
                                       : directory.string().c_str());
    }
    reload();
}

std::filesystem::path working_directory() {
    std::scoped_lock lock(g_mutex);
    return g_working_directory;
}

std::filesystem::path directory() {
    std::scoped_lock lock(g_mutex);
    return g_directory;
}

bool install(const std::filesystem::path& source, std::string& error) {
    std::filesystem::path destination_root;
    {
        std::scoped_lock lock(g_mutex);
        destination_root = g_directory;
    }
    if (destination_root.empty()) {
        error = "Custom tracks have no install directory yet.";
        return false;
    }

    std::error_code code;
    if (!std::filesystem::is_directory(source, code)) {
        error = "A track is a .dkrmap folder, not a single file.";
        return false;
    }
    if (source.extension() != ".dkrmap") {
        error = "That folder is not named *.dkrmap.";
        return false;
    }
    if (!std::filesystem::is_regular_file(source / "manifest.json", code)) {
        error = "That folder has no manifest.json.";
        return false;
    }

    // Parse before copying so a broken track is rejected rather than installed
    // and then reported as skipped on the next scan.
    Track probe;
    if (!parse_track(source, probe, error)) {
        return false;
    }

    const std::filesystem::path destination =
        destination_root / source.filename();
    std::filesystem::create_directories(destination_root, code);
    if (std::filesystem::exists(destination, code)) {
        std::filesystem::remove_all(destination, code);
    }
    std::filesystem::copy(source, destination,
                          std::filesystem::copy_options::recursive, code);
    if (code) {
        error = "Could not copy the track: " + code.message();
        return false;
    }

    reload();
    error.clear();
    return true;
}

void reload() {
    std::scoped_lock lock(g_mutex);

    // Once a level table has been built the game may be inside a level whose
    // objects come from the blobs a rescan would rebuild. Defer rather than
    // rebuild underneath it; build_extended_table picks this up at the next
    // level load, which is the only safe moment.
    if (g_sections[section_slot(Section::LevelHeaders)].built) {
        g_rescan_pending = true;
        std::fprintf(stderr,
                     "[custom-tracks] rescan deferred to the next level load\n");
        return;
    }

    // Preserve the author's enable/disable choices across the reload.
    std::vector<std::pair<std::string, bool>> previous;
    for (const Track& track : g_tracks) {
        previous.emplace_back(track.id, track.enabled);
    }
    scan_locked(g_directory);
    for (Track& track : g_tracks) {
        for (const auto& [id, enabled] : previous) {
            if (track.id == id) {
                track.enabled = enabled;
            }
        }
    }
}

} // namespace dkr::runtime::custom_tracks

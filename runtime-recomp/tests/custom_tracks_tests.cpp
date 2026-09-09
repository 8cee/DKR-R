#include "custom_tracks.hpp"

#include <cassert>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

using namespace dkr::runtime::custom_tracks;

namespace {

// A retail-shaped table: [o0, o1, o2, oEnd, -1] describes three levels, the
// final entry existing only to size the last one by difference.
constexpr std::int32_t kRetail[] = {0x0, 0x100, 0x250, 0x400, -1};

void write_file(const std::filesystem::path& path, const std::string& text) {
    std::ofstream out(path, std::ios::binary);
    out.write(text.data(), static_cast<std::streamsize>(text.size()));
}

void write_track(const std::filesystem::path& root, const std::string& id,
                 std::size_t payload_size) {
    std::filesystem::create_directories(root);
    write_file(root / "manifest.json",
               "{\"schemaVersion\":1,\"id\":\"" + id + "\",\"name\":\"" + id +
                   "\",\"adds\":[{\"section\":\"LEVEL_HEADERS\","
                   "\"file\":\"h.bin\"}]}");
    write_file(root / "h.bin", std::string(payload_size, 'x'));
}

// Reproduces the retail counting loop from level_global_init verbatim.
int level_count(const std::vector<std::int32_t>& table) {
    int count = 0;
    while (table[count] != -1) {
        ++count;
    }
    return count - 1;
}

} // namespace

int main() {
    const std::filesystem::path root =
        std::filesystem::temp_directory_path() / "dkrr-custom-tracks-tests";
    std::filesystem::remove_all(root);
    write_track(root / "alpha.dkrmap", "alpha", 128U);
    write_track(root / "beta.dkrmap", "beta", 192U);

    scan(root);
    assert(tracks().size() == 2U);
    assert(enabled_count() == 2U);

    std::vector<std::int32_t> table =
        build_extended_table(Section::LevelHeaders, kRetail);
    assert(!table.empty());
    assert(level_count(table) == 5);

    // Every retail entry keeps its authored offset AND size. The third one is
    // the load-bearing case: its size still derives from the retail end offset
    // that the first custom entry now shares.
    assert(table[0] == 0x0 && table[1] - table[0] == 0x100);
    assert(table[1] == 0x100 && table[2] - table[1] == 0x150);
    assert(table[2] == 0x250 && table[3] - table[2] == 0x1B0);

    // Custom entries continue from the retail end offset by exact sizes.
    assert(table[3] == 0x400 && table[4] - table[3] == 128);
    assert(table[4] == 0x480 && table[5] - table[4] == 192);
    assert(resolved_level_id("alpha") == 3);
    assert(resolved_level_id("beta") == 4);

    // Retail offsets belong to the ROM; custom offsets resolve to a payload.
    assert(payload_for(Section::LevelHeaders, 0x250, 0x1B0) == nullptr);
    assert(payload_for(Section::LevelHeaders, 0x400, 128) != nullptr);
    assert(payload_for(Section::LevelHeaders, 0x480, 192) != nullptr);
    // A read that runs past the payload is refused rather than served short.
    assert(payload_for(Section::LevelHeaders, 0x480, 1024) == nullptr);

    // Disabling a track must not leave a stale level id behind: the remaining
    // track takes the freed id, and the disabled one reports none.
    set_enabled("alpha", false);
    table = build_extended_table(Section::LevelHeaders, kRetail);
    assert(level_count(table) == 4);
    assert(resolved_level_id("alpha") == -1);
    assert(resolved_level_id("beta") == 3);
    assert(table[3] == 0x400 && table[4] - table[3] == 192);

    // tracks() must hand back a snapshot, because a reload replaces the
    // backing vector while the UI thread is still reading it.
    const std::vector<Track> snapshot = tracks();
    reload();
    assert(snapshot.size() == 2U);
    bool disable_survived = false;
    for (const Track& track : tracks()) {
        if (track.id == "alpha" && !track.enabled) {
            disable_survived = true;
        }
    }
    assert(disable_survived);

    // A section with nothing added publishes an empty table, telling the
    // caller to keep the retail one untouched.
    assert(build_extended_table(Section::LevelModels, kRetail).empty());

    // A track that ships a header and an object map must have its header
    // pointed at its own map, and the two sections have different retail
    // counts, so the indices genuinely differ.
    std::filesystem::remove_all(root);
    {
        const std::filesystem::path pair = root / "paired.dkrmap";
        std::filesystem::create_directories(pair);
        write_file(pair / "manifest.json",
                   "{\"schemaVersion\":1,\"id\":\"paired\",\"name\":\"Paired\","
                   "\"adds\":[{\"section\":\"LEVEL_HEADERS\","
                   "\"file\":\"h.bin\"},"
                   "{\"section\":\"LEVEL_OBJECT_MAPS\",\"slot\":\"structure\","
                   "\"file\":\"s.bin\"},"
                   "{\"section\":\"LEVEL_OBJECT_MAPS\",\"slot\":\"collectables\","
                   "\"file\":\"o.bin\"}]}");
        write_file(pair / "h.bin", std::string(200U, 'h'));
        write_file(pair / "s.bin", std::string(48U, 's'));
        write_file(pair / "o.bin", std::string(64U, 'o'));
    }
    scan(root);
    assert(tracks().size() == 1U);

    // Headers: 3 retail entries. Object maps: a different table, 2 entries.
    constexpr std::int32_t kMaps[] = {0x0, 0x80, 0x100, -1};
    const std::vector<std::int32_t> headers =
        build_extended_table(Section::LevelHeaders, kRetail);
    const std::vector<std::int32_t> maps =
        build_extended_table(Section::LevelObjectMaps, kMaps);
    assert(level_count(headers) == 4);   // 3 retail + 1
    assert(level_count(maps) == 4);      // 2 retail + 2 slots

    assert(resolved_level_id("paired") == 3);

    // The two slots must resolve to DIFFERENT indices, and neither to the
    // level id: pointing both header fields at one map would spawn the same
    // objects twice and drop the other layer entirely.
    const std::int32_t structure = sibling_index(
        Section::LevelHeaders, 0x400, Section::LevelObjectMaps,
        MapSlot::Structure);
    const std::int32_t collectables = sibling_index(
        Section::LevelHeaders, 0x400, Section::LevelObjectMaps,
        MapSlot::Collectables);
    assert(structure == 2 && collectables == 3);

    // A retail offset has no sibling, and neither does an unrelated section.
    assert(sibling_index(Section::LevelHeaders, 0x100,
                         Section::LevelObjectMaps, MapSlot::Collectables) == -1);
    assert(sibling_index(Section::LevelHeaders, 0x400,
                         Section::LevelModels, MapSlot::None) == -1);

    // A header with only one of the two maps leaves the other field at 0,
    // which is object map 0 rather than "none" - the game then spawns another
    // level's layer and hangs. Such a package must be refused, not loaded.
    {
        const std::filesystem::path half = root / "halfmaps.dkrmap";
        std::filesystem::create_directories(half);
        write_file(half / "manifest.json",
                   "{\"schemaVersion\":1,\"id\":\"halfmaps\",\"name\":\"Half\","
                   "\"adds\":[{\"section\":\"LEVEL_HEADERS\","
                   "\"file\":\"h.bin\"},"
                   "{\"section\":\"LEVEL_OBJECT_MAPS\",\"slot\":\"structure\","
                   "\"file\":\"s.bin\"}]}");
        // Zero-filled, which is what the exporter writes into 0x36 and 0xBA
        // because the real indices are assigned at load.
        write_file(half / "h.bin", std::string(200U, '\0'));
        write_file(half / "s.bin", std::string(48U, 's'));
    }
    scan(root);
    for (const Track& track : tracks()) {
        assert(track.id != "halfmaps");
    }
    assert(tracks().size() == 1U);

    // The same header is fine once both maps are there, and equally fine with
    // neither if it names real retail indices instead of zero - a track built
    // on an existing level's objects needs no payload at all.
    {
        const std::filesystem::path retail_maps = root / "retailmaps.dkrmap";
        std::filesystem::create_directories(retail_maps);
        write_file(retail_maps / "manifest.json",
                   "{\"schemaVersion\":1,\"id\":\"retailmaps\","
                   "\"name\":\"Retail maps\",\"adds\":["
                   "{\"section\":\"LEVEL_HEADERS\",\"file\":\"h.bin\"}]}");
        std::string header(200U, '\0');
        header[0x36] = 0; header[0x37] = 73;   // Ancient Lake's collectables
        header[0xBA] = 0; header[0xBB] = 5;    // and its structure map
        write_file(retail_maps / "h.bin", header);
    }
    scan(root);
    bool retail_loaded = false;
    for (const Track& track : tracks()) {
        if (track.id == "retailmaps") {
            retail_loaded = true;
        }
    }
    assert(retail_loaded);

    // Two tracks with one id break every cross-reference that keys on it, and
    // importing a copy of a track that is also being watched produces exactly
    // that pair. The second must be refused, not silently shadow the first.
    {
        const std::filesystem::path twin = root / "twin.dkrmap";
        std::filesystem::create_directories(twin);
        write_file(twin / "manifest.json",
                   "{\"schemaVersion\":1,\"id\":\"retailmaps\","
                   "\"name\":\"Twin\",\"adds\":["
                   "{\"section\":\"LEVEL_HEADERS\",\"file\":\"h.bin\"}]}");
        std::string header(200U, '\0');
        header[0x37] = 73;
        header[0xBB] = 5;
        write_file(twin / "h.bin", header);
    }
    scan(root);
    int with_that_id = 0;
    for (const Track& track : tracks()) {
        if (track.id == "retailmaps") {
            ++with_that_id;
        }
    }
    assert(with_that_id == 1);

    // An object map entry without a slot is ambiguous and must be refused
    // outright: merging the two maps is exactly the failure this guards.
    {
        const std::filesystem::path bad = root / "noslot.dkrmap";
        std::filesystem::create_directories(bad);
        write_file(bad / "manifest.json",
                   "{\"schemaVersion\":1,\"id\":\"noslot\",\"name\":\"No slot\","
                   "\"adds\":[{\"section\":\"LEVEL_OBJECT_MAPS\","
                   "\"file\":\"o.bin\"}]}");
        write_file(bad / "o.bin", std::string(32U, 'o'));
    }
    scan(root);
    for (const Track& track : tracks()) {
        assert(track.id != "noslot");
    }

    std::filesystem::remove_all(root);
    std::printf("custom_tracks_tests: ok\n");
    return 0;
}

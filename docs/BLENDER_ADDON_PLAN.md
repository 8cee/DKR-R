# DKR track editor - Blender addon plan

Working plan for a Blender addon that lets a creator author a Diddy Kong Racing
track and export a `.dkrmap` that DKR-R loads from `custom-tracks/`.

Everything under "Verified" was read out of retail assets or the matching
decomp and cross-checked. Everything under "Proposed" is design that has not
been built yet. Keep that line sharp when picking this up.

**Status: Phase 1 is built.** The addon lives in `tools/blender/`, with its own
`README.md` covering install and use. Steps 1 through 5 of the implementation
order below are done and tested; step 6 waits on the DKR-R runtime hooks. Two
rules this plan proposed turned out to be wrong when measured against retail
data, and are corrected in place below.

Companion references in this repo:

- `tools/blender/README.md` - the built addon
- `docs/LEVEL_OBJECT_MAP_FORMAT.md` - the object-map binary format, verified
  against retail bytes; what an encoder is written from
- `docs/LEVEL_MODEL_FORMAT.md` - the decoded track geometry format
- `docs/CUSTOM_TRACKS.md` - the runtime side and the `.dkrmap` container

## Why this is tractable

Object placement in DKR is **already glTF**. Each track's object map extracts to
a two line JSON pointing at a glTF file:

```json
{ "objects": "asset_level_object_maps_0.gltf", "type": "LevelObjectMap" }
```

and every object is a glTF node carrying `translation` plus custom properties:

```json
{
  "name": "GroundZipper",
  "translation": [3133.0, 449.0, 171.0],
  "extras": { "id": "ASSET_OBJECT_GROUNDZIPPER", "angleY": 106.875, "scale": 100 }
}
```

Blender exports custom properties as glTF `extras` natively, so the round trip
already exists. The addon is mostly UI over a format both sides already speak.

**Correction, from building it.** The addon does *not* use Blender's glTF
importer or exporter. An object map is not general glTF: it has no meshes,
buffers, materials or animations, just one root node named `objects` whose
children carry a `translation` and an `extras` dict. Blender's stock exporter
rewrites all of that - axis conversion, node reordering, mesh and buffer
boilerplate - and coerces integer `extras` to float, which is the one thing the
format cannot survive. `tools/blender/dkr_track_editor/gltf_io.py` reads and
writes these documents directly instead, in about 200 lines, and that is what
makes the round trip exact.

Values are human readable, not raw bytes: angles in degrees, enums by name
(`BALLOON_TYPE_BOOST`, `ASSET_LEVEL_DINODOMAINHUB`). The `Hint(...)` macros in
the decomp's `include/level_object_entries.h` are what drive that translation
inside `dkr_assets_tool`.

## Scope: two phases

Phase 1 is fully unblocked. Phase 2 waits on a geometry encoder that does not
exist yet.

| Feature | Phase 1 | Phase 2 |
|---|---|---|
| Place balloons, zippers, coins, scenery | yes | |
| AI path from splines | yes | |
| Spawn points and checkpoints | yes | |
| Hub doors and level exits | yes | |
| Track geometry from a Blender mesh | | yes |
| Invisible walls | | yes |
| Collision tuning | | yes |

Phase 1 is "remix an existing track": the creator reworks objects, items and the
racing line over shipped geometry. That is a real creative tool, and it
validates the whole pipeline - editor, `.dkrmap`, install, runtime - at low risk.

## Verified data model

### Object catalogue

85 distinct object types appear across the retail object maps. Recover the list
and the per type field sets by parsing the extracted glTFs:

```
extern/dkr-decomp/assets/.vanilla/us.v77/levels/objectMaps/unknown/*.gltf
```

Highest value types for a racing track:

| Object | Purpose |
|---|---|
| `ASSET_OBJECT_GROUNDZIPPER` | ground turbo pad |
| `ASSET_OBJECT_AIRZIPPERS` / `WATERZIPPERS` | plane and boat turbos |
| `ASSET_OBJECT_WEAPONBALLOON` | weapon balloon, `balloonType` selects the kind |
| `ASSET_OBJECT_CHECKPOINT` | lap and respawn checkpoints |
| `ASSET_OBJECT_SETUPPOINT` | racer spawn |
| `ASSET_OBJECT_AINODE` | AI racing line graph |
| `ASSET_OBJECT_COIN` / `SILVERCOIN` / `GOLDCOIN` | pickups |
| `ASSET_OBJECT_CAMERA_CONTROL` | camera hints |
| `ASSET_OBJECT_EXIT` / `ASSET_OBJECT_DOOR` | hub navigation |

### Structures that constrain the addon

```c
struct LevelObjectEntry_AiNode {
    u8 nodeID;        // u8: at most 256 nodes per track
    u8 adjacent[4];   // up to 4 neighbours, 255 = empty
    s8 elevation;
};

struct LevelObjectEntry_SetupPoint {
    u8 racerIndex; u8 entranceID;
    u8 angleY;                 // degrees / 64
    s8 vehicle;                // Enum:Vehicle
};

struct LevelObjectEntry_Exit {
    u8 destinationMapId;       // index into ASSET_LEVEL_HEADERS
    s8 overworldSpawnIndex; u8 returnSpawnIndex;
    u8 radius; s8 bossFlag;
};

struct LevelObjectEntry_Door {
    u8 modelIndex; u8 balloonCount; s8 keyID;
    s8 localBalloons;          // count against the world, not the total
    u8 textID; u8 scale;
};
```

A hub gate is **two** objects: `Exit` performs the warp, `Door` is the visible
lock carrying the balloon and key requirement.

### Render flags Phase 2 will need

From `src/textures_sprites.h`, confirmed in use by `render_level_segment`:

```c
RENDER_HIDDEN       = (1 << 8)   // batch is skipped when drawing
RENDER_NO_COLLISION = (1 << 9)   // batch is skipped when deriving collision
```

The bits are independent, so an invisible wall is bit 8 set with bit 9 clear.
Collision itself is never authored - the game derives it at load time from the
triangles of every batch that does not opt out.

## Proposed addon architecture

```
dkr_track_editor/
  __init__.py            registration, panels
  catalog.py             object type schema, loaded from a generated JSON
  operators/
    place_object.py      "add DKR object" buttons
    ai_from_curve.py     sample a curve into an AiNode graph
    validate.py          pre-export checks
  export/
    gltf_objects.py      write the object map glTF
    dkrmap.py            build the .dkrmap archive
  ui/
    panels.py            sidebar: place, AI, validate, export
```

### Catalogue as generated data, not hand written

Do not transcribe 85 structs by hand. Generate `catalog.json` from the decomp by
parsing `include/level_object_entries.h` (the `Hint(...)` annotations carry the
types and enums) and by sampling real values out of the extracted glTFs. Keep
the generator in the repo so the catalogue can be regenerated when the decomp
moves.

### AI graph from a spline

The biggest quality of life win, because hand authoring an AI graph is the
tedious part of track making.

1. Creator draws a Bezier or NURBS curve along the racing line.
2. An operator samples it at configurable spacing into `AINODE` empties.
3. Adjacency fills automatically from sampling order, closed into a loop.
4. Branches: a second curve marked as a branch attaches at its nearest nodes,
   consuming free `adjacent` slots.
5. Validation refuses more than 256 nodes, or any node needing a fifth neighbour.

### Validation before export

Cheap checks that prevent confusing in game failures. The list below is what
`validate.py` ended up enforcing, which is not quite what this plan first
proposed: `tests/test_validate.py` runs every rule over all 272 retail object
maps on the principle that **a rule which rejects a shipped track is a wrong
rule**, and two of the original rules were.

Errors, each an invariant that holds across all retail data:

- at most **255** AI nodes, not 256. `nodeID` is a `u8` and 255 is the
  empty-link sentinel, so a node numbered 255 could never be referenced.
- no node with five or more neighbours, and no dangling link
- **every AI link is reciprocal.** Measured across the 16 retail maps that have
  an AI graph: 440 directed edges, not one of them one-way.
- at least one `SETUPPOINT` on a racing track
- no two racers on the same `racerIndex` within an `entranceID`
- no duplicate checkpoint `index` within a `(vehicleType, isAltCheckpoint)` chain

Warnings, because retail does these too:

- AI nodes unreachable from the first node. 27 retail nodes have no neighbours
  at all, so this cannot be an error.
- an `EXIT.destinationMapId` outside the retail level list, which is exactly
  what a custom track legitimately adds

#### Two rules that measurement disproved

**"Checkpoint indices contiguous from zero" is false.** Retail indices
typically step by 2, and a chain may start at 2, 8 or 12. The reason is that
checkpoints are not one sequence: a map carries an independent chain per
`vehicleType`, so Ancient Lake has three, one each for car, hovercraft and
plane, each numbered on its own. What does hold, in all 51 retail chains, is
that an index is unique within its chain. That is the rule now enforced.

**"A full race grid is 8" is false as a rule.** Retail entrance groups hold 1,
2, 4 or 8 start positions - eight is a race grid, one is a hub arrival point -
so the count carries no rule at all. Only the uniqueness of `racerIndex`
survives, and it holds across all 92 retail entrance groups.

#### Ranges come from the C type, never from observation

A field's editable range is what its C type can hold, not the range retail
happens to use. Clamping to observed values would stop an author from using a
value the game accepts perfectly well - a zipper scaled past any retail zipper.
The observed range is carried alongside as `seen_min`/`seen_max` and shown in
the tooltip as guidance only.

Angles need the asset tool's own rule to get this right. `get_hint_angle` in
`helpers/c/cStructGltfHelper.cpp` computes `value / divideBy * 360`, then, only
for an unsigned field and only when the result exceeds 360, wraps it negative by
subtracting a whole turn's worth of raw steps. So a `u8` with `DivideBy:64`
yields 0..360 together with -1074..-5.625, while the same type with
`DivideBy:256` never exceeds 360 and so is never wrapped, giving 0..358.59.
Assuming a single signedness for all angle fields clips legal values, which is
how this was found.

## Implementation order

1. ~~**Prove the round trip.**~~ **Done.** All 272 retail object maps across
   `us.v77` and `us.v80`, 18,863 placed objects, read into a Blender scene,
   exported and compared byte for byte against the original. The serialisation
   contract is `json.dumps(indent=2, sort_keys=True)` plus a trailing newline,
   established empirically against every retail file.
   `tests/test_blender_roundtrip.py` is the regression gate.
2. ~~**Generate `catalog.json`**~~ **Done.** `generate_catalog.py` parses the
   decomp header for struct layout, field order, C types and `Hint(...)`
   annotations, then surveys the extracted glTFs for concrete JSON types and
   real value ranges. All 85 object types match a struct. `--check` fails if the
   committed catalogue is stale.
3. ~~**Placement UX**~~ **Done, including surface snapping.** See "Reading
   geometry is not Phase 2" below: the track loads as a reference mesh, so
   Blender's face snapping works and a *Drop To Surface* operator raycasts
   objects onto the road. Objects are drawn with the game's own artwork rather
   than as identical markers, grouped into a collection per category, and
   rotating one in the viewport writes its angle field.
4. ~~**AI spline operator plus validation.**~~ **Done.** Arc-length sampling
   with branch attachment, and the rules above.
5. ~~**`.dkrmap` export**~~ **Done for the object map.** The manifest, the glTF
   sources and the compiled `objects.bin` are all written by the addon.
   `object_map_encoder.py` produces the section payload directly, and
   `tests/test_encoder.py` requires it to reproduce all 136 retail object maps
   byte for byte from their glTFs - the correct answer already exists in
   `assets.bin`, so correctness is a byte comparison rather than a play test.
   `LEVEL_HEADERS` is written too, by `level_header.py`, with
   `tests/test_header.py` rebuilding all 65 retail headers byte for byte. A
   package now carries every payload it needs: a header and both object maps.
6. **Round trip test inside DKR-R** once the runtime hooks land. Still open:
   `docs/CUSTOM_TRACKS.md` lists the two policy hooks as remaining work.
7. Phase 2 only after 1 through 6 are stable.

### Why the packager stops short of a loadable track

Section payloads are compiled by the decomp's `dkr_assets_tool`, and that tool
builds a whole `assets.bin` from the decomp's asset tree rather than emitting
one section at a time. It also ships as a Linux ELF binary. So the addon writes
the manifest, the authored object map as the glTF pair the tool consumes, and a
`HOW-TO-BUILD.md` describing the remaining step. It never writes a manifest
entry for a payload that is not present, because a manifest promising bytes that
do not exist fails at load time with a much more confusing error.

Closing this gap means either a per-section build mode in `dkr_assets_tool`, or
an encoder for the `LEVEL_OBJECT_MAPS` section alone. The second needs no C++
toolchain and is fully specified: `docs/LEVEL_OBJECT_MAP_FORMAT.md` documents the
binary format, verified entry by entry against the retail `assets.bin` - 136
maps, 9,426 entries, all 85 object types - and `tools/blender/tests/
test_binary_format.py` re-checks every claim in it on each run.

That verification cuts both ways: because the correct bytes already exist in
`assets.bin`, an encoder can be proved right by byte comparison rather than by
play testing.

## Reading geometry is not Phase 2

The plan treated all track geometry as blocked behind Phase 2. That conflates
two different problems: Phase 2 needs an **encoder**, and there is none. A
**decoder** is a much smaller job, and `docs/LEVEL_MODEL_FORMAT.md` already
documents the format completely enough to write one.

That distinction matters because without it the addon is unusable for its actual
purpose. An author placing a zipper on a road they cannot see is editing
coordinates, not designing a track.

So `level_model.py` decodes level models and `object_model.py` decodes object
models, both read-only. All 110 retail level models and all 390 object models
decode and pass structural checks. What that unblocked:

- the track loads as a reference mesh, split into surface, decoration and
  invisible walls, so Blender's face snapping and a *Drop To Surface* operator
  both work
- **986 invisible walls** across retail tracks are visible and countable, which
  confirms this plan's reading of the two render bits: hidden set, collision
  clear
- objects are drawn with their own artwork, resolved through the decomp's asset
  manifests: `ASSET_OBJECT_PALMTREETOP` to its header, to its sprite, to the
  extracted PNG. 81 of the 85 object types that appear in retail tracks resolve
  to a sprite or a mesh.

Most DKR scenery turns out to be **sprite billboards, not meshes** - 84 of the
304 object headers, and it is the ones an author places most: palm trees,
balloons, coins, bushes. A preview that only handled meshes would have left
exactly those as nothing.

Meshes carry their own textures: a model's texture table stores an index into
the global 3D texture list, and each triangle carries UVs as fixed point with
five fractional bits, in texels. Of 6,562 batches across all 390 models, 6,264
resolve to a texture and the remaining 298 genuinely have none. Getting there
needed one non-obvious step: an **animated** texture has no file at its own
stem, only numbered frames listed in its sidecar, so a naive lookup leaves
things like the zipper as untextured grey rings.

Types whose header points at a debug placeholder - AI nodes, camera hints - keep
the addon's own markers instead. That is deliberate: reproducing the game's
debug sphere faithfully would replace clear, sized markers with a row of
identical dots, which reads far worse when the point is to see the shape of an
AI graph.

### A track is two object maps, not one

Reading the level headers turned up something this plan did not account for.
Every one of the 65 retail headers names **two** object maps:

| Field | Holds |
|---|---|
| `map-2` | the track: checkpoints, zippers, scenery, the AI line |
| `map-collectables` | the pickups: coins, bananas, weapon balloons |

So a remix that edits only `map-2` silently drops every collectable on the
track. Ancient Lake is 98 objects in its first map and 184 across both.

The header is also what makes the assets findable at all: it names the level
model and both maps by asset id, which is how the addon offers "Ancient Lake"
rather than asking an author to guess which of 138 files called
`asset_level_object_maps_<n>` is the right one.

None of this is written back, so it changes nothing about Phase 2 below.

## Phase 2: the geometry encoder

The blocker: `buildLevelModel.cpp` in `dkr_assets_tool` is 21 lines and only
copies a raw binary. There is no glTF path for level geometry, so new tracks,
invisible walls and collision changes all wait on writing one.

The format is fully decoded in `docs/LEVEL_MODEL_FORMAT.md`. What an encoder
must do:

| Task | Notes |
|---|---|
| Container | DEFLATE plus a `[u32 LE size][0x09]` header |
| Header and texture table | direct field writes |
| Segment the mesh spatially | the author's choice of partition |
| BSP over the segments | standard axis and split value tree |
| Batch triangles | group by texture and flags |
| Collision | nothing to do |

Two hard constraints:

- Triangle vertex indices are **batch local** and `u8`, so no batch may address
  more than 256 vertices.
- Batches must be sorted opaque first. `numberofOpaqueBatches` is the split
  point `render_level_segment` reads.

Before starting this, ask the DKR decomp and DKR-R communities whether an
encoder already exists. It is a large piece of work to duplicate.

## Open questions

- ~~Does the Blender glTF exporter preserve integer `extras`?~~ **Answered, and
  it no longer matters.** The addon does not use that exporter; it writes these
  documents itself, which is both simpler and exact. See the correction under
  "Why this is tractable".
- **How is the `LEVEL_OBJECT_MAPS` payload produced without a Linux build of
  `dkr_assets_tool`?** This is the one thing standing between the addon and an
  end-to-end Phase 1 track. See "Why the packager stops short" above.
- How are per level textures referenced from a `.dkrmap` that adds a track?
  Phase 1 sidesteps this by reusing the host track's texture table.
- Minimap parameters live in the `LevelModel` header, so a Phase 1 remix cannot
  change the minimap. Confirm whether that matters to creators.
- `elevation` on an AI node is not a height. Retail values (-1, 0, 1, 3) do not
  track the node's Y position, and 143 of 208 nodes leave it 0. It reads like a
  route tier. Worth identifying before the AI operator tries to set it
  automatically; right now the author chooses it and it defaults to 0.

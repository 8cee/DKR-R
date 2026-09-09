# DKR track editor - Blender addon plan

Working plan for a Blender addon that lets a creator author a Diddy Kong Racing
track and export a `.dkrmap` that DKR-R loads from `custom-tracks/`.

Everything under "Verified" was read out of retail assets or the matching
decomp and cross-checked. Everything under "Proposed" is design that has not
been built yet. Keep that line sharp when picking this up.

**Status: Phase 1 is built, and Phase 2 is under way.** The addon lives in
`tools/blender/`, with its own `README.md` covering install and use. Steps 1
through 5 of the implementation order below are done and tested; step 6 waits on
the DKR-R runtime hooks. Phase 2 is now three steps rather than one, and all
three are built: a level model encoder proved byte-exact against every extracted
model, a Blender side that reshapes a track without changing how much of it
there is, and a layout builder plus the Blender half that lets geometry be added
and removed. See "Phase 2: the geometry encoder" below. Several rules this plan
proposed turned out to be wrong when measured against retail data, and are
corrected in place below.

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

Phase 1 is built. Phase 2 turned out to be three steps rather than one wall, and
all three are built; see "Phase 2: the geometry encoder".

| Feature | Phase 1 | Phase 2 | State |
|---|---|---|---|
| Place balloons, zippers, coins, scenery | yes | | built |
| AI path from splines | yes | | built |
| Spawn points and checkpoints | yes | | built |
| Hub doors and level exits | yes | | built |
| Reshape shipped track geometry | | step 2 | built |
| Invisible walls | | step 2 | built |
| Collision tuning | | step 2 | built, and free — the game derives collision from the triangles, so reshaping the road moves what is drivable |
| Minimap parameters | | step 2 | built — they live in the `LevelModel` header, so they ship with a model payload |
| Add or remove geometry | | step 3 | built |
| Vertex colours and UVs an author edits | | after step 3 | not built — both are display-only in each direction; the export uses the raw values, so unwrapping or repainting in Blender does not reach the track |
| Track geometry from a new Blender mesh | | beyond step 3 | not built, and needs three things, not one — see "What a track from scratch actually needs" |

So a track's shape *and* its budget are now editable. What bounds a track is no
longer the count it shipped with but the memory ceiling — see step 3 - and two
limits that only became reachable once geometry could be created: a UV spans at
most 1024 texels, and a segment with an oversized bounding box crowds the
ten-slot collision candidate list.

The end-to-end path is verified: a `.dkrmap` produced by the addon has been
loaded and played in DKR-R.

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
| `ASSET_OBJECT_AINODE` | AI navigation graph — **not** the racing line; see the note under "Sampling a curve" |
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

1. Creator draws a Bezier or NURBS curve along the route the graph should follow.
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

- the track loads as a mesh, so Blender's face snapping and a *Drop To Surface*
  operator both work. It was split into surface, decoration and invisible walls
  until step 2 below needed one vertex to mean one vertex; the three are
  material slots now
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
| `map-2` | the track: checkpoints, zippers, scenery, the AI graph |
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

The format is fully decoded in `docs/LEVEL_MODEL_FORMAT.md`, which closed the
last two gaps in it: `segmentsBitfields` is a PVS sized
`numberOfSegments * ceil(numberOfSegments / 8)`, and the fifth of the blob past
`unkC` is reserved `CollisionFacetPlanes` storage at `numberOfTriangles * 8`
bytes a segment. Nothing in a level model is unaccounted for now.

That turns one large encoder into three steps that ship independently, because
what an author can do grows with each and only the last needs a mesh rebuilt
from Blender.

### Step 1 — layout-preserving re-encoder (**built**)

`level_model_encoder.py` writes a decoded model back at the offsets it was read
from. `tests/test_level_model_roundtrip.py` decodes all 110 extracted level
models, re-encodes each from its decoded values and requires byte equality; it
also counts what no structure claimed, holding every unclaimed run to 16 bytes
so a dropped array cannot pass as alignment padding. Coverage is 99.74%, the
remainder being padding of 12 bytes or less.

This is the same proof the object map encoder rests on, and it is what makes
everything below checkable rather than arguable.

### Step 2 — edit without changing topology (**built**)

Move vertices and change render flags. Every count and offset is unchanged, so
the encoder patches in place and step 1's guarantee still holds. Bounding boxes
do have to be recomputed when vertices move, or the game culls geometry the
camera should see; `level_model_edit.py` owns that, and measuring the retail set
settled two rules the plan had guessed at. Segment boxes are exactly the bounds
of the segment's own vertices in 1008 of 1146 segments, the rest being flat ones
whose `y2` is one greater. The **BSP is deliberately not recomputed**: it reads
as a containment tree and is not one - 132 of 1977 segment-to-split
relationships have the segment outside its own half-space - so it partitions the
camera, not the geometry, and a topology-preserving edit leaves it alone.

What the Blender side needed was one vertex meaning one vertex. The old importer
split the model into three meshes by render flag and gave each of them *all* of
a segment's vertices whenever any of that segment's batches matched, which put
223,968 of the 250,578 retail vertices in two meshes at once and left
"which copy did the author move" with no answer. It also ran `mesh.validate()`,
which silently drops the 8 degenerate and 134 duplicate faces retail ships.

So the importer now builds **one** mesh carrying every vertex exactly once, with
`dkr_segment` and `dkr_vertex` integer attributes naming the file vertex each
one is, and `dkr_flags` on the faces carrying the whole `u32` its batch was
drawn with. Surface, decoration and invisible wall became material slots. The
exporter reloads the shipped `.bin` and applies only the differences, so
everything untouched stays byte-identical - checked against all 110 retail
models - and refuses, naming what collided, rather than guessing when an
identity is not unique.

Vertex colours and textures are edit*able* in `level_model_edit.py` but not yet
wired to the mesh: the importer converts colours sRGB to linear and UVs to
normalised and V-flipped, and neither survives the return trip yet.

### Step 3 — change triangle and vertex counts (**encoder built**)

Adding or removing geometry shifts every offset after it, so the blob is laid
out afresh. `level_model_layout.py` does that: it decomposes a segment into
loose faces, re-batches them opaque-first, assigns fresh offsets in retail's
section order, resizes the collision facet reservations and rewrites
`modelSize`. Segmentation and the PVS carry through unchanged.

Retail's own layout cannot be regenerated — its padding follows no rule — so
this step cannot be gated on byte equality the way step 1 was. What replaces it
is stronger than it sounds. `tests/test_level_model_layout.py` requires that
**decomposing and re-batching an untouched segment is the identity**: same
batches, same vertex order, same triangles, across all 2292 retail segments.
That only holds because a face remembers which batch it came from — grouping on
the rendering fields alone merges the 411 segments that hold two batches
agreeing on every one of them. On top of that, a rebuilt layout has to carry
every value through encode and decode, and the batch-window invariant is checked
as a postcondition rather than assumed.

The memory ceiling becomes real at this step, because it scales with triangles:
`LEVEL_MODEL_MAX_SIZE` is `0x82A00` and covers the blob plus the loader's
scratch, where a collidable triangle costs 16 bytes as a `Triangle`, 8 as its
facet reservation, 2 in `unk10` and 64 in collision planes — 90 bytes all told,
against 26 for one that opts out of collision. `level_model_layout.runtime_size`
and `headroom_triangles` compute it. Retail's worst is Bluey at 68% of the
budget and the median track is at 30%, so there is real room, but an author
adding geometry needs to see the number before export rather than meet
`ERROR!! TrackMem overflow` at load.

The Blender half is built, and building it corrected the assumption above about
how a new vertex is spotted. **Blender propagates both point and face attributes
through extrude, subdivide and duplicate** — measured with sentinel values, not
assumed: a face extruded from one carrying `0x7ABCDE` comes out carrying
`0x7ABCDE`, and the new vertices inherit the identity of the vertices they were
pulled from. Only geometry conjured from nothing arrives filled with zeroes.

That cuts both ways. It is why new geometry needs no annotation at all — an
extruded face inherits the render flags, texture, opaque side and source batch
of the face it grew out of, so it joins the right draw call on its own. But it
means **zero-fill is not how an added vertex is recognised**: an extruded vertex
is new and reads as the vertex it came from, so the same `(segment, vertex)`
pair legitimately appears twice. Identity is therefore read as *which segment,
and where in the pool*, never as a unique key. The bias by one is still worth
having — it separates "no source at all" from "vertex 0 of segment 0" — and a
schema stamp on the mesh refuses an older scene, which would otherwise read one
slot off rather than fail.

Added geometry is recognised instead by comparing the mesh against the file: a
segment whose faces and pool no longer match what `decompose` gives has been
edited. That comparison picks between two export paths, and keeping them apart
is what stops a merely reshaped track losing its byte equality now that a
rebuild exists — a reshaping edit still patches the file in place, and only a
count change goes through the layout builder. Extrude produces quads, which the
format cannot store, so they are fanned into triangles on the way out rather
than refused; refusing would make the commonest modelling operation unusable.

All three ceilings — memory, collision candidates and the 1024-texel UV span —
are surfaced in the addon's Geometry panel, computed by calling
`level_model_layout` rather than restating its thresholds.

### What a track from scratch actually needs

Measured, not reasoned, because the question kept being answered from the shape
of the code rather than by running it. Modelling a track in Blender and
exporting a `.dkrmap`, on the addon as it stands:

* **Nothing placed.** The export refuses outright — *nothing to export; no DKR
  objects in the scene* — and writes no package at all.
* **One spawn point placed.** The export succeeds and writes a package whose
  manifest holds `LEVEL_OBJECT_MAPS` twice and nothing else. No geometry, and
  **no header**. It warns *Still missing LEVEL_HEADERS*.

So the result is a package with no track in it. It does not load.

The geometry half of that is expected and is what the segmenter is for. The
header half was not on anyone's list, and it is a separate blocker:

**`_base_header` derives the header from the track being remixed.** It reads
`scene.dkr.source_path` or `geometry_path`, resolves the level through
`AssetTree.level_using`, and loads that level's extracted header JSON. With no
import both paths are empty, so it returns `None` and `encode_header` never
runs. The header is what points at the geometry, so a package without one has
nothing to load even once geometry exists.

`level_header.encode` is not the gap — it already reproduces all 65 retail
headers exactly. The gap is that **nothing produces a header document for a
track with no ancestor**.

That was first written here as "someone has to decide what roughly 200 bytes
hold", which overstated it, and measuring the 65 retail headers cut it down.
`level_header.py` models 138 fields:

* **22 are identical in all 65 headers.** Copied from any of them, no decision.
* **95 vary but have a dominant value** — one setting holds in at least 33 of
  the 65 — so they take a surveyed default rather than an answer. Fog, the sky
  gradient, background colour and the whole waves group are here.
* **1 is held back** because its default names an asset, which only an
  extracted tree resolves; see the asset constraint below.
* **8 have no dominant value at all** and are genuine choices.

The first figure was recorded here as 61, which was wrong: the survey behind it
walked JSON paths without handling list indices, so every field under an array
read as absent and counted as constant. Corrected against a generator that
handles them.

`level_header_template.CHOICES` is the authored set, and it is 16 rather than 8
— the extra eight are fields with a dominant value that an author still wants in
front of them, like lap count and the background colour channels. `/model` looks
like a choice and is not: the runtime patches `0x34` from the shipped
`LEVEL_MODELS` payload, and `0x36` and `0xBA` from the two object map slots, so
none of the three is in the template and nothing in it waits on the geometry.

So the work is a template with the constants filled and the cosmetic block
defaulted, plus a form of about a dozen controls over it. A decision and a
panel, not an archaeology project.

So a track from scratch needs three pieces and not one:

1. **Segmentation** — partition an arbitrary mesh into segments, with the BSP
   and PVS that go with them. The next piece of work, and the one that also
   raises the ceiling on ordinary remixing.
2. **An importer that accepts an arbitrary mesh** — the Blender side. Smaller
   and more mechanical: today a mesh with no `dkr_geometry` marking is named and
   explained rather than silently skipped, but it still cannot be exported.
3. **A header written from nothing** — the piece recorded here.

There is a fourth constraint that no amount of geometry work removes: a
`.dkrmap` has **no texture section**. `SECTIONS` carries `LEVEL_HEADERS`,
`LEVEL_NAMES` and `LEVEL_MODELS`, plus `LEVEL_OBJECT_MAPS`. A custom track can
therefore only use textures already in the ROM's table. Texture packs replace by
hash and replace globally, so they change how a texture looks everywhere in the
game rather than adding one for a single track. Bringing an outside course in
means its geometry with DKR's textures.

### Tried and failed: growing a new track out of a host track

Someone wanting to bring an outside track in — a Mario Kart 64 course, in the
case this was written from — asked the obvious question: can step 3 do it? It
can add geometry now, so take a shipped DKR track, delete what you do not want
and extrude the new shape out of what is left.

**It was tried and it does not work.** The report back was that collision
stopped working, materials came out wrong, and the result was broadly broken.
Recorded here because the failure is informative and because the next person
will have the same idea.

What is actually known, kept separate from what is guessed, because only the
first was measured:

**Known.** The addon accepted the edit and exported it. Nothing refused, nothing
warned beyond the oversized-segment notice. So the failure is not in the
encoding — it is in what the encoding faithfully produced.

**Leading explanation for the collision loss, and it was predicted before the
attempt.** Extruded geometry inherits its segment from the face it grew out of,
so a shape extruded a long way stays in the segment it started in and stretches
that segment's bounding box across the map. `collision.c` picks at most ten
candidate segments by box overlap, so a segment shaped like that overlaps every
query and holds a slot everywhere. The ground a racer is actually standing on
stops being considered, and the symptom appears somewhere other than the cause —
which matches "collision stopped working" rather than "collision is wrong here".
`level_model_layout.oversized_segments` reports this and the Geometry panel shows
it, but showing it does not make the edit workable.

**Plausible explanation for the materials, not verified.** New corners get their
raw UVs interpolated from the corners they came from, so a swept side face
carries UV values that are well-formed and geometrically meaningless. The
texture index itself is inherited through the batch serial and should be right,
so "no material" most likely means "the right texture, mapped incoherently". A
sample of the broken export was not examined, so this stays a hypothesis.

**A third mechanism, not in the original report, reasoned from the format rather
than measured.** The PVS is inherited too, and it knows nothing about the new
ground. Extruded geometry stays in the segment it grew from, so it is drawn
exactly when that segment is drawn — and which segment the camera is *in* is
decided by the BSP, which still splits on the host's segmentation. Drive into
the new area and the BSP places you in whichever host segment owns that space;
if that segment's visibility bitmask does not list the segment your new geometry
belongs to, the new geometry is not drawn at all. That presents as scenery
appearing and disappearing as the camera turns, which is a different symptom from
the collision loss and would be easy to blame on the same cause.

**The conclusion, which is the point of the entry.** The three steps of Phase 2
edit a track that already has a segmentation. Nothing in them creates one, and a
track that grows far outside the segmentation it inherited is not a new track —
it is an old track with one segment stretched around the world, which is
precisely the shape the collision candidate list handles worst. A new track
needs the geometry partitioned into segments of its own, and the host-track
route cannot approximate that.

Two pieces of good news for whoever picks up the segmenter:

* **The PVS does not have to be computed to begin with.** `rebuild` falls back
  to an all-visible bitfield when a model carries none, which is conservative —
  everything is drawn — so it costs speed and not correctness. Note the
  condition: a model built from nothing, which is what a segmenter produces, so
  the good news is real for that path. A model decoded from a file always
  carries a PVS, and `rebuild` writes that one through unchanged. That is
  correct for editing a track inside its own footprint and it is exactly the
  trap described above — the host-track route never reaches the fallback, so it
  inherits visibility bits that say nothing about the ground it added.
* **The BSP does not have to match retail's, and arguably should not.** Walking
  every retail model, 132 of 1977 segment-to-split relationships have the
  segment outside its own half-space. It partitions the camera rather than the
  geometry, so a BSP built by recursive median split would be no worse than the
  data the game ships with.

So the missing piece is genuinely the segmentation itself, plus a Blender-side
importer that accepts an arbitrary mesh instead of requiring the identity
attributes a decoded track carries.

**One defect this turned up, now fixed.** A mesh an author models themselves
carries no `dkr_geometry` marking, so `build_edited_model` did not see it and the
export ignored it in silence — no payload, no warning, no error. Someone
modelling a track from scratch would export and find nothing had happened, with
nothing to explain why. The export now names the meshes it skipped and says why
it cannot use them. It does not make them exportable; it replaces a mystery with
a reason, which is what an author needs until the segmenter exists.

Re-segmenting from scratch, and with it a recomputed BSP and PVS, is beyond
these three and is what a brand-new track would need.

Before extending past step 3, ask the DKR decomp and DKR-R communities whether
an encoder already exists. It is a large piece of work to duplicate.

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

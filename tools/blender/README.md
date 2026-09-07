# DKR track editor - Blender addon

Author a Diddy Kong Racing track in Blender: place objects, items and the AI
racing line over a track's geometry, then write the object map back out and
package it as a `.dkrmap` for DKR-R's `custom-tracks/` folder.

This is Phase 1 of `docs/BLENDER_ADDON_PLAN.md`: remixing an existing track.
Authoring new geometry is Phase 2 and is still blocked on a level-model encoder.

## Install

```
python tools/blender/generate_catalog.py     # needs the decomp checked out
python tools/blender/package_addon.py
```

Then in Blender: **Edit > Preferences > Add-ons > Install from Disk**, pick
`tools/blender/dkr_track_editor.zip`, and enable *DKR Track Editor*. The panels
appear in the 3D viewport sidebar (`N`) under a **DKR** tab.

**Point it at your decomp assets.** Object artwork lives in an extracted decomp
tree, not inside the addon. When the addon is run from a checkout of this
repository it finds `extern/dkr-decomp/assets/.vanilla/<version>` on its own; an
installed copy cannot, so set **Decomp Assets** in the addon's preferences. The
Place panel shows which tree is in use, and warns when there is none.

Verified against Blender 5.2. The manifest declares 4.2 as the minimum, and the
zip carries both `blender_manifest.toml` and `bl_info` so it installs as an
extension or as a legacy addon.

## Use

**Import a track.** Press **Import Track** and pick one of the 65 retail levels
by name. That loads its geometry and *both* of its object maps in one go.

The two maps matter. A level header names `map-2` for the track - checkpoints,
zippers, scenery, the AI line - and `map-collectables` for the pickups. Loading
only the first gives a track with no coins and no balloons: Ancient Lake goes
from 184 objects to 98.

`File > Import > DKR Object Map` still loads a single map by path, for a map
that is not part of a retail level. Either way, objects arrive **drawn with the
artwork the game uses** - a palm tree looks like
a palm tree, a boost balloon looks different from a trap balloon - sorted into a
collection per category, with every decoded field as a custom property. Track
coordinates run to several thousand units, so the importer widens the viewport
clipping to match.

**Import the track geometry.** The Geometry panel loads a level model from
`levels/models/<world>/*.bin`; *Import Track* does it for you. Without it there
is nothing to aim at: objects float in an empty viewport. The geometry arrives
**textured**, from the level model's own texture table and per-triangle UVs, so
the road looks like road and the grass like grass. It is read-only reference -
decoded from what the game ships, never written back - and it is split three
ways:

| Mesh | What it is |
|---|---|
| `<track> surface` | the road, drawn and driven on |
| `<track> invisible walls` | `RENDER_HIDDEN` batches, most of them still solid |
| `<track> decoration` | drawn but not collidable |

Invisible walls start hidden, since they otherwise bury the track. Once geometry
is loaded, Blender's own face snapping works, and *Drop To Surface* casts the
selected objects straight down onto the road.

**Place objects.** The Place panel lists all 85 object types that appear in
retail tracks, filtered by category, with the ones a track author reaches for
first pinned at the top. Press *Coin* and a coin appears; press *Frog* and the
decoded frog mesh appears, textured. A new object is placed at the 3D cursor
carrying the field values retail uses most, so it behaves like the ones already
shipped.

How an object is drawn comes from its own header, so it matches the game:

| | |
|---|---|
| sprite billboard | 49 of the 85 types - trees, balloons, coins, bushes |
| textured mesh | 32 types, built from the decoded object model |
| marker | 4 types whose header points at a debug sphere, such as AI nodes |

A weapon balloon reads its `balloonType` and shows that weapon's sprite, so a
boost balloon and a trap balloon look different the way they do in game.

*Refresh Object Artwork* redraws everything, which is what to press after
setting the asset path for the first time.

**Edit fields.** Select an object and the DKR Object panel shows its fields with
the right widget for each: a slider bounded by what the C type can hold, or a
dropdown of an enum's members. Padding and unknown bytes are hidden behind a
toggle, because they exist to reproduce bytes rather than to be authored. Where
a type has an angle, rotate the object in the viewport and the field follows.

**Draw the AI line.** Add a curve, draw the racing line, then *AI Nodes From
Curve*. It samples the curve at a spacing you choose, numbers the nodes and
wires the adjacency, closing the loop if the curve is cyclic. A second curve can
be spliced on as a branch, attaching to the nearest nodes that still have a free
link slot.

**Validate.** Checks the things that are painful to diagnose in game: an AI
graph with one-way or dangling links, duplicate checkpoint indices, two racers
on the same start square, an exit pointing nowhere. Errors mean the map is
wrong; warnings mean it is unusual, which retail tracks sometimes are too.

**Package.** Fill in the track name and author, then *Export .dkrmap*. The next
section covers what lands in the package and the one rule about sharing it.

## What the packager produces

`Export .dkrmap` writes a directory holding the manifest, a compiled
`header.bin`, both compiled object maps, and the glTF sources beside them.

**Everything is compiled here**, without the decomp's `dkr_assets_tool` - that
tool builds a whole `assets.bin` and ships as a Linux binary, so depending on it
would have put a C++ toolchain between an author and their track. Neither
encoder is merely plausible: the correct bytes already exist in the retail
`assets.bin`, and the tests require reproducing them exactly - all 136 shipped
object maps, all 65 level headers, byte for byte.

**A level has two object maps and they stay separate.** The runtime patches a
different header field from each - `0xBA` from the structure slot, `0x36` from
collectables - so the package carries `objects_structure.bin` and
`objects_collectables.bin`, and each manifest entry names its slot.

Two header offsets are left at **zero** for the runtime to patch, since a custom
track's maps only get their indices when it builds the extended asset table.
Zero rather than -1: the game guards the table with a signed `mapID >= i`, so -1
slips past the clamp and reads `objMapTable[-1]`.

**A header therefore always ships with both slots.** Zero is a valid index, not
an absence - anything out of range clamps to 0 and loads object map 0 - so a
header with only one payload points the other slot at another level's objects
and hangs. An empty slot gets an **empty** map, 16 bytes with `fileSize` 0,
which is what retail does in 16 of its own maps.

Payloads dropped in by hand survive a re-export, and a manifest never claims a
payload that is not there.

**Do not commit a built package.** A remix keeps whatever the base track had, so
its payloads contain retail object-map data verbatim wherever nothing was
changed - the structure slot of a lightly edited remix is the base track's map
byte for byte. `docs/ASSET_POLICY.md` forbids committing extracted maps, and
`scripts/scan_for_game_assets.py` will not catch it: that scanner checks file
extensions, ROM magic and size, and cannot see map data inside a 1.3 KB `.bin`.
`custom-tracks/` is in `.gitignore` for this reason. Share the `.blend` instead -
anyone with the decomp can rebuild the package from it.

Install a package by copying it into DKR-R's `custom-tracks/` directory, or with
the Track Lab's Import Track button. Not `mods/`: librecomp owns that for its
`.nrm` format and rejects anything else it finds there.

## Layout

```
tools/blender/
  generate_catalog.py       builds data/catalog.json from the decomp
  package_addon.py          builds the installable zip
  run_tests.py              runs every suite
  dkr_track_editor/
    __init__.py             registration; imports bpy only inside register()
    gltf_io.py              object-map reader and writer
    catalog.py              the generated catalogue, and value coercion
    level_model.py          track geometry decoder, and the shared primitives
    object_model.py         object mesh decoder
    object_map_encoder.py   object map -> section bytes
    level_header.py         level header -> its 200 bytes
    assets.py               resolve an asset name to a file in the decomp tree
    preview.py              build the artwork an object is drawn with
    ai_graph.py             sampling, adjacency and the format's limits
    validate.py             pre-export checks
    dkrmap.py               the .dkrmap container
    scene.py                object map <-> Blender scene
    props.py                scene settings
    prefs.py                where to find the decomp assets
    operators/              import, export, place, AI, validate, package
    ui/panels.py            the sidebar
    data/catalog.json       generated; do not edit by hand
  tests/
    test_roundtrip.py           byte-exact read/write, no Blender needed
    test_validate.py            the rules, checked against retail tracks
    test_geometry.py            every retail level model decodes
    test_assets.py              every object type resolves to its artwork
    test_binary_format.py       the object-map binary format, vs assets.bin
    test_encoder.py             all 136 retail object maps re-encode exactly
    test_header.py              all 65 retail headers rebuild exactly
    test_blender_roundtrip.py   byte-exact through a real Blender scene
    test_blender_operators.py   the operators actually work
```

Everything except `scene.py`, `preview.py`, `props.py`, `operators/` and `ui/`
avoids `bpy`, so the formats and rules can be tested on a plain Python.

## Tests

```
python tools/blender/run_tests.py            # all nine suites
python tools/blender/run_tests.py --all      # every retail map, not a sample
python tools/blender/run_tests.py --skip-blender
```

The one that matters most is the round trip. Every retail object map - 272 of
them across `us.v77` and `us.v80`, 18,863 placed objects - is read, turned into
Blender objects, exported and compared byte for byte against the original, and
then again with the object artwork built. That is the guarantee that editing one
zipper does not silently perturb anything else in the track, and that what an
object is *drawn* with never leaks into what it *is*.

`test_geometry.py` decodes all 110 retail level models and `test_assets.py` all
390 object models, checking the structural limits the formats impose (a batch
addresses at most 256 vertices, because the index is a `u8`).

`test_validate.py` runs the validation rules over those same retail maps on the
principle that a rule which rejects a shipped track is a wrong rule. It caught
two during development; see the plan document.

## Regenerating the catalogue

`data/catalog.json` is generated, never hand-edited. Rebuild it when the decomp
moves:

```
python tools/blender/generate_catalog.py
python tools/blender/generate_catalog.py --check   # fail if stale, for CI
```

# DKR track editor - Blender addon

Author a Diddy Kong Racing track in Blender: place objects, items and the AI
AI node graph over a track's geometry, reshape the geometry itself, then write
it all back out and package it as a `.dkrmap` for DKR-R's `custom-tracks/`
folder.

This is Phase 1 of `docs/BLENDER_ADDON_PLAN.md` - remixing an existing track -
plus all three steps of Phase 2: the track's own geometry can be reshaped, and
geometry can be added and removed.

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
zippers, scenery, the AI graph - and `map-collectables` for the pickups. Loading
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
the road looks like road and the grass like grass.

It arrives as **one mesh**, holding every vertex of every segment exactly once.
That is what makes it editable. An edit is addressed in the file as
`(segment, vertex index)`, so each Blender vertex records its own in the
`dkr_segment` and `dkr_vertex` integer attributes and the exporter can put a
moved vertex back where it came from. The three kinds a batch can be are
material slots rather than three separate objects, because a segment holding
batches of more than one kind would otherwise need its vertices in two meshes at
once - and then "which copy did the author move" has no answer:

| Slot | What it is |
|---|---|
| `dkr surface ...` | the road, drawn and driven on |
| `dkr decoration ...` | drawn but not collidable |
| `dkr invisible walls` | `RENDER_HIDDEN` batches, most of them still solid |

Blender's own material-slot *Select* button is how you isolate one kind in Edit
Mode, and solid viewport shading tints each slot so the split reads at a glance
without turning the textures off. Invisible walls start masked out, since they
otherwise bury the track; *Hide/Show Invisible Walls* toggles the mask, and the
mesh keeps their vertices either way.

**Reshape the track.** *Edit Geometry* unlocks the mesh and opens it in Edit
Mode. Move vertices, extrude, subdivide, delete faces. *Check Geometry Changes*
reports what an export would write without writing anything.

There are two ways back out, and which one runs is decided by what you did
rather than chosen:

- **Nothing was added or removed.** The shipped `.bin` is reloaded and only your
  differences are applied to it, so everything you did not touch stays
  byte-identical. Import a track, change nothing, export, and the model is the
  one the game ships, byte for byte - checked against all 110 retail models.
- **Counts changed.** Then every offset after the change shifts, so each segment
  is rebatched and the file is laid out afresh. That cannot be byte-identical to
  retail and is not meant to be; retail's padding between arrays follows no
  rule, so a rebuild writes a valid layout rather than the original one.

Keeping the two apart is the point: reshaping a track never loses its byte
equality just because the addon is now able to rebuild one.

When the geometry is untouched the package carries no `model.bin` at all and the
track keeps pointing at the base track's geometry.

New geometry keeps working because Blender propagates the attributes: a face you
extrude inherits the render flags, texture and source batch of the face it grew
from, and its vertices inherit which segment they are in. A face built from
nothing instead of extruded has no source, so if it also belongs to no segment
the export says so rather than putting it somewhere arbitrary. Extrude makes
quads, which the file cannot store, so they are fanned into triangles on the way
out.

Two ceilings are worth knowing about, both shown in the Geometry panel:

- **Load budget.** The game reserves a fixed arena for a level model and the
  heaviest retail track already uses 68% of it. Going over does not fail - it
  writes past the heap, and the only complaint is a debug print no retail build
  shows - so the panel shows the percentage and how many more triangles fit.
- **Oversized segments.** Collision considers at most ten segments at a time,
  chosen by bounding-box overlap, so a segment stretched across the map holds a
  slot everywhere and can push the ground a racer is standing on out of the
  running. The symptom is falling through the floor somewhere else entirely,
  with no diagnostic at all. One giant polygon is enough to do it.

**Or build the track from your own mesh.** Model one in Blender and the Geometry
panel offers to convert it: *Track From Mesh* starts from a shipped track's
texture table, which brings a coherent set of images and their surface types
with it, and *Track From Mesh, No Textures* starts from nothing. Neither decides
what the track can look like - that is the Textures panel below. The mesh is
partitioned into segments with the bounding boxes, BSP and PVS to match, written
out as its own `.bin`, and imported back as ordinary editable geometry.

**Texture the track with anything in the ROM.** The Textures panel browses every
one of DKR's 3D textures - **1401** of them in the US v1.0 extraction - as
thumbnails, filtered by folder (`dino`, `winter`, `water`, `space` and the rest)
and by a search over their names. Select faces in Edit Mode, pick a texture,
press *Apply To Selected Faces*.

A track is not limited to the textures it was built from. A level model's
texture table stores indices into the ROM's global texture list, so it can name
any of them; the addon appends an entry to the table and points the faces at it.

Three things come with the texture rather than being asked about:

- **Surface type.** Chosen in the panel, because it lives on the table entry
  rather than on the face. The same picture applied twice with different surface
  types is two entries, which is how one image is road in one place and grass in
  another.
- **Animation.** A texture with more than one frame flags the batches drawing it
  for animation, and a still one clears the flag. That is what retail does for
  every animated texture and only for those, so a picked waterfall moves.
- **Mapping.** *Keep The Mapping* leaves the picture covering the same ground as
  the one it replaced, rescaled for the new texture's size. *Project Flat*
  plants the texture on the world along whichever axis each face most faces, at
  a scale in map units per repeat - which is what a face you built or extruded
  needs, since it inherits UVs that are well-formed and mean nothing. The
  default, 256 units, is retail's own median. Projection tiles continuously
  across a join rather than restarting the texture at every triangle.

*Select* picks out every face already drawn with the chosen texture, *Remove*
puts faces back on their baked colours alone, and *Apply UV Editing* writes the
mapping you made in Blender's UV editor into the track.

**Or with a picture of your own.** The top of the Textures panel is *This
track's own artwork*: press **+**, pick any image Blender can read, and the
track ships it. The package carries the texture, DKR-R publishes a longer
`ASSET_TEXTURES_3D` table for it, and from that point it behaves like any other
texture in the panel - browse it, apply it, project it, select by it.

Two limits are the console's and the addon refuses rather than warns:

- A level texture is loaded into the RDP's **4 KiB of texture memory as one
  block**, so a colour image gets 2048 texels - **64x32**. The eight-bit
  greyscale formats reach 64x64. Pick the format in the file dialog; it decides
  the largest size, and the import says what it took the picture down from.
- A side larger than **64** cannot tile. `material_init` only recognises powers
  of two up to that, and gives anything else a clamp - the texture stretches
  once across each face instead of repeating.

The reduction is severe and there is no way around it, so look at the thumbnail
before building a track on it. Everything else is arranged so you do not have
to think about it: the image is resampled to the largest size that fits, in the
shape closest to the original's, and written as a PNG in `dkr_textures/` beside
the `.blend` so the package can be rebuilt from the scene alone.

The **order** of the list is the texture's identity - the runtime hands out ids
by position - so removing one moves the rest, and removing one the geometry has
already given a table entry is refused with the mesh named. Point those faces at
something else first.

For a one-command example, `tools/blender/make_texture_demo_track.py` builds a
flat track surfaced with an image you pass it, through the same operators:

```sh
blender --background --factory-startup \
    --python tools/blender/make_texture_demo_track.py -- \
    --image path/to/picture.jpg --out build/my-track.dkrmap
```

Adding a texture makes the export rebuild the layout rather than patch the file,
since everything after the texture table moves. A track's table tops out at 255
entries, which no retail track comes near - the largest is Spaceport Alpha at 63.

One thing does not come back yet: vertex colours are read for display only, so
repainting the baked lighting in Blender does not reach the track. UVs do come
back, but only through *Apply UV Editing* - editing the `UVMap` alone leaves the
file's own values in place.

Once geometry is loaded, Blender's own face snapping works, and *Drop To
Surface* casts the selected objects straight down onto the road - carrying the
ray on through decoration and walls, which now share one mesh with it.

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
dropdown of an enum's members. Where a type has an angle, rotate the object in
the viewport and the field follows.

`pad*` and `unk*` fields are hidden behind the **Show Raw Bytes** toggle. They
exist so an entry encodes to the bytes the game expects, and nobody has
identified what the `unk` ones do - a checkpoint declares 19 editable fields of
which 15 are `unk`, which buried the four that decide how it behaves. Thirteen
object types are nothing but raw bytes; the panel says so rather than showing a
wall of them.

**Draw the AI node graph.** This is *not* the racing line, which the game
interpolates from the checkpoints and which no node is read for. The graph
drives the Battle and Bananas challenges, hub NPCs and loop-de-loops, so it is
worth drawing for an arena or a hub and does nothing for a normal circuit.

Add a curve, draw the route, then *AI Nodes From
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
`header.bin`, both compiled object maps, any textures the track ships in
`textures/`, and the glTF sources beside them.

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
    textures.py             the ROM's 3D textures, and encoding your own
    scene.py                object map <-> Blender scene
    props.py                scene settings
    prefs.py                where to find the decomp assets
    operators/              import, export, place, AI, validate, package
    operators/geometry_export.py   the mesh's edits -> a level model
    operators/textures.py          pick, apply and map a texture
    operators/custom_textures.py   an image -> a texture the track ships
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
    test_textures.py            the ROM's table, vs what retail wrote
    test_custom_textures.py     an image -> the bytes the asset tool would write
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

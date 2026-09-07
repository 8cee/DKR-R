"""Exercise the addon's operators inside Blender.

The round-trip tests prove the data survives. This proves the buttons work:
registration, placing an object, sampling a curve into an AI line, validation
and writing a ``.dkrmap``. It is a smoke test - it checks that each operator
runs and leaves the scene in the state it claims, not that the UI looks right.

    blender --background --python tools/blender/tests/test_blender_operators.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import bpy

_HERE = os.path.dirname(os.path.abspath(__file__))
for argument in sys.argv:
    if argument.endswith("test_blender_operators.py"):
        _HERE = os.path.dirname(os.path.abspath(argument))
        break

sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

import dkr_track_editor  # noqa: E402
from dkr_track_editor import ai_graph, catalog as catalog_module, gltf_io, scene  # noqa: E402

from test_roundtrip import find_object_maps  # noqa: E402

FAILURES = []


def check(condition, message):
    if condition:
        print("  ok   %s" % message)
    else:
        print("  FAIL %s" % message)
        FAILURES.append(message)


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ---------------------------------------------------------------------------

def test_registration():
    print("registration")
    for name in ("import_object_map", "export_object_map", "place_object",
                 "ai_from_curve", "ai_add_branch", "validate", "export_dkrmap",
                 "set_enum_field", "reset_field", "select_by_type",
                 "import_geometry", "drop_to_surface", "toggle_walls",
                 "refresh_artwork", "set_slot"):
        check(hasattr(bpy.ops.dkr, name), "operator dkr.%s exists" % name)
    check(hasattr(bpy.types.Scene, "dkr"), "scene settings registered")


def test_place():
    print("placing objects")
    fresh()
    bpy.context.scene.cursor.location = (100.0, 200.0, 300.0)
    result = bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_GROUNDZIPPER")
    check(result == {"FINISHED"}, "place returns FINISHED")

    placed = scene.iter_dkr_objects(bpy.context)
    check(len(placed) == 1, "one object in the scene")
    if not placed:
        return
    empty = placed[0]
    check(str(empty[scene.PROP_ID]) == "ASSET_OBJECT_GROUNDZIPPER", "carries its type")
    check("scale" in empty and "angleY" in empty, "carries its fields")

    catalog = catalog_module.load()
    exported = scene.export_object_map(bpy.context, catalog)
    check(len(exported.objects) == 1, "exports one object")
    obj = exported.objects[0]
    # The cursor was set in Blender space; it must come back as map space.
    check(obj.translation == [100.0, 300.0, -200.0],
          "position converts Z-up to Y-up (got %r)" % (obj.translation,))
    check(isinstance(obj.fields["scale"], int), "int field stays an int")
    check(isinstance(obj.fields["angleY"], float), "angle field stays a float")

    # Blender turns an operator's ERROR report into an exception when it is
    # called from Python, so refusal shows up as a RuntimeError rather than a
    # CANCELLED return.
    try:
        bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_NOT_REAL")
        check(False, "unknown type is refused")
    except RuntimeError as error:
        check("unknown object type" in str(error), "unknown type is refused")
    check(len(scene.iter_dkr_objects(bpy.context)) == 1,
          "the refused object was not added")


def test_ai_from_curve():
    print("AI line from a curve")
    fresh()

    curve_data = bpy.data.curves.new("racing-line", type="CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    corners = [(-1000, -1000, 0), (1000, -1000, 0), (1000, 1000, 0), (-1000, 1000, 0)]
    spline.points.add(len(corners) - 1)
    for point, corner in zip(spline.points, corners):
        point.co = (corner[0], corner[1], corner[2], 1.0)
    spline.use_cyclic_u = True
    curve_object = bpy.data.objects.new("racing-line", curve_data)
    bpy.context.scene.collection.objects.link(curve_object)
    bpy.context.view_layer.objects.active = curve_object

    result = bpy.ops.dkr.ai_from_curve(spacing=400.0, closed="AUTO")
    check(result == {"FINISHED"}, "ai_from_curve returns FINISHED")

    nodes = [
        o for o in scene.iter_dkr_objects(bpy.context)
        if str(o[scene.PROP_ID]) == "ASSET_OBJECT_AINODE"
    ]
    check(len(nodes) >= 4, "sampled %d nodes from an 8000-unit lap" % len(nodes))

    ids = sorted(int(n["nodeID"]) for n in nodes)
    check(ids == list(range(len(nodes))), "node ids are 0..n-1 with no gaps")

    links = {int(n["nodeID"]): [a for a in n["adjacent"] if a != 255] for n in nodes}
    check(all(len(v) <= 4 for v in links.values()), "no node exceeds four neighbours")
    check(
        all(node in links.get(other, []) for node, nbrs in links.items() for other in nbrs),
        "every link is reciprocal, as retail data is",
    )
    check(all(len(v) == 2 for v in links.values()),
          "a closed loop gives every node exactly two neighbours")

    # The graph must survive a round trip through the file format.
    catalog = catalog_module.load()
    exported = scene.export_object_map(bpy.context, catalog)
    rebuilt = gltf_io.parse(json.loads(gltf_io.dumps(exported)))
    check(len(rebuilt.by_id("ASSET_OBJECT_AINODE")) == len(nodes),
          "AI nodes survive a write and read")
    adjacency = rebuilt.by_id("ASSET_OBJECT_AINODE")[0].fields["adjacent"]
    check(isinstance(adjacency, list) and len(adjacency) == 4,
          "adjacent stays a four-element list")


def test_ai_limits():
    print("AI graph limits")
    line = [(float(i) * 10.0, 0.0, 0.0) for i in range(600)]
    try:
        ai_graph.build_from_path(line, 1.0, closed=False)
        check(False, "over-long line is refused")
    except ai_graph.AiGraphError as error:
        check("255" in str(error), "over-long line is refused with the real limit")

    graph = ai_graph.AiGraph()
    hub = graph.add((0.0, 0.0, 0.0))
    spokes = [graph.add((float(i + 1), 0.0, 0.0)) for i in range(5)]
    for spoke in spokes[:4]:
        graph.link(hub, spoke)
    try:
        graph.link(hub, spokes[4])
        check(False, "a fifth neighbour is refused")
    except ai_graph.AiGraphError:
        check(True, "a fifth neighbour is refused")


def run_validate():
    """Call the operator, tolerating the exception Blender raises on ERROR."""
    try:
        bpy.ops.dkr.validate()
    except RuntimeError:
        pass
    return list(bpy.context.scene.dkr.results)


def test_validation():
    print("validation")
    fresh()
    bpy.context.scene.dkr.is_racing_track = True
    bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_GROUNDZIPPER")

    results = run_validate()
    check(bool(results), "validate fills in the results list")
    check(any(r.severity == "error" for r in results),
          "a track with no start line is an error")

    bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_SETUPPOINT")
    results = run_validate()
    errors = [r for r in results if r.severity == "error"]
    check(not errors, "adding a start position clears the error")

    # A hub is not a race, so the same scene must pass with the flag off.
    fresh()
    bpy.context.scene.dkr.is_racing_track = False
    bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_GROUNDZIPPER")
    errors = [r for r in run_validate() if r.severity == "error"]
    check(not errors, "a non-racing map is not required to have a start line")


def test_dkrmap_export():
    print("dkrmap package")
    fresh()
    bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_SETUPPOINT")
    bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_GROUNDZIPPER")

    settings = bpy.context.scene.dkr
    settings.track_name = "Ancient Lake Remix"
    settings.track_id = "ancient-lake-remix"
    settings.track_author = "test"

    temporary = tempfile.mkdtemp(prefix="dkr-track-")
    try:
        target = os.path.join(temporary, "ancient-lake-remix.dkrmap")
        result = bpy.ops.dkr.export_dkrmap(filepath=target, validate_first=True)
        check(result == {"FINISHED"}, "export_dkrmap returns FINISHED")
        check(os.path.isdir(target), "package directory created")

        manifest_path = os.path.join(target, "manifest.json")
        check(os.path.isfile(manifest_path), "manifest written")
        if os.path.isfile(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            check(manifest["id"] == "ancient-lake-remix", "manifest carries the id")
            check(manifest["schemaVersion"] == 1, "manifest declares its schema")

            # The manifest must claim exactly what is on disk: a promised
            # payload that is not there fails at load time, and one that is
            # there but unclaimed is silently ignored.
            claimed = {entry["file"] for entry in manifest["adds"]}
            present = {
                name for name in os.listdir(target)
                if name.endswith(".bin")
            }
            check(claimed == present,
                  "manifest claims exactly the payloads present "
                  "(claims %s, has %s)" % (sorted(claimed), sorted(present)))

            from dkr_track_editor import prefs
            if prefs.resolve(bpy.context) is not None:
                check("objects_structure.bin" in present,
                      "the structure map was compiled into the package")
                # A level has two object maps and the runtime patches a
                # different header field from each, so an entry without a slot
                # is refused rather than guessed.
                maps = [e for e in manifest["adds"]
                        if e["section"] == "LEVEL_OBJECT_MAPS"]
                check(maps, "the manifest names the object-map section")
                check(all("slot" in e for e in maps),
                      "every object-map entry carries its slot")
                check(all(e["slot"] in ("structure", "collectables")
                          for e in maps),
                      "slots are named as the runtime expects")

        source = os.path.join(target, "source", "objects_structure.gltf")
        check(os.path.isfile(source), "asset-tool source glTF written per slot")
        if os.path.isfile(source):
            written = gltf_io.load(source)
            check(len(written.objects) == 2,
                  "both objects went to the structure map by default")
        check(os.path.isfile(os.path.join(target, "source",
                                          "objects_structure.json")),
              "sidecar written")
        check(os.path.isfile(os.path.join(target, "HOW-TO-BUILD.md")),
              "build instructions written")

        # A payload the addon cannot produce must survive a re-export, or the
        # instruction to drop one in is a trap.
        with open(os.path.join(target, "header.bin"), "wb") as handle:
            handle.write(b"\x00" * 200)
        bpy.ops.dkr.export_dkrmap(filepath=target, validate_first=False)
        check(os.path.isfile(os.path.join(target, "header.bin")),
              "a supplied header.bin survives re-export")
        with open(manifest_path, "r", encoding="utf-8") as handle:
            again = json.load(handle)
        check(any(e["file"] == "header.bin" for e in again["adds"]),
              "and the manifest picks it up")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def test_import_export_operators():
    print("import and export operators")
    paths = find_object_maps()
    if not paths:
        print("  skip: no extracted object maps")
        return
    source = paths[len(paths) // 2]

    fresh()
    result = bpy.ops.dkr.import_object_map(filepath=source, frame_view=False)
    check(result == {"FINISHED"}, "import returns FINISHED")
    imported = len(scene.iter_dkr_objects(bpy.context))
    check(imported == len(gltf_io.load(source).objects), "every object imported")
    check(bpy.context.scene.dkr.source_path == source, "source path remembered")

    temporary = tempfile.mkdtemp(prefix="dkr-io-")
    try:
        target = os.path.join(temporary, "objects.gltf")
        result = bpy.ops.dkr.export_object_map(filepath=target, write_sidecar=True)
        check(result == {"FINISHED"}, "export returns FINISHED")
        with open(source, "rb") as a, open(target, "rb") as b:
            check(a.read() == b.read(), "exported file matches the imported one byte for byte")
        check(os.path.isfile(os.path.join(temporary, "objects.json")), "sidecar written")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def test_place_shows_artwork():
    """The plain flow: fresh scene, press a button, see the object.

    This is what the addon is for. It has to work with no import beforehand and
    no path configured, which means the asset tree must be discovered rather
    than only remembered from a previous import.
    """
    print("artwork on a freshly placed object")
    from dkr_track_editor import prefs

    fresh()
    tree = prefs.resolve(bpy.context)
    if tree is None:
        print("  skip: no extracted decomp assets to draw from")
        return
    check(True, "asset tree discovered without configuration (%s)" % tree.label)

    expectations = [
        ("ASSET_OBJECT_COIN", "sprite", "banana"),
        ("ASSET_OBJECT_SILVERCOIN", "sprite", "silver_coin"),
        ("ASSET_OBJECT_PALMTREETOP", "sprite", "palm_tree_top"),
        ("ASSET_OBJECT_FROG", "mesh", None),
        ("ASSET_OBJECT_AIRZIPPERS", "mesh", None),
    ]
    for object_id, expected_kind, texture in expectations:
        bpy.ops.dkr.place_object(object_id=object_id)
        obj = bpy.context.active_object
        kind = str(obj.get("dkr_preview", "marker"))
        label = object_id.replace("ASSET_OBJECT_", "")

        check(kind == expected_kind,
              "%s is drawn as a %s (got %s)" % (label, expected_kind, kind))
        check(obj.type == "MESH" and obj.data is not None,
              "%s has real geometry" % label)
        if obj.type == "MESH":
            check(len(obj.data.polygons) > 0,
                  "%s has faces (%d)" % (label, len(obj.data.polygons)))
        if texture:
            check(texture in _texture_names(obj),
                  "%s is textured with %s (got %s)"
                  % (label, texture, _texture_names(obj)))

    # The data must be untouched by any of it.
    catalog = catalog_module.load()
    exported = scene.export_object_map(bpy.context, catalog)
    check(len(exported.objects) == len(expectations),
          "every placed object still exports")
    check(all(o.object_id.startswith("ASSET_OBJECT_") for o in exported.objects),
          "exported objects keep their type")


def _texture_names(obj):
    names = []
    for material in obj.data.materials if obj.type == "MESH" else []:
        if material is None or not material.node_tree:
            continue
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                names.append(node.image.name)
    return ", ".join(names) or "<none>"


def test_balloon_variants():
    """A balloon's type has to pick the matching sprite, not a neighbouring one.

    The header lists its five sprites in enum declaration order, so the index
    must come from there. Taking it from the catalogue's observed values, which
    are sorted alphabetically, draws a missile balloon as a trap.
    """
    print("balloon type picks its own sprite")
    from dkr_track_editor import prefs, preview

    tree = prefs.resolve(bpy.context)
    catalog = catalog_module.load()
    if tree is None or "BalloonType" not in catalog.enums:
        print("  skip: no assets or no BalloonType enum")
        return

    for balloon_type in catalog.enums["BalloonType"]:
        variant = preview.variant_for(
            "ASSET_OBJECT_WEAPONBALLOON", {"balloonType": balloon_type}, catalog
        )
        _kind, path, _header = tree.preview_for("ASSET_OBJECT_WEAPONBALLOON", variant)
        name = os.path.basename(path).lower() if path else ""
        stem = balloon_type.replace("BALLOON_TYPE_", "").lower()
        # The asset spells missile "missle"; match on the shared prefix.
        check(stem[:5] in name,
              "%s uses %s (got %s)" % (balloon_type, stem, name or "<none>"))


def find_ancient_lake():
    from test_roundtrip import VANILLA
    import glob
    hits = sorted(glob.glob(os.path.join(
        VANILLA, "*", "levels", "models", "dino_domain", "ancient_lake.bin"
    )))
    return hits[0] if hits else None


def test_slots():
    """A level has two object maps and an object must go back to its own.

    The split is not semantic - 39 of the 85 object types appear in both maps
    across retail tracks, many near half and half - so it is remembered per
    object at import, never inferred from the type.
    """
    print("object map slots")
    path = find_ancient_lake()
    if path is None:
        print("  skip: no extracted level models")
        return

    from dkr_track_editor import prefs
    fresh()
    tree = prefs.resolve(bpy.context)
    if tree is None:
        print("  skip: no decomp assets")
        return
    lake = next((l for l in tree.levels() if l.label == "Ancient Lake"), None)
    if lake is None:
        print("  skip: Ancient Lake not in the index")
        return

    bpy.ops.dkr.import_level(level=lake.name)
    counts = scene.slot_counts(bpy.context)
    check(counts[scene.SLOT_STRUCTURE] > 0 and counts[scene.SLOT_COLLECTABLES] > 0,
          "both maps loaded (%d structure, %d collectables)"
          % (counts[scene.SLOT_STRUCTURE], counts[scene.SLOT_COLLECTABLES]))

    catalog = catalog_module.load()
    total = len(scene.export_object_map(bpy.context, catalog).objects)
    parts = {
        slot: len(scene.export_object_map(bpy.context, catalog, slot=slot).objects)
        for slot in scene.SLOTS
    }
    check(sum(parts.values()) == total,
          "the two maps partition the scene (%d + %d = %d)"
          % (parts[scene.SLOT_STRUCTURE], parts[scene.SLOT_COLLECTABLES], total))
    check(parts == counts, "export agrees with the scene's own count")

    # Each map has to match what it was loaded from, object for object.
    from dkr_track_editor import gltf_io as gio
    original = {
        scene.SLOT_STRUCTURE: gio.load(lake.objects_path),
        scene.SLOT_COLLECTABLES: gio.load(lake.collectables_path),
    }
    for slot, source in original.items():
        rebuilt = scene.export_object_map(bpy.context, catalog, slot=slot)
        check(gio.dumps(rebuilt) == gio.dumps(source),
              "the %s map round-trips byte-exactly on its own" % slot)

    # Moving an object between maps must move exactly one.
    obj = [o for o in scene.iter_dkr_objects(bpy.context)
           if scene.slot_of(o) == scene.SLOT_STRUCTURE][0]
    for other in bpy.context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.dkr.set_slot(slot="collectables")
    moved = scene.slot_counts(bpy.context)
    check(moved[scene.SLOT_STRUCTURE] == counts[scene.SLOT_STRUCTURE] - 1
          and moved[scene.SLOT_COLLECTABLES] == counts[scene.SLOT_COLLECTABLES] + 1,
          "set_slot moves exactly one object")


def test_partial_export_is_safe():
    """A header must never ship without a payload for both object-map slots.

    The header leaves 0x36 and 0xBA at zero for the runtime to patch, and zero
    is a valid index rather than an absence: the game clamps anything out of
    range to 0 and loads object map 0. So a header shipped with only one slot
    points the other at some other level's objects, which hangs on load.

    The fix is not to refuse - a track with no pickups is a legitimate thing to
    author - but to ship an **empty** map for the empty slot, which is what
    retail does in 16 of its own maps.
    """
    print("partial export")
    import struct
    import zlib

    from dkr_track_editor import prefs

    tree = prefs.resolve(bpy.context)
    if tree is None:
        print("  skip: no decomp assets")
        return
    lake = next((l for l in tree.levels() if l.label == "Ancient Lake"), None)
    if lake is None:
        print("  skip: Ancient Lake not in the index")
        return

    fresh()
    bpy.ops.dkr.import_level(level=lake.name, with_collectables=False)
    counts = scene.slot_counts(bpy.context)
    check(counts[scene.SLOT_COLLECTABLES] == 0,
          "the scene really has an empty collectables slot")

    temporary = tempfile.mkdtemp(prefix="dkr-partial-")
    try:
        target = os.path.join(temporary, "Untitled")
        bpy.ops.dkr.export_dkrmap(filepath=target, validate_first=False)
        target += ".dkrmap"

        with open(os.path.join(target, "manifest.json"), "r", encoding="utf-8") as h:
            manifest = json.load(h)
        sections = [e["section"] for e in manifest["adds"]]
        slots = sorted(e["slot"] for e in manifest["adds"]
                       if e["section"] == "LEVEL_OBJECT_MAPS")

        if "LEVEL_HEADERS" in sections:
            check(slots == ["collectables", "structure"],
                  "a header ships with both slots (got %s)" % slots)

        empty = os.path.join(target, "objects_collectables.bin")
        check(os.path.isfile(empty), "the empty slot still gets a payload")
        if os.path.isfile(empty):
            with open(empty, "rb") as handle:
                blob = zlib.decompress(handle.read()[5:], -15)
            check(struct.unpack_from(">I", blob, 0)[0] == 0,
                  "and it is an empty map, fileSize 0")
            check(len(blob) == 16, "which is 16 bytes")

        # The id must follow the folder, not a stale name from an import.
        check(manifest["id"] == "untitled",
              "the id comes from the folder being exported to (got %r)"
              % manifest["id"])
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def test_geometry_import():
    print("geometry import")
    from dkr_track_editor.operators import geometry as geometry_ops

    path = find_ancient_lake()
    if path is None:
        print("  skip: no extracted level models")
        return

    fresh()
    result = bpy.ops.dkr.import_geometry(filepath=path, include_hidden=True)
    check(result == {"FINISHED"}, "import_geometry returns FINISHED")

    meshes = [o for o in bpy.context.scene.objects if geometry_ops.PROP_GEOMETRY in o]
    check(len(meshes) >= 1, "geometry objects created (%d)" % len(meshes))
    kinds = {str(o[geometry_ops.PROP_GEOMETRY]) for o in meshes}
    check(geometry_ops.SURFACE in kinds, "the drivable surface was built")

    surface = [o for o in meshes if o[geometry_ops.PROP_GEOMETRY] == geometry_ops.SURFACE]
    if surface:
        mesh = surface[0].data
        check(len(mesh.polygons) > 100,
              "surface has real geometry (%d faces)" % len(mesh.polygons))
        check("baked" in [a.name for a in mesh.color_attributes],
              "baked vertex lighting imported as a colour attribute")
        check(surface[0].hide_select,
              "geometry is locked against selection so it is not picked by mistake")

    walls = [o for o in meshes if o[geometry_ops.PROP_GEOMETRY] == geometry_ops.INVISIBLE_WALLS]
    if walls:
        check(walls[0].hide_get(), "invisible walls start hidden")
        bpy.ops.dkr.toggle_walls()
        check(not walls[0].hide_get(), "toggle shows them")
        bpy.ops.dkr.toggle_walls()
        check(walls[0].hide_get(), "toggle hides them again")

    # Geometry must never be mistaken for a placed object.
    check(len(scene.iter_dkr_objects(bpy.context)) == 0,
          "geometry is not collected as an exportable object")

    check(bpy.context.scene.dkr.geometry_path == path, "geometry path remembered")


def test_drop_to_surface():
    print("drop to surface")
    from dkr_track_editor.operators import geometry as geometry_ops

    path = find_ancient_lake()
    if path is None:
        print("  skip: no extracted level models")
        return

    fresh()
    bpy.ops.dkr.import_geometry(filepath=path, include_hidden=False)
    surface = [
        o for o in bpy.context.scene.objects
        if geometry_ops.PROP_GEOMETRY in o
        and o[geometry_ops.PROP_GEOMETRY] == geometry_ops.SURFACE
    ]
    if not surface:
        print("  skip: no surface built")
        return

    # Put the cursor above a real face, place a zipper there, then drop it.
    mesh = surface[0].data
    centre = surface[0].matrix_world @ mesh.polygons[len(mesh.polygons) // 2].center
    bpy.context.scene.cursor.location = (centre.x, centre.y, centre.z + 5000.0)
    bpy.ops.dkr.place_object(object_id="ASSET_OBJECT_GROUNDZIPPER")

    zipper = [o for o in scene.iter_dkr_objects(bpy.context)][0]
    before = zipper.location.z
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    zipper.select_set(True)
    bpy.context.view_layer.objects.active = zipper

    result = bpy.ops.dkr.drop_to_surface(offset=0.0)
    check(result == {"FINISHED"}, "drop_to_surface returns FINISHED")
    check(zipper.location.z < before, "the object fell (%0.1f -> %0.1f)"
          % (before, zipper.location.z))
    check(abs(zipper.location.z - centre.z) < 1.0,
          "it landed on the face it was above (%0.2f vs %0.2f)"
          % (zipper.location.z, centre.z))


def main():
    dkr_track_editor.register()
    try:
        test_registration()
        test_place()
        test_ai_from_curve()
        test_ai_limits()
        test_validation()
        test_dkrmap_export()
        test_import_export_operators()
        test_geometry_import()
        test_drop_to_surface()
        test_place_shows_artwork()
        test_balloon_variants()
        test_slots()
        test_partial_export_is_safe()
    finally:
        dkr_track_editor.unregister()

    print()
    if FAILURES:
        print("FAIL: %d check(s)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("PASS: all operator checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())

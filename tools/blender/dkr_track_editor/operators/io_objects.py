"""Import and export object maps."""

from __future__ import annotations

import os
import traceback

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .. import assets, catalog as catalog_module, gltf_io, prefs, scene


def _report_exception(operator, message, error):
    operator.report({"ERROR"}, "%s: %s" % (message, error))
    traceback.print_exc()
    return {"CANCELLED"}


#: Which importer handles which kind of asset.
_HANDLED_BY = {
    assets.KIND_OBJECT_MAP: "Import Object Map",
    assets.KIND_LEVEL_MODEL: "Import Geometry",
}


def _wrong_kind(context, path, expected):
    """A message naming the right button, when the wrong file was picked.

    Everything in the extracted tree is a ``.json`` sidecar, so an object map
    and a level model are indistinguishable in a file browser. Saying only that
    a file "is not a LevelObjectMap sidecar" leaves an author with nowhere to
    go; naming the track it belongs to does not.
    """
    kind = assets.identify(path)
    if kind is None or kind == expected:
        return None

    name = os.path.basename(path)
    handler = _HANDLED_BY.get(kind)
    if handler is None:
        return "%s is a %s, which this importer does not handle" % (name, kind)

    # Look in the tree the file itself sits in, which is not necessarily the
    # one configured: an author can browse to a different extracted revision.
    described = {
        assets.KIND_LEVEL_MODEL: "the geometry",
        assets.KIND_OBJECT_MAP: "an object map",
    }.get(kind, "a %s" % kind)

    tree = assets.AssetTree.find(path) or prefs.resolve(context)
    level = tree.level_using(path) if tree else None
    if level is not None:
        return (
            "%s is %s for %s, not an object map. Use Import Track to load the "
            "whole thing, or %s for just this"
            % (name, described, level.label, handler)
        )
    return "%s is a %s; use %s instead" % (name, kind, handler)


class DKR_OT_import_object_map(bpy.types.Operator, ImportHelper):
    """Load a DKR object map, either the glTF or its .json sidecar"""

    bl_idname = "dkr.import_object_map"
    bl_label = "Import DKR Object Map"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".gltf"
    filter_glob: StringProperty(default="*.gltf;*.json", options={"HIDDEN"})

    clear_existing: BoolProperty(
        name="Replace Existing",
        description="Delete objects already imported before loading",
        default=True,
    )
    slot: bpy.props.EnumProperty(
        name="Object Map",
        description=(
            "Which of a level's two object maps these objects belong to. The "
            "runtime patches a different header field from each, so this has to "
            "match where they came from"
        ),
        items=[
            ("structure", "Structure", "The track: checkpoints, spawns, scenery"),
            ("collectables", "Collectables", "Pickups: coins, balloons"),
        ],
        default="structure",
    )
    show_artwork: BoolProperty(
        name="Show Object Artwork",
        description=(
            "Draw each object with the sprite or model the game uses, found in "
            "the same extracted asset tree the map came from. Without it every "
            "object is an unlabelled marker"
        ),
        default=True,
    )
    frame_view: BoolProperty(
        name="Frame In View",
        description=(
            "Zoom to the track and widen the viewport clipping. Tracks span "
            "thousands of units, well past Blender's default far clip"
        ),
        default=True,
    )

    def execute(self, context):
        path = self.filepath

        wrong = _wrong_kind(context, path, assets.KIND_OBJECT_MAP)
        if wrong:
            self.report({"ERROR"}, wrong)
            return {"CANCELLED"}

        try:
            if path.lower().endswith(".json"):
                path = gltf_io.load_sidecar(path)
            object_map = gltf_io.load(path)
        except Exception as error:  # noqa: BLE001 - surfaced to the user
            return _report_exception(self, "could not read %s" % os.path.basename(path), error)

        try:
            catalog = catalog_module.load()
        except Exception as error:  # noqa: BLE001
            return _report_exception(self, "catalogue unavailable", error)

        if self.clear_existing:
            _clear_existing(context)

        tree = None
        if self.show_artwork:
            # The tree the map itself came from is the right one; fall back to
            # whatever the author configured.
            tree = assets.AssetTree.find(path) or prefs.resolve(context)
        created = scene.import_object_map(
            context, object_map, catalog, tree, self.slot
        )
        context.scene.dkr.source_path = path
        if tree is not None:
            context.scene.dkr.asset_root = tree.root
            prefs.invalidate()
        elif self.show_artwork:
            self.report(
                {"WARNING"},
                "no extracted asset tree above this map, so objects are drawn "
                "as plain markers",
            )

        unknown = sorted({
            o.object_id for o in object_map.objects if o.object_id not in catalog
        })
        if unknown:
            self.report(
                {"WARNING"},
                "%d object(s) of unknown type kept verbatim: %s"
                % (len(unknown), ", ".join(unknown[:3])),
            )
        self.report({"INFO"}, "imported %d objects from %s"
                    % (len(created), os.path.basename(path)))

        if self.frame_view:
            _frame_view(context)
        return {"FINISHED"}


def _clear_existing(context):
    for obj in list(scene.iter_dkr_objects(context)):
        bpy.data.objects.remove(obj, do_unlink=True)


def _frame_view(context):
    """Track coordinates run to several thousand units; the default clip hides them."""
    for area in context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.clip_start = max(space.clip_start, 1.0)
                space.clip_end = max(space.clip_end, 100000.0)


class DKR_OT_export_object_map(bpy.types.Operator, ExportHelper):
    """Write the scene back out as a DKR object map glTF"""

    bl_idname = "dkr.export_object_map"
    bl_label = "Export DKR Object Map"
    bl_options = {"REGISTER"}

    filename_ext = ".gltf"
    filter_glob: StringProperty(default="*.gltf", options={"HIDDEN"})

    selected_only: BoolProperty(
        name="Selected Only",
        description="Export only the selected objects",
        default=False,
    )
    write_sidecar: BoolProperty(
        name="Write .json Sidecar",
        description=(
            "Also write the two-line file that names the glTF, which is what "
            "the asset tool actually reads"
        ),
        default=True,
    )

    def execute(self, context):
        try:
            catalog = catalog_module.load()
            object_map = scene.export_object_map(
                context, catalog, selected_only=self.selected_only
            )
        except Exception as error:  # noqa: BLE001
            return _report_exception(self, "could not build the object map", error)

        if not object_map.objects:
            self.report({"ERROR"}, "nothing to export; no DKR objects in the scene")
            return {"CANCELLED"}

        try:
            gltf_io.save(object_map, self.filepath)
            if self.write_sidecar:
                stem = os.path.splitext(self.filepath)[0]
                gltf_io.save_sidecar(
                    stem + ".json", os.path.basename(self.filepath)
                )
        except OSError as error:
            return _report_exception(self, "could not write %s" % self.filepath, error)

        self.report({"INFO"}, "exported %d objects to %s"
                    % (len(object_map.objects), os.path.basename(self.filepath)))
        return {"FINISHED"}


class DKR_OT_export_over_source(bpy.types.Operator):
    """Overwrite the object map this scene was imported from"""

    bl_idname = "dkr.export_over_source"
    bl_label = "Save Over Source"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.dkr.source_path)

    def invoke(self, context, event):
        # Overwriting the file the scene came from is not obviously reversible,
        # so make the author confirm it rather than doing it on a single click.
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        path = context.scene.dkr.source_path
        try:
            catalog = catalog_module.load()
            object_map = scene.export_object_map(context, catalog)
            gltf_io.save(object_map, path)
        except Exception as error:  # noqa: BLE001
            return _report_exception(self, "could not write %s" % path, error)
        self.report({"INFO"}, "wrote %d objects to %s"
                    % (len(object_map.objects), os.path.basename(path)))
        return {"FINISHED"}


def level_items(self, context):
    """Every retail level, grouped by world, for the picker."""
    tree = prefs.resolve(context)
    if tree is None:
        return [("NONE", "no decomp assets found", "")]
    entries = []
    for level in sorted(tree.levels(), key=lambda l: (l.world_label, l.label)):
        if not level.is_complete:
            continue
        world = level.world_label or "Other"
        entries.append((level.name, level.label, "%s | %s" % (world, level.race_type)))
    return entries or [("NONE", "no levels found", "")]


class DKR_OT_import_level(bpy.types.Operator):
    """Load a whole retail track: its geometry and both of its object maps"""

    bl_idname = "dkr.import_level"
    bl_label = "Import DKR Track"
    bl_options = {"REGISTER", "UNDO"}

    level: bpy.props.EnumProperty(
        name="Track",
        description="Which retail track to load",
        items=level_items,
    )
    with_geometry: BoolProperty(
        name="Include Geometry",
        description="Load the track model to place objects against",
        default=True,
    )
    with_collectables: BoolProperty(
        name="Include Collectables",
        description=(
            "Load the second object map as well. A track's pickups - coins and "
            "balloons - live in their own map, so without this the track has none"
        ),
        default=True,
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        """Show the track list, or the way to make the track list exist.

        An installed addon cannot find the decomp on its own - it lives in
        Blender's addons folder, nowhere near the repository - so the first time
        this dialog opens it is usually empty. Offering the path field right
        here means an author fixes it where they hit it, rather than being sent
        to a preferences window to hunt for a setting.
        """
        layout = self.layout
        tree = prefs.resolve(context)

        if tree is None:
            box = layout.box()
            box.label(text="No decomp assets found", icon="ERROR")
            box.label(text="Point this at your extracted decomp:")
            addon = context.preferences.addons.get(prefs.package_name())
            if addon is not None:
                box.prop(addon.preferences, "asset_root", text="")
            box.label(text="the folder holding asset_objects.meta.json,")
            box.label(text="e.g. .../assets/.vanilla/us.v77")
            return

        layout.label(text="Assets: %s" % tree.label, icon="CHECKMARK")
        layout.prop(self, "level")
        layout.prop(self, "with_geometry")
        layout.prop(self, "with_collectables")

    def execute(self, context):
        tree = prefs.resolve(context)
        if tree is None:
            self.report(
                {"ERROR"},
                "no extracted decomp assets found; set the path in this dialog "
                "or in Preferences > Add-ons > DKR Track Editor",
            )
            return {"CANCELLED"}

        level = tree.level(self.level)
        if level is None:
            self.report({"ERROR"}, "unknown track %r" % self.level)
            return {"CANCELLED"}

        _clear_existing(context)
        try:
            catalog = catalog_module.load()
        except Exception as error:  # noqa: BLE001
            return _report_exception(self, "catalogue unavailable", error)

        if self.with_geometry and level.model_path:
            bpy.ops.dkr.import_geometry(
                filepath=level.model_path, replace_existing=True
            )

        # map-2 is the structure slot and map-collectables the other; the
        # runtime patches a different header field from each, so an object has
        # to go back to the map it came from.
        maps = [(scene.SLOT_STRUCTURE, level.objects_path)]
        if self.with_collectables and level.collectables_path:
            maps.append((scene.SLOT_COLLECTABLES, level.collectables_path))

        total = 0
        for slot, path in maps:
            if not path:
                continue
            object_map = gltf_io.load(path)
            # Each map gets its own disjoint order range, so exporting either
            # one alone reproduces the file it came from.
            created = scene.import_object_map(
                context, object_map, catalog, tree, slot, order_base=total
            )
            total += len(created)

        context.scene.dkr.source_path = level.objects_path or ""
        context.scene.dkr.asset_root = tree.root
        context.scene.dkr.track_name = level.label
        prefs.invalidate()
        _frame_view(context)

        counts = scene.slot_counts(context)
        self.report(
            {"INFO"},
            "loaded %s: %d objects (%d structure, %d collectables)%s"
            % (level.label, total, counts[scene.SLOT_STRUCTURE],
               counts[scene.SLOT_COLLECTABLES],
               ", plus geometry" if self.with_geometry and level.model_path else ""),
        )
        return {"FINISHED"}


CLASSES = (
    DKR_OT_import_level,
    DKR_OT_import_object_map,
    DKR_OT_export_object_map,
    DKR_OT_export_over_source,
)

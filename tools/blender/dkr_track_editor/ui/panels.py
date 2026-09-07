"""The sidebar: place, edit, AI, validate, export."""

from __future__ import annotations

import bpy

from .. import catalog as catalog_module, prefs, scene
from ..operators import geometry as geometry_ops
from ..operators.edit import object_type_items

CATEGORY = "DKR"


class DkrPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


def _catalog_or_none():
    try:
        return catalog_module.load()
    except Exception:  # noqa: BLE001 - the panel must still draw
        return None


class DKR_PT_track(DkrPanel, bpy.types.Panel):
    bl_label = "Track"
    bl_idname = "DKR_PT_track"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dkr

        catalog = _catalog_or_none()
        if catalog is None:
            box = layout.box()
            box.label(text="Catalogue not loaded", icon="ERROR")
            box.label(text="Run tools/blender/generate_catalog.py")
            return

        layout.operator("dkr.import_level", icon="WORLD", text="Import Track")

        column = layout.column(align=True)
        column.operator("dkr.import_object_map", text="Import Object Map", icon="IMPORT")
        row = column.row(align=True)
        row.operator("dkr.export_object_map", icon="EXPORT")
        row.operator("dkr.export_over_source", text="", icon="FILE_TICK")

        if settings.source_path:
            layout.label(text=bpy.path.basename(settings.source_path), icon="FILE")

        counts = _counts(context)
        if counts:
            layout.label(text="%d objects, %d types" % (sum(counts.values()), len(counts)))
            slots = scene.slot_counts(context)
            layout.label(
                text="structure %d  |  collectables %d"
                % (slots[scene.SLOT_STRUCTURE], slots[scene.SLOT_COLLECTABLES]),
                icon="MOD_BUILD",
            )


class DKR_PT_geometry(DkrPanel, bpy.types.Panel):
    bl_label = "Geometry"
    bl_idname = "DKR_PT_geometry"
    bl_parent_id = "DKR_PT_track"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dkr

        layout.operator("dkr.import_geometry", icon="MESH_DATA")

        if not settings.geometry_path:
            box = layout.box()
            box.label(text="Load the track to place", icon="INFO")
            box.label(text="objects against. Without it")
            box.label(text="there is nothing to aim at.")
            box.label(text="levels/models/<world>/*.bin")
            return

        layout.label(text=bpy.path.basename(settings.geometry_path), icon="FILE")

        walls = [
            o for o in context.scene.objects
            if geometry_ops.PROP_GEOMETRY in o
            and o[geometry_ops.PROP_GEOMETRY] == geometry_ops.INVISIBLE_WALLS
        ]
        if walls:
            row = layout.row()
            row.operator(
                "dkr.toggle_walls",
                text="Hide Invisible Walls" if not walls[0].hide_get()
                else "Show Invisible Walls",
                icon="MOD_SOLIDIFY",
            )

        column = layout.column(align=True)
        column.operator("dkr.drop_to_surface", icon="SNAP_NORMAL")

        box = layout.box()
        box.label(text="Reference only, never exported", icon="LOCKED")
        box.label(text="Writing geometry is Phase 2")


def _counts(context):
    counts = {}
    for obj in scene.iter_dkr_objects(context):
        object_id = str(obj.get(scene.PROP_ID, ""))
        counts[object_id] = counts.get(object_id, 0) + 1
    return counts


class DKR_PT_place(DkrPanel, bpy.types.Panel):
    bl_label = "Place"
    bl_idname = "DKR_PT_place"
    bl_parent_id = "DKR_PT_track"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dkr
        catalog = _catalog_or_none()
        if catalog is None:
            return

        tree = prefs.resolve(context)
        if tree is None:
            box = layout.box()
            box.label(text="No decomp assets found", icon="ERROR")
            box.label(text="Objects will be plain markers.")
            box.label(text="Set the path in Preferences >")
            box.label(text="Add-ons > DKR Track Editor")
            box.operator("dkr.refresh_artwork", icon="FILE_REFRESH")
        else:
            row = layout.row(align=True)
            row.label(text="Artwork: %s" % tree.label, icon="TEXTURE")
            row.operator("dkr.refresh_artwork", text="", icon="FILE_REFRESH")

        layout.prop(settings, "slot")
        layout.prop(settings, "category")

        featured = catalog.featured()
        if featured and settings.category in ("ALL", ""):
            box = layout.box()
            box.label(text="Common", icon="SOLO_ON")
            grid = box.grid_flow(row_major=True, columns=2, align=True)
            for object_type in featured:
                grid.operator(
                    "dkr.place_object", text=object_type.label
                ).object_id = object_type.object_id

        types = (
            list(catalog.types.values())
            if settings.category in ("ALL", "")
            else catalog.in_category(settings.category)
        )
        types.sort(key=lambda t: (not t.featured, -t.retail_count, t.object_id))

        box = layout.box()
        box.label(text="All types (%d)" % len(types))
        column = box.column(align=True)
        for object_type in types[:60]:
            row = column.row(align=True)
            row.operator(
                "dkr.place_object", text=object_type.label
            ).object_id = object_type.object_id
            row.operator(
                "dkr.select_by_type", text="", icon="RESTRICT_SELECT_OFF"
            ).object_id = object_type.object_id
        if len(types) > 60:
            box.label(text="...and %d more; narrow by category" % (len(types) - 60))


class DKR_PT_object(DkrPanel, bpy.types.Panel):
    bl_label = "DKR Object"
    bl_idname = "DKR_PT_object"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and scene.PROP_ID in obj

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dkr
        obj = context.active_object
        catalog = _catalog_or_none()
        if catalog is None:
            return

        object_id = str(obj[scene.PROP_ID])
        object_type = catalog.get(object_id)

        header = layout.box()
        header.label(text=object_type.label if object_type else object_id, icon="EMPTY_DATA")
        header.label(text=object_id)
        if object_type and object_type.struct:
            header.label(text=object_type.struct)

        if object_type is None:
            layout.label(text="Not in the catalogue; kept verbatim", icon="INFO")
            return

        row = layout.row(align=True)
        row.operator("dkr.select_by_type", icon="RESTRICT_SELECT_OFF")
        row.prop(settings, "show_padding", text="", icon="THREE_DOTS")

        # Which of the level's two maps this object goes back to. Not inferred:
        # retail puts the same types in both.
        row = layout.row(align=True)
        row.label(text="Object map")
        row.operator(
            "dkr.set_slot",
            text=scene.slot_of(obj).title(),
            icon="MOD_BUILD",
        )

        angle_field = object_type.angle_field
        if angle_field is not None:
            note = layout.box()
            note.label(text="Rotate in the viewport to set %s" % angle_field.name,
                       icon="DRIVER_ROTATIONAL_DIFFERENCE")

        column = layout.column()
        drawn = 0
        for field in object_type.fields:
            if field.unused:
                continue
            if field.is_padding and not settings.show_padding:
                continue
            if angle_field is not None and field is angle_field:
                continue
            _draw_field(column, obj, field, object_type)
            drawn += 1

        if not drawn:
            column.label(text="This type carries only a position")

        absent = obj.get(scene.PROP_ABSENT)
        if absent:
            layout.label(text="Omitted on import: %s" % absent, icon="INFO")


def _draw_field(layout, obj, field, object_type):
    """One row per field, with the widget the field's kind calls for."""
    if field.name not in obj:
        row = layout.row(align=True)
        row.label(text=field.name)
        row.operator("dkr.reset_field", text="Add", icon="ADD").field = field.name
        return

    row = layout.row(align=True)
    if field.kind == "enum":
        row.label(text=field.name)
        row.operator(
            "dkr.set_enum_field", text=str(obj[field.name]), icon="DOWNARROW_HLT"
        ).field = field.name
    else:
        try:
            row.prop(obj, '["%s"]' % field.name, text=field.name)
        except (RuntimeError, TypeError):
            row.label(text="%s: %s" % (field.name, obj[field.name]))
    row.operator("dkr.reset_field", text="", icon="LOOP_BACK").field = field.name


class DKR_PT_ai(DkrPanel, bpy.types.Panel):
    bl_label = "AI Racing Line"
    bl_idname = "DKR_PT_ai"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        nodes = sum(
            1 for o in scene.iter_dkr_objects(context)
            if str(o.get(scene.PROP_ID)) == "ASSET_OBJECT_AINODE"
        )
        layout.label(text="%d AI node(s) in the scene" % nodes)

        if obj is None or obj.type != "CURVE":
            box = layout.box()
            box.label(text="Select a curve to sample", icon="INFO")
            box.label(text="Add > Curve, draw the racing line")
            return

        column = layout.column(align=True)
        column.operator("dkr.ai_from_curve", icon="CURVE_PATH")
        column.operator("dkr.ai_add_branch", icon="CURVE_BEZCIRCLE")


class DKR_PT_validate(DkrPanel, bpy.types.Panel):
    bl_label = "Validate"
    bl_idname = "DKR_PT_validate"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dkr

        layout.prop(settings, "is_racing_track")
        layout.operator("dkr.validate", icon="CHECKMARK")

        if not settings.has_validated:
            return
        if not len(settings.results):
            layout.label(text="No problems found", icon="CHECKMARK")
            return

        icons = {"error": "ERROR", "warning": "ERROR", "info": "INFO"}
        for group in ("error", "warning", "info"):
            entries = [r for r in settings.results if r.severity == group]
            if not entries:
                continue
            box = layout.box()
            box.label(text="%s (%d)" % (group.title(), len(entries)),
                      icon=icons.get(group, "INFO"))
            column = box.column(align=True)
            for entry in entries[:12]:
                for line in _wrap(entry.message, 44):
                    column.label(text=line)
            if len(entries) > 12:
                column.label(text="...and %d more" % (len(entries) - 12))


def _wrap(text, width):
    """Blender labels do not wrap, so break the message onto several."""
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


class DKR_PT_export(DkrPanel, bpy.types.Panel):
    bl_label = "Package"
    bl_idname = "DKR_PT_export"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.dkr

        column = layout.column()
        column.prop(settings, "track_name")
        column.prop(settings, "track_id")
        column.prop(settings, "track_author")

        # The id keys a track for arming and sibling resolution, so two tracks
        # sharing one collide. Show what will actually be written, since a
        # stale id set once persists across exports and is otherwise invisible.
        from .. import dkrmap
        if settings.track_id:
            resolved = settings.track_id
            source = "set explicitly"
        else:
            resolved = dkrmap.normalise_id(settings.track_name) or "<from folder>"
            source = "from the name" if settings.track_name else "from the folder"
        row = layout.row()
        row.label(text="id: %s" % resolved, icon="COPY_ID")
        row.label(text=source)

        layout.operator("dkr.export_dkrmap", icon="PACKAGE")

        slots = scene.slot_counts(context)
        box = layout.box()
        box.label(text="Writes header and both maps:", icon="INFO")
        box.label(text="structure %d, collectables %d"
                  % (slots[scene.SLOT_STRUCTURE], slots[scene.SLOT_COLLECTABLES]))
        if not slots[scene.SLOT_COLLECTABLES]:
            box.label(text="An empty slot ships an empty")
            box.label(text="map, not nothing: zero in the")
            box.label(text="header means map 0, not none.")


CLASSES = (
    DKR_PT_track,
    DKR_PT_geometry,
    DKR_PT_place,
    DKR_PT_object,
    DKR_PT_ai,
    DKR_PT_validate,
    DKR_PT_export,
)

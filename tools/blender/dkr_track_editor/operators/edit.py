"""Placing objects and editing their fields."""

from __future__ import annotations

import bpy
from bpy.props import EnumProperty, StringProperty

from .. import catalog as catalog_module, prefs, scene
from ..gltf_io import MapObject


def _catalog():
    return catalog_module.load()


def _asset_tree(context):
    """Where to read artwork from, however the author configured it."""
    return prefs.resolve(context)


def object_type_items(self, context):
    """Every object type, grouped so the featured ones come first."""
    try:
        catalog = _catalog()
    except Exception:  # noqa: BLE001 - an enum callback must not raise
        return [("NONE", "catalogue unavailable", "")]

    settings = context.scene.dkr if context and context.scene else None
    category = getattr(settings, "category", "ALL")

    types = list(catalog.types.values())
    if category and category not in ("ALL", ""):
        types = [t for t in types if t.category == category]
    types.sort(key=lambda t: (not t.featured, -t.retail_count, t.object_id))

    items = []
    for object_type in types:
        description = "%s | %s | %d in retail tracks" % (
            object_type.object_id, object_type.category, object_type.retail_count
        )
        label = object_type.label
        if object_type.featured:
            label += "  *"
        items.append((object_type.object_id, label, description))
    return items or [("NONE", "no types in this category", "")]


class DKR_OT_place_object(bpy.types.Operator):
    """Add a DKR object at the 3D cursor"""

    bl_idname = "dkr.place_object"
    bl_label = "Place DKR Object"
    bl_options = {"REGISTER", "UNDO"}

    object_id: StringProperty(
        name="Object Type",
        description="ASSET_OBJECT_* identifier to place",
    )

    def execute(self, context):
        catalog = _catalog()
        object_id = self.object_id or context.scene.dkr.object_type
        object_type = catalog.get(object_id)
        if object_type is None:
            self.report({"ERROR"}, "unknown object type %r" % object_id)
            return {"CANCELLED"}

        placed = MapObject(
            object_id=object_id,
            name=object_type.node_name,
            translation=scene.to_map(context.scene.cursor.location),
            fields=object_type.fresh_fields(),
        )

        root = scene.ensure_root(context)
        empty = scene.create_empty(context, placed, catalog, root,
                                   _asset_tree(context),
                                   context.scene.dkr.slot)
        empty["dkr_order"] = scene.next_order(context)

        for obj in context.selected_objects:
            obj.select_set(False)
        empty.select_set(True)
        context.view_layer.objects.active = empty

        if empty.type == "EMPTY" and _asset_tree(context) is None:
            self.report(
                {"WARNING"},
                "placed %s as a marker; set the decomp asset path in the addon "
                "preferences to draw objects with their real artwork"
                % object_type.label,
            )
        else:
            self.report({"INFO"}, "placed %s" % object_type.label)
        return {"FINISHED"}


class DKR_OT_set_enum_field(bpy.types.Operator):
    """Pick a value for an enum field from the full set the game defines"""

    bl_idname = "dkr.set_enum_field"
    bl_label = "Set Field"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    field: StringProperty(options={"HIDDEN"})

    def _items(self, context):
        obj = context.active_object
        if obj is None or scene.PROP_ID not in obj:
            return [("", "", "")]
        catalog = _catalog()
        object_type = catalog.get(str(obj[scene.PROP_ID]))
        if object_type is None:
            return [("", "", "")]
        field = object_type.field(self.field)
        if field is None:
            return [("", "", "")]
        members = catalog.enum_members(field)
        seen = set(field.values)
        return [
            (m, m, "used by retail tracks" if m in seen else "")
            for m in members
        ]

    value: EnumProperty(name="Value", items=_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_search_popup(self)

    def execute(self, context):
        obj = context.active_object
        if obj is None or not self.field:
            return {"CANCELLED"}
        obj[self.field] = self.value
        # Nudge the UI so the new value shows without the author clicking away.
        obj.update_tag()
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


class DKR_OT_reset_field(bpy.types.Operator):
    """Put a field back to the value a freshly placed object would have"""

    bl_idname = "dkr.reset_field"
    bl_label = "Reset Field"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    field: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        obj = context.active_object
        if obj is None or scene.PROP_ID not in obj:
            return {"CANCELLED"}
        object_type = _catalog().get(str(obj[scene.PROP_ID]))
        field = object_type.field(self.field) if object_type else None
        if field is None:
            return {"CANCELLED"}
        obj[self.field] = field.fresh()
        for area in context.screen.areas:
            area.tag_redraw()
        return {"FINISHED"}


class DKR_OT_select_by_type(bpy.types.Operator):
    """Select every object of the active object's type"""

    bl_idname = "dkr.select_by_type"
    bl_label = "Select Same Type"
    bl_options = {"REGISTER", "UNDO"}

    object_id: StringProperty(options={"HIDDEN"})

    def execute(self, context):
        target = self.object_id
        if not target:
            active = context.active_object
            if active is None or scene.PROP_ID not in active:
                self.report({"ERROR"}, "no active DKR object")
                return {"CANCELLED"}
            target = str(active[scene.PROP_ID])

        count = 0
        for obj in scene.iter_dkr_objects(context):
            match = str(obj[scene.PROP_ID]) == target
            obj.select_set(match)
            count += int(match)
        self.report({"INFO"}, "selected %d %s" % (count, target))
        return {"FINISHED"}


class DKR_OT_refresh_artwork(bpy.types.Operator):
    """Redraw every placed object with its sprite or model"""

    bl_idname = "dkr.refresh_artwork"
    bl_label = "Refresh Object Artwork"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from .. import gltf_io, preview

        prefs.invalidate()
        tree = prefs.resolve(context)
        if tree is None:
            self.report(
                {"ERROR"},
                "no extracted decomp assets found; set the path in the addon "
                "preferences",
            )
            return {"CANCELLED"}

        catalog = _catalog()
        existing = scene.export_object_map(context, catalog)
        root = scene.ensure_root(context)

        # An object's Blender type is fixed at creation, so an Empty cannot grow
        # a mesh. Rebuilding is the only way to give artwork to objects that
        # were placed before the asset path was known.
        for obj in list(scene.iter_dkr_objects(context)):
            bpy.data.objects.remove(obj, do_unlink=True)

        slots = [scene.slot_of(o) for o in scene.iter_dkr_objects(context)]
        rebuilt = [
            scene.create_empty(context, obj, catalog, root, tree, slot)
            for obj, slot in zip(existing.objects, slots)
        ]
        scene.stamp_order(rebuilt)

        drawn = sum(1 for o in rebuilt if preview.PROP_PREVIEW in o)
        self.report(
            {"INFO"},
            "redrew %d object(s), %d with artwork from %s"
            % (len(rebuilt), drawn, tree.label),
        )
        return {"FINISHED"}


class DKR_OT_set_slot(bpy.types.Operator):
    """Move the selected objects to the other object map"""

    bl_idname = "dkr.set_slot"
    bl_label = "Object Map"
    bl_options = {"REGISTER", "UNDO"}

    slot: EnumProperty(
        name="Object Map",
        items=[
            ("structure", "Structure", "The track: checkpoints, spawns, scenery"),
            ("collectables", "Collectables", "Pickups: coins, balloons"),
            ("TOGGLE", "Toggle", "Swap each selected object to the other map"),
        ],
        default="TOGGLE",
    )

    def execute(self, context):
        targets = [o for o in context.selected_objects if scene.is_dkr_object(o)]
        if not targets:
            active = context.active_object
            if active is None or not scene.is_dkr_object(active):
                self.report({"ERROR"}, "no DKR object selected")
                return {"CANCELLED"}
            targets = [active]

        for obj in targets:
            if self.slot == "TOGGLE":
                current = scene.slot_of(obj)
                obj[scene.PROP_SLOT] = (
                    scene.SLOT_COLLECTABLES
                    if current == scene.SLOT_STRUCTURE
                    else scene.SLOT_STRUCTURE
                )
            else:
                obj[scene.PROP_SLOT] = self.slot

        for area in context.screen.areas:
            area.tag_redraw()
        self.report({"INFO"}, "moved %d object(s)" % len(targets))
        return {"FINISHED"}


CLASSES = (
    DKR_OT_place_object,
    DKR_OT_set_slot,
    DKR_OT_set_enum_field,
    DKR_OT_reset_field,
    DKR_OT_select_by_type,
    DKR_OT_refresh_artwork,
)

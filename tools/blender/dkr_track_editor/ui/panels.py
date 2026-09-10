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

        from ..operators import new_track as new_track_ops
        if new_track_ops.convertible(context):
            box = layout.box()
            box.label(text="A mesh of your own is in", icon="INFO")
            box.label(text="the scene. Track From Mesh")
            box.label(text="turns it into geometry. Start")
            box.label(text="from a track's textures, or")
            box.label(text="from none and pick your own -")
            box.label(text="any of the ROM's will load.")
            column = box.column(align=True)
            column.operator("dkr.track_from_mesh", icon="MESH_MONKEY")
            column.operator("dkr.track_from_mesh_blank", icon="MESH_MONKEY")

        if not settings.geometry_path:
            box = layout.box()
            box.label(text="Load the track to place", icon="INFO")
            box.label(text="objects against, and to")
            box.label(text="reshape. Without it there")
            box.label(text="is nothing to aim at.")
            box.label(text="levels/models/<world>/*.bin")
            return

        layout.label(text=bpy.path.basename(settings.geometry_path), icon="FILE")

        objects = geometry_ops.geometry_objects(context)
        for obj in objects[:1]:
            layout.label(
                text="%d vertices, %d faces"
                % (len(obj.data.vertices), len(obj.data.polygons)),
                icon="MESH_DATA",
            )
            # The game reserves a fixed arena for a level model, and the
            # heaviest retail track already sits at 68% of it, so an author
            # adding geometry needs to see the ceiling before an export rather
            # than meet it as an overflow at load.
            budget = geometry_ops.budget_of(obj)
            if budget is not None:
                fraction, headroom = budget
                layout.label(
                    text="Load budget %d%%, %d tris spare"
                    % (round(fraction * 100.0), headroom),
                    icon="ERROR" if fraction >= 0.9 else "INFO",
                )
            # The quieter ceiling: collision looks at ten segments at a time,
            # so segments stretched across the map hold slots everywhere and
            # the ground a racer stands on stops being considered. It produces
            # no diagnostic in game at all, which is why it is shown here.
            pressure = geometry_ops.collision_pressure(obj)
            if pressure is not None and pressure[0] > pressure[1]:
                box = layout.box()
                box.label(text="%d oversized segments" % pressure[0], icon="ERROR")
                box.label(text="Collision sees %d at a time," % pressure[2])
                box.label(text="so these crowd it out and")
                box.label(text="racers fall through the")
                box.label(text="floor somewhere else.")

        if any(geometry_ops.WALL_GROUP in o.vertex_groups for o in objects):
            hidden = geometry_ops.walls_hidden(context)
            row = layout.row()
            row.operator(
                "dkr.toggle_walls",
                text="Show Invisible Walls" if hidden else "Hide Invisible Walls",
                icon="MOD_SOLIDIFY",
            )

        _draw_surface(layout, context, objects)

        column = layout.column(align=True)
        column.operator("dkr.edit_geometry", icon="EDITMODE_HLT")
        column.operator("dkr.check_geometry", icon="CHECKMARK")
        column.operator("dkr.resegment", icon="MOD_EXPLODE")
        column.operator("dkr.drop_to_surface", icon="SNAP_NORMAL")

        box = layout.box()
        box.label(text="Move vertices freely. The", icon="INFO")
        box.label(text="export reloads the shipped")
        box.label(text="model and applies only what")
        box.label(text="you changed, so the rest is")
        box.label(text="byte-identical. Adding or")
        box.label(text="deleting vertices is a later")
        box.label(text="step, and an export says so")
        box.label(text="rather than dropping it.")


class DKR_PT_textures(DkrPanel, bpy.types.Panel):
    """Browse the ROM's 3D textures and put one on the selected faces.

    A separate panel rather than a corner of the geometry one, because it is a
    gallery: fourteen hundred textures is not something that fits beside a
    paragraph, and picking one is the step an author spends time on. Everything
    it needs is in the scene, so it keeps its state across a mode switch into
    Edit Mode - which is where the faces get selected.
    """

    bl_label = "Textures"
    bl_idname = "DKR_PT_textures"
    bl_parent_id = "DKR_PT_track"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return bool(geometry_ops.geometry_objects(context))

    def draw(self, context):
        from .. import textures as texture_catalogue
        from ..operators import textures as texture_ops

        layout = self.layout
        settings = context.scene.dkr

        _draw_own_textures(layout, context, settings, texture_ops)

        tree = prefs.resolve(context)
        entries = texture_catalogue.catalogue(tree)
        if not entries:
            box = layout.box()
            box.label(text="No extracted textures found", icon="INFO")
            box.label(text="A track can also draw with any")
            box.label(text="of the ROM's 1401 textures, but")
            box.label(text="the addon has to be able to see")
            box.label(text="them. Set the path in")
            box.label(text="Preferences > Add-ons.")
            _draw_chosen_texture(layout, context, settings, texture_ops)
            return

        layout.separator()
        layout.label(text="The ROM's textures", icon="ASSET_MANAGER")
        row = layout.row(align=True)
        row.prop(settings, "texture_group", text="")
        row.prop(settings, "texture_query", text="", icon="VIEWZOOM")

        matches = texture_catalogue.search(
            entries, settings.texture_query, settings.texture_group
        )
        layout.label(text="%d of %d textures" % (len(matches), len(entries)))

        grid = layout.grid_flow(row_major=True, columns=6, align=True)
        for entry in matches[:texture_ops.PAGE]:
            grid.operator(
                "dkr.pick_texture", text="", icon_value=texture_ops.icon_for(entry)
            ).index = entry.index
        if len(matches) > texture_ops.PAGE:
            layout.label(
                text="...and %d more; search to narrow"
                % (len(matches) - texture_ops.PAGE),
                icon="INFO",
            )

        _draw_chosen_texture(layout, context, settings, texture_ops)


def _draw_own_textures(layout, context, settings, texture_ops):
    """The pictures the track ships itself, above the ones the ROM shipped.

    Above rather than below because they are the ones the author put there, and
    because a track can be textured entirely with them - on a machine with no
    extraction at all, where everything under this is an explanation of why the
    gallery is empty.
    """
    from ..operators import custom_textures

    own = custom_textures.entries(context)

    header = layout.row(align=True)
    header.label(text="This track's own artwork", icon="IMAGE_DATA")
    header.operator("dkr.add_custom_texture", text="", icon="ADD")
    if own:
        header.operator("dkr.remove_custom_texture", text="", icon="REMOVE")

    if not own:
        box = layout.box()
        box.label(text="Add an image and the track", icon="INFO")
        box.label(text="ships it: the package carries")
        box.label(text="the texture and the runtime")
        box.label(text="adds it to the ROM's table.")
        box.label(text="Colour tops out at 64x32, so")
        box.label(text="expect a heavy reduction.")
        return

    grid = layout.grid_flow(row_major=True, columns=6, align=True)
    for entry in own:
        grid.operator(
            "dkr.pick_texture", text="", icon_value=texture_ops.icon_for(entry)
        ).index = entry.index

    # The list is the only place the order is visible, and the order is the
    # texture's identity: the runtime hands out ids by position and the level
    # model names them by the same position. Numbered for that reason, and
    # clicking a row picks it, so Remove has something unambiguous to act on.
    column = layout.column(align=True)
    for position, entry in enumerate(own):
        chosen = int(settings.texture_id) == entry.index
        column.operator(
            "dkr.pick_texture",
            text="%d. %s  %dx%d" % (position + 1, entry.name,
                                    entry.width, entry.height),
            icon="RADIOBUT_ON" if chosen else "RADIOBUT_OFF",
            emboss=chosen,
        ).index = entry.index


def _draw_chosen_texture(layout, context, settings, texture_ops):
    """The picked texture, what it will behave like, and how it gets mapped."""
    chosen = texture_ops.picked(context)
    if chosen is None:
        box = layout.box()
        box.label(text="Pick a texture above, then", icon="INFO")
        box.label(text="select faces in Edit Mode and")
        box.label(text="apply it. A custom track is not")
        box.label(text="limited to the textures it was")
        box.label(text="built from - any of the ROM's")
        box.label(text="will load.")
        return

    box = layout.box()
    box.template_icon(icon_value=texture_ops.icon_for(chosen), scale=5.0)
    box.label(text=chosen.name, icon="TEXTURE")
    box.label(text="%dx%d, %s%s" % (chosen.width, chosen.height, chosen.group,
                                    ", animated" if chosen.animated else ""))

    box.prop(settings, "texture_surface")
    box.prop(settings, "texture_mapping", text="")
    if settings.texture_mapping == "PROJECT":
        box.prop(settings, "texture_scale")

    column = box.column(align=True)
    column.operator("dkr.apply_texture", icon="TEXTURE")
    row = column.row(align=True)
    row.operator("dkr.select_by_texture", text="Select", icon="RESTRICT_SELECT_OFF")
    row.operator("dkr.clear_texture", text="Remove", icon="X")
    column.operator("dkr.sync_uvs", icon="UV")

    obj = texture_ops.target(context)
    if obj is not None:
        added = len(geometry_ops.extra_textures(obj))
        if added:
            layout.label(
                text="%d texture(s) added to this track" % added, icon="PLUS"
            )


def _draw_surface(layout, context, objects):
    """What the active material's ground behaves like.

    Per material rather than per face, because that is where the game keeps it:
    the surface type is a byte on the texture table entry, so every face drawn
    with one entry behaves the same way and nothing finer is expressible. In
    Edit Mode the active slot follows the selection, so picking a face and
    reading this is how an author finds out what they are standing on.
    """
    obj = context.active_object
    if obj is None or obj not in objects:
        return
    material = obj.active_material
    if material is None or geometry_ops.PROP_TEXTURE_INDEX not in material:
        return

    box = layout.box()
    box.label(text="Surface", icon="MATERIAL")
    surface = material.get(geometry_ops.PROP_SURFACE)
    row = box.row(align=True)
    row.label(text="texture %d" % int(material[geometry_ops.PROP_TEXTURE_INDEX]))
    row.operator(
        "dkr.set_surface_type",
        text=geometry_ops.surface_name(surface) if surface is not None else "set",
        icon="DOWNARROW_HLT",
    )


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
        row.prop(settings, "show_raw", text="", icon="THREE_DOTS")

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
            if is_hidden_raw(field, settings.show_raw):
                continue
            if angle_field is not None and field is angle_field:
                continue
            _draw_field(column, obj, field, object_type)
            drawn += 1

        if not drawn:
            usable = [f for f in object_type.fields if not f.unused]
            if usable:
                # Every field this type has is a pad or an unidentified byte.
                column.label(text="Every field of this type is a raw byte",
                             icon="INFO")
                column.label(text="nobody has identified. Position is")
                column.label(text="all there is to author.")
            else:
                column.label(text="This type carries only a position")

        absent = obj.get(scene.PROP_ABSENT)
        if absent:
            layout.label(text="Omitted on import: %s" % absent, icon="INFO")


def is_hidden_raw(field, show_raw: bool) -> bool:
    """Whether a field is a byte to hide rather than something to author.

    A field carrying a label is no longer unidentified, whatever its name still
    looks like. A checkpoint's ``unkB``..``unk16`` are three groups of four -
    lateral offset, vertical offset and route flag, one slot per AI lane - and
    leaving those behind *Show Raw Bytes* buries the part of a checkpoint an
    author would most want to reach. The rule keeps itself up to date: labelling
    a field in the catalogue is what reveals it here, with no edit needed.
    """
    return bool(field.is_raw and field.label == field.name and not show_raw)


def _draw_field(layout, obj, field, object_type):
    """One row per field, with the widget the field's kind calls for.

    Drawn under ``field.label`` and stored under ``field.name``. The two are the
    same for most fields, and deliberately different where the decomp has
    identified what a byte does: the catalogue keeps the name, because it is the
    custom property key an existing ``.blend`` already holds and renaming it
    would drop the author's value in silence, and carries the meaning alongside.
    """
    if field.name not in obj:
        row = layout.row(align=True)
        row.label(text=field.label)
        row.operator("dkr.reset_field", text="Add", icon="ADD").field = field.name
        return

    row = layout.row(align=True)
    if field.kind == "enum":
        row.label(text=field.label)
        row.operator(
            "dkr.set_enum_field", text=str(obj[field.name]), icon="DOWNARROW_HLT"
        ).field = field.name
    else:
        try:
            row.prop(obj, '["%s"]' % field.name, text=field.label)
        except (RuntimeError, TypeError):
            row.label(text="%s: %s" % (field.label, obj[field.name]))
    row.operator("dkr.reset_field", text="", icon="LOOP_BACK").field = field.name


class DKR_PT_ai(DkrPanel, bpy.types.Panel):
    bl_label = "AI Node Graph"
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
            box.label(text="Add > Curve, draw the route")
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
                if entry.objects:
                    count = len(entry.objects.split(","))
                    column.operator(
                        "dkr.select_issue",
                        text="Select the %d object(s)" % count,
                        icon="RESTRICT_SELECT_OFF",
                    ).objects = entry.objects
                column.separator()
            if len(entries) > 12:
                column.label(text="...and %d more" % (len(entries) - 12))


class DKR_PT_header(DkrPanel, bpy.types.Panel):
    """The level header, for a track with no ancestor to inherit one from."""

    bl_label = "Level Header"
    bl_idname = "DKR_PT_header"
    bl_parent_id = "DKR_PT_export"

    def draw(self, context):
        from ..operators import header as header_ops
        from .. import level_header_template as template

        layout = self.layout
        settings = context.scene.dkr

        if settings.source_path or settings.geometry_path:
            box = layout.box()
            box.label(text="This track inherits its", icon="INFO")
            box.label(text="header from the one it")
            box.label(text="was imported from, so")
            box.label(text="these are unused.")

        layout.operator("dkr.header_defaults", icon="LOOP_BACK")

        outstanding = header_ops.unanswered(context)
        if outstanding:
            box = layout.box()
            box.label(text="%d field(s) unanswered" % len(outstanding), icon="ERROR")
            box.label(text="Zero is a real world and a")
            box.label(text="real race type, so a track")
            box.label(text="that never answered would")
            box.label(text="quietly become one.")

        column = layout.column(align=True)
        for choice in template.CHOICES:
            _draw_header_choice(column, context, choice, header_ops)


def _draw_header_choice(layout, context, choice, header_ops):
    """One row per header field, with the widget its kind calls for.

    Everything shown here is read from the template's own descriptors - the
    label, the kind, the enum it draws from, the range - so a field added or
    changed on that side appears with no edit here. Hard-coding the pointers
    would have drifted the first time the template moved, with nothing to catch
    it.
    """
    key = header_ops.key_for(choice.pointer)
    answered = key in context.scene

    if choice.kind == "bitfield":
        box = layout.box()
        row = box.row(align=True)
        row.label(text=choice.label)
        row.operator(
            "dkr.set_header_choice", text="", icon="ADD"
        ).pointer = choice.pointer
        for member in (list(context.scene[key]) if answered else []):
            entry = box.row(align=True)
            entry.label(text=str(member), icon="DOT")
            drop = entry.operator("dkr.clear_header_choice", text="", icon="X")
            drop.pointer = choice.pointer
            drop.member = str(member)
        return

    row = layout.row(align=True)
    if choice.kind in ("enum", "asset"):
        row.label(text=choice.label)
        shown = str(context.scene[key]) if answered else "not set"
        row.operator(
            "dkr.set_header_choice", text=shown, icon="DOWNARROW_HLT"
        ).pointer = choice.pointer
    elif answered:
        try:
            row.prop(context.scene, '["%s"]' % key, text=choice.label)
        except (RuntimeError, TypeError):
            row.label(text="%s: %s" % (choice.label, context.scene[key]))
    else:
        row.label(text=choice.label)
        row.label(text="default")

    if answered:
        row.operator(
            "dkr.clear_header_choice", text="", icon="X"
        ).pointer = choice.pointer


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
    DKR_PT_textures,
    DKR_PT_place,
    DKR_PT_object,
    DKR_PT_ai,
    DKR_PT_validate,
    DKR_PT_export,
    DKR_PT_header,
)

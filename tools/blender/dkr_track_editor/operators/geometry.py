"""Import track geometry as a reference mesh, and drop objects onto it.

This is what turns the addon from a coordinate editor into something an author
can actually aim with. The geometry is read-only: it is decoded from the level
model the game already ships and is never written back, because encoding one is
Phase 2. Its whole job is to give placement something to sit on, and to let
Blender's own face snapping work.

The mesh is split three ways, because the render flags mean genuinely different
things to an author:

* **surface** - the track as it is drawn and driven on
* **invisible walls** - batches flagged ``RENDER_HIDDEN`` but still solid, which
  is what keeps a racer on the road. Hidden in the viewport by default, since
  they otherwise bury the track, but there to be looked at.
* **decoration** - drawn but not collidable
"""

from __future__ import annotations

import os
import traceback

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector

from .. import assets, level_model, prefs, scene
from ..preview import _srgb_to_linear, _textured_material, reset_node_tree

#: Marks a mesh as decoded reference geometry rather than something to export.
PROP_GEOMETRY = "dkr_geometry"

GEOMETRY_COLLECTION = "geometry"

COLOUR_ATTRIBUTE = "baked"

SURFACE = "surface"
INVISIBLE_WALLS = "invisible walls"
DECORATION = "decoration"


def _material(name, colour, show_vertex_colours=False):
    """A material for the reference mesh.

    ``diffuse_color`` is the part that matters: it is what solid viewport
    shading draws, which is the mode an author places objects in. The node tree
    is built on top for rendered shading, defensively, because socket and node
    names have shifted between Blender releases and a cosmetic material is never
    worth failing an import over.
    """
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing

    material = bpy.data.materials.new(name)
    material.diffuse_color = colour
    try:
        _build_material_nodes(material, colour, show_vertex_colours)
    except Exception:  # noqa: BLE001 - appearance only
        traceback.print_exc()
    return material


def _build_material_nodes(material, colour, show_vertex_colours):
    tree, surface = reset_node_tree(material)
    if tree is None:
        return

    shader = tree.nodes.new("ShaderNodeBsdfDiffuse")
    shader.location = (-200, 0)
    colour_input = shader.inputs.get("Color")
    if colour_input is not None:
        colour_input.default_value = colour
    tree.links.new(shader.outputs[0], surface)

    if show_vertex_colours and colour_input is not None:
        # Level geometry carries no normals; the vertex colours are the baked
        # lighting, so showing them is what makes the track readable.
        attribute = tree.nodes.new("ShaderNodeVertexColor")
        attribute.layer_name = COLOUR_ATTRIBUTE
        attribute.location = (-400, 0)
        tree.links.new(attribute.outputs["Color"], colour_input)


def _build_mesh(stem, kind, model, want, collection, tree=None, fallback=None):
    """Build one mesh object from the batches matching ``want``.

    Batches are grouped by texture into material slots and the triangles carry
    their own UVs, so the track comes out looking like the track. A batch whose
    texture was not extracted falls back to the baked vertex colours, which is
    also what the invisible-wall mesh uses - a wall has no look of its own, and
    a flat tint reads better than whatever texture happens to be on it.
    """
    name = "%s %s" % (stem, kind)
    vertices = []
    colours = []
    faces = []
    face_slots = []
    face_uvs = []
    slots = {}
    materials = []

    def slot_for(png):
        key = png or "<vertex colours>"
        if key not in slots:
            slots[key] = len(materials)
            materials.append(
                _textured_material(png) if png
                else _material("dkr %s" % kind, fallback or (0.6, 0.6, 0.6, 1.0), True)
            )
        return slots[key]

    for segment in model.segments:
        base = len(vertices)
        used = False
        for batch in segment.batches:
            if not want(batch):
                continue
            texture = model.texture_for(batch)
            png = (
                tree.texture_3d_png(texture.texture_id)
                if (tree is not None and texture is not None and fallback is None)
                else None
            )
            slot = slot_for(png)
            for face_index in range(batch.face_offset,
                                    batch.face_offset + batch.face_count):
                if face_index >= len(segment.triangles):
                    break
                _flags, vi0, vi1, vi2 = segment.triangles[face_index]
                indices = tuple(
                    base + batch.vertex_offset + i for i in (vi0, vi1, vi2)
                )
                if max(indices) - base >= len(segment.vertices):
                    continue
                faces.append(indices)
                face_slots.append(slot)
                face_uvs.append(
                    level_model.normalise_uv(segment.uvs[face_index], texture)
                    if (png and face_index < len(segment.uvs)) else None
                )
                used = True
        if not used:
            continue
        for (x, y, z), rgba in zip(segment.vertices, segment.colours):
            vertices.append(scene.to_blender((x, y, z)))
            colours.append(
                tuple(_srgb_to_linear(c / 255.0) for c in rgba[:3]) + (rgba[3] / 255.0,)
            )

    if not faces:
        return None

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in vertices], [], faces)
    mesh.validate(verbose=False)
    mesh.update()

    if colours and len(colours) == len(mesh.vertices):
        layer = mesh.color_attributes.new(COLOUR_ATTRIBUTE, "FLOAT_COLOR", "POINT")
        for index, colour in enumerate(colours):
            layer.data[index].color = colour

    for material in materials:
        mesh.materials.append(material)

    # ``validate`` can drop a degenerate face, so only apply the per-face data
    # when the counts still line up.
    if len(mesh.polygons) == len(faces):
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for index, polygon in enumerate(mesh.polygons):
            polygon.material_index = face_slots[index]
            coordinates = face_uvs[index]
            if coordinates is None:
                continue
            for corner, loop_index in enumerate(polygon.loop_indices):
                if corner < len(coordinates):
                    uv_layer.data[loop_index].uv = coordinates[corner]

    obj = bpy.data.objects.new(name, mesh)
    obj[PROP_GEOMETRY] = kind
    collection.objects.link(obj)
    return obj


def _geometry_collection(context):
    root = scene.ensure_root(context)
    for child in root.children:
        if child.name == GEOMETRY_COLLECTION:
            return child
    collection = bpy.data.collections.new(GEOMETRY_COLLECTION)
    root.children.link(collection)
    return collection


class DKR_OT_import_geometry(bpy.types.Operator, ImportHelper):
    """Load a track's geometry as a read-only reference to place objects against"""

    bl_idname = "dkr.import_geometry"
    bl_label = "Import DKR Track Geometry"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".bin"
    filter_glob: StringProperty(default="*.bin;*.json", options={"HIDDEN"})

    replace_existing: BoolProperty(
        name="Replace Existing",
        description="Remove geometry already imported first",
        default=True,
    )
    include_hidden: BoolProperty(
        name="Include Invisible Walls",
        description=(
            "Import batches flagged RENDER_HIDDEN as their own mesh. They are "
            "not drawn in game but most are still solid"
        ),
        default=True,
    )
    textured: BoolProperty(
        name="Use Track Textures",
        description=(
            "Draw the track with the textures it ships with. Without it the "
            "geometry falls back to its baked vertex colours, which is faster "
            "but far harder to read"
        ),
        default=True,
    )
    make_unselectable: BoolProperty(
        name="Lock Selection",
        description=(
            "Stop the geometry being picked in the viewport, so box-selecting "
            "objects over the track does not grab the track itself"
        ),
        default=True,
    )

    def execute(self, context):
        path = self.filepath

        kind = assets.identify(path)
        if kind is not None and kind != assets.KIND_LEVEL_MODEL:
            tree = assets.AssetTree.find(path) or prefs.resolve(context)
            level = tree.level_using(path) if tree else None
            if level is not None:
                self.report(
                    {"ERROR"},
                    "%s is an object map for %s, not geometry. Use Import Track "
                    "to load the whole thing, or Import Object Map for just this"
                    % (os.path.basename(path), level.label),
                )
            else:
                self.report(
                    {"ERROR"},
                    "%s is a %s, not a level model; use Import Object Map"
                    % (os.path.basename(path), kind),
                )
            return {"CANCELLED"}

        try:
            if path.lower().endswith(".json"):
                resolved = level_model.sidecar_target(path)
                if not resolved:
                    self.report({"ERROR"}, "%s names no binary" % os.path.basename(path))
                    return {"CANCELLED"}
                path = resolved
            model = level_model.load(path)
        except level_model.LevelModelError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, "could not read %s: %s" % (os.path.basename(path), error))
            return {"CANCELLED"}

        if self.replace_existing:
            for obj in list(context.scene.objects):
                if PROP_GEOMETRY in obj:
                    bpy.data.objects.remove(obj, do_unlink=True)

        collection = _geometry_collection(context)
        stem = os.path.splitext(os.path.basename(path))[0]
        tree = assets.AssetTree.find(path) or prefs.resolve(context)
        if self.textured and tree is None:
            self.report(
                {"WARNING"},
                "no extracted assets found, so the track is drawn with its baked "
                "vertex colours instead of its textures",
            )

        art = tree if self.textured else None
        built = []
        surface = _build_mesh(
            stem, SURFACE, model,
            lambda b: not b.hidden and b.collidable, collection, art,
        )
        decoration = _build_mesh(
            stem, DECORATION, model,
            lambda b: not b.hidden and not b.collidable, collection, art,
        )
        walls = None
        if self.include_hidden:
            # Walls are never textured: they are not drawn in game at all, so a
            # flat tint says what they are far better than whatever texture the
            # batch happens to carry.
            walls = _build_mesh(
                stem, INVISIBLE_WALLS, model,
                lambda b: b.hidden, collection, None, (0.85, 0.25, 0.25, 0.35),
            )

        for obj in (surface, decoration, walls):
            if obj is None:
                continue
            built.append(obj)
            if self.make_unselectable:
                obj.hide_select = True

        if walls is not None:
            # They bury the track if left on, but an author needs to be able to
            # see where the walls are, so import them switched off rather than
            # not at all.
            walls.hide_set(True)
            walls.display_type = "WIRE"

        if not built:
            self.report({"ERROR"}, "the model decoded but held no drawable geometry")
            return {"CANCELLED"}

        context.scene.dkr.geometry_path = path
        tree = assets.AssetTree.find(path)
        if tree is not None:
            context.scene.dkr.asset_root = tree.root
            prefs.invalidate()
        _frame_view(context)

        solid_walls = sum(
            1 for s in model.segments for b in s.batches if b.invisible_wall
        )
        self.report(
            {"INFO"},
            "%s: %d segments, %d triangles, %d invisible wall batch(es)"
            % (stem, len(model.segments), model.triangle_count, solid_walls),
        )
        return {"FINISHED"}


def _frame_view(context):
    for area in context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.clip_start = max(space.clip_start, 1.0)
                space.clip_end = max(space.clip_end, 100000.0)


class DKR_OT_drop_to_surface(bpy.types.Operator):
    """Drop the selected objects straight down onto the track surface"""

    bl_idname = "dkr.drop_to_surface"
    bl_label = "Drop To Surface"
    bl_options = {"REGISTER", "UNDO"}

    offset: FloatProperty(
        name="Height Above Surface",
        description="Leave the object this far above where it lands",
        default=0.0,
        soft_min=-200.0,
        soft_max=200.0,
    )
    search_distance: FloatProperty(
        name="Search Distance",
        description="How far to look up and down for a surface",
        default=20000.0,
        min=1.0,
    )

    @classmethod
    def poll(cls, context):
        return any(scene.is_dkr_object(o) for o in context.selected_objects)

    def execute(self, context):
        targets = [
            o for o in context.scene.objects
            if PROP_GEOMETRY in o and o[PROP_GEOMETRY] == SURFACE
        ]
        if not targets:
            self.report(
                {"ERROR"},
                "no track surface in the scene; import the geometry first",
            )
            return {"CANCELLED"}

        depsgraph = context.evaluated_depsgraph_get()
        moved = missed = 0
        for obj in context.selected_objects:
            if not scene.is_dkr_object(obj):
                continue
            landing = self._raycast(obj.matrix_world.translation, targets, depsgraph)
            if landing is None:
                missed += 1
                continue
            obj.location = landing + Vector((0.0, 0.0, self.offset))
            moved += 1

        if not moved:
            self.report({"WARNING"}, "nothing landed on the surface")
            return {"CANCELLED"}
        if missed:
            self.report({"INFO"}, "dropped %d, %d found no surface below"
                        % (moved, missed))
        else:
            self.report({"INFO"}, "dropped %d object(s)" % moved)
        return {"FINISHED"}

    def _raycast(self, origin, targets, depsgraph):
        """Nearest hit straight down, falling back to straight up.

        Looking up matters: an object sitting slightly under the road should
        come back to the surface rather than be left buried.
        """
        best = None
        for direction in (Vector((0.0, 0.0, -1.0)), Vector((0.0, 0.0, 1.0))):
            for target in targets:
                matrix = target.matrix_world
                inverse = matrix.inverted()
                local_origin = inverse @ origin
                local_direction = (inverse.to_3x3() @ direction).normalized()
                hit, location, _normal, _index = target.ray_cast(
                    local_origin, local_direction, distance=self.search_distance
                )
                if not hit:
                    continue
                world = matrix @ location
                distance = (world - origin).length
                if best is None or distance < best[0]:
                    best = (distance, world)
            if best is not None:
                break
        return best[1] if best else None


class DKR_OT_toggle_walls(bpy.types.Operator):
    """Show or hide the invisible-wall geometry"""

    bl_idname = "dkr.toggle_walls"
    bl_label = "Toggle Invisible Walls"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        walls = [
            o for o in context.scene.objects
            if PROP_GEOMETRY in o and o[PROP_GEOMETRY] == INVISIBLE_WALLS
        ]
        if not walls:
            self.report({"WARNING"}, "no invisible-wall geometry in the scene")
            return {"CANCELLED"}
        showing = walls[0].hide_get()
        for wall in walls:
            wall.hide_set(not showing)
        self.report({"INFO"}, "invisible walls %s" % ("shown" if showing else "hidden"))
        return {"FINISHED"}


CLASSES = (
    DKR_OT_import_geometry,
    DKR_OT_drop_to_surface,
    DKR_OT_toggle_walls,
)

"""Turn a mesh an author modelled into track geometry.

The three steps of Phase 2 all start from a track the game already ships. This
is the one that does not: a mesh built in Blender, with no segmentation, no
texture table and no identity on any vertex, becoming a level model.

**How it works, and why in that order.** The mesh is read into loose faces and
one vertex pool, exactly the shape :func:`level_model_layout.rebatch_segment`
takes. :func:`level_model_layout.blank_model` supplies a model with every field
of the segment struct that is not safe to leave at zero already set - which is
why nothing here names one. The faces go into its single segment, and then
:func:`level_model_layout.resegment` partitions the whole thing properly and
builds the bounding boxes, the BSP and the PVS to match.

The result is written out as a ``.bin`` and then imported back through the
ordinary path, rather than being turned into a mesh directly. That is not a
detour: the author gets the same editable geometry as any other track, with the
identity attributes, the material slots and the base file that every other
operator here already understands, and there is exactly one importer to keep
correct instead of two.

**The ceiling this cannot lift.** A ``.dkrmap`` has no texture section - the
runtime's table has four entries and none of them is textures - so a new track
can only draw with textures the ROM already holds. That is why a donor track is
asked for rather than inferred: its texture table is what the new track will
use, and an author choosing it is choosing what their track can look like.
"""

from __future__ import annotations

import os
import traceback

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .. import (assets, level_model, level_model_encoder, level_model_layout,
                prefs, scene)
from . import geometry

#: Where the marker lives, so both this module and the export's "meshes I cannot
#: use" check read one name rather than two that have to agree.
PROP_CONVERTED = geometry.PROP_CONVERTED


def convertible(context) -> list:
    """Meshes that could be turned into a track: the author's own, unconverted."""
    return [
        obj for obj in geometry.unusable_meshes(context)
        if PROP_CONVERTED not in obj
    ]


def _texture_for(material, slot: int, count: int) -> int:
    """Which entry of the donor's texture table a material draws.

    A material that came from an imported track already names one. A material an
    author made does not, so it falls back to its slot position - which is
    arbitrary, and is why the operator says which textures it used.
    """
    if material is not None and geometry.PROP_TEXTURE_INDEX in material:
        index = int(material[geometry.PROP_TEXTURE_INDEX])
        if 0 <= index < count:
            return index
    if count <= 0:
        return level_model.NO_TEXTURE
    return min(max(0, slot), count - 1)


def _flags_for(material) -> int:
    """Render flags from the material's kind, defaulting to drawn and solid."""
    kind = material.get(geometry.PROP_CATEGORY) if material is not None else None
    if kind == geometry.INVISIBLE_WALLS:
        return level_model.RENDER_HIDDEN
    if kind == geometry.DECORATION:
        return level_model.RENDER_NO_COLLISION
    return 0


def _raw_uv(uv, texture):
    """A Blender UV back into the fixed point the file stores.

    The inverse of :func:`level_model.normalise_uv`. Exact for anything the
    format can hold: the drift is bounded by float32's relative precision times
    the coordinate, and an s16 coordinate keeps that three hundred times under
    the half unit rounding needs.
    """
    if texture is None:
        return (0, 0)
    u, v = float(uv[0]), float(uv[1])
    return (
        int(round(u * level_model.UV_FRACTIONAL_BITS * texture.width)),
        int(round((1.0 - v) * level_model.UV_FRACTIONAL_BITS * texture.height)),
    )


def read_source_mesh(obj, textures):
    """``(faces, positions, colours)`` for :func:`rebatch_segment`.

    Quads are fanned into triangles rather than refused, for the same reason the
    geometry export fans them: the file stores triangles and Blender's modelling
    tools produce quads, so refusing would make the ordinary way of building a
    mesh unusable.
    """
    mesh = obj.data
    matrix = obj.matrix_world

    positions = []
    for index, vertex in enumerate(mesh.vertices):
        place = scene.to_map(matrix @ vertex.co)
        rounded = tuple(int(round(float(c))) for c in place)
        for component in rounded:
            if not -32768 <= component <= 32767:
                raise ValueError(
                    "vertex %d sits at %r, outside the s16 a level model stores "
                    "positions in. Scale the mesh down - a retail track spans "
                    "roughly 20000 units end to end" % (index, rounded)
                )
        positions.append(rounded)

    colours = _read_colours(mesh)
    uv_layer = mesh.uv_layers.active

    faces = []
    for polygon in mesh.polygons:
        material = (mesh.materials[polygon.material_index]
                    if polygon.material_index < len(mesh.materials) else None)
        index = _texture_for(material, polygon.material_index, len(textures))
        texture = textures[index] if 0 <= index < len(textures) else None
        key = level_model_layout.BatchKey(
            index, _flags_for(material), 0, 0, 0, True, None,
        )
        corners = list(polygon.loop_indices)
        vertices = list(polygon.vertices)
        for corner in range(1, len(vertices) - 1):
            picks = (0, corner, corner + 1)
            uvs = tuple(
                _raw_uv(uv_layer.data[corners[p]].uv, texture) if uv_layer
                else (0, 0)
                for p in picks
            )
            faces.append(level_model_layout.Face(
                key, tuple(vertices[p] for p in picks), uvs, 0
            ))
    return faces, positions, colours


def _read_colours(mesh) -> list:
    """The baked lighting, white where the author painted none.

    White rather than black: the colours are multiplied into the texture, so
    black would render the whole track unlit and look like a broken import.
    """
    white = (255, 255, 255, 255)
    layer = mesh.color_attributes.get(geometry.COLOUR_ATTRIBUTE)
    if layer is None or layer.domain != "POINT":
        return [white] * len(mesh.vertices)

    values = [0.0] * (len(layer.data) * 4)
    try:
        layer.data.foreach_get("color", values)
    except (RuntimeError, TypeError):
        return [white] * len(mesh.vertices)

    from ..preview import _linear_to_srgb  # noqa: PLC0415 - optional helper

    colours = []
    for index in range(len(mesh.vertices)):
        at = index * 4
        if at + 4 > len(values):
            colours.append(white)
            continue
        colours.append(tuple(
            max(0, min(255, int(round(_linear_to_srgb(values[at + c]) * 255.0))))
            for c in range(4)
        ))
    return colours


class DKR_OT_track_from_mesh(bpy.types.Operator, ImportHelper):
    """Turn the selected mesh into DKR track geometry, borrowing a track's textures"""

    bl_idname = "dkr.track_from_mesh"
    #: What the file browser's confirm button says. It is not "Track From Mesh":
    #: by the time the browser is open the author has already asked for that, and
    #: what the button actually does is choose the track to borrow textures from.
    #: Left as the operator name it read as "pick your mesh", which is the one
    #: thing this dialog is not for.
    bl_label = "Use This Track's Textures"
    bl_options = {"REGISTER"}

    filename_ext = ".bin"
    filter_glob: StringProperty(default="*.bin;*.json", options={"HIDDEN"})

    keep_source: BoolProperty(
        name="Keep The Original Mesh",
        description=(
            "Leave the mesh you modelled in the scene, hidden. It is your own "
            "work and the addon does not delete it; the converted geometry is a "
            "separate object"
        ),
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return bool(convertible(context))

    def draw(self, context):
        """Say what the file browser is asking for.

        Without this it offers a file dialog with no explanation, and the
        obvious guess - that it wants the mesh, or the track being replaced - is
        wrong. It wants a texture table, and which one is a real choice: it is
        the whole set of images the new track can ever draw with.
        """
        layout = self.layout
        sources = convertible(context)

        box = layout.box()
        box.label(text="Pick a track to borrow from", icon="TEXTURE")
        box.label(text="levels/models/<world>/*.bin")
        box.separator()
        box.label(text="Its texture table becomes")
        box.label(text="the only set of images your")
        box.label(text="track can use. A .dkrmap")
        box.label(text="cannot add textures, so this")
        box.label(text="choice is not cosmetic.")

        if sources:
            note = layout.box()
            note.label(text="Converting: %s" % sources[0].name, icon="MESH_DATA")
            note.label(text="%d faces" % len(sources[0].data.polygons))

        layout.prop(self, "keep_source")

    def execute(self, context):
        sources = convertible(context)
        active = context.active_object
        obj = active if active in sources else (sources[0] if sources else None)
        if obj is None:
            self.report(
                {"ERROR"},
                "no mesh of your own in the scene to convert. Model one, or "
                "import a track's geometry and reshape that instead",
            )
            return {"CANCELLED"}

        if not bpy.data.filepath:
            self.report(
                {"ERROR"},
                "save the .blend first. A converted track is written as its own "
                "model file beside it, because that file becomes the base every "
                "later export is applied to",
            )
            return {"CANCELLED"}

        donor = self.filepath
        if donor.lower().endswith(".json"):
            donor = level_model.sidecar_target(donor) or donor
        try:
            textures = level_model.load(donor).textures
        except level_model.LevelModelError as error:
            self.report(
                {"ERROR"},
                "could not read the texture table from %s: %s"
                % (os.path.basename(donor), error),
            )
            return {"CANCELLED"}
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, "could not read %s: %s"
                        % (os.path.basename(donor), error))
            return {"CANCELLED"}

        context.view_layer.update()
        try:
            faces, positions, colours = read_source_mesh(obj, textures)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        if not faces:
            self.report({"ERROR"}, "%s has no faces to build a track from" % obj.name)
            return {"CANCELLED"}

        try:
            model = level_model_layout.blank_model(textures)
            level_model_layout.rebatch_segment(
                model.segments[0], faces, positions, colours
            )
            segments = level_model_layout.resegment(model)
            payload = level_model_encoder.pack(model)
        except (level_model_layout.LayoutError,
                level_model_encoder.LevelModelEncodeError) as error:
            self.report({"ERROR"}, "could not build the track: %s" % error)
            return {"CANCELLED"}

        stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        target = os.path.join(
            os.path.dirname(bpy.data.filepath), "%s-geometry.bin" % stem
        )
        try:
            with open(target, "wb") as handle:
                handle.write(payload)
        except OSError as error:
            self.report({"ERROR"}, "could not write %s: %s" % (target, error))
            return {"CANCELLED"}

        obj[PROP_CONVERTED] = target
        if self.keep_source:
            obj.hide_set(True)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)

        # Imported back through the ordinary path, so the author gets the same
        # editable geometry as any other track and there is one importer to keep
        # correct rather than two.
        for existing in list(context.scene.objects):
            if geometry.PROP_GEOMETRY in existing:
                bpy.data.objects.remove(existing, do_unlink=True)
        collection = geometry._geometry_collection(context)
        tree = assets.AssetTree.find(donor) or prefs.resolve(context)
        built, stats = geometry._build_geometry(
            stem, model, collection, tree, include_hidden=True
        )
        built[geometry.PROP_MODEL_PATH] = target
        built[geometry.PROP_AUTHORED_BASE] = True
        geometry.record_budget(built, model)
        context.scene.dkr.geometry_path = target

        for warning in _budget_warnings(model, textures):
            self.report({"WARNING"}, warning)

        self.report(
            {"INFO"},
            "built %d triangles into %d segments from %s, using %s's %d "
            "textures, and wrote %s"
            % (model.triangle_count, segments, obj.name if self.keep_source
               else "the mesh", os.path.basename(donor), len(textures),
               os.path.basename(target)),
        )
        return {"FINISHED"}


def _budget_warnings(model, textures) -> list:
    messages = []
    used = level_model_layout.runtime_size(model)
    if used > level_model_layout.BUDGET:
        messages.append(
            "this track needs %d bytes at load, over the %d the game reserves. "
            "The overflow does not refuse - it writes past the heap - so this "
            "has to come down before the track is played"
            % (used, level_model_layout.BUDGET)
        )
    messages.extend(level_model_layout.check_collision_pressure(model))
    if not textures:
        messages.append(
            "the donor track has no textures, so nothing in this track will be "
            "drawn with one"
        )
    return messages


CLASSES = (DKR_OT_track_from_mesh,)

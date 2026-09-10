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

**The ceiling this cannot lift, and the one it no longer has.** A ``.dkrmap``
has no texture section - the runtime's table has four entries and none of them
is textures - so a new track can only draw with textures the ROM already holds.
That much stands.

What used to sit on top of it, and does not any more, is that the new track was
stuck with the *donor's* table: two or three dozen images picked once and
unchangeable. A level model's table stores indices into the ROM's global 3D
texture list, so it can name any texture the ROM holds, and :mod:`..textures`
and the Textures panel are how an author picks them. A donor table is therefore a
starting point and a convenience - it brings a coherent set of images and their
surface types with it - which is why :class:`DKR_OT_track_from_mesh_blank`
exists beside it for authors who would rather choose everything themselves.
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
    """Which entry of the starting texture table a material draws.

    A material that came from an imported track already names one. A material an
    author made does not, so it falls back to its slot position - which is
    arbitrary, and is why the operator says which textures it used. With no
    starting table at all every face comes out untextured, which is the honest
    answer: the author picks the textures afterwards, in the Textures panel,
    where the whole ROM is available rather than one track's table.
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
        wrong. It wants a texture table to start from.
        """
        layout = self.layout
        sources = convertible(context)

        box = layout.box()
        box.label(text="Pick a track to start from", icon="TEXTURE")
        box.label(text="levels/models/<world>/*.bin")
        box.separator()
        box.label(text="Its texture table is where")
        box.label(text="your track begins - a coherent")
        box.label(text="set of images with their")
        box.label(text="surface types. You can add any")
        box.label(text="of the ROM's other textures")
        box.label(text="afterwards, in the Textures")
        box.label(text="panel.")

        if sources:
            note = layout.box()
            note.label(text="Converting: %s" % sources[0].name, icon="MESH_DATA")
            note.label(text="%d faces" % len(sources[0].data.polygons))

        layout.prop(self, "keep_source")

    def execute(self, context):
        obj = _source_mesh(self, context)
        if obj is None:
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

        return build_track(self, context, obj, textures, self.keep_source,
                           donor=donor)


def _source_mesh(operator, context):
    """The mesh being converted, or ``None`` with the reason already reported."""
    sources = convertible(context)
    active = context.active_object
    obj = active if active in sources else (sources[0] if sources else None)
    if obj is None:
        operator.report(
            {"ERROR"},
            "no mesh of your own in the scene to convert. Model one, or "
            "import a track's geometry and reshape that instead",
        )
        return None

    if not bpy.data.filepath:
        operator.report(
            {"ERROR"},
            "save the .blend first. A converted track is written as its own "
            "model file beside it, because that file becomes the base every "
            "later export is applied to",
        )
        return None
    return obj


def build_track(operator, context, obj, textures, keep_source, donor=None):
    """Build a level model out of one mesh and import it back as geometry.

    Shared by the two ways in, which differ only in where the starting texture
    table comes from: a donor track's, or nothing at all. Everything after that
    point is the same, which is the reason it is one function - the segmenting,
    the layout and the re-import are exactly what must not drift between them.
    """
    context.view_layer.update()
    try:
        faces, positions, colours = read_source_mesh(obj, textures)
    except ValueError as error:
        operator.report({"ERROR"}, str(error))
        return {"CANCELLED"}

    if not faces:
        operator.report({"ERROR"},
                        "%s has no faces to build a track from" % obj.name)
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
        operator.report({"ERROR"}, "could not build the track: %s" % error)
        return {"CANCELLED"}

    stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    target = os.path.join(
        os.path.dirname(bpy.data.filepath), "%s-geometry.bin" % stem
    )
    try:
        with open(target, "wb") as handle:
            handle.write(payload)
    except OSError as error:
        operator.report({"ERROR"}, "could not write %s: %s" % (target, error))
        return {"CANCELLED"}

    name = obj.name
    obj[PROP_CONVERTED] = target
    if keep_source:
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
    tree = (assets.AssetTree.find(donor) if donor else None) or prefs.resolve(context)
    built, _stats = geometry._build_geometry(
        stem, model, collection, tree, include_hidden=True
    )
    built[geometry.PROP_MODEL_PATH] = target
    built[geometry.PROP_AUTHORED_BASE] = True
    geometry.record_budget(built, model)
    context.scene.dkr.geometry_path = target

    for warning in _budget_warnings(model, textures):
        operator.report({"WARNING"}, warning)

    source = "%s's %d textures" % (os.path.basename(donor), len(textures))         if donor else "no textures yet"
    operator.report(
        {"INFO"},
        "built %d triangles into %d segments from %s, with %s, and wrote %s"
        % (model.triangle_count, segments, name if keep_source else "the mesh",
           source, os.path.basename(target)),
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
            "this track starts with no texture table, so every face is "
            "untextured until you give it one. Select faces and apply a texture "
            "from the Textures panel; any of the ROM's will load"
        )
    return messages


class DKR_OT_track_from_mesh_blank(bpy.types.Operator):
    """Turn the selected mesh into DKR track geometry, choosing textures later

    The same conversion, without borrowing a starting texture table. Every face
    comes out untextured and the Textures panel is where they get their look -
    which is the honest shape of the job now that a track can name any texture
    in the ROM rather than only the ones a donor happened to ship with.
    """

    bl_idname = "dkr.track_from_mesh_blank"
    bl_label = "Track From Mesh, No Textures"
    bl_options = {"REGISTER"}

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

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        sources = convertible(context)
        if sources:
            box = layout.box()
            box.label(text="Converting: %s" % sources[0].name, icon="MESH_DATA")
            box.label(text="%d faces" % len(sources[0].data.polygons))

        box = layout.box()
        box.label(text="Every face comes out", icon="INFO")
        box.label(text="untextured. Pick textures in")
        box.label(text="the Textures panel afterwards -")
        box.label(text="any texture in the ROM will do.")

        layout.prop(self, "keep_source")

    def execute(self, context):
        obj = _source_mesh(self, context)
        if obj is None:
            return {"CANCELLED"}
        return build_track(self, context, obj, [], self.keep_source)


CLASSES = (DKR_OT_track_from_mesh, DKR_OT_track_from_mesh_blank)

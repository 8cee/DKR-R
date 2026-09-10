"""Bring a picture into a track as artwork the ROM never had.

:mod:`..textures` holds the whole of the *format* side of this - what a
``TextureHeader`` is, what fits texture memory, what id a level model stores for
a texture its package ships. None of it needs Blender and all of it is tested
without one. This module is the other half: getting an author's JPEG or PNG,
whatever size and shape it is, down to something that side will accept.

**Resampling is the work, and it is brutal.** A level texture is loaded into the
RDP's 4 KiB of texture memory as a single block, so a colour image gets 2048
texels - 64x32. A 2752x1536 photograph is 4.2 million. There is no version of
this that keeps the picture; the honest thing is to do the reduction plainly,
say what it did, and put the result in front of the author as a thumbnail before
they build a track around it.

**Why the PNG beside the .blend rather than the file the author picked.** The
package has to be rebuildable from the ``.blend``, and the picked file might be
a JPEG on a drive that is not there any more. So the import writes what it
resampled, as a PNG, in a folder beside the scene, and everything afterwards -
the thumbnail, the material, the export - reads that. The original is kept as a
note about where the picture came from and is never read again.

**Ordinals are positions and positions are identity.** The runtime hands a
track's textures ids by their order in its manifest, and the level model names
them by the same order. So adding goes on the end, and removing has to move
every id behind it down one - which the mesh records, not the scene, so the two
are stepped together here.

That is also why removing stops short of a texture the geometry has already
taken a *table entry* for. A table index is a position too, and dropping an
entry would move every later one along with the faces that hold it, the
materials keyed by it and the surface types read off those materials. No other
operator in the addon removes a table entry - clearing a texture off faces
leaves the entry standing - so this one does not invent that either. It says
which mesh is holding on and what to do about it.
"""

from __future__ import annotations

import os
import traceback

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .. import textures as texture_module
from . import geometry

#: Where the resampled PNGs go, beside the ``.blend`` that names them.
FOLDER = "dkr_textures"


class CustomTextureError(Exception):
    """The picture cannot become a texture, with the reason an author can act on."""


# ---------------------------------------------------------------------------
# The scene's list, as the rest of the addon wants to see it
# ---------------------------------------------------------------------------

def entries(context) -> list:
    """The track's own textures as :class:`..textures.CustomTexture`.

    In collection order, which is ordinal order, which is the order the package
    writes them in. Nothing sorts this.
    """
    settings = getattr(context.scene, "dkr", None)
    if settings is None:
        return []
    found = []
    for ordinal, record in enumerate(settings.custom_textures):
        found.append(texture_module.CustomTexture(
            ordinal=ordinal,
            name=record.name,
            png=resolve(record.png),
            width=record.width,
            height=record.height,
            texture_format=record.format,
            render_mode=record.render_mode or "OPAQUE",
            source=record.source,
        ))
    return found


def resolve(stored: str) -> str:
    """A stored image path as something that can be opened.

    Paths are kept relative to the ``.blend``'s directory so that a scene and
    its pictures can be moved or handed to someone else together. Absolute is
    still accepted, because an unsaved scene has nothing to be relative to.
    """
    if not stored:
        return ""
    if os.path.isabs(stored):
        return stored
    if not bpy.data.filepath:
        return stored
    return os.path.normpath(
        os.path.join(os.path.dirname(bpy.data.filepath), stored)
    )


def by_id(context, texture_id):
    """The track's own texture an id names, or ``None`` if it names the ROM's."""
    ordinal = texture_module.custom_ordinal(texture_id)
    if ordinal is None:
        return None
    found = entries(context)
    return found[ordinal] if 0 <= ordinal < len(found) else None


def folder(context) -> str:
    """Where a resampled PNG is written.

    Beside the ``.blend`` when there is one, so the package travels with the
    scene. An unsaved scene gets Blender's temporary directory, which is honest
    about what it is: the author is told to save.
    """
    if bpy.data.filepath:
        return os.path.join(os.path.dirname(bpy.data.filepath), FOLDER)
    return os.path.join(bpy.app.tempdir, FOLDER)


def _unique(directory: str, stem: str) -> str:
    """A path in ``directory`` that is not taken.

    A re-import must not write over the PNG a previous one produced: the preview
    system caches a thumbnail against the path, so the old picture would go on
    being drawn for the new texture until Blender restarted.
    """
    candidate = os.path.join(directory, stem + ".png")
    suffix = 2
    while os.path.exists(candidate):
        candidate = os.path.join(directory, "%s-%d.png" % (stem, suffix))
        suffix += 1
    return candidate


def _slug(text: str) -> str:
    kept = [char if char.isalnum() else "-" for char in (text or "").lower()]
    return "".join(kept).strip("-").replace("--", "-") or "texture"


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------

def resample(source: str, destination: str, width: int, height: int):
    """Read any image Blender reads, scale it, and write it as an 8-bit PNG.

    ``(was_width, was_height)`` comes back, so the operator can say what it took
    the picture down from.

    Blender is used for this and only this. It decodes JPEG, PNG, TGA and the
    rest, and it resamples; what it must not do is colour-manage on the way
    through, because the texels written afterwards are the bytes in this file.

    For the ordinary case it does not: an eight-bit image round-trips through
    ``scale`` and ``save`` byte for byte - measured on a 2752x1536 JPEG, whose
    channel means came back identical with and without the line below.
    ``Non-Color`` is set anyway because that guarantee is only for eight-bit
    images, and a float source (an EXR, an HDR) *is* transformed on the way out.
    """
    image = bpy.data.images.load(source, check_existing=False)
    try:
        was = (image.size[0], image.size[1])
        if was[0] <= 0 or was[1] <= 0:
            raise CustomTextureError(
                "%s has no pixels; Blender could not read it as an image"
                % os.path.basename(source)
            )
        try:
            image.colorspace_settings.name = "Non-Color"
        except (AttributeError, TypeError):
            pass  # A build without that name still writes the buffer as it is.
        image.scale(int(width), int(height))
        image.file_format = "PNG"
        image.filepath_raw = destination
        image.save()
        return was
    finally:
        bpy.data.images.remove(image)


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def _parse_size(text: str, texture_format: int, was):
    """The size to resample to: what the author typed, or the best fit."""
    text = (text or "").strip().lower().replace(" ", "")
    if not text:
        return texture_module.best_size(texture_format, was[0], was[1])
    for separator in ("x", "*", ","):
        if separator in text:
            left, _sep, right = text.partition(separator)
            try:
                return (int(left), int(right))
            except ValueError:
                break
    raise CustomTextureError(
        "%r is not a size; write it as WxH, for example 64x32, or leave it "
        "blank to take the largest the format allows" % text
    )


def _format_items(self, context):
    """The same list the scene's own Format menu offers, from one place."""
    from .. import props  # noqa: PLC0415 - registered after this module loads

    return props.texture_format_items(self, context)


class DKR_OT_add_custom_texture(bpy.types.Operator, ImportHelper):
    """Add an image of your own to this track's artwork"""

    bl_idname = "dkr.add_custom_texture"
    bl_label = "Add Custom Texture"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ""
    filter_glob: StringProperty(
        default="*.png;*.jpg;*.jpeg;*.tga;*.bmp;*.tif;*.tiff;*.exr;*.webp",
        options={"HIDDEN"},
    )

    texture_format: EnumProperty(
        name="Format",
        description="How the texture is stored, which sets how large it can be",
        items=_format_items,
    )

    size: StringProperty(
        name="Size",
        description=(
            "Width and height to resample to, as WxH. Both have to be powers "
            "of two no larger than 64. Blank takes the largest the format "
            "allows, in the shape closest to the picture's"
        ),
        default="",
    )

    def invoke(self, context, event):
        settings = context.scene.dkr
        self.texture_format = settings.custom_format
        self.size = settings.custom_size
        return ImportHelper.invoke(self, context, event)

    def execute(self, context):
        settings = context.scene.dkr
        code = int(self.texture_format)
        settings.custom_format = self.texture_format
        settings.custom_size = self.size

        if len(settings.custom_textures) >= texture_module.CUSTOM_ID_COUNT:
            self.report({"ERROR"},
                        "a track can add at most %d textures of its own"
                        % texture_module.CUSTOM_ID_COUNT)
            return {"CANCELLED"}

        source = self.filepath
        if not source or not os.path.isfile(source):
            self.report({"ERROR"}, "pick an image file")
            return {"CANCELLED"}

        directory = folder(context)
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as error:
            self.report({"ERROR"}, "could not write to %s: %s" % (directory, error))
            return {"CANCELLED"}

        stem = _slug(os.path.splitext(os.path.basename(source))[0])
        destination = _unique(directory, stem)

        try:
            was = _probe(source)
            width, height = _parse_size(self.size, code, was)
            texture_module.check_size(width, height, code)
            was = resample(source, destination, width, height)
            # Read it straight back through the addon's own decoder. Blender
            # writing a PNG the encoder cannot read is the failure that would
            # otherwise wait until export, with a track already built on it.
            texture_module.encode_texture(destination, code)
        except (CustomTextureError, texture_module.TextureEncodeError) as error:
            _discard(destination)
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        except Exception as error:  # noqa: BLE001 - Blender image errors vary
            traceback.print_exc()
            _discard(destination)
            self.report({"ERROR"}, "could not read %s: %s"
                        % (os.path.basename(source), error))
            return {"CANCELLED"}

        record = settings.custom_textures.add()
        record.name = os.path.splitext(os.path.basename(source))[0]
        record.source = source
        record.png = _stored_path(destination)
        record.width = width
        record.height = height
        record.format = code
        record.render_mode = "OPAQUE"

        # Select it in the browser so the next click is Apply rather than a
        # hunt through fourteen hundred thumbnails for the one just added.
        settings.texture_id = texture_module.custom_id(
            len(settings.custom_textures) - 1
        )

        if not bpy.data.filepath:
            self.report(
                {"WARNING"},
                "%s was written to Blender's temporary folder because this "
                "scene has never been saved. Save the .blend and add it again, "
                "or the picture will be gone next session"
                % os.path.basename(destination),
            )
        self.report(
            {"INFO"},
            "added %s at %dx%d, down from %dx%d" % (record.name, width, height,
                                                    was[0], was[1]),
        )
        return {"FINISHED"}


def _probe(source: str):
    """The picture's size before anything is done to it."""
    image = bpy.data.images.load(source, check_existing=False)
    try:
        return (image.size[0], image.size[1])
    finally:
        bpy.data.images.remove(image)


def _stored_path(path: str) -> str:
    """Relative to the ``.blend``'s directory where possible, so the scene moves."""
    if not bpy.data.filepath:
        return path
    try:
        relative = os.path.relpath(path, os.path.dirname(bpy.data.filepath))
    except ValueError:
        return path  # A different drive on Windows has no relative path.
    if relative.startswith(".."):
        return path  # Outside the scene's folder; it would not travel anyway.
    return relative.replace(os.sep, "/")


def _discard(path: str) -> None:
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


class DKR_OT_remove_custom_texture(bpy.types.Operator):
    """Remove one of this track's own textures, renumbering the rest"""

    bl_idname = "dkr.remove_custom_texture"
    bl_label = "Remove Custom Texture"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        settings = getattr(context.scene, "dkr", None)
        return bool(settings and len(settings.custom_textures))

    def execute(self, context):
        settings = context.scene.dkr
        position = texture_module.custom_ordinal(settings.texture_id)
        if position is None or position >= len(settings.custom_textures):
            self.report(
                {"ERROR"},
                "pick one of this track's own textures first; the browser is "
                "currently on one of the ROM's, which a track cannot remove",
            )
            return {"CANCELLED"}
        going = texture_module.custom_id(position)
        name = settings.custom_textures[position].name

        # A texture the geometry has taken a table entry for cannot be removed
        # here, and the reason is not squeamishness. A table index is a
        # position: dropping an entry moves every later one, so every face
        # holding a higher index, every material keyed by one, and every
        # surface type read off those materials would all have to move with it.
        # The addon has no operation that removes a table entry - clearing a
        # texture off faces leaves the entry standing - so inventing one here,
        # in the operator least likely to be tested, is how a track quietly
        # starts drawing its neighbour's pictures.
        using = _table_users(context, going)
        if using:
            self.report(
                {"ERROR"},
                "%s already has a place in the texture table of %s, and removing "
                "it would move every entry after it - repainting whatever "
                "draws them. Point those faces at another texture first: "
                "pick one, Select, then Apply"
                % (name, " and ".join(sorted(using))),
            )
            return {"CANCELLED"}

        # Nothing refers to it by table entry, so all that is left is the ids
        # of the textures behind it in the queue, which each move down one.
        moved = _renumber(context, going)

        settings.custom_textures.remove(position)
        settings.texture_id = -1

        if moved:
            self.report({"INFO"},
                        "removed %s; %d later texture(s) moved up" % (name, moved))
        else:
            self.report({"INFO"}, "removed %s" % name)
        return {"FINISHED"}


def _table_users(context, texture_id: int) -> set:
    """The geometry whose texture table has an entry for this texture."""
    found = set()
    for obj in geometry.geometry_objects(context):
        for record in geometry.extra_textures(obj):
            if int(record.get("id", 0)) == int(texture_id):
                found.add(obj.data.name)
                break
    return found


def _renumber(context, going: int) -> int:
    """Move every recorded id past ``going`` down one, and say how many moved.

    The ids live on the mesh and the ordinals live in the scene, so this is the
    one place the two have to be kept in step by hand. Only the id changes; no
    entry is added or dropped, so every table index stays exactly where it was.
    """
    moved = 0
    for obj in geometry.geometry_objects(context):
        extras = geometry.extra_textures(obj)
        if not extras:
            continue
        changed = False
        for record in extras:
            identifier = int(record.get("id", 0))
            if texture_module.is_custom_id(identifier) and identifier > going:
                record["id"] = identifier - 1
                changed = True
                moved += 1
        if changed:
            geometry.set_extra_textures(obj, extras)
    return moved


CLASSES = (
    DKR_OT_add_custom_texture,
    DKR_OT_remove_custom_texture,
)

"""Scene-level settings for the track editor."""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty,
    PointerProperty, StringProperty,
)

from . import catalog as catalog_module

#: Blender hands an enum callback's strings to C without taking a reference, so
#: a list built fresh each call can be collected while the menu still points at
#: it - the symptom being a picker that opens empty. Holding the last list
#: returned for each key is what keeps them alive.
_ITEMS = {}


def _keep(key, items):
    _ITEMS[key] = items
    return items


def category_items(self, context):
    items = [("ALL", "All", "Every object type")]
    try:
        catalog = catalog_module.load()
    except Exception:  # noqa: BLE001 - an enum callback must not raise
        return items
    for category in catalog.categories:
        count = len(catalog.in_category(category))
        if count:
            items.append((category, category.title(), "%d types" % count))
    return items


def texture_group_items(self, context):
    """The folders the ROM's 3D textures are extracted into.

    Imported here rather than at module scope because resolving them reaches for
    the asset tree, and this module is imported while the addon is still being
    registered.
    """
    items = [("ALL", "All", "Every texture in the ROM")]
    try:
        from . import prefs, textures as texture_catalogue  # noqa: PLC0415

        entries = texture_catalogue.catalogue(prefs.resolve(context))
        for group in texture_catalogue.groups(entries):
            count = sum(1 for entry in entries if entry.group == group)
            items.append((group, group.title(), "%d textures" % count))
    except Exception:  # noqa: BLE001 - an enum callback must not raise
        pass
    return _keep("texture_group", items)


def texture_surface_items(self, context):
    """What the ground made of a newly applied texture behaves like.

    The same list the Set Surface Type operator offers, from the catalogue's
    ``SurfaceType``, because it is the same choice - made when the texture is
    applied rather than afterwards, since the surface type is part of what
    decides whether an entry can be reused or a new one is needed.
    """
    try:
        from .operators import geometry as geometry_ops  # noqa: PLC0415

        found = [(str(value), name, help_text)
                 for value, name, help_text in geometry_ops.surface_items()]
    except Exception:  # noqa: BLE001 - an enum callback must not raise
        found = []
    return _keep("texture_surface", found or [("0", "Road", "")])


def texture_format_items(self, context):
    """The formats a texture a track brings with it may be written in.

    Not the whole of ``FORMAT_CODES``: the two colour-indexed ones need a
    palette out of ``ASSET_EMPTY_14``, and a track cannot add one of those.
    """
    from . import textures as texture_module  # noqa: PLC0415

    described = {
        "RGBA16": "Colour, one bit of alpha. What 1034 of the ROM's own use",
        "RGBA32": "Full colour and alpha. Four times the memory, so 32x32 at most",
        "IA16": "Greyscale with a full alpha channel",
        "IA8": "Greyscale with alpha, four bits each",
        "IA4": "Greyscale with one bit of alpha, four bits a texel",
        "I8": "Greyscale. Reaches 64x64, where colour stops at 64x32",
        "I4": "Greyscale, four bits a texel. The smallest",
    }
    items = []
    for name in texture_module.CUSTOM_FORMATS:
        code = texture_module.FORMAT_CODES[name]
        best = texture_module.largest_size(code) or (0, 0)
        items.append((
            str(code), name,
            "%s. Up to %dx%d" % (described.get(name, name), best[0], best[1]),
        ))
    return _keep("texture_format", items)


class DKR_CustomTexture(bpy.types.PropertyGroup):
    """One image the track ships itself, as the scene remembers it.

    The PNG is the record, not the file the author picked: it has already been
    resampled to a size the RDP can load and written where a re-export can find
    it, so the package can be rebuilt from a ``.blend`` alone. ``source`` is
    kept only so the panel can say where the picture came from.
    """

    name: StringProperty(name="Name", default="Texture")
    source: StringProperty(name="From", default="")
    #: Relative to the directory the ``.blend`` is in, so the scene and its
    #: pictures move together. Plain text rather than a ``FILE_PATH``: Blender's
    #: ``//`` prefix is what a path property understands, and only from 4.5
    #: onwards and only when the property opts in - a warning on every assign
    #: for anyone on 4.2, which is the version this addon says it needs.
    #: :func:`..operators.custom_textures.resolve` is the other half.
    png: StringProperty(name="Image", default="")
    #: The same picture at full resolution, as a PNG, stored the way ``png`` is.
    #: The track never reads it; the high-resolution texture pack the export
    #: writes beside the ``.dkrmap`` does. Empty for a texture added before the
    #: pack existed, which the export then rebuilds from ``source`` if it can.
    original: StringProperty(name="Original", default="")
    width: IntProperty(default=0)
    height: IntProperty(default=0)
    #: A ``FORMAT_CODES`` value, stored as the number the file stores.
    format: IntProperty(default=1)
    render_mode: StringProperty(default="OPAQUE")
    #: Which invisible bit the export flips to tell this texture apart from
    #: another that reduced to the same pixels; 0 for none. See
    #: :func:`..textures.nudge_texels`.
    nudge: IntProperty(default=0)


class DKR_ValidationEntry(bpy.types.PropertyGroup):
    severity: StringProperty(default="info")
    message: StringProperty(default="")
    object_id: StringProperty(default="")
    #: Comma-separated document positions, so the result can select what it is
    #: about rather than leaving the author to hunt for it.
    objects: StringProperty(default="")


class DKR_SceneSettings(bpy.types.PropertyGroup):
    """Everything the sidebar needs to remember between clicks."""

    source_path: StringProperty(
        name="Source",
        description="The object map this scene was imported from",
        default="",
        subtype="FILE_PATH",
    )

    asset_root: StringProperty(
        name="Asset Tree",
        description=(
            "Extracted decomp asset version directory the artwork is read from"
        ),
        default="",
        subtype="DIR_PATH",
    )

    geometry_path: StringProperty(
        name="Geometry",
        description="The level model loaded as reference geometry",
        default="",
        subtype="FILE_PATH",
    )

    category: EnumProperty(
        name="Category",
        description="Narrow the object list",
        items=category_items,
    )

    object_type: StringProperty(
        name="Object Type",
        description="The type the Place button will add",
        default="ASSET_OBJECT_GROUNDZIPPER",
    )

    track_name: StringProperty(
        name="Track Name",
        description="Shown in game and in the mod list",
        default="",
    )
    track_id: StringProperty(
        name="Track Id",
        description=(
            "Directory name and manifest id: lowercase words joined by hyphens. "
            "Left blank, it is derived from the track name"
        ),
        default="",
    )
    track_author: StringProperty(name="Author", default="")

    is_racing_track: BoolProperty(
        name="Racing Track",
        description=(
            "Apply the checks that only make sense for a track people race on, "
            "such as needing somewhere to start. Turn it off for a hub"
        ),
        default=True,
    )

    slot: EnumProperty(
        name="Object Map",
        description=(
            "Which of the level's two object maps a newly placed object joins. "
            "The split is not semantic - retail puts the same object types in "
            "both - so it is remembered per object rather than inferred"
        ),
        items=[
            ("structure", "Structure", "The track: checkpoints, spawns, scenery"),
            ("collectables", "Collectables", "Pickups: coins, balloons"),
        ],
        default="structure",
    )

    show_raw: BoolProperty(
        name="Show Raw Bytes",
        description=(
            "Show the pad and unk fields. They exist so an entry encodes to the "
            "bytes the game expects, and nobody has identified what the unk ones "
            "do - a checkpoint has 15 of them around the 4 that matter"
        ),
        default=False,
    )

    # -- the texture browser ---------------------------------------------
    #
    # A track can draw with any texture the ROM holds, not only the ones its
    # base model shipped with, so what is remembered here is a choice out of
    # 1401 rather than out of a table.

    texture_id: IntProperty(
        name="Texture",
        description=(
            "Index into the ROM's 3D texture list - what a level model's "
            "texture table actually stores. -1 means nothing is chosen"
        ),
        default=-1,
    )

    texture_query: StringProperty(
        name="Search",
        description=(
            "Narrow the textures by name. Every word has to appear, so "
            "\"ice wall\" finds the icy walls and not every wall"
        ),
        default="",
        options={"TEXTEDIT_UPDATE"},
    )

    texture_group: EnumProperty(
        name="Set",
        description="Which of the extraction's texture folders to browse",
        items=texture_group_items,
    )

    texture_surface: EnumProperty(
        name="Surface",
        description=(
            "What the ground made of this texture behaves like. It is stored on "
            "the texture table entry, so applying the same picture with two "
            "surface types makes two entries - which is how the game gets one "
            "image that is road in one place and grass in another"
        ),
        items=texture_surface_items,
    )

    texture_mapping: EnumProperty(
        name="Mapping",
        description="What to do with the UVs of the faces being retextured",
        items=[
            ("KEEP", "Keep The Mapping",
             "Leave the picture covering the same ground as the one it "
             "replaces, rescaled for the new texture's size. A face that had no "
             "texture has no mapping to keep, so project those instead"),
            ("PROJECT", "Project Flat",
             "Plant the texture on the world along whichever axis each face "
             "most faces. This is what new geometry needs: a face extruded out "
             "of the track inherits UVs that are well-formed and mean nothing"),
        ],
        default="KEEP",
    )

    texture_scale: FloatProperty(
        name="Units Per Repeat",
        description=(
            "How much ground one repeat of the texture covers when projecting. "
            "Retail's median is 268 map units, measured over 257,035 textured "
            "triangle edges"
        ),
        default=256.0,
        min=1.0,
        soft_max=2048.0,
    )

    # -- the track's own artwork -----------------------------------------
    #
    # Position in this collection is the texture's identity: the runtime hands
    # out ids by position within a track's manifest, and the level model refers
    # to them by the same position. Reordering it repaints the track, which is
    # why nothing here offers to sort or move an entry.

    custom_textures: CollectionProperty(type=DKR_CustomTexture)

    custom_format: EnumProperty(
        name="Format",
        description=(
            "How the image is stored. The choice sets the largest size it can "
            "be: the RDP has 4KB of texture memory and a level texture is "
            "loaded into it as one block"
        ),
        items=texture_format_items,
    )

    custom_size: StringProperty(
        name="Size",
        description=(
            "Width and height to resample to, as WxH. Both have to be powers "
            "of two no larger than 64 - material_init clamps anything else "
            "instead of tiling it. Blank picks the largest the format allows"
        ),
        default="",
    )

    has_validated: BoolProperty(default=False)
    results: CollectionProperty(type=DKR_ValidationEntry)


CLASSES = (
    DKR_CustomTexture,
    DKR_ValidationEntry,
    DKR_SceneSettings,
)


def register_pointers():
    bpy.types.Scene.dkr = PointerProperty(type=DKR_SceneSettings)


def unregister_pointers():
    if hasattr(bpy.types.Scene, "dkr"):
        del bpy.types.Scene.dkr

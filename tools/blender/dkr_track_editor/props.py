"""Scene-level settings for the track editor."""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, PointerProperty,
    StringProperty,
)

from . import catalog as catalog_module


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


class DKR_ValidationEntry(bpy.types.PropertyGroup):
    severity: StringProperty(default="info")
    message: StringProperty(default="")
    object_id: StringProperty(default="")


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

    show_padding: BoolProperty(
        name="Show Padding Fields",
        description=(
            "Show the pad and unknown bytes. They exist so an entry encodes to "
            "the bytes the game expects and are rarely worth editing"
        ),
        default=False,
    )

    has_validated: BoolProperty(default=False)
    results: CollectionProperty(type=DKR_ValidationEntry)


CLASSES = (
    DKR_ValidationEntry,
    DKR_SceneSettings,
)


def register_pointers():
    bpy.types.Scene.dkr = PointerProperty(type=DKR_SceneSettings)


def unregister_pointers():
    if hasattr(bpy.types.Scene, "dkr"):
        del bpy.types.Scene.dkr

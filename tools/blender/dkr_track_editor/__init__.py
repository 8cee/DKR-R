"""DKR track editor - a Blender addon for authoring Diddy Kong Racing tracks.

Places objects, items and the AI racing line over a track's geometry and writes
the object map back out, plus the ``.dkrmap`` package DKR-R loads from
``custom-tracks/``.
See docs/BLENDER_ADDON_PLAN.md for the design and what is still Phase 2.

Importing this package must not require Blender: the format, catalogue,
AI-graph, validation and packaging modules are all plain Python so they can be
tested outside it. Only :func:`register` reaches for ``bpy``.
"""

from __future__ import annotations

bl_info = {
    "name": "DKR Track Editor",
    "author": "DKR-R",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > DKR",
    "description": "Author Diddy Kong Racing tracks and export .dkrmap packages",
    "category": "Import-Export",
    "doc_url": "https://github.com/ThatGuyMcd/DKR-R/blob/main/docs/BLENDER_ADDON_PLAN.md",
}

#: Populated by :func:`register`; kept so :func:`unregister` can undo exactly
#: what was registered even if a later module failed to import.
_REGISTERED = []


def _module_classes():
    """Every class to register, in dependency order.

    Imported here rather than at module scope so that ``import
    dkr_track_editor`` works without Blender, which is what lets the tests run
    on a plain Python.
    """
    from . import prefs, props
    from .operators import ai, checks, edit, geometry, io_objects, pack
    from .ui import panels

    classes = []
    classes += list(prefs.CLASSES)
    classes += list(props.CLASSES)
    classes += list(io_objects.CLASSES)
    classes += list(geometry.CLASSES)
    classes += list(edit.CLASSES)
    classes += list(ai.CLASSES)
    classes += list(checks.CLASSES)
    classes += list(pack.CLASSES)
    classes += list(panels.CLASSES)
    return classes


def _menu_import(self, context):
    self.layout.operator("dkr.import_level", text="DKR Track (retail)")
    self.layout.operator(
        "dkr.import_object_map", text="DKR Object Map (.gltf)"
    )
    self.layout.operator(
        "dkr.import_geometry", text="DKR Track Geometry (.bin)"
    )


def _menu_export(self, context):
    self.layout.operator(
        "dkr.export_object_map", text="DKR Object Map (.gltf)"
    )


def register():
    import bpy

    from . import props

    for cls in _module_classes():
        bpy.utils.register_class(cls)
        _REGISTERED.append(cls)

    props.register_pointers()
    bpy.types.TOPBAR_MT_file_import.append(_menu_import)
    bpy.types.TOPBAR_MT_file_export.append(_menu_export)


def unregister():
    import bpy

    from . import props

    bpy.types.TOPBAR_MT_file_export.remove(_menu_export)
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import)
    props.unregister_pointers()

    while _REGISTERED:
        cls = _REGISTERED.pop()
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

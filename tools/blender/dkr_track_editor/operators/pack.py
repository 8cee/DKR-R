"""Write the scene out as a ``.dkrmap`` track package."""

from __future__ import annotations

import json
import os
import traceback

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from .. import catalog as catalog_module, dkrmap, prefs, scene, validate


class DKR_OT_export_dkrmap(bpy.types.Operator, ExportHelper):
    """Write a .dkrmap track directory for DKR-R's custom-tracks folder"""

    bl_idname = "dkr.export_dkrmap"
    bl_label = "Export .dkrmap"
    bl_options = {"REGISTER"}

    filename_ext = ""
    use_filter_folder = True
    filter_glob: StringProperty(default="", options={"HIDDEN"})

    validate_first: BoolProperty(
        name="Validate First",
        description="Refuse to write the package if validation finds an error",
        default=True,
    )

    def execute(self, context):
        settings = context.scene.dkr
        try:
            catalog = catalog_module.load()
            object_map = scene.export_object_map(context, catalog)
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            self.report({"ERROR"}, "could not build the object map: %s" % error)
            return {"CANCELLED"}

        if not object_map.objects:
            self.report({"ERROR"}, "nothing to export; no DKR objects in the scene")
            return {"CANCELLED"}

        if self.validate_first:
            report = validate.validate(
                object_map, catalog, require_racing_track=settings.is_racing_track
            )
            if report.errors:
                self.report(
                    {"ERROR"},
                    "%d validation error(s); fix them or turn off Validate First. "
                    "First: %s" % (len(report.errors), report.errors[0].message),
                )
                return {"CANCELLED"}

        directory = self.filepath
        if not directory.endswith(dkrmap.SUFFIX):
            directory = directory.rstrip("/\\") + dkrmap.SUFFIX

        # The id keys a track for arming and for sibling resolution, so two
        # tracks sharing one collide. Take the author's if they set one, then
        # the folder being exported to - the most direct statement of intent at
        # this moment - and only then the track name, which an import sets and
        # which therefore persists across exports without the author noticing.
        folder = os.path.splitext(os.path.basename(directory))[0]
        track_id = (
            settings.track_id
            or dkrmap.normalise_id(folder)
            or dkrmap.normalise_id(settings.track_name)
        )

        try:
            tree = prefs.resolve(context)
            package = dkrmap.TrackPackage(
                directory=directory,
                track_id=track_id,
                name=settings.track_name or track_id,
                author=settings.track_author,
                revision=tree.label if tree else "",
            )
            package.notes.append(
                "%d objects, roughly %d bytes encoded"
                % (len(object_map.objects),
                   validate.estimate_size(object_map, catalog))
            )
            # A level has two object maps and the runtime patches a different
            # header field from each, so they are written separately - a single
            # merged payload would spawn the whole track through the
            # collectables slot while the retail structure map kept spawning
            # beside it.
            table = tree.translation_table() if tree else []
            # Both slots are always written, even when one is empty. A header
            # leaves 0x36 and 0xBA at zero for the runtime to patch, and zero is
            # a valid index rather than "no map" - the game clamps out-of-range
            # ids to 0 and loads object map 0. So a header shipped without a
            # payload for a slot points that slot at another level's objects and
            # hangs. An empty map is the honest way to say "nothing here", and
            # it is what retail does: 16 of its object maps have fileSize 0.
            written = []
            for slot in scene.SLOTS:
                part = scene.export_object_map(context, catalog, slot=slot)
                package.write_object_map(part, "objects_" + slot)
                if not table:
                    continue
                payload = package.encode_object_map(
                    slot, part, catalog, table, tree.asset_index
                )
                written.append("%s %d objects, %d bytes"
                               % (slot, len(part.objects), len(payload)))

            if table:
                package.notes += written
            else:
                package.notes.append(
                    "object maps not compiled: no decomp assets configured, so "
                    "the level-object translation table was unavailable"
                )

            # The header comes from the track being remixed, so the geometry,
            # world and race type stay whatever the base track had.
            base = _base_header(context, tree)
            if base is not None:
                header = package.encode_header(
                    base, catalog.raw.get("enumValues", {}),
                    tree.asset_index if tree else None,
                )
                package.notes.append("header.bin %d bytes" % len(header))

            _attach_existing_payloads(package)
            package.write()
        except dkrmap.DkrMapError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        except OSError as error:
            self.report({"ERROR"}, "could not write %s: %s" % (directory, error))
            return {"CANCELLED"}

        if not package.manifest()["adds"]:
            self.report(
                {"ERROR"},
                "nothing was compiled, so the package would contain no payloads "
                "at all. Set the decomp asset path in the addon preferences and "
                "export again",
            )
            return {"CANCELLED"}

        missing = package.missing_sections()
        if missing:
            self.report(
                {"WARNING"},
                "wrote %s with %d objects compiled. Still missing %s, which the "
                "addon does not write yet - see HOW-TO-BUILD.md"
                % (os.path.basename(directory), len(object_map.objects),
                   ", ".join(missing)),
            )
        else:
            self.report(
                {"INFO"},
                "wrote %s: %d objects, ready to install in custom-tracks/"
                % (os.path.basename(directory), len(object_map.objects)),
            )
        return {"FINISHED"}


def _base_header(context, tree):
    """The extracted header of the track this scene was loaded from.

    A Phase 1 remix reworks objects over shipped geometry, so its header is the
    base track's - only the name and whatever the author edits change. Without
    a base there is nothing to derive one from, and the addon says so rather
    than inventing 200 bytes.
    """
    if tree is None:
        return None
    source = context.scene.dkr.source_path or context.scene.dkr.geometry_path
    level = tree.level_using(source) if source else None
    if level is None or not level.header_path:
        return None
    try:
        with open(level.header_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return None


def _attach_existing_payloads(package):
    """Pick up any payload already sitting in the track directory.

    Re-exporting must not throw away a payload the addon did not write. An
    author who drops in a ``header.bin`` - which the addon cannot produce yet -
    has to still have it after the next export, or the instruction to do so is a
    trap.
    """
    for section, filename in dkrmap.SECTIONS.items():
        candidate = os.path.join(package.directory, filename)
        if os.path.isfile(candidate):
            package.add_payload(section, candidate)
    for slot, filename in dkrmap.OBJECT_MAP_SLOTS.items():
        candidate = os.path.join(package.directory, filename)
        if slot not in package.object_maps and os.path.isfile(candidate):
            package.object_maps[slot] = candidate


CLASSES = (DKR_OT_export_dkrmap,)

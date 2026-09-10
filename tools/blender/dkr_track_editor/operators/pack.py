"""Write the scene out as a ``.dkrmap`` track package."""

from __future__ import annotations

import json
import os
import traceback

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from .. import catalog as catalog_module, dkrmap, prefs, scene, validate
from . import geometry_export


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
            if base is None:
                base = _authored_header(context)
            if base is not None:
                header = package.encode_header(
                    base, catalog.raw.get("enumValues", {}),
                    tree.asset_index if tree else None,
                )
                package.notes.append("header.bin %d bytes" % len(header))

            # Before the geometry, because the model's texture table names
            # these by position and a failure to compile one has to stop the
            # export rather than ship a model pointing at a payload that is
            # not there.
            _encode_textures(self, context, package)
            _encode_geometry(self, context, package)
            _warn_header_without_geometry(self, context, package)

            stale = _attach_existing_payloads(package)
            if stale:
                # The addon writes the object maps itself, so one it did not
                # write this time is one the scene has already moved past.
                # Shipping it is still safer than dropping it - a header whose
                # slot has no payload points at another level's objects and
                # hangs - but it must not pass for success.
                message = (
                    "the object maps could not be compiled this time, so the "
                    "package ships %s from an earlier export. The objects now "
                    "in the scene reached source/ only. Set the decomp asset "
                    "path in the addon preferences and export again"
                    % ", ".join(sorted(stale))
                )
                package.notes.append(message)
                self.report({"WARNING"}, message)
            package.write()
        except geometry_export.GeometryExportError as error:
            self.report(
                {"ERROR"},
                "the track geometry cannot be exported: %s" % error,
            )
            return {"CANCELLED"}
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
                "wrote %s with %d object(s). Still missing %s, which the "
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


def _encode_textures(operator, context, package):
    """Compile the artwork the track ships itself into the package.

    Every texture the scene holds is written, not only the ones the geometry
    draws. An unused one costs a few kilobytes and keeps the numbering the
    author sees in the panel identical to the numbering the runtime hands out -
    and dropping the unused ones would renumber the used ones, which is the one
    thing that silently repaints a track.
    """
    from .. import textures as texture_module  # noqa: PLC0415
    from . import custom_textures, geometry as geometry_ops  # noqa: PLC0415

    own = custom_textures.entries(context)

    # A table entry naming a texture the package will not carry is the one
    # failure here that the game cannot survive: the id falls outside the
    # extended table and load_texture reads whatever is past the end of it.
    # It happens if the scene is opened without the images, so it is checked
    # against what is about to be written rather than assumed away.
    dangling = set()
    for obj in geometry_ops.geometry_objects(context):
        for record in geometry_ops.extra_textures(obj):
            ordinal = texture_module.custom_ordinal(record.get("id", 0))
            if ordinal is not None and ordinal >= len(own):
                dangling.add(ordinal + 1)
    if dangling:
        raise dkrmap.DkrMapError(
            "the geometry draws with texture %s of this track's own, but the "
            "scene holds %d. Add the missing image, or point those faces at "
            "something else"
            % (", ".join(str(number) for number in sorted(dangling)), len(own))
        )

    if not own:
        return

    missing = [entry.name for entry in own
               if not entry.png or not os.path.isfile(entry.png)]
    if missing:
        raise dkrmap.DkrMapError(
            "the resampled image for %s is gone from %s. The .blend records "
            "where it was, not the picture itself, so add it again"
            % (", ".join(missing), custom_textures.folder(context))
        )

    payloads = package.encode_textures(own)
    package.notes.append(
        "%d texture(s) of this track's own, %d bytes: %s"
        % (len(payloads), sum(len(payload) for payload in payloads),
           ", ".join("%s %dx%d" % (entry.name, entry.width, entry.height)
                     for entry in own))
    )


def _encode_geometry(operator, context, package):
    """Compile the edited track geometry into the package, if it changed.

    A track that only reworks the objects standing on shipped geometry ships no
    model payload at all: the header's geometry field then keeps pointing at the
    base track's model, and the package stays small and stays correct. Writing
    an unchanged copy would work and would make every remix carry a hundred
    kilobytes that say nothing.
    """
    edit = geometry_export.build_edited_model(context)
    if edit is None:
        _report_unusable_meshes(operator, context)
        return

    for note in edit.notes:
        operator.report({"WARNING"}, note)

    if edit.ships:
        payload = package.encode_level_model(edit.model)
        package.notes.append(
            "model.bin %d bytes: %s" % (len(payload), edit.describe())
        )
        return

    package.notes.append(
        "geometry unchanged, so no model payload; the header keeps pointing at %s"
        % os.path.basename(edit.path)
    )
    # A model.bin from an earlier export is kept, like any payload sitting in
    # the directory - but an author who has since undone their edits would
    # otherwise have no way of knowing the old geometry is still shipping.
    stale = os.path.join(package.directory, dkrmap.SECTIONS["LEVEL_MODELS"])
    if os.path.isfile(stale):
        operator.report(
            {"WARNING"},
            "the geometry in the scene matches the base track, but %s already "
            "holds a model.bin from an earlier export and it is kept. Delete it "
            "if the track should ship the shipped geometry"
            % os.path.basename(package.directory),
        )


def _report_unusable_meshes(operator, context):
    """Say why a mesh the author modelled themselves produced no geometry.

    The addon can only write geometry it decoded from a level model, because a
    vertex has to name the segment of the track it belongs to and a mesh built
    in Blender names nothing. Modelling a track from scratch needs a segmenter,
    which does not exist yet - but an author finding that out from an empty
    package and no message is the wrong way to learn it.
    """
    from . import geometry as geometry_ops

    meshes = geometry_ops.unusable_meshes(context)
    if not meshes:
        return
    names = ", ".join(sorted(o.name for o in meshes)[:4])
    if len(meshes) > 4:
        names += " and %d more" % (len(meshes) - 4)
    operator.report(
        {"WARNING"},
        "%d mesh(es) in the scene were not exported as track geometry (%s). The "
        "addon can only write geometry it imported from a level model: every "
        "vertex has to name the segment of the track it belongs to, and a mesh "
        "modelled in Blender names none. Import a track's geometry and reshape "
        "that, or wait for the segmenter" % (len(meshes), names),
    )


def _warn_header_without_geometry(operator, context, package):
    """A header authored from nothing has nothing to point at yet.

    A remix leaves ``/model`` alone because the header it inherited already
    names the base track's geometry. A track built from scratch has neither: the
    template leaves ``/model`` unset on purpose, since the runtime patches
    ``0x34`` from the ``LEVEL_MODELS`` payload - and with no payload nothing
    patches it. The package is well formed and the manifest is honest, so
    nothing here refuses; but "ready to install" would be a lie about a track
    with no ground in it.
    """
    if "LEVEL_HEADERS" not in package.payloads:
        return
    if "LEVEL_MODELS" in package.payloads:
        return
    from . import geometry as geometry_ops

    # A remix inherits a header that still names the base track's geometry, so
    # shipping no model is correct there. The test cannot be "was anything
    # imported" - a track built from a mesh sets the geometry path too, and
    # pointed at its own file, which is exactly the case that must not stay
    # quiet.
    if any(geometry_ops.PROP_AUTHORED_BASE not in o
           for o in geometry_ops.geometry_objects(context)):
        return
    if not geometry_ops.geometry_objects(context) and (
            context.scene.dkr.source_path or context.scene.dkr.geometry_path):
        return
    operator.report(
        {"WARNING"},
        "this package has a header but no geometry, so there is nothing for it "
        "to point at and the track will not load. The header leaves the "
        "geometry field for the runtime to patch from a LEVEL_MODELS payload, "
        "and there is none. Building track geometry from a Blender mesh is not "
        "supported yet - import a track's geometry and reshape it instead",
    )


def _authored_header(context):
    """A header built from the template, for a track with no ancestor.

    Returns ``None`` when the author has answered nothing, which leaves the
    package exactly as it was before this existed - no header, and the warning
    that says so. A partial answer is refused rather than filled in, because
    the two fields with no default are world and race type, and zero is a real
    world and a real race type: a track that never answered would not fail, it
    would quietly become a Central Area default race.
    """
    from . import header as header_ops
    from .. import level_header_template as template

    overrides = header_ops.overrides(context)
    if not overrides:
        return None

    outstanding = template.missing(overrides)
    if outstanding:
        raise dkrmap.DkrMapError(
            "the level header has %d unanswered field(s) - %s - and they have "
            "no default because retail has no dominant value for them. Zero is "
            "a real setting rather than an absence, so a track shipped without "
            "them becomes something other than what you built. Fill them in "
            "under Level Header"
            % (len(outstanding), ", ".join(outstanding))
        )
    return template.document(overrides)


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

    The object maps are the one case where falling back is not neutral, so this
    returns the ones it had to fall back on. The addon compiles those itself
    whenever it can, and the only reason it cannot is that the decomp assets
    are unreachable and the level-object translation table with them. A file
    left from an earlier export then no longer matches the scene, and an export
    that quietly ships it has claimed to save work it did not save.
    """
    for section, filename in dkrmap.SECTIONS.items():
        candidate = os.path.join(package.directory, filename)
        if os.path.isfile(candidate):
            package.add_payload(section, candidate)

    stale = []
    for slot, filename in dkrmap.OBJECT_MAP_SLOTS.items():
        candidate = os.path.join(package.directory, filename)
        if slot not in package.object_maps and os.path.isfile(candidate):
            package.object_maps[slot] = candidate
            stale.append(filename)
    return stale


CLASSES = (DKR_OT_export_dkrmap,)

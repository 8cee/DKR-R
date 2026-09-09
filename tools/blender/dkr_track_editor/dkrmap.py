"""Write the ``.dkrmap`` container DKR-R loads custom tracks from.

The layout and the rules are in docs/CUSTOM_TRACKS.md. A track is a directory
named ``*.dkrmap`` holding a manifest and one binary payload per asset-table
section, and DKR-R serves those bytes without ever parsing a level format.

**What this module produces.** The ``LEVEL_OBJECT_MAPS`` payload is written
here, by :mod:`object_map_encoder`, without the decomp's ``dkr_assets_tool`` -
that tool builds a whole ``assets.bin`` and ships as a Linux binary, so
depending on it would have put a C++ toolchain between an author and their
track. The encoder is checked against the retail bytes: it reproduces all 136
shipped object maps exactly.

``LEVEL_HEADERS`` is not written yet, so a package still needs one supplied.
The glTF sources go in beside the payloads either way, both as the input the
asset tool would take and as something an author can read.

A manifest never claims a payload that is not there: bytes promised and missing
fail at load time with a far more confusing error than the one reported here.

Deliberately free of ``bpy``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from typing import Dict, List, Optional

from . import gltf_io, level_header, level_model_encoder, object_map_encoder
from .gltf_io import ObjectMap

MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1
SUFFIX = ".dkrmap"

#: Sections a track can add, and the payload file each conventionally uses.
SECTIONS = {
    "LEVEL_HEADERS": "header.bin",
    "LEVEL_NAMES": "name.bin",
    "LEVEL_MODELS": "model.bin",
}

#: A level has **two** object maps, and the runtime needs to know which is
#: which: it patches header 0xBA from the ``structure`` slot and 0x36 from
#: ``collectables``. A ``LEVEL_OBJECT_MAPS`` entry without a slot is refused
#: rather than guessed, so the two are named here.
OBJECT_MAP_SECTION = "LEVEL_OBJECT_MAPS"
OBJECT_MAP_SLOTS = {
    "structure": "objects_structure.bin",
    "collectables": "objects_collectables.bin",
}

#: Where the addon leaves asset-tool input inside the track directory.
SOURCE_DIR = "source"

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class DkrMapError(Exception):
    pass


def normalise_id(text: str) -> str:
    """Turn a track title into the lowercase hyphenated id the manifest wants."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "untitled-track"


def validate_id(track_id: str) -> None:
    if not _ID_RE.match(track_id):
        raise DkrMapError(
            "track id %r must be lowercase words joined by single hyphens"
            % track_id
        )


class TrackPackage:
    """One ``.dkrmap`` directory being assembled."""

    def __init__(self, directory: str, track_id: str, name: str, author: str = "",
                 revision: str = ""):
        validate_id(track_id)
        self.directory = directory
        self.track_id = track_id
        self.name = name or track_id
        self.author = author
        #: Which extracted revision the payloads were built from, e.g.
        #: ``us.v80``. The encoding and the asset indices are portable between
        #: revisions, but a header's *content* is not: seven of its unknown
        #: fields differ in all 65 retail levels. Recording it lets the runtime
        #: warn when a track is loaded against a different ROM.
        self.revision = revision
        #: section -> absolute path of a compiled payload the author supplied.
        self.payloads: Dict[str, str] = {}
        #: slot -> absolute path, for the two object maps.
        self.object_maps: Dict[str, str] = {}
        self.notes: List[str] = []

    # -- sources ---------------------------------------------------------

    def write_object_map(self, object_map: ObjectMap, stem: str = "objects") -> str:
        """Write one map's glTF pair into ``source/``, named for its slot."""
        source = os.path.join(self.directory, SOURCE_DIR)
        os.makedirs(source, exist_ok=True)
        gltf_name = stem + ".gltf"
        gltf_path = os.path.join(source, gltf_name)
        gltf_io.save(object_map, gltf_path)
        gltf_io.save_sidecar(os.path.join(source, stem + ".json"), gltf_name)
        return gltf_path

    def encode_object_map(self, slot: str, object_map: ObjectMap, catalog,
                          translation_table, asset_index=None) -> bytes:
        """Compile one of the two object maps and attach it under its slot.

        This is what makes a package loadable rather than merely well formed.
        The bytes are the same ones the asset tool would produce; see
        ``tests/test_encoder.py``, which requires exactly that for every retail
        map.
        """
        if slot not in OBJECT_MAP_SLOTS:
            raise DkrMapError(
                "%r is not an object-map slot; expected %s"
                % (slot, " or ".join(sorted(OBJECT_MAP_SLOTS)))
            )
        payload = object_map_encoder.pack(
            object_map, catalog, translation_table, asset_index
        )
        os.makedirs(self.directory, exist_ok=True)
        path = os.path.join(self.directory, OBJECT_MAP_SLOTS[slot])
        with open(path, "wb") as handle:
            handle.write(payload)
        self.object_maps[slot] = path
        return payload

    def encode_header(self, document: Dict, enum_values,
                      asset_index=None) -> bytes:
        """Compile the level header and attach it.

        ``document`` is an extracted level header, normally the base track's:
        a Phase 1 remix keeps its geometry, world and race type and changes only
        what the author edits. The two runtime-owned offsets are left at zero.
        """
        payload = level_header.encode(document, enum_values, asset_index)
        os.makedirs(self.directory, exist_ok=True)
        path = os.path.join(self.directory, SECTIONS["LEVEL_HEADERS"])
        with open(path, "wb") as handle:
            handle.write(payload)
        self.payloads["LEVEL_HEADERS"] = path
        return payload

    def encode_level_model(self, model) -> bytes:
        """Compile edited track geometry and attach it as ``LEVEL_MODELS``.

        Only worth calling when the author actually changed the geometry. A
        track that reworks objects over shipped geometry should ship no model
        payload at all: the header's ``geometry`` field then keeps pointing at
        the base track's model, and the package stays small and stays correct.
        Writing an unchanged copy would work, but it makes every remix carry a
        hundred kilobytes that say nothing.

        The bytes are what the game loads, not what the asset tool takes as
        input - see :mod:`level_model_encoder`, held to byte equality against
        every extracted retail model.
        """
        try:
            payload = level_model_encoder.pack(model)
        except level_model_encoder.LevelModelEncodeError as error:
            raise DkrMapError("could not compile the track geometry: %s" % error)
        os.makedirs(self.directory, exist_ok=True)
        path = os.path.join(self.directory, SECTIONS["LEVEL_MODELS"])
        with open(path, "wb") as handle:
            handle.write(payload)
        self.payloads["LEVEL_MODELS"] = path
        return payload

    def add_payload(self, section: str, path: str) -> None:
        """Attach a compiled section payload produced by the asset tool."""
        if section not in SECTIONS:
            raise DkrMapError(
                "%r is not an asset-table section; expected one of %s"
                % (section, ", ".join(sorted(SECTIONS)))
            )
        if not os.path.isfile(path):
            raise DkrMapError("payload for %s not found: %s" % (section, path))
        self.payloads[section] = path

    # -- output ----------------------------------------------------------

    def manifest(self) -> Dict[str, object]:
        """The manifest, listing only payloads that actually exist."""
        adds = [
            {"section": section, "file": SECTIONS[section]}
            for section in SECTIONS
            if section in self.payloads
        ]
        # Every object-map entry carries its slot; the runtime refuses one
        # without, rather than guessing which header field to patch.
        adds += [
            {
                "section": OBJECT_MAP_SECTION,
                "slot": slot,
                "file": OBJECT_MAP_SLOTS[slot],
            }
            for slot in OBJECT_MAP_SLOTS
            if slot in self.object_maps
        ]
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "id": self.track_id,
            "name": self.name,
            "adds": adds,
        }
        if self.author:
            manifest["author"] = self.author
        if self.revision:
            manifest["builtFrom"] = self.revision
        return manifest

    def missing_sections(self) -> List[str]:
        """What a playable track still needs.

        Neither object-map slot is optional once a header ships. The header
        leaves 0x36 and 0xBA at zero for the runtime, and zero is a valid index,
        not an absence - the game clamps anything out of range to 0 and loads
        object map 0. A slot with no payload therefore points at another level's
        objects. An empty map is how a track says it has none.
        """
        missing = [s for s in ("LEVEL_HEADERS",) if s not in self.payloads]
        if "LEVEL_HEADERS" not in missing:
            missing += [
                "LEVEL_OBJECT_MAPS (%s)" % slot
                for slot in OBJECT_MAP_SLOTS
                if slot not in self.object_maps
            ]
        elif "structure" not in self.object_maps:
            missing.append("LEVEL_OBJECT_MAPS (structure)")
        return missing

    def write(self) -> str:
        """Create the directory, copy payloads in and write the manifest."""
        os.makedirs(self.directory, exist_ok=True)
        for section, source_path in self.payloads.items():
            destination = os.path.join(self.directory, SECTIONS[section])
            if os.path.abspath(source_path) != os.path.abspath(destination):
                shutil.copyfile(source_path, destination)

        manifest_path = os.path.join(self.directory, MANIFEST_NAME)
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(self.manifest(), indent=2, sort_keys=True) + "\n")

        self._write_build_notes()
        return manifest_path

    def _write_build_notes(self) -> None:
        """Leave the author instructions for the step the addon cannot do."""
        missing = self.missing_sections()
        path = os.path.join(self.directory, "HOW-TO-BUILD.md")
        lines = [
            "# %s" % self.name,
            "",
            "Written by the DKR track editor Blender addon.",
            "",
            "`%s/` holds the authored object map as the glTF pair that the" % SOURCE_DIR,
            "decomp's `dkr_assets_tool` consumes. The addon stops there: that tool",
            "builds a whole `assets.bin` from the decomp's asset tree rather than",
            "emitting one section at a time, so producing the `.bin` payloads is a",
            "separate step.",
            "",
        ]
        if self.object_maps:
            lines += [
                "## Object maps",
                "",
                "A level has **two**, and the runtime patches a different header",
                "field from each: `0xBA` from `structure`, `0x36` from",
                "`collectables`. Both are compiled here by the addon, and are the",
                "same bytes the asset tool would produce - the encoder is checked",
                "against all 136 retail maps in",
                "`tools/blender/tests/test_encoder.py`.",
                "",
            ] + [
                "- `%s` (%s slot)" % (os.path.basename(path), slot)
                for slot, path in sorted(self.object_maps.items())
            ] + [""]
        if missing:
            lines += [
                "## Still needed",
                "",
                "This track will not load yet. Missing payloads: %s."
                % ", ".join(missing),
                "",
                "`LEVEL_HEADERS` has to come from the level header the track is",
                "based on, rebuilt with its own name and geometry. The addon does",
                "not write one yet.",
                "",
                "Drop the missing `.bin` into this directory and export again; the",
                "manifest picks up whatever is present.",
                "",
            ]
        else:
            lines += [
                "## Ready",
                "",
                "Every payload the manifest needs is present.",
                "",
            ]
        lines += [
            "## Do not commit this package",
            "",
            "A remix keeps whatever the base track had, so the payloads here",
            "contain retail object-map data verbatim wherever you did not change",
            "it. `docs/ASSET_POLICY.md` forbids committing extracted maps, and",
            "notes that deleting a file later does not remove it from history.",
            "",
            "Share the `.blend` and this addon instead; anyone with the decomp",
            "can rebuild the package. Only a track built from synthetic data,",
            "with nothing carried over, is safe to publish.",
            "",
            "## Installing",
            "",
            "Copy this directory into DKR-R's `custom-tracks/`, or use the Track",
            "Lab's Import Track button. Not `mods/`: librecomp owns that for its",
            "own `.nrm` format and rejects anything else it finds there.",
            "",
            "Payloads you drop in here are kept: re-exporting from Blender",
            "rewrites the object maps and leaves everything else alone.",
            "",
            "See `docs/CUSTOM_TRACKS.md` in DKR-R for the manifest contract and",
            "`docs/LEVEL_OBJECT_MAP_FORMAT.md` for the binary format.",
            "",
        ]
        if self.notes:
            lines += ["## Notes", ""] + ["- %s" % n for n in self.notes] + [""]
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines))


def package_path(directory: str, track_id: str) -> str:
    """``custom-tracks/`` path for a track: the id with the ``.dkrmap`` suffix."""
    return os.path.join(directory, track_id + SUFFIX)


def read_manifest(package_directory: str) -> Optional[Dict[str, object]]:
    path = os.path.join(package_directory, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)

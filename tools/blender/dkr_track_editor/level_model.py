"""Decoder for DKR level geometry.

docs/LEVEL_MODEL_FORMAT.md describes this format for the benefit of a future
*encoder*, which is what Phase 2 of the addon plan is blocked on. Reading it is a
separate and much smaller problem, and worth solving now: without the track in
front of them, an author is placing zippers and checkpoints against an empty
viewport with nothing to aim at.

So this module decodes a level model into plain vertex, triangle and batch
lists. The addon builds a read-only reference mesh out of that, which gives
placement something to sit on and makes Blender's own face snapping work. None
of it is written back - the geometry an author sees is exactly the geometry the
game already ships.

Every offset here was verified against Ancient Lake
(``levels/models/dino_domain/ancient_lake.bin``), whose decoded values match the
figures in the format document: 25 textures, 24 segments, 7 animated textures,
bounds X -5918..-23, Y -56..885, Z -12559..-2048.

Deliberately free of ``bpy``.
"""

from __future__ import annotations

import os
import struct
import zlib
from typing import List, Optional, Tuple

#: Container: decompressed size as u32 little endian, then this tag byte, then a
#: raw DEFLATE stream with no zlib or gzip wrapper.
CONTAINER_TAG = 0x09
CONTAINER_HEADER = 5

#: Everything past the container is N64 data, so big endian.
ENDIAN = ">"

SEGMENT_SIZE = 0x44
BATCH_SIZE = 12
TRIANGLE_SIZE = 16
VERTEX_SIZE = 10

#: ``textures_sprites.h``. The bits are independent: an invisible wall is
#: HIDDEN set with NO_COLLISION clear.
RENDER_HIDDEN = 1 << 8
RENDER_NO_COLLISION = 1 << 9

#: ``TriangleBatchInfo.textureIndex``.
NO_TEXTURE = 0xFF

#: ``Triangle.flags``.
TRIANGLE_DRAW_BACKFACE = 0x40

#: ``DkrTextureInfo``: an id indexing the global 3D texture list, then the size
#: and format. Shared with object models, which use the same table.
TEXTURE_INFO_SIZE = 8

#: A triangle's UVs are fixed point with five fractional bits, in texels rather
#: than normalised, so a normalised coordinate is ``raw / 32 / texture_size``.
#: Track surfaces tile heavily, so values far outside 0..1 are normal.
UV_FRACTIONAL_BITS = 32.0


class TextureRef:
    """One entry of a model's texture table."""

    __slots__ = ("texture_id", "width", "height", "format", "surface_type")

    def __init__(self, texture_id, width, height, texture_format, surface_type):
        #: Index into ``ASSET_TEXTURES_3D``, which is what names the PNG.
        self.texture_id = texture_id
        self.width = width or 1
        self.height = height or 1
        self.format = texture_format
        #: ``SurfaceType`` for level geometry - what the ground behaves like.
        self.surface_type = surface_type

    def __repr__(self):
        return "TextureRef(%d, %dx%d)" % (self.texture_id, self.width, self.height)


def parse_texture_table(blob, offset, count):
    """Decode ``count`` :class:`TextureRef` entries starting at ``offset``."""
    textures = []
    for index in range(max(0, count)):
        at = offset + index * TEXTURE_INFO_SIZE
        if at + TEXTURE_INFO_SIZE > len(blob):
            break
        texture_id, = struct.unpack_from(ENDIAN + "i", blob, at)
        textures.append(TextureRef(
            texture_id, blob[at + 4], blob[at + 5], blob[at + 6], blob[at + 7]
        ))
    return textures


def normalise_uv(raw_uv, texture):
    """Fixed-point texel UVs to Blender's normalised, V-flipped convention."""
    if texture is None:
        return None
    return tuple(
        (
            s / UV_FRACTIONAL_BITS / texture.width,
            1.0 - (t / UV_FRACTIONAL_BITS / texture.height),
        )
        for s, t in raw_uv
    )


class LevelModelError(Exception):
    pass


class Batch:
    """One draw call: a window of vertices and triangles sharing a texture."""

    __slots__ = ("texture_index", "vertex_offset", "face_offset", "flags",
                 "vertex_count", "face_count", "vertex_override", "misc", "texture_offset")

    def __init__(self, texture_index, vertex_offset, face_offset, flags,
                 vertex_override=0, misc=0, texture_offset=0):
        self.texture_index = texture_index
        self.vertex_offset = vertex_offset
        self.face_offset = face_offset
        self.flags = flags
        self.vertex_override = vertex_override
        self.misc = misc
        self.texture_offset = texture_offset
        self.vertex_count = 0
        self.face_count = 0

    @property
    def hidden(self) -> bool:
        return bool(self.flags & RENDER_HIDDEN)

    @property
    def collidable(self) -> bool:
        return not (self.flags & RENDER_NO_COLLISION)

    @property
    def invisible_wall(self) -> bool:
        """Not drawn, but still solid - the reason the two bits are separate."""
        return self.hidden and self.collidable

    @property
    def textured(self) -> bool:
        return self.texture_index != NO_TEXTURE


class Segment:
    """One spatial partition of the track."""

    __slots__ = ("index", "vertices", "colours", "triangles", "uvs", "batches",
                 "opaque_batches")

    def __init__(self, index):
        self.index = index
        #: ``[(x, y, z), ...]`` in map space, still Y-up.
        self.vertices: List[Tuple[int, int, int]] = []
        #: ``[(r, g, b, a), ...]``, the baked lighting.
        self.colours: List[Tuple[int, int, int, int]] = []
        #: ``[(flags, vi0, vi1, vi2), ...]`` with batch-local indices.
        self.triangles: List[Tuple[int, int, int, int]] = []
        #: ``[((s0, t0), (s1, t1), (s2, t2)), ...]``, raw fixed point per triangle.
        self.uvs: List[Tuple[Tuple[int, int], ...]] = []
        self.batches: List[Batch] = []
        self.opaque_batches = 0


class LevelModel:
    def __init__(self):
        self.segments: List[Segment] = []
        self.textures: List[TextureRef] = []
        self.animated_texture_count = 0
        self.bounds = (0, 0, 0, 0, 0, 0)
        self.minimap_sprite_index = 0

    @property
    def texture_count(self) -> int:
        return len(self.textures)

    def texture_for(self, batch: Batch) -> Optional[TextureRef]:
        index = batch.texture_index
        if index == NO_TEXTURE or not (0 <= index < len(self.textures)):
            return None
        return self.textures[index]

    @property
    def vertex_count(self) -> int:
        return sum(len(s.vertices) for s in self.segments)

    @property
    def triangle_count(self) -> int:
        return sum(len(s.triangles) for s in self.segments)

    @property
    def batch_count(self) -> int:
        return sum(len(s.batches) for s in self.segments)

    def faces(self, include_hidden=False):
        """Yield ``(triangle_indices, colour_indices, batch)`` in world terms.

        Triangle vertex indices are batch-local, so they are resolved against
        the batch's vertex window here and come out as segment-local indices.
        The caller still offsets those by where the segment landed in a merged
        mesh.
        """
        for segment in self.segments:
            for batch in segment.batches:
                if batch.hidden and not include_hidden:
                    continue
                base = batch.vertex_offset
                for face in range(batch.face_offset,
                                  batch.face_offset + batch.face_count):
                    if face >= len(segment.triangles):
                        break
                    _flags, vi0, vi1, vi2 = segment.triangles[face]
                    yield segment, (base + vi0, base + vi1, base + vi2), batch


def decompress(data: bytes) -> bytes:
    """Unwrap the five byte container and inflate the DEFLATE stream."""
    if len(data) < CONTAINER_HEADER:
        raise LevelModelError("file is too short to be a level model")
    size, tag = struct.unpack_from("<IB", data, 0)
    if tag != CONTAINER_TAG:
        raise LevelModelError(
            "container tag is 0x%02X, expected 0x%02X; this is not a compressed "
            "level model" % (tag, CONTAINER_TAG)
        )
    try:
        blob = zlib.decompress(data[CONTAINER_HEADER:], -15)
    except zlib.error as error:
        raise LevelModelError("DEFLATE stream is corrupt: %s" % error)
    if len(blob) != size:
        raise LevelModelError(
            "inflated to %d bytes but the header declares %d" % (len(blob), size)
        )
    return blob


def parse(blob: bytes) -> LevelModel:
    """Decode an already decompressed ``LevelModel``."""
    if len(blob) < 0x48:
        raise LevelModelError("blob is too short to hold a LevelModel header")

    model = LevelModel()
    textures_ptr, segments_ptr = struct.unpack_from(ENDIAN + "II", blob, 0x00)
    texture_count, segment_count = struct.unpack_from(ENDIAN + "hh", blob, 0x18)
    animated, = struct.unpack_from(ENDIAN + "h", blob, 0x1E)
    minimap, = struct.unpack_from(ENDIAN + "i", blob, 0x20)
    model.textures = parse_texture_table(blob, textures_ptr, texture_count)
    model.animated_texture_count = animated
    model.minimap_sprite_index = minimap
    model.bounds = struct.unpack_from(ENDIAN + "6h", blob, 0x3C)

    if segment_count < 0 or segment_count > 4096:
        raise LevelModelError("implausible segment count %d" % segment_count)

    for index in range(segment_count):
        base = segments_ptr + index * SEGMENT_SIZE
        if base + SEGMENT_SIZE > len(blob):
            raise LevelModelError("segment %d runs past the blob" % index)
        model.segments.append(_parse_segment(blob, base, index))
    return model


def _parse_segment(blob: bytes, base: int, index: int) -> Segment:
    vertices_ptr, triangles_ptr = struct.unpack_from(ENDIAN + "II", blob, base + 0x00)
    batches_ptr, = struct.unpack_from(ENDIAN + "I", blob, base + 0x0C)
    vertex_count, triangle_count, batch_count = struct.unpack_from(
        ENDIAN + "hhh", blob, base + 0x1C
    )
    segment = Segment(index)
    segment.opaque_batches = blob[base + 0x40]

    for i in range(max(0, vertex_count)):
        offset = vertices_ptr + i * VERTEX_SIZE
        if offset + VERTEX_SIZE > len(blob):
            break
        x, y, z = struct.unpack_from(ENDIAN + "3h", blob, offset)
        segment.vertices.append((x, y, z))
        segment.colours.append(tuple(blob[offset + 6:offset + 10]))

    for i in range(max(0, triangle_count)):
        offset = triangles_ptr + i * TRIANGLE_SIZE
        if offset + TRIANGLE_SIZE > len(blob):
            break
        segment.triangles.append(tuple(blob[offset:offset + 4]))
        raw = struct.unpack_from(ENDIAN + "6h", blob, offset + 4)
        segment.uvs.append(((raw[0], raw[1]), (raw[2], raw[3]), (raw[4], raw[5])))

    # The batch array carries a terminator holding the end offsets, so each
    # batch's span is the difference to the next entry. That is the same
    # size-by-difference convention the asset tables use.
    raw = []
    for i in range(max(0, batch_count) + 1):
        offset = batches_ptr + i * BATCH_SIZE
        if offset + BATCH_SIZE > len(blob):
            break
        texture_index = blob[offset]
        vertex_override, = struct.unpack_from(ENDIAN + "b", blob, offset + 1)
        vertex_offset, face_offset = struct.unpack_from(ENDIAN + "hh", blob, offset + 2)
        misc, texture_offset = blob[offset + 6], blob[offset + 7]
        flags, = struct.unpack_from(ENDIAN + "I", blob, offset + 8)
        raw.append(Batch(texture_index, vertex_offset, face_offset, flags,
                         vertex_override, misc, texture_offset))

    for i in range(len(raw) - 1):
        batch = raw[i]
        batch.vertex_count = raw[i + 1].vertex_offset - batch.vertex_offset
        batch.face_count = raw[i + 1].face_offset - batch.face_offset
        segment.batches.append(batch)
    return segment


def load(path: str) -> LevelModel:
    """Read a ``*.bin`` level model off disk."""
    with open(path, "rb") as handle:
        data = handle.read()
    return parse(decompress(data))


#: A level model's sidecar names the binary under ``raw``, as
#: ``{"raw": "ancient_lake.bin", "type": "LevelModel"}``.
SIDECAR_TYPE = "LevelModel"


def sidecar_target(path: str) -> Optional[str]:
    """Resolve a level model's ``.json`` sidecar to the ``.bin`` beside it."""
    import json

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("type") != SIDECAR_TYPE:
        raise LevelModelError("%s is not a %s sidecar" % (path, SIDECAR_TYPE))
    name = data.get("raw")
    return os.path.join(os.path.dirname(path), name) if name else None

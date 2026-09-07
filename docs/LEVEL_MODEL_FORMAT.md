# DKR level model format

Reference notes for anyone writing a track geometry encoder. Every field below
was read out of a retail asset and cross-checked against the matching decomp's
structures; the layout arithmetic is self-consistent and is shown so it can be
re-verified.

Worked example throughout: Ancient Lake (`levels/models/dino_domain/`).

## Compressed container

Level assets are stored compressed. The container is five bytes followed by a
raw DEFLATE stream:

```text
bytes 0..3   decompressed size, u32 LITTLE endian
byte  4      0x09
bytes 5..    raw DEFLATE (no zlib or gzip wrapper)
```

Verified across every level model in the US v1.0 asset set: the declared size
matched the inflated size in all cases. Ancient Lake is 24,912 bytes
compressed and 49,644 inflated.

## LevelModel header

Pointer fields are byte offsets into the decompressed blob; the game fixes them
up after loading.

```text
0x00 textures            0x18 numberOfTextures        s16
0x04 segments            0x1A numberOfSegments        s16
0x08 boundingBoxes       0x1E numberOfAnimatedTextures s16
0x0C unkC                0x20 minimapSpriteIndex      s32
0x10 segmentsBitfields   0x28 minimapXScale/YScale    f32
0x14 segmentsBspTree     0x3C lowerXBounds .. bounds  s16
```

Ancient Lake: 25 textures, **24 segments**, 7 animated textures, bounds
X -5918..-23, Y -56..885, Z -12559..-2048.

The per-segment arrays confirm their own element sizes:

```text
boundingBoxes 0x9B60..0x9C80 = 288 bytes / 24 = 12  -> LevelModelSegmentBoundingBox
bspTree       0x9C80..0x9D40 = 192 bytes / 24 =  8  -> BspTreeNode
```

## Segments and the BSP tree

A `LevelModelSegment` is 0x44 bytes and points at its own vertex, triangle and
batch arrays. Bounding boxes tile the world, and the BSP splits exactly on
those boundaries:

```text
seg0 X -5918..-4764     seg1 X -4764..-2623
bsp node0: axis=X split=-2623 left=1 right=12    (leaf nodes use left=right=-1)
```

## Batches, triangles, vertices

```text
DkrBatch     12 bytes   textureIndex (0xFF = none), verticesOffset,
                        trianglesOffset, lightSource, flags u32
DkrTriangle  16 bytes   flags (0x40 = draw backface), vi0..vi2, 3 x uv (s16,s16)
DkrVertex    10 bytes   x, y, z (s16) + r, g, b, a
```

Two rules an encoder must respect:

- **The batch list carries a terminator.** The entry after the last real batch
  holds the end offsets, so each batch's span is `batch[i+1] - batch[i]`. The
  same size-by-difference convention governs the asset tables.
- **Triangle vertex indices are batch-local, not segment-local.** Triangle 3 of
  Ancient Lake's segment 0 indexes `(0,1,2)` inside a batch whose window starts
  at vertex 5. Because the index is a `u8`, a batch can address at most 256
  vertices.

Vertex colour is the baked lighting; level geometry carries no normals.

Each `DkrTriangle` also carries three UV pairs, `s16` fixed point with five
fractional bits and measured in **texels**, so a normalised coordinate is
`raw / 32 / texture_size`. Track surfaces tile heavily, so values well outside
0..1 are normal. `DkrBatch.textureIndex` selects from the model's own texture
table, an array of 8-byte `DkrTextureInfo` whose `id` indexes the global
`ASSET_TEXTURES_3D` list - the same indirection object models use.

Decoding all of that is what lets the Blender addon show a track as it looks
rather than as a grey shell; see `tools/blender/dkr_track_editor/level_model.py`.

## Collision is generated, not authored

`collisionFacets` and `collisionPlanes` are **NULL in the asset**. The game
allocates and derives both at load time from the triangles:

```c
if (model->collisionFacets != NULL) return;
for (i = 0; i < model->numberOfBatches; i++) {
    facesOffset     = model->batches[i].facesOffset;
    nextFacesOffset = model->batches[i + 1].facesOffset;
    if (model->batches[i].flags & RENDER_NO_COLLISION) continue;
    s4 += nextFacesOffset - facesOffset;
}
model->collisionPlanes = mempool_alloc(s4 * (sizeof(f32) * 16), COLOUR_TAG_RED);
```

Sixteen floats per facet is four planes of `(A, B, C, D)`: the triangle's own
plane plus three edge bisectors. A batch opts out with
`RENDER_NO_COLLISION = 1 << 9` (`textures_sprites.h`), which shares bit 9 with
coverage because level geometry ignores coverage.

**An encoder therefore never computes collision.** It only decides which
batches are solid.

## What an encoder actually has to do

| Task | Notes |
|---|---|
| Container | DEFLATE plus the five byte header |
| Header and texture table | direct field writes |
| Segment the mesh spatially | the author's choice of partition |
| Build the BSP over segments | standard axis/split-value tree |
| Batch triangles | group by texture and flags, at most 256 vertices each |
| Collision | nothing to do; runtime derives it |

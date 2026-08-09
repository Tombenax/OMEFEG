import random
import numpy as np
from perlineNoise import PerlinNoiseFactory
from Chunk import Chunk


def _stable_seed(offsett):
    return random.Random((offsett[0] * 1000003) ^ (offsett[1] * 10007) ^ (offsett[2] * 1009))


def build_chunk_mesh(offsett, rules, tex_mapping, cube_v, cube_i):
    seed = _stable_seed(offsett)
    heightmap = PerlinNoiseFactory(dimension=2, octaves=1, seed=seed)
    chunk = Chunk(offsett, heightmap, rules, seed=seed)
    result = chunk.get_blocks()

    new_textures = []
    new_positions = []
    for block in result:
        new_textures.append(tex_mapping[block.texture])
        new_positions.append(block.position)

    mesh_vertices, mesh_indices = _export_chunk_mesh(
        np.asarray(new_positions, dtype=np.float32),
        np.asarray(new_textures, dtype=np.int32),
        cube_v,
        cube_i,
    )

    return offsett, result, mesh_vertices, mesh_indices


def _export_chunk_mesh(models, layers, cube_v, cube_i):
    if len(models) == 0:
        return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')

    if models.ndim == 1:
        models = models.reshape(1, 3)

    ATLAS_SIZE = 320
    BLOCK_SIZE = 64
    ATLAS_BLOCKS = ATLAS_SIZE // BLOCK_SIZE

    base_vertices = cube_v.reshape(-1, 8).astype(np.float32)
    base_indices = cube_i.astype(np.int32)

    translated = np.repeat(base_vertices[None, :, :], len(models), axis=0)
    translated[:, :, 0] += models[:, 0][:, None]
    translated[:, :, 1] += models[:, 1][:, None]
    translated[:, :, 2] += models[:, 2][:, None]

    uvs = translated[:, :, 6:8].copy()
    atlas_u = uvs[:, :, 0]
    atlas_v = uvs[:, :, 1]

    bx = layers % ATLAS_BLOCKS
    by = ATLAS_BLOCKS - 1 - (layers // ATLAS_BLOCKS)

    atlas_u = atlas_u / ATLAS_BLOCKS + (bx[:, None] / ATLAS_BLOCKS)
    atlas_v = atlas_v / ATLAS_BLOCKS + (by[:, None] / ATLAS_BLOCKS)

    translated[:, :, 6] = atlas_u
    translated[:, :, 7] = atlas_v

    merged_vertices = translated.reshape(-1, 8)

    vertex_offsets = np.arange(len(models), dtype=np.int32) * len(base_vertices)
    merged_indices = np.repeat(base_indices[None, :], len(models), axis=0) + vertex_offsets[:, None]
    merged_indices = merged_indices.reshape(-1)

    return merged_vertices.astype('f4'), merged_indices.astype('i4')

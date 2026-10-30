from numpy import asarray, empty
import numpy as np

from Chunk import Chunk
from Block import Block
import collections
import os
import random as _random
import struct as _struct
import sys
import time
from queue import Queue

from perlineNoise import PerlinNoiseFactory

# True on PC, False on Android phones. Override with OMEFEG_DESKTOP=0/1.
DESKTOP = os.environ.get("OMEFEG_DESKTOP")
if DESKTOP is None:
    DESKTOP = not hasattr(sys, "getandroidapilevel")
else:
    DESKTOP = DESKTOP == "1"

if DESKTOP:
    from Render import CUBE_MODEL_INFO
else:
    from MobileRender import CUBE_MODEL_INFO
from allBlocks import *
from lists import *
from Number import Number
from utils import (export_and_load_chunk, square_range, camera_frustum,
                     chunk_visible_from, get_block, get_texture)
if DESKTOP:
    from Render import *
else:
    from MobileRender import *

import threading

MIN_WORLD_Y = -64


import math

def circle_points(center, radius, size=1, gap=1, plane="XZ"):
    """Dashed ring of tangentially-rotated blocks (like the sketch).

    Blocks sit evenly spaced along the circumference with ``gap`` air
    between neighbours (center-to-center spacing = ``size + gap``),
    each rotated so one face points at the center and the next runs
    along the curve -- the pinwheel look from the drawing. Verified
    against the render pipeline: the inward face normal dot radial ==
    1.0 at every angle, on all three planes.

    plane: "XZ" (flat ring on the ground, spins around Y),
           "XY" (upright ring facing +-Z, spins around Z),
           "YZ" (upright ring facing +-X, spins around X).

    Returns [[x, y, z, angle_x, angle_y, angle_z], ...].
    """
    cx, cy, cz = center
    plane = plane.upper()
    if plane not in ("XZ", "XY", "YZ"):
        raise ValueError(f"plane must be XZ, XY or YZ, got {plane!r}")

    if radius <= 0:
        return [[cx, cy, cz, 0.0, 0.0, 0.0]]

    circumference = 2 * math.pi * radius
    count = max(3, int(round(circumference / (size + gap))))

    points = []
    for k in range(count):
        print(f"{k}/{count}")
        theta = 2 * math.pi * k / count
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        if plane == "XZ":
            x = cx + radius * cos_t
            y_pos = cy
            z = cz + radius * sin_t
            angles = [0.0, math.degrees(theta), 0.0]
        elif plane == "XY":
            x = cx + radius * cos_t
            y_pos = cy + radius * sin_t
            z = cz
            angles = [0.0, 0.0, -math.degrees(theta)]
        else:  # YZ
            x = cx
            y_pos = cy + radius * cos_t
            z = cz + radius * sin_t
            angles = [-math.degrees(theta), 0.0, 0.0]

        points.append([x, y_pos, z, angles[0], angles[1], angles[2]])

    return points


def sphere_points(center, radius, size=1, gap=0.8, x=None, y=None, z=None, chunk_size=10, rotation=False):
    """Closed voxel sphere shell on the block grid.

    Every integer voxel whose cube (``[g-0.5, g+0.5]`` per axis --
    blocks are centered cubes, see Render) is crossed by the mathematical
    sphere surface is emitted, so the shell has no holes by
    construction. Voxel ``g`` is kept exactly when::

        dist(center, cube) <= radius <= dist(center, farthest corner)

    ``size``/``gap`` are kept for backward compatibility but no longer
    affect the output (a dashed lattice cannot cover the grid without
    holes, which is why they were dropped).

    Pass a chunk origin ``x``, ``y``, ``z`` to emit only the voxels of
    the sphere inside that cube: ``x <= gx < x + chunk_size``,
    ``y <= gy < y + chunk_size`` and ``z <= gz < z + chunk_size``
    (voxels are assigned by grid coords, so neighbouring chunks
    partition the sphere with no doubles/misses). Omit them for the
    whole sphere. Candidates are enumerated per y-slab (and clipped to
    the chunk box), so chunk queries cost ~chunk volume, not ~sphere
    volume.

    ``rotation``: pass True to include the radial facing angles
    (local +Y face points along the voxel-center radial normal).
    Default False emits ``0.0, 0.0, 0.0`` for every block.

    Returns [[gx, gy, gz, angle_x, angle_y, angle_z], ...] with
    integer voxel coords and float angles.
    """
    cx, cy, cz = center
    r = abs(float(radius))
    r2 = r * r

    # Voxel bounding box (superset of the shell), clipped to the chunk
    # box when one is requested. +-1 slop is harmless: membership is
    # re-checked exactly below.
    bx0 = int(math.floor(cx - r - 1.0))
    bx1 = int(math.ceil(cx + r + 1.0)) + 1
    by0 = int(math.floor(cy - r - 1.0))
    by1 = int(math.ceil(cy + r + 1.0)) + 1
    bz0 = int(math.floor(cz - r - 1.0))
    bz1 = int(math.ceil(cz + r + 1.0)) + 1
    if x is None:
        qx0, qx1 = bx0, bx1
    else:
        qx0 = max(bx0, int(math.floor(x)) - 1)
        qx1 = min(bx1, int(math.ceil(x + chunk_size)) + 1)
    if y is None:
        qy0, qy1 = by0, by1
    else:
        qy0 = max(by0, int(y) - chunk_size)
        qy1 = min(by1, int(y) + chunk_size + 1)
    if z is None:
        qz0, qz1 = bz0, bz1
    else:
        qz0 = max(bz0, int(math.floor(z)) - 1)
        qz1 = min(bz1, int(math.ceil(z + chunk_size)) + 1)
    if qx0 >= qx1 or qy0 >= qy1 or qz0 >= qz1:
        return []

    xs = np.arange(qx0, qx1, dtype=np.float64)
    ys = np.arange(qy0, qy1, dtype=np.float64)
    zs = np.arange(qz0, qz1, dtype=np.float64)

    # Per-axis |voxel - center| and the min/max per-axis distances from
    # the center to the voxel cube: min is 0 inside the slab, else the
    # gap past the cube face; max is always the far side (+0.5).
    ax = np.abs(xs - cx)
    ay = np.abs(ys - cy)
    az = np.abs(zs - cz)
    pnx = np.maximum(ax - 0.5, 0.0)
    pny = np.maximum(ay - 0.5, 0.0)
    pnz = np.maximum(az - 0.5, 0.0)
    pxx = ax + 0.5
    pyy = ay + 0.5
    pzz = az + 0.5

    # Walk y in slabs to bound transient memory (~17 bytes/voxel:
    # two float64 distance fields + one bool mask).
    slab = max(1, 500000 // max(1, int(xs.size * zs.size)))

    out_gx, out_gy, out_gz, out_nx, out_ny, out_nz = [], [], [], [], [], []
    for s in range(0, int(ys.size), slab):
        e = min(int(ys.size), s + slab)
        # (m, nx, nz) fields via broadcasting; no copies of the 1D terms.
        dmin2 = (pnx[None, :, None] ** 2
                 + pny[s:e, None, None] ** 2
                 + pnz[None, None, :] ** 2)
        dmax2 = (pxx[None, :, None] ** 2
                 + pyy[s:e, None, None] ** 2
                 + pzz[None, None, :] ** 2)
        keep = (dmin2 <= r2) & (dmax2 >= r2)
        if not bool(np.any(keep)):
            continue
        iy, ix, iz = np.where(keep)
        gx = qx0 + ix
        gy = qy0 + s + iy
        gz = qz0 + iz
        dx = xs[ix] - cx
        dy = ys[s + iy] - cy
        dz = zs[iz] - cz
        dc = np.sqrt(dx * dx + dy * dy + dz * dz)
        inv = np.zeros_like(dc)
        nz_mask = dc > 0.0
        inv[nz_mask] = 1.0 / dc[nz_mask]
        # Voxel centered exactly on `center` (only possible for tiny
        # radii): fall back to straight up.
        nxk = dx * inv
        nyk = dy * inv
        nzk = dz * inv
        nyk[~nz_mask] = 1.0
        out_gx.append(gx)
        out_gy.append(gy)
        out_gz.append(gz)
        out_nx.append(nxk)
        out_ny.append(nyk)
        out_nz.append(nzk)

    if not out_gx:
        return []
    gx = np.concatenate(out_gx).astype(np.int64)
    gy = np.concatenate(out_gy).astype(np.int64)
    gz = np.concatenate(out_gz).astype(np.int64)
    nx = np.concatenate(out_nx)
    ny = np.concatenate(out_ny)
    nz = np.concatenate(out_nz)

    # Exact voxel-chunk membership.
    if x is not None or y is not None or z is not None:
        keep = np.ones(gx.shape, dtype=bool)
        if x is not None:
            keep &= (gx >= x) & (gx < x + chunk_size)
        if y is not None:
            keep &= (gy >= y - chunk_size) & (gy <= y + chunk_size)
        if z is not None:
            keep &= (gz >= z) & (gz < z + chunk_size)
        if not bool(np.any(keep)):
            return []
        gx = gx[keep]
        gy = gy[keep]
        gz = gz[keep]
        nx = nx[keep]
        ny = ny[keep]
        nz = nz[keep]

    n_out = int(gx.shape[0])
    if n_out == 0:
        return []
    if rotation:
        # Euler order in the renderer is M = Rx @ Ry @ Rz applied to row
        # vectors (translation lives in row 3 of the instance matrix), so
        # local +Y maps to (sin(ax)*sin(ay), cos(ax), -sin(ax)*cos(ay)).
        # Inverting for the voxel normal (nx, ny, nz): ax = acos(ny),
        # ay = -atan2(-nx, -nz). Verified against the repo's own pyrr:
        # face-normal dot radial == 1.0 for every voxel, poles included
        # (tilt 0/180 makes yaw irrelevant there, so the old pole
        # special-cases are dropped; the old bottom branch emitted
        # (0, 0), leaving tip voxels unflipped).
        angle_x = -np.degrees(np.arccos(np.clip(-ny, -1.0, 1.0))) + 180.0
        angle_y = -np.degrees(np.arctan2(-nx, -nz))
    else:
        angle_x = np.zeros(n_out, dtype=np.float64)
        angle_y = np.zeros(n_out, dtype=np.float64)

    angle_z = np.zeros(n_out, dtype=np.float64)
    stacked = np.column_stack((gx, gy, gz, angle_x, angle_y, angle_z)).tolist()
    # Positions are integral floats here: convert back to int so blocks
    # land on true grid coords (struct saves, int-keyed lookups, ...).
    return [[int(r[0]), int(r[1]), int(r[2]), 0.0, 0.0, 0.0] for r in stacked]



class World:
    def __init__(self, render, radius, origin, render_radious=100):
        self.render = render
        self.blocks = BlocksList()
        self.seed = _random.randint(0, 18_446_744_073_709_551_616)
        self.heightmap = PerlinNoiseFactory(self.seed, 1)
        self.update_queue = Queue()
        self.last_update_time = time.time()
        self.UPDATE_INTERVAL = 0.2
        self.blocksInstancedModel = InstancedModel(render=render, vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1])
        self.generated_chunks = set()
        self.origin = origin
        self.radius = radius
        self._am_i_generating_chunk = False
        self.sphere = None
        
        self.render_radious = render_radious

        self._last_xyz = None
    
    def get_neighbours(self, block_pos):
        x, y, z = block_pos
        neighbours = {}
        for dx, dy, dz in [(-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)]:
            neighbour_pos = (x + dx, y + dy, z + dz)
            neighbour_block = self.blocks.positions_blocks.get(neighbour_pos)
            neighbours[neighbour_pos] = neighbour_block
        return neighbours
    
    def place_block(self, block: Block, rotation=[0, 0, 0]):
        self.blocks.add(block)
        self.update_queue.put(block.update(self.get_neighbours(block.position)))
        # No per-call upload: render_blocks() uploads once per frame when
        # the visible set actually changed (same for the methods below).
        self.blocksInstancedModel.add_instances([block.position], [block.texture], [rotation])

    def place_blocks(self, pos, tex, rotations=[[0, 0, 0]]):
        for pos_, tex_ in zip(pos, tex):
            block = get_texture(tex_, *pos_)
            self.blocks.add(block)
            self.update_queue.put(block.update(self.get_neighbours(block.position)))
        
        self.blocksInstancedModel.add_instances(pos, tex, rotations)

    def place_blocks_blocks(self, blocks, rotations=[[0, 0, 0]], return_updates=False):
        self.blocks.extend(blocks)

        pos, tex, up = [], [], []

        for block in blocks:
            if not return_updates:
                self.update_queue.put(block.update(self.get_neighbours(block.position)))
            else:
                up.append(block.update(self.get_neighbours(block.position)))

            pos.append(block.position)
            tex.append(block.texture)
        
        self.blocksInstancedModel.add_instances(pos, tex, rotations)

        if return_updates: return up

    def update(self):
        curr_time = time.time()
        if curr_time - self.last_update_time >= self.UPDATE_INTERVAL:
            self.last_update_time = curr_time

            updates = []

            while not self.update_queue.qsize() == 0:
                new_block:Block = self.update_queue.get()

                if new_block is not None:
                    updates.extend(self.place_blocks_blocks(new_block, return_updates=True))

            for update in updates: self.update_queue.put(update)

    
    def destroy_block(self, block: Block):
        self.blocks.remove(block)
        self.blocksInstancedModel.remove_instances([block.position])


    def _generate_chunk_thread(self, x, y, z):
        sphere = sphere_points(self.origin, self.radius, x=x, y=y, z=z, gap=1, rotation=True)
        self.sphere = sphere
        
        self.generated_chunks.add((x, y, z))

    def generate_chunk(self, x, y, z):
        if (x, y, z) in self.generated_chunks: return

        if not self._am_i_generating_chunk:
            self._am_i_generating_chunk = True

            self.generating_thread = threading.Thread(target=self._generate_chunk_thread, args=(x, y, z), daemon=True)
            self.generating_thread.start()

        else:

            if not self.generating_thread.is_alive():

                if self.sphere:
                    result = [
                        [row[i:i+3] for row in self.sphere]
                        for i in range(0, len(self.sphere[0]), 3)
                    ]

                    positions = result[0]
                    textures = [GRASS] * len(result[0])
                    rotations = result[1]

                    self.place_blocks(positions, textures, rotations)

                    self.sphere = None
            
                self._am_i_generating_chunk = False
    
    def get_block_y_at(self, x, z):
        return 1

    def render_blocks(self):
        model:InstancedModel = self.blocksInstancedModel
        if len(model.instances) == 0:
            return


        cam = getattr(self.render, "CAMERA", None)
        if cam is None:
            cam = getattr(self.render, "camera", None)
        if cam is None:
            model.render()
            return

        try:
            cam_pos = cam.position
        except Exception:
            model.render()
            return


        if True:#self._last_xyz is None or abs(np.sum(cam_pos[[0, 2]] - self._last_xyz[[0, 2]])) >= 10:

            self._last_xyz = cam_pos.copy()

            # Get X/Z position from every 4x4 matrix
            points = model.instances[:, 3, [0, 2]]

            # Camera X/Z
            cam_xz = np.asarray(cam_pos)[[0, 2]]

            # Squared distance from camera
            dist_sq = np.sum((points - cam_xz) ** 2, axis=1)

            # Boolean mask
            inside = dist_sq <= self.render_radious ** 2

            # Get the actual matrices
            model.active_instances = model.instances[inside]

            model.active_tex_insta = model.tex_insta[inside]

            model._upload()

        model.render()

    
    def get_block_at(self, position):
        return self.blocks.positions_blocks.get(tuple(position), None)
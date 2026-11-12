import numpy as np

from Chunk import Chunk
import os
import random as _random
import sys
import time
from queue import Empty, Queue

from utils import get_block, get_texture

import json

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
from Vec3 import Vec3
from collections.abc import Sequence
if DESKTOP:
    from Render import *
else:
    from MobileRender import *

import threading

MIN_WORLD_Y = -64
_ADJACENT_NEIGHBOUR_OFFSETS = (
    (-1, 0, 0), (1, 0, 0), (0, -1, 0),
    (0, 1, 0), (0, 0, -1), (0, 0, 1),
)
_PLAYER_NEIGHBOUR_OFFSETS = tuple(
    (dx, dy, dz)
    for dy in (-1, 0, 1)
    for dx in (-1, 0, 1)
    for dz in (-1, 0, 1)
)


import math

def circle_points(center:Vec3 | Sequence[Number], radius, size=1, gap=1, plane="XZ"):
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

    Returns ``[(position: Vec3, rotation: Vec3), ...]``.
    """
    cx, cy, cz = center
    plane = plane.upper()
    if plane not in ("XZ", "XY", "YZ"):
        raise ValueError(f"plane must be XZ, XY or YZ, got {plane!r}")

    if radius <= 0:
        return [(Vec3(cx, cy, cz), Vec3(0.0, 0.0, 0.0))]

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

        points.append((Vec3(x, y_pos, z), Vec3(*angles)))

    return points


def sphere_points(center:Vec3 | Sequence[Number], radius, size=1, gap=0.8, x=None, y=None, z=None, chunk_size=10, rotation=False):
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

    Returns ``[(position: Vec3, rotation: Vec3), ...]`` with integer
    voxel coordinates and float angles.
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
        qy0 = max(by0, int(y))
        qy1 = min(by1, int(y) + chunk_size)
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
            keep &= (gy >= y) & (gy < y + chunk_size)
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
    return [
        (Vec3(int(px), int(py), int(pz)), Vec3(float(ax), float(ay), float(az)))
        for px, py, pz, ax, ay, az in zip(gx, gy, gz, angle_x, angle_y, angle_z)
    ]


def all_sphere_points(center:Vec3 | Sequence[Number], radius, size=1, gap=0.8, rotation=False):
    """Return all voxels in a sphere shell, without chunk filtering."""
    return sphere_points(center, radius, size=size, gap=gap, rotation=rotation)

BENCH_MODEL = load_obj("assets/models/bench.obj")

class World:
    def __init__(self, render, radius, origin:Vec3 | Sequence[Number], render_radious=100):
        self.render = render
        self.blocks = BlocksList()
        self.seed = _random.randint(0, 18_446_744_073_709_551_616)
        self.heightmap = PerlinNoiseFactory(self.seed, 1)
        self.update_queue = Queue()
        self.last_update_time = time.time()
        self.UPDATE_INTERVAL = 0.2
        self.model = Model(renderer=render)
        self.model.add_model(vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1], identifier="block")
        self.model.add_model(vertices=BENCH_MODEL[0], indices=BENCH_MODEL[1], identifier="bench")
        self.generated_chunks = set()
        self.origin = origin.copy() if isinstance(origin, Vec3) else Vec3(*origin)
        self.radius = radius
        self.diameter = radius * 2
        self._am_i_generating_chunk = False
        self.sphere = None
        self.lock = threading.Lock()
        self.thig_dict_to_return = {"result":None}

        self.generate_chunk_queue = Queue()
        
        self.render_radious = render_radious

        self.generate_all_chunks = False

        self.can_generate_any_chunks = True

        self.last_xyz = None

        self._last_idx = None

        self._STRUCTURES = {}

        self.th = None

        if self.generate_all_chunks:
            self.generate_entire_world()


    
    def get_neighbours(self, block_pos:Vec3 | Sequence[Number], player:bool=False):
        if isinstance(block_pos, Vec3):
            x, y, z = block_pos.xyz
        else:
            x, y, z = block_pos
        positions_blocks = self.blocks.positions_blocks
        offsets = _PLAYER_NEIGHBOUR_OFFSETS if player else _ADJACENT_NEIGHBOUR_OFFSETS
        neighbours = {}
        for dx, dy, dz in offsets:
            neighbour_pos = (x + dx, y + dy, z + dz)
            neighbours[neighbour_pos] = positions_blocks.get(neighbour_pos)
        return neighbours

    @staticmethod
    def _block_key(position):
        return tuple(int(round(float(value))) for value in position)

    def place_block(self, block: Block, rotation=[0, 0, 0]):
        self.blocks.add(block)
        self.update_queue.put(block.update(self.get_neighbours(block.position)))
        self.model.add_instances(
            [block.position], [block.texture], block.model, [tuple(rotation)]
        )

    def place_blocks(self, pos, tex, rotations=[[0, 0, 0]]):
        rotations = list(rotations)
        things = {}
        for index, (pos_, tex_) in enumerate(zip(pos, tex)):
            block = get_block(tex_, pos_)
            self.blocks.add(block)
            self.update_queue.put(block.update(self.get_neighbours(block.position)))
            rotation = tuple(rotations[index] if index < len(rotations) else (0, 0, 0))
            model = block.model

            if things.get(model) is None: things[model] = [[], [], []]

            things[model][0].append(block.position)
            things[model][1].append(block.texture)
            things[model][2].append(rotation)

        """
        output = {}

        for model, position in zip(models, pos):
            if model not in output:
                output[model] = []

            output[model].append(position)
        
        """

        if things:
            for model, (pos, tex, rot) in things.items():
                self.model.add_instances(
                    pos, tex, model, rot
                )

    def place_blocks_blocks(self, blocks, rotations=[[0, 0, 0]], return_updates=False, model="block"):
        blocks = list(blocks)
        rotations = list(rotations)
        self.blocks.extend(blocks)

        pos, tex, up = [], [], []
        block_positions, block_textures, block_rotations = [], [], []

        for index, block in enumerate(blocks):
            if not return_updates:
                self.update_queue.put(block.update(self.get_neighbours(block.position)))
            else:
                up.append(block.update(self.get_neighbours(block.position)))

            pos.append(block.position)
            tex.append(block.texture)
            rotation = tuple(rotations[index] if index < len(rotations) else (0, 0, 0))
            block_positions.append(block.position)
            block_textures.append(block.texture)
            block_rotations.append(rotation)

        if block_positions:
            self.model.add_instances(
                block_positions, block_textures, model, block_rotations
            )
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

    
    def destroy_block(self, block: Block, model="block"):
        if block.proprieties["breakable"]:
            self.blocks.remove(block)
            self.model.remove_instances([block.position], model_identifier=model)

    def load_structure(self, name:str):

        if a := self._STRUCTURES.get(name):
            return a

        else:

            with open("worldgeneration/structures/"+name) as f:
                structure = json.load(f)

            self._STRUCTURES[name] = structure["blocks"]

        return structure["blocks"]




    def _generate_chunk_thread(self, x, y, z):

        self.generated_chunks.add((x, y, z))

        sphere = sphere_points(self.origin, self.radius, x=x, y=y, z=z, gap=1, rotation=False)

        positions = []
        rotations = []
        textures = []

        rem = Vec3(0, 1, 0)

        if sphere:
            """
            for pos, rot in sphere:

                positions.append(pos)
                rotations.append(rot)
                textures.append(GRASS)

                for i in range(1):
                    positions.append(pos - rem * (i+1))
                    rotations.append(rot)
                    textures.append(STONE)
            
            """

            arr = np.array(sphere)

            positions.extend(arr[:, 0])
            rotations.extend(arr[:, 1])
            textures = [GRASS] * len(arr)

            stone_arr = [STONE] * len(arr)

            positions.extend(arr[:, 0] - rem)
            rotations.extend(arr[:, 1] - rem)
            textures.extend(stone_arr)


            positions.extend(arr[:, 0] - rem*2)
            rotations.extend(arr[:, 1] - rem*2)
            textures.extend([UNBREKABLE] * len(arr))
            
            blocks = self.load_structure("oak_medium_tree.json")

            blocks_arr = np.asarray(blocks)

            positions.extend(blocks_arr[:, [0, 1, 2]].astype(np.int64)+[x+5, y+1, z+5])
            rotations.extend([[0, 0, 0]] * len(blocks_arr))
            textures.extend(blocks_arr[:, 3])

            gen_temple = random.random()

            if gen_temple >= 0.99:

                blocks = self.load_structure("temple.json")

                blocks_arr = np.asarray(blocks)

                positions.extend(blocks_arr[:, [0, 1, 2]].astype(np.int64)+[x+10, y+1, z+10])
                rotations.extend([[0, 0, 0]] * len(blocks_arr))
                textures.extend(blocks_arr[:, 3])

                blocks = self.load_structure("benchStructure.json")

                blocks_arr = np.asarray(blocks)

                positions.extend(blocks_arr[:, [0, 1, 2]].astype(np.int64)+[x+14, y+1, z+10])
                rotations.extend([[0, 0, 0]] * len(blocks_arr))
                textures.extend(blocks_arr[:, 3])

        self.generate_chunk_queue.put((positions, rotations, textures))

    def generate_entire_world(self):

        self.can_generate_any_chunks = False

        sphere = all_sphere_points(self.origin, self.radius, gap=1, rotation=True)
        self.sphere = sphere

        print("Gnratd al of the sphere")

        if self.sphere:
            positions = [position for position, _rotation in self.sphere]
            textures = [GRASS] * len(positions)
            rotations = [rotation for _position, rotation in self.sphere]

            self.place_blocks(positions, textures, rotations)

            self.sphere = None

    def place_chunks(self):
        try:
            sphere = self.generate_chunk_queue.get_nowait()
        except Empty:
            return

        positions = sphere[0]
        rotations = sphere[1]
        textures = sphere[2]

        self.place_blocks(positions, textures, rotations)

    def generate_chunk(self, x, y, z):
        if (x, y, z) in self.generated_chunks and self.can_generate_any_chunks: return

        self.generating_thread = threading.Thread(target=self._generate_chunk_thread, args=(x, y, z), daemon=True)
        self.generating_thread.start()

    
    def get_block_y_at(self, x, z):
        return 1

    def place_chunks_step(self, thig_dict_to_return):

        try:
            sphere = self.generate_chunk_queue.get_nowait()
        except Empty:
            return

        pos = sphere[0]
        rotations = sphere[1]
        tex = sphere[2]

        rotations = list(rotations)
        things = {}
        for index, (pos_, tex_) in enumerate(zip(pos, tex)):
            block = get_block(tex_, pos_)
            self.blocks.add(block)
            self.update_queue.put(block.update(self.get_neighbours(block.position)))
            rotation = tuple(rotations[index] if index < len(rotations) else (0, 0, 0))
            model = block.model

            if things.get(model) is None: things[model] = [[], [], []]

            things[model][0].append(block.position)
            things[model][1].append(block.texture)
            things[model][2].append(rotation)


        thig_dict_to_return["result"] = things
        


    def render_blocks(self):

        if (self.th is None or not self.th.is_alive()) and self.thig_dict_to_return["result"] is None:
            self.th = threading.Thread(target=self.place_chunks_step, args=(self.thig_dict_to_return,), daemon=True)
            self.th.start()

        if self.thig_dict_to_return["result"] is not None:
            for model, (pos, tex, rot) in self.thig_dict_to_return["result"].items():
                self.model.add_instances(
                    pos, tex, model, rot
                )

            self.thig_dict_to_return["result"] = None

        model:InstancedModel = self.model.instanedmodels["block"]

        cam = getattr(self.render, "CAMERA", None)
        if cam is None:
            cam = getattr(self.render, "camera", None)
        if cam is None:
            if len(model.instances):
                self.model.render()
            return

        try:
            cam_pos = cam.position
        except Exception:
            if len(model.instances):
                self.model.render()
            print("Exception at 606 in World.py")
            return


        if len(model.instances) and (
            self.last_xyz is None
            or np.abs(np.asarray(cam_pos) - np.asarray(self.last_xyz)).sum() >= 20.0
        ):

            self.last_xyz = cam_pos.copy()

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

            self.model.instanedmodels["block"] = model

        if len(model.instances):
            self.model.render()

    
    def get_block_at(self, position:Vec3 | Sequence[Number]):
        return self.blocks.positions_blocks.get(tuple(position), None)

    def get_important_collisions(self, player_position:Vec3) -> set[tuple]:
        neighbours = self.get_neighbours(player_position.round(), player=True)
        return {position for position, block in neighbours.items() if block is not None}

    def get_neighbours_extened_in_circle(self, pos:Vec3, radius) -> set[tuple]:
        res = set()
        radius = abs(radius)
        radius_squared = radius * radius
        min_x = math.floor(pos.x - radius)
        max_x = math.floor(pos.x + radius)
        min_z = math.floor(pos.z - radius)
        max_z = math.floor(pos.z + radius)
        positions_by_xz = self.blocks.positions_by_xz

        for x in range(min_x, max_x + 1):
            for z in range(min_z, max_z + 1):
                for position in positions_by_xz.get((x, z), ()):
                    dx = position[0] - pos.x
                    dz = position[2] - pos.z
                    if dx * dx + dz * dz <= radius_squared:
                        res.add(position)
        return res
        
        
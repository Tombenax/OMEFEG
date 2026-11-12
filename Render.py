import time
from collections.abc import Sequence
from typing import Any, Callable

from pyrr import Matrix44

from Number import Number
from Vec3 import Vec3
from BlenderModel import attach_blender_model
import moderngl
from PIL import Image
import numpy as np
import os
import random
from utils import distance, chunk_time, clip
import math

# Import glfw abstraction
import glfw

glfw.init()

PROJECTION_MAX = 1000

WIDTH, HEIGHT = 1280, 720

ATLAS = Image.open("assets/textures/texture.png")

ATLAS_W, ATLAS_H = ATLAS.size

TEXTURE_W, TEXTURE_H = 64, 64

TEXTURES_X, TEXTURES_Y = ATLAS_W // TEXTURE_W, ATLAS_H // TEXTURE_H

TEXTURES = (ATLAS_W // TEXTURE_W) * (ATLAS_H // TEXTURE_H)

CHAR = Image.open("assets/textures/charset.png")

CHAR_W, CHAR_H = CHAR.size

CHR_W, CHR_H = 16, 16

CHRS = (CHAR_W / CHR_W) * (CHAR_H / CHR_H)

ITEMS = Image.open("assets/textures/Items.png")

ITEMS_W, ITEMS_H = ITEMS.size

ITEM_W, ITEM_H = 32, 32

ITEMS_X, ITEMS_Y = ITEMS_W // ITEM_W, ITEMS_H // ITEM_H

ITEMS_COUNT = (ITEMS_W / ITEM_W) * (ITEMS_H / ITEM_H)

INVSCR_IMAGE = Image.open("assets/textures/InventoryScroll.png").convert("RGBA")

INVSCR_W, INVSCR_H = INVSCR_IMAGE.size

BODY_SLOTS = Image.open("assets/textures/body_slots.png").convert("RGBA")

BODY_SLOTS_W, BODY_SLOTS_H = BODY_SLOTS.size

BENCH_IMG = Image.open("assets/GUIs/BENCH.png").convert("RGBA")

BENCH_W, BENCH_H = BENCH_IMG.size


# Blocks that filter light instead of blocking it (leaf canopies give
# dappled shade, water tints instead of full shadow). Encoded as 127 in
# the occupancy volume (solid = 255); the shaders turn each filter voxel
# into 0.5x transmittance. Names match Block.block in allBlocks.py.
LIGHT_FILTER_BLOCKS = frozenset({"birch_leave", "oak_leave", "water"})


def _position_match_mask(instance_positions, requested):
    """Boolean mask over instance_positions rows matching requested rows.

    Integer fast path when every requested coord is integral and inside
    the int32 packing range (packs to one int64 key per row, matched
    with vectorized isin -- ~4x faster than per-row tuple hashing at
    100k+ instances). Falls back to exact float tuple matching otherwise
    (rotated/non-integral content), so results are always identical.
    Non-integral master rows can never equal integral requested tuples,
    so skipping them on the fast path is exact, not approximate.
    """
    inst = np.ascontiguousarray(instance_positions, dtype="f8").reshape(-1, 3)
    if len(inst) == 0:
        return np.zeros((0,), dtype=bool)
    req = np.ascontiguousarray(requested, dtype="f8").reshape(-1, 3)
    if len(req) == 0:
        return np.zeros((len(inst),), dtype=bool)

    OFF, S, LIM = 300000, 524288, 224000
    try:
        req_i = req.astype(np.int32)
        if bool((req == req_i).all()) and bool(np.abs(req_i).max(initial=0) <= LIM):
            mi = inst.astype(np.int32)
            whole = (inst == mi).all(axis=1)
            if bool(np.abs(mi[whole]).max(initial=0) <= LIM):
                mk = ((mi[:, 0].astype(np.int64) + OFF) * S + (mi[:, 1].astype(np.int64) + OFF)) * S + (mi[:, 2].astype(np.int64) + OFF)
                ek = ((req_i[:, 0].astype(np.int64) + OFF) * S + (req_i[:, 1].astype(np.int64) + OFF)) * S + (req_i[:, 2].astype(np.int64) + OFF)
                mask = np.zeros((len(inst),), dtype=bool)
                mask[whole] = np.isin(mk[whole], ek)
                return mask
    except (ValueError, OverflowError):
        pass

    requested_set = {tuple(p) for p in req}
    return np.array([tuple(p) in requested_set for p in inst], dtype=bool)


class Render:

    PRESS = glfw.PRESS

    KEY_W = glfw.KEY_W
    KEY_S = glfw.KEY_S
    KEY_A = glfw.KEY_A
    KEY_D = glfw.KEY_D

    KEY_RIGHT_ARROW = glfw.KEY_RIGHT
    KEY_LEFT_ARROW = glfw.KEY_LEFT

    KEY_LEFT_CONTROL = glfw.KEY_LEFT_CONTROL

    KEY_F = glfw.KEY_F

    KEY_R = glfw.KEY_R

    KEY_G = glfw.KEY_G

    KEY_ESCAPE = glfw.KEY_ESCAPE

    KEY_LEFT_SHIFT = glfw.KEY_LEFT_SHIFT

    CURSOR = glfw.CURSOR
    CURSOR_NORMAL = glfw.CURSOR_NORMAL
    CURSOR_DISABLED = glfw.CURSOR_DISABLED

    MOUSE_BUTTON_RIGHT = glfw.MOUSE_BUTTON_RIGHT

    MOUSE_BUTTON_LEFT = glfw.MOUSE_BUTTON_LEFT

    KEY_LEFT_ALT = glfw.KEY_LEFT_ALT

    FOV = 60

    PROJECTION = np.array(Matrix44.perspective_projection(FOV, WIDTH/HEIGHT, 0.1, PROJECTION_MAX), dtype='f8')

    def get_key(self, key:int):
        return glfw.get_key(self.window, key)

    def set_cursor_pos_callback(self, callback:Callable):
        glfw.set_cursor_pos_callback(self.window, callback)

    def set_window_size_callback(self, callback:Callable):
        glfw.set_window_size_callback(self.window, callback)

    def set_input_mode(self, input_mode, value):
        glfw.set_input_mode(self.window, input_mode, value)

    def get_mouse_button(self, button:int):
        return glfw.get_mouse_button(self.window, button)

    def set_window_pos(self, x, y):
        glfw.set_window_pos(self.window, x, y)

    def get_window_pos(self):
        return glfw.get_window_pos(self.window)

    def get_cursor_pos(self):
        return glfw.get_cursor_pos(self.window)

    def get_window_size(self):
        return glfw.get_window_size(self.window)

    def window_should_close(self):
        return glfw.window_should_close(self.window)

    def poll_events(self):
        glfw.poll_events()

    def swap_buffers(self):
        glfw.swap_buffers(self.window)

    def request_text_buffer(self):
        return self.text_buffer

    def set_text_buffer(self, value:str):
        self.text_buffer = value

    def set_window_should_close(self, value):
        glfw.set_window_should_close(self.window, value)

    def set_cursor_pos(self, x, y):
        glfw.set_cursor_pos(self.window, x, y)

    def resized(self, width, height):
        global PROJECTION, WIDTH, HEIGHT

        self.ctx.viewport = (0, 0, width, height)

        WIDTH, HEIGHT = width, height

        self.PROJECTION = np.array(Matrix44.perspective_projection(self.FOV, WIDTH/HEIGHT, 0.1, PROJECTION_MAX), dtype='f8')

    def init_programs(self):
        self.blocks_program["atlasArray"] = 0
        self.blocks_program["blockOccupancy"] = 3
        self.blocks_program["projection"].write(self.PROJECTION)
        self.blocks_program["frame"] = 0
        self.blocks_program["chance"] = -1
        self.blocks_program["TEXTURE_W"] = TEXTURE_W
        self.blocks_program["TEXTURE_H"] = TEXTURE_H
        self.blocks_program["ATLAS_W"] = ATLAS_W
        self.blocks_program["ATLAS_H"] = ATLAS_H
        # worldMin is the minimum *corner* of the occupancy volume.
        # Blocks are centered cubes (block.obj spans +/-0.5), so the
        # voxel for block P covers [P-0.5, P+0.5] and the volume corner
        # is minimum - 0.5. See update_block_occupancy and the shadow
        # code in the blocks/chunk fragment shaders.
        self.blocks_program["worldMin"].value = (-0.5, -0.5, -0.5)
        self.blocks_program["worldSize"].value = (1, 1, 1)
        self._upload_lights()

        self.text_program["atlasArray"] = 1
        self.text_program["projection"].write(self.PROJECTION)
        self.text_program["frame"] = 0
        self.text_program["chance"] = -1
        self.text_program["TEXTURE_W"] = CHR_W
        self.text_program["TEXTURE_H"] = CHR_H
        self.text_program["ATLAS_W"] = CHAR_W
        self.text_program["ATLAS_H"] = CHAR_H

        self.item_program["atlasArray"] = 2
        self.item_program["projection"].write(self.PROJECTION)
        self.item_program["frame"] = 0
        self.item_program["chance"] = -1
        self.item_program["TEXTURE_W"] = ITEM_W
        self.item_program["TEXTURE_H"] = ITEM_H
        self.item_program["ATLAS_W"] = ITEMS_W
        self.item_program["ATLAS_H"] = ITEMS_H

        self.chunk_program["atlasArray"] = 0
        self.chunk_program["blockOccupancy"] = 3
        self.chunk_program["projection"].write(self.PROJECTION)
        self.chunk_program["TEXTURE_W"] = TEXTURE_W
        self.chunk_program["TEXTURE_H"] = TEXTURE_H
        self.chunk_program["ATLAS_W"] = ATLAS_W
        self.chunk_program["ATLAS_H"] = ATLAS_H
        self.chunk_program["worldMin"].value = (-0.5, -0.5, -0.5)
        self.chunk_program["worldSize"].value = (1, 1, 1)

        self.HUDText_program["atlasArray"] = 1
        self.HUDText_program["screenSize"].value = (WIDTH, HEIGHT)
        self.HUDText_program["TEXTURE_W"] = CHR_W
        self.HUDText_program["TEXTURE_H"] = CHR_H
        self.HUDText_program["ATLAS_W"] = CHAR_W
        self.HUDText_program["ATLAS_H"] = CHAR_H

    def char_callback(self, window, char):        
        self.text_buffer += chr(char)

    def key_callback(self, window, key, arg1, pressed, arg3):

        if pressed == 0:
            return

        if key == glfw.KEY_ENTER:
            self.text_buffer += "\n"

        elif key == glfw.KEY_BACKSPACE:
            self.text_buffer = self.text_buffer[:-1]

    def __init__(self, init_function:Callable, update_function:Callable, settings=None):
        self.init_function = init_function
        self.update_function = update_function
        self.settings = settings if settings is not None else {"shaders": True}

        self.text_buffer = ""

        self.window = glfw.create_window(WIDTH, HEIGHT, "OMEFEG", None, None)

        glfw.make_context_current(self.window)

        glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_DISABLED)

        glfw.set_char_callback(self.window, self.char_callback)

        glfw.set_key_callback(self.window, self.key_callback)

        icon = Image.open("assets/icon.png").convert("RGBA")
        width, height = icon.size
        pixels = np.array(icon, dtype=np.uint8)

        glfw.set_window_icon(self.window, 1, [(width, height, pixels)])

        self.ctx = moderngl.create_context()

        self.ctx.enable(moderngl.CULL_FACE)

        self.block_occupancy = self.ctx.texture3d((1, 1, 1), 1, b"\x00")
        self.block_occupancy.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.block_occupancy.use(location=3)
        self._occupancy_size = (1, 1, 1)
        # Incremental occupancy state (see update_block_occupancy):
        # persistent CPU volume + per-chunk stamp tracking, so steady
        # walking only touches new chunks instead of rescanning the world.
        self._occ_data = None
        self._occ_min = None  # Vec3 block coordinates of the volume corner
        self._occ_stamped = set()  # chunk keys already in the volume
        self._occ_chunk_bounds = {}  # chunk key -> (cmin, cmax) int tuples
        self.light_positions = [Vec3(9, 50, 9)]
        self.light_colors = [(1, 1, 1, 1)]

        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        self.load_shaders("OPENGL shaders", os.listdir("OPENGL shaders"))

        self.create_programs()

        self.load_textures()

        self.CAMERA = Camera([0, 15, 0], self)

        self.set_cursor_pos_callback(self.CAMERA.cursor_move)

        self.init_programs()

        self.init_function(self)

        self.update()

    
    def load_texture_array(self, atlas:Image.Image, atlas_h, teture_h, atlas_w, texture_w, show=False):
        new_atlas = atlas.copy()

        for i in range(int(atlas_h / teture_h)):
            Image.Image.paste(new_atlas, atlas.crop((0, i*teture_h, (atlas_w / texture_w) * texture_w, i*teture_h+teture_h)).transpose(Image.FLIP_TOP_BOTTOM), (0, i*teture_h))
            if show:
                atlas.crop((0, i*teture_h, (atlas_w / texture_w) * texture_w, i*teture_h+teture_h)).transpose(Image.FLIP_TOP_BOTTOM).show("a")
        if show:
            new_atlas.show("a")
        width, height = atlas.size
        depth = 1
        data = b''.join([new_atlas.convert('RGBA').tobytes()])
        tex_array = self.ctx.texture_array((width, height, depth), 4, data)
        tex_array.filter = (moderngl.NEAREST, moderngl.NEAREST)
        return tex_array


    def load_textures(self):
        self.blocks_texture = self.load_texture_array(ATLAS, ATLAS_H, TEXTURE_H, ATLAS_W, TEXTURE_W)
        self.blocks_texture.use(location=0)

        self.chars_texture = self.load_texture_array(CHAR, CHAR_H, CHR_H, CHAR_W, CHR_W)
        self.chars_texture.use(location=1)


        self.items_texture = self.load_texture_array(ITEMS, ITEMS_H, ITEM_H, ITEMS_W, ITEM_W)
        self.items_texture.use(location=2)

    def create_programs(self):
        for shader_name, shaders in self.shaders.items():
            setattr(self, shader_name+"_program", self.ctx.program(*shaders))


    def load_shader(self, shader_path):
        with open(shader_path, "r") as f:
            readed = f.read()
        return readed

    def load_shaders(self, shader_base_path, shader_names):
        self.shaders = {}
        for shader in shader_names:
            self.shaders[shader] = [
                self.load_shader(os.path.join(shader_base_path, shader, "vertex.glsl")),
                self.load_shader(os.path.join(shader_base_path, shader, "fragment.glsl"))
                ]

    def update_programs(self):
        shaders_enabled = self.settings.get("shaders") is True
        self.blocks_program["enable_shaders"].value = shaders_enabled
        self.chunk_program["enable_shaders"].value = shaders_enabled
        self.text_program["enable_shaders"].value = shaders_enabled
        self.item_program["enable_shaders"].value = shaders_enabled

        self.blocks_program["view"].write(self.CAMERA.view.astype("f8").tobytes())
        self.blocks_program["viewPos"].write(self.CAMERA.position.xyz.astype("f8").tobytes())

        self.text_program["view"].write(self.CAMERA.view.astype("f8").tobytes())
        self.text_program["lightPos"].value = (9, 50, 9)
        self.text_program["viewPos"].write(self.CAMERA.position.xyz.astype("f8").tobytes())

        self.chunk_program["view"].write(self.CAMERA.view.astype("f8").tobytes())
        self.chunk_program["viewPos"].write(self.CAMERA.position.xyz.astype("f8").tobytes())

        self.item_program["view"].write(self.CAMERA.view.astype("f8").tobytes())
        self.item_program["lightPos"].value = (9, 50, 9)
        self.item_program["viewPos"].write(self.CAMERA.position.xyz.astype("f8").tobytes())

    def set_lights(self, positions, colors):
        if len(positions) != len(colors):
            raise ValueError("positions and colors must have the same length")
        if len(positions) > 16:
            raise ValueError("A maximum of 16 lights is supported")
        self.light_positions = [
            position.copy() if isinstance(position, Vec3) else Vec3(*position)
            for position in positions
        ]
        self.light_colors = [tuple(color) for color in colors]
        self._upload_lights()

    def _upload_lights(self):
        self.blocks_program["lightCount"].value = len(self.light_positions)
        positions = np.zeros((16, 3), dtype="f8")
        colors = np.zeros((16, 4), dtype="f4")
        positions[:len(self.light_positions)] = self.light_positions
        colors[:len(self.light_colors)] = self.light_colors
        self.blocks_program["lightPositions"].write(positions.tobytes())
        self.blocks_program["lightColors"].write(colors.tobytes())
        self.chunk_program["lightCount"].value = len(self.light_positions)
        self.chunk_program["lightPositions"].write(positions.tobytes())
        self.chunk_program["lightColors"].write(colors.tobytes())

    # Padding for the occupancy volume: walking straight grows bounds
    # ~10 blocks per new chunk row. XZ padding absorbs ~6 rows so steady
    # walking stamps + uploads instead of reallocating; Y varies little
    # (terrain height band), so it gets a smaller pad to save VRAM.
    _OCC_PAD_XZ = 64
    _OCC_PAD_Y = 16

    @staticmethod
    def _occ_chunk_bounds_of(chunk):
        occ = chunk.blocks.occupied
        if not occ:
            cx, _, cz = chunk.position
            return (cx, 0, cz), (cx + 9, 0, cz + 9)
        arr = np.asarray(list(occ), dtype=np.int32)
        return tuple(map(int, arr.min(axis=0))), tuple(map(int, arr.max(axis=0)))

    def _occ_stamp_chunk(self, chunk):
        """Write one chunk's voxels into the persistent CPU volume.

        Plain loop on purpose: measured faster than a vectorized fancy-
        index version at chunk scale (~6700 voxels into a tiny volume;
        index-array build + broadcast overhead beats the scalar stores).
        """
        base = self._occ_min
        data = self._occ_data
        bx, by, bz = int(base[0]), int(base[1]), int(base[2])
        for x, y, z in chunk.blocks.occupied:
            data[z - bz, y - by, x - bx] = 255
        for block in chunk.blocks.blocks_list:
            if getattr(block, "block", "") in LIGHT_FILTER_BLOCKS:
                p = block.position
                data[p[2] - bz, p[1] - by, p[0] - bx] = 127

    def _occ_upload_new_volume(self, minimum, size, data):
        new_size = tuple(map(int, size))
        self.block_occupancy.release()
        self.block_occupancy = self.ctx.texture3d(new_size, 1, data.tobytes())
        self.block_occupancy.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.block_occupancy.use(location=3)
        self._occupancy_size = new_size
        # Blocks are centered cubes spanning [P-0.5, P+0.5] (see
        # assets/models/block.obj), so the occupancy volume corner is
        # minimum - 0.5. The shaders compute cell = floor(pos - worldMin),
        # which then maps block P to texel P - minimum as stored above.
        world_min_corner = minimum.xyz.astype("f8") - 0.5
        self.blocks_program["blockOccupancy"] = 3
        self.blocks_program["worldMin"].value = tuple(map(float, world_min_corner))
        self.blocks_program["worldSize"].value = tuple(map(int, size))
        self.chunk_program["blockOccupancy"] = 3
        self.chunk_program["worldMin"].value = tuple(map(float, world_min_corner))
        self.chunk_program["worldSize"].value = tuple(map(int, size))

    def _occ_grow_and_blit(self, need_min, need_max):
        """Enlarge the volume to fit need_min/need_max, reusing voxels.

        Pads only the side(s) that actually grew (no drift), blits the
        old volume into the new one, and reallocates once. No chunk
        rescan: every stamped voxel stays valid, only its offset changes.
        """
        old_min = [int(v) for v in self._occ_min]
        old_shape = self._occ_data.shape  # (dz, dy, dx); axis a has dim shape[2-a]
        old_max = [old_min[a] + old_shape[2 - a] - 1 for a in range(3)]
        alloc_min, alloc_max = list(old_min), list(old_max)
        for a in range(3):
            pad = self._OCC_PAD_Y if a == 1 else self._OCC_PAD_XZ
            if need_min[a] < old_min[a]:
                alloc_min[a] = need_min[a] - pad
            if need_max[a] > old_max[a]:
                alloc_max[a] = need_max[a] + pad
        new_size = tuple(alloc_max[a] - alloc_min[a] + 1 for a in range(3))
        data = np.zeros((new_size[2], new_size[1], new_size[0]), dtype=np.uint8)
        # Blit overlap: old voxel (x,y,z) -> new index (v - alloc_min).
        off = [old_min[a] - alloc_min[a] for a in range(3)]
        oz, oy, ox = off[2], off[1], off[0]
        dz, dy, dx = old_shape
        data[oz:oz + dz, oy:oy + dy, ox:ox + dx] = self._occ_data
        minimum = Vec3(*alloc_min)
        size = np.asarray(new_size, dtype=np.int32)
        self._occ_data = data
        self._occ_min = minimum
        self._occ_upload_new_volume(minimum, size, data)

    def _occ_full_rebuild(self, world, keys_now):
        from allBlocks import BIRCH_LEAVE, OAK_LEAVE, WATER
        occupied = set()
        filt_parts = []
        for chunk in world.chunks.blocks_list:
            try:
                occ = chunk.blocks.occupied
            except AttributeError:
                continue
            if occ:
                occupied.update(occ)
            # Light-filter voxels by texture id (same voxels the old
            # getattr-per-block loop collected, without the 330k lookups).
            try:
                tex = chunk.blocks.textures
                pos = chunk.blocks.positions
            except AttributeError:
                continue
            if tex and pos:
                try:
                    ta = np.asarray(tex, dtype=np.int32)
                    pa = np.asarray(pos, dtype=np.int32).reshape(-1, 3)
                except (ValueError, TypeError):
                    continue
                if ta.shape[0] != pa.shape[0] or ta.shape[0] == 0:
                    continue
                mask = (ta == BIRCH_LEAVE) | (ta == OAK_LEAVE) | (ta == WATER)
                if bool(mask.any()):
                    filt_parts.append(pa[mask])

        if occupied:
            all_arr = np.asarray(list(occupied), dtype=np.int32).reshape(-1, 3)
            minimum = Vec3(*all_arr.min(axis=0))
            maximum = all_arr.max(axis=0)
            size = maximum - minimum + 1
        else:
            all_arr = None
            minimum = Vec3(0, 0, 0)
            size = np.ones(3, dtype="i8")

        data = np.zeros((int(size[2]), int(size[1]), int(size[0])), dtype=np.uint8)
        if all_arr is not None and all_arr.shape[0]:
            data[all_arr[:, 2] - minimum[2],
                 all_arr[:, 1] - minimum[1],
                 all_arr[:, 0] - minimum[0]] = 255
        if filt_parts:
            fall = np.concatenate(filt_parts).reshape(-1, 3)
            if fall.shape[0]:
                data[fall[:, 2] - minimum[2],
                     fall[:, 1] - minimum[1],
                     fall[:, 0] - minimum[0]] = 127

        self._occ_data = data
        self._occ_min = minimum
        self._occ_stamped = set(keys_now)
        self._occ_chunk_bounds = {}
        for chunk in world.chunks.blocks_list:
            key = tuple(chunk.position)
            if key in self._occ_stamped:
                self._occ_chunk_bounds[key] = self._occ_chunk_bounds_of(chunk)
        self._occ_upload_new_volume(minimum, size, data)

    def refresh_chunk_occupancy(self, chunk):
        """Re-stamp one edited chunk (place/destroy). Returns True if the
        volume was updated incrementally, False if the caller should fall
        back to update_block_occupancy (no volume yet)."""
        if self._occ_data is None:
            return False
        key = tuple(chunk.position)
        if key not in self._occ_stamped:
            return False
        base = self._occ_min
        data = self._occ_data
        # Clear the chunk's column footprint, then re-stamp current blocks
        # (clears voxels of removed blocks; 10x10 columns x full height).
        ix0 = int(chunk.position[0] - base[0])
        iz0 = int(chunk.position[2] - base[2])
        ix1 = ix0 + 10
        iz1 = iz0 + 10
        if ix0 < 0 or iz0 < 0 or ix1 > data.shape[2] or iz1 > data.shape[0]:
            return False
        _rt0 = time.perf_counter()
        data[iz0:iz1, :, ix0:ix1] = 0
        self._occ_stamp_chunk(chunk)
        try:
            self.block_occupancy.write(data.tobytes())
            self.block_occupancy.use(location=3)
        except Exception:
            return False
        self._occ_chunk_bounds[key] = self._occ_chunk_bounds_of(chunk)
        chunk_time("occupancy-refresh", _rt0)
        return True

    def remove_chunks_occupancy(self, world, evicted):
        """Drop evicted chunks' voxels without a world rescan.

        `evicted` is an iterable of (key, occupied) where `occupied` is
        the chunk's voxel set of (x, y, z) int tuples, captured BEFORE the
        chunk was removed from the world.

        Each chunk owns disjoint 10-wide columns, so its column box is
        cleared exactly (nothing kept can live in there). Structure spill
        (tree/temple blocks outside the chunk's own columns) is cleared
        voxel-by-voxel, but only when no kept chunk still occupies the
        voxel: a kept neighbour may own a coincident voxel with its own
        solid column, which must survive.

        Single GPU upload at the end. Returns True when handled, False
        when the caller should fall back to update_block_occupancy (no
        volume yet, box outside the volume, or upload failure).
        """
        if self._occ_data is None:
            return False
        try:
            evicted = list(evicted)
        except TypeError:
            return False
        if not evicted:
            return True
        data = self._occ_data
        base = self._occ_min
        try:
            bx, by, bz = int(base[0]), int(base[1]), int(base[2])
        except (TypeError, IndexError, ValueError):
            return False
        dz, dy, dx = data.shape
        items = []
        for key, occ in evicted:
            try:
                kx = int(key[0])
                kz = int(key[2])
            except (TypeError, IndexError, ValueError):
                return False
            ix0 = kx - bx
            iz0 = kz - bz
            if ix0 < 0 or iz0 < 0 or ix0 + 10 > dx or iz0 + 10 > dz:
                return False
            items.append((key, kx, kz, ix0, iz0, occ))
        # Pass 1: clear own column boxes (exact: columns are disjoint, so
        # no kept chunk can own a voxel in here).
        for _key, _kx, _kz, ix0, iz0, _occ in items:
            data[iz0:iz0 + 10, :, ix0:ix0 + 10] = 0
        # Pass 2: structure spill outside the own box.
        try:
            kept = world.chunks.positions_blocks
        except AttributeError:
            return False
        gone = set()
        for key, _kx, _kz, _ix0, _iz0, _occ in items:
            try:
                gone.add((int(key[0]), int(key[1]), int(key[2])))
            except (TypeError, IndexError, ValueError):
                return False
        for _key, kx, kz, _ix0, _iz0, occ in items:
            try:
                it = iter(occ) if occ is not None else iter(())
            except TypeError:
                return False
            for v in it:
                try:
                    x, y, z = int(v[0]), int(v[1]), int(v[2])
                except (TypeError, IndexError, ValueError):
                    continue
                if kx <= x < kx + 10 and kz <= z < kz + 10:
                    continue  # own box already cleared
                if not (0 <= x - bx < dx and 0 <= y - by < dy
                        and 0 <= z - bz < dz):
                    # Voxel outside the volume: volume state is suspect,
                    # fall back to a full rebuild rather than mis-clear.
                    return False
                okey = (x // 10 * 10, 0, z // 10 * 10)
                if okey in gone:
                    continue  # owner evicted too: its box-clear handled it
                try:
                    owner = kept.get(okey)
                except AttributeError:
                    return False
                if owner is not None:
                    try:
                        owns = (x, y, z) in owner.blocks.occupied
                    except (AttributeError, TypeError):
                        return False
                    if owns:
                        continue
                data[z - bz, y - by, x - bx] = 0
        for key, _kx, _kz, _ix0, _iz0, _occ in items:
            try:
                nkey = (int(key[0]), int(key[1]), int(key[2]))
            except (TypeError, IndexError, ValueError):
                continue
            self._occ_stamped.discard(nkey)
            self._occ_chunk_bounds.pop(nkey, None)
        # Compact the volume: evicting the leading edge would otherwise
        # leave permanent zero padding (unbounded growth while walking
        # straight: full re-uploads of a ever-wider texture per chunk).
        # Tight bounds come from the per-chunk stamps (O(chunks), no voxel
        # rescan); the dropped region is proven air because every kept
        # voxel (spill included) sits inside some kept chunk's bounds. A
        # stamped chunk without bounds (vanished mid-update) disables
        # compaction rather than risk cutting live voxels.
        # _compact_occupancy uploads itself when it reallocs, so the
        # plain write below only runs when the volume was untouched.
        try:
            compacted = bool(self._compact_occupancy())
        except Exception:
            compacted = False
        if compacted:
            return True
        try:
            self.block_occupancy.write(self._occ_data.tobytes())
            self.block_occupancy.use(location=3)
        except Exception:
            return False
        return True

    def _compact_occupancy(self):
        """Crop the volume to the stamped chunks' tight bounds.

        Returns True when it reallocated + uploaded (caller must skip its
        own write), False when the volume was left untouched. Uses
        _occ_upload_new_volume (single realloc + upload with refreshed
        uniforms) when cropping.
        """
        data = self._occ_data
        if data is None:
            return False
        if not self._occ_stamped:
            # Everything evicted (far teleport): drop the whole volume
            # instead of carrying a giant zero padding. The next chunk-add
            # regrows from the 1-cell volume via the normal grow path.
            import numpy as _np
            empty = _np.zeros((1, 1, 1), dtype=_np.uint8)
            self._occ_data = empty
            self._occ_min = Vec3(0, 0, 0)
            self._occ_chunk_bounds = {}
            self._occ_upload_new_volume(self._occ_min, (1, 1, 1), empty)
            return True
        bounds_vals = []
        for k in self._occ_stamped:
            b = self._occ_chunk_bounds.get(k)
            if b is None:
                return False
            bounds_vals.append(b)
        if not bounds_vals:
            return False
        base = self._occ_min
        bx, by, bz = int(base[0]), int(base[1]), int(base[2])
        tmin = [min(b[0][a] for b in bounds_vals) for a in range(3)]
        tmax = [max(b[1][a] for b in bounds_vals) for a in range(3)]
        dz, dy, dx = data.shape
        if (tmin[0] <= bx and tmin[1] <= by and tmin[2] <= bz
                and tmax[0] >= bx + dx - 1 and tmax[1] >= by + dy - 1
                and tmax[2] >= bz + dz - 1):
            return False  # volume already tight: plain write by the caller
        sx0, sy0, sz0 = tmin[0] - bx, tmin[1] - by, tmin[2] - bz
        sx1, sy1, sz1 = tmax[0] - bx + 1, tmax[1] - by + 1, tmax[2] - bz + 1
        if sx0 < 0 or sy0 < 0 or sz0 < 0 or sx1 > dx or sy1 > dy or sz1 > dz:
            return False  # tight box escapes the volume: leave it
        import numpy as _np
        minimum = Vec3(*tmin)
        cropped = data[sz0:sz1, sy0:sy1, sx0:sx1].copy()
        self._occ_data = cropped
        self._occ_min = minimum
        self._occ_upload_new_volume(minimum, cropped.shape[::-1], cropped)
        return True

    def update_block_occupancy(self, world):
        keys_now = set(world.chunks.positions_blocks.keys())
        # Incremental path: stamp only not-yet-stamped chunks when they
        # fit the current volume, then a single upload. This is the
        # steady-walking case: O(new blocks) instead of O(world).
        if self._occ_data is not None:
            if keys_now >= self._occ_stamped:
                new_keys = keys_now - self._occ_stamped
                if not new_keys:
                    return
                bounds = world.chunks.positions_blocks
                need_min = None
                need_max = None
                new_bounds = {}
                for key in new_keys:
                    chunk = bounds.get(key)
                    if chunk is None:
                        continue
                    # Worker-computed bounds travel on the chunk (see
                    # _finish_payload): reuse avoids a list->array pass
                    # per added chunk. Edits invalidate the cache (see
                    # _flush_placements/destroy_block), so a hit is exact.
                    cmin = cmax = None
                    try:
                        cached = getattr(chunk, "_occ_bounds", None)
                        if cached is not None:
                            cmin = tuple(map(int, cached[0]))
                            cmax = tuple(map(int, cached[1]))
                    except (TypeError, IndexError, ValueError):
                        cmin = cmax = None
                    if cmin is None or cmax is None:
                        cmin, cmax = self._occ_chunk_bounds_of(chunk)
                    new_bounds[key] = (cmin, cmax)
                    if need_min is None:
                        need_min = list(cmin)
                        need_max = list(cmax)
                    else:
                        for a in range(3):
                            if cmin[a] < need_min[a]:
                                need_min[a] = cmin[a]
                            if cmax[a] > need_max[a]:
                                need_max[a] = cmax[a]
                base = self._occ_min
                shape = self._occ_data.shape  # (dz, dy, dx)
                fits = True
                if need_min is not None:
                    for a in range(3):
                        lo = need_min[a] - int(base[a])
                        hi = need_max[a] - int(base[a])
                        dim = shape[2 - a]
                        if lo < 0 or hi >= dim:
                            fits = False
                            break
                if not fits and need_min is not None:
                    # Outgrew the volume: enlarge (padding only the grown
                    # side), reusing every stamped voxel via blit - no
                    # world rescan. Afterwards the new chunks fit.
                    self._occ_grow_and_blit(need_min, need_max)
                if need_min is not None:
                    for key in new_keys:
                        chunk = bounds.get(key)
                        if chunk is None:
                            continue
                        self._occ_stamp_chunk(chunk)
                    try:
                        self.block_occupancy.write(self._occ_data.tobytes())
                        self.block_occupancy.use(location=3)
                    except Exception:
                        self._occ_full_rebuild(world, keys_now)
                        return
                    self._occ_stamped.update(new_keys)
                    self._occ_chunk_bounds.update(new_bounds)
                    return
                return
            # Chunks were removed (or volume predates them): full rebuild
            # to drop stale voxels.
            self._occ_full_rebuild(world, keys_now)
            return
        self._occ_full_rebuild(world, keys_now)

    def update(self):
        last = time.time()
        while not glfw.window_should_close(self.window):
            now = time.time()
            self.dt = now-last
            last = now

            self.ctx.clear(0, 0, 0)

            glfw.poll_events()

            self.update_programs()

            self.update_function(self)

            glfw.swap_buffers(self.window)

        glfw.terminate()

class InstancedModel:
    def __init__(self, **kwargs:dict[str, Any]):
        """
        aruments:
            render: Render instance
            indices: model's indices
            vertices: model's vertices
            !USED BY CHUNKS DUMMIES! is_chunk_dummy
        """

        self.ctx:moderngl.Context = kwargs["render"].ctx
        self.is_chunk_dummy = bool(kwargs.get("is_chunk_dummy"))
        self.repeat_block_textures = bool(kwargs.get("repeat_block_textures"))
        self.program = kwargs["render"].blocks_program if not self.is_chunk_dummy else kwargs["render"].chunk_program

        self.indices = np.asarray(kwargs["indices"], dtype="i4")
        self.vertices = kwargs["vertices"]

        self.vbo = self.ctx.buffer(np.asarray(self.vertices, dtype="f4").tobytes())
        self.ibo = self.ctx.buffer(self.indices.tobytes())

        self.instance_buffer = self.ctx.buffer(reserve=64 * 1024)
        self.layer_buffer = self.ctx.buffer(reserve=4 * 1024)

        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (
                    self.vbo,
                    '3f 3f 2f',
                    'in_position',
                    'in_normal',
                    'in_uv'
                ),
                (
                    self.instance_buffer,
                    '16f8/i',
                    'instance_model'
                ),
                (
                    self.layer_buffer,
                    '1i/i',
                    'instance_layer'
                ),
            ],
            self.ibo
        )

        self.instances = np.zeros((0, 4, 4), dtype="f8")
        self.tex_insta = np.zeros((0,), dtype="f8")

        self.active_instances = np.zeros((0, 4, 4), dtype="f8")
        self.active_tex_insta = np.zeros((0,), dtype="f8")

    def add_instances(self, positions:Sequence[Vec3 | Sequence[Number]] | np.ndarray, textures:list[int] | np.ndarray, rotations:list[list[Number]]=[], upload=True):

        if not isinstance(positions, np.ndarray):
            positions = np.asarray(positions, dtype='f8')

        if positions.ndim == 1:
            positions = positions.reshape(1, -1)

        new_models = np.eye(4, dtype='f8').reshape(1, 4, 4)
        new_models = np.repeat(new_models, len(positions), axis=0)
        new_models[:, 3, 0] = positions[:, 0]
        new_models[:, 3, 1] = positions[:, 1]
        new_models[:, 3, 2] = positions[:, 2]

        for idx, rotation in enumerate(rotations):
            x, y, z = [
                Matrix44.from_x_rotation(math.radians(rotation[0])),
                Matrix44.from_y_rotation(math.radians(rotation[1])),
                Matrix44.from_z_rotation(math.radians(rotation[2]))
            ]

            new_models[idx] = x @ y @ z @ new_models[idx]

        self.instances = np.concatenate((self.instances, new_models))

        self.tex_insta = np.concatenate((self.tex_insta, np.array(textures, dtype="f8")))

        # New instances are visible by default: mirror them into the
        # active (rendered) subset. self.instances/self.tex_insta stay
        # the full master list even when instances are hidden.
        self.active_instances = np.concatenate((self.active_instances, new_models))

        self.active_tex_insta = np.concatenate((self.active_tex_insta, np.array(textures, dtype="f8")))

        if upload:
            self._upload()

    def remove_instance(self, i, upload=True):
        """Remove an instance at the given indx"""
        removed_model = self.instances[i].copy()
        removed_tex = self.tex_insta[i].copy()

        self.instances = np.delete(self.instances, i, axis=0)
        self.tex_insta = np.delete(self.tex_insta, i, axis=0)

        # Keep the visible subset in sync: drop one matching entry.
        for j in range(len(self.active_instances)):
            if self.active_tex_insta[j] == removed_tex and np.array_equal(self.active_instances[j], removed_model):
                self.active_instances = np.delete(self.active_instances, j, axis=0)
                self.active_tex_insta = np.delete(self.active_tex_insta, j, axis=0)
                break

        if upload:
            self._upload()

    def remove_instances(self, positions:Sequence[Vec3 | Sequence[Number]] | np.ndarray, upload=True):
        """Remove instances whose model translations match the given positions.

        Pass upload=False when the caller (e.g. World render/cull paths)
        uploads once afterwards -- otherwise every call re-uploads the
        full instance buffers by itself.
        """
        if len(positions) == 0:
            return 0

        remove_mask = _position_match_mask(self.instances[:, 3, :3], positions)
        removed = int(np.count_nonzero(remove_mask))

        if removed:
            self.instances = self.instances[~remove_mask]
            self.tex_insta = self.tex_insta[~remove_mask]

            if len(self.active_instances):
                active_mask = _position_match_mask(self.active_instances[:, 3, :3], positions)
                if np.any(active_mask):
                    self.active_instances = self.active_instances[~active_mask]
                    self.active_tex_insta = self.active_tex_insta[~active_mask]

            if upload:
                self._upload()

        return removed

    def _upload(self):
        self.instance_buffer.orphan(len(self.active_instances.tobytes()))
        self.instance_buffer.write(self.active_instances.tobytes())

        layer_bytes = self.active_tex_insta.astype('i4').tobytes()
        self.layer_buffer.orphan(len(layer_bytes))
        self.layer_buffer.write(layer_bytes)

    def set_vertices(self, vertices):
        vertices = np.asarray(vertices, dtype="f8").reshape(-1)
        if vertices.size != self.vertices.size:
            raise ValueError("Animated mesh vertices must preserve the exported layout")
        self.vertices = vertices
        self.vbo.write(vertices.astype("f4").tobytes())

    def set_visible(self, position_or_visible, value=None):
        """Per-instance visibility toggle plus whole-model show/hide.

        Called with a single bool (``set_visible(True/False)``) this is
        the whole-model show/hide switch (mobile parity: detaches canvas
        objects there). Desktop redraws from scratch every frame, so that
        is only state; Menus.activate/deactivate drive it on both builds
        uniformly.

        Called with ``(position, value)`` it toggles individual
        instances: ``self.instances``/``self.tex_insta`` always keep the
        full master list, while ``self.active_instances``/
        ``self.active_tex_insta`` hold the visible subset that is
        uploaded/rendered. ``value=True`` puts the master entries at
        ``position`` into the active subset (if not already there);
        ``value=False`` removes them from the active subset (master
        untouched in both cases).
        """
        if value is None:
            self._hidden = not bool(position_or_visible)
            return

        position = position_or_visible
        visible = bool(value)

        positions = np.asarray(position, dtype="f8")
        if positions.ndim == 1:
            positions = positions.reshape(1, 3)

        if len(self.instances) == 0:
            return

        if visible:
            # Add every master entry at the requested positions that is
            # not already in the active subset (exact matrix+texture
            # match, so rotated duplicates at one position all restore).
            candidates = _position_match_mask(self.instances[:, 3, :3], positions)
            if not np.any(candidates):
                return
            active_keys = {(m.tobytes(), float(t)) for m, t in zip(self.active_instances, self.active_tex_insta)}
            to_add_models = []
            to_add_tex = []
            for idx in np.nonzero(candidates)[0]:
                if (self.instances[idx].tobytes(), float(self.tex_insta[idx])) not in active_keys:
                    to_add_models.append(self.instances[idx])
                    to_add_tex.append(self.tex_insta[idx])
            if to_add_models:
                self.active_instances = np.concatenate(
                    (self.active_instances, np.stack(to_add_models).astype("f8"))
                )
                self.active_tex_insta = np.concatenate(
                    (self.active_tex_insta, np.array(to_add_tex, dtype="f8"))
                )
                self._upload()
        else:
            if len(self.active_instances) == 0:
                return
            hide_mask = _position_match_mask(self.active_instances[:, 3, :3], positions)
            if np.any(hide_mask):
                self.active_instances = self.active_instances[~hide_mask]
                self.active_tex_insta = self.active_tex_insta[~hide_mask]
                self._upload()

    def render(self):
        if getattr(self, "_hidden", False):
            return
        if len(self.active_instances) == 0: return

        if not self.is_chunk_dummy:
            self.program["repeatBlockTextures"].value = self.repeat_block_textures
        self.vao.render(instances=len(self.active_instances))


class Model:
    def __init__(self, renderer:Render):
        self.instanedmodels:dict[str, InstancedModel] = {}
        self.animated_models = {}
        self.renderer = renderer

    def add_model(self, identifier:str, **kwargs:dict[str, Any]):
        """
        args:
            vertices: model's vertices
            indices: model's indices
            !ONlY USED BY CHUNK DUMMIES! is_chunk_dummy
        """
        self.animated_models.pop(identifier, None)
        old = self.instanedmodels.get(identifier)
        if old is not None:
            # The replaced model's GPU objects would otherwise leak: chunk
            # dummy rebuilds replace this model on every block edit (and
            # every frame while the player is inside the chunk).
            for resource in ("vao", "vbo", "ibo", "instance_buffer",
                             "layer_buffer"):
                try:
                    getattr(old, resource).release()
                except Exception:
                    pass
        self.instanedmodels[identifier] = InstancedModel(
            render=self.renderer,
            indices = kwargs["indices"],
            vertices = kwargs["vertices"],
            is_chunk_dummy = kwargs.get("is_chunk_dummy"),
            repeat_block_textures = identifier == "block",
        )

    def load_blender_model(
        self,
        identifier: str,
        path: str,
        position=(0, 0, 0),
        texture: int = 0,
        rotation=None,
    ):
        """Load a ``.omefeg`` export and return its animation controller."""
        return attach_blender_model(
            self, identifier, path, position, texture, rotation
        )

    def play_animation(self, identifier: str, animation: str, loop: bool = True):
        self.animated_models[identifier].play(animation, loop=loop)

    def stop_animation(self, identifier: str, reset: bool = False):
        self.animated_models[identifier].stop(reset=reset)

    
    def add_instances(self, positions:Sequence[Vec3 | Sequence[Number]] | np.ndarray, textures:list[int], model_identifier:str, rotations:list[list[Number]]=[]):
        self.instanedmodels[model_identifier].add_instances(positions, textures, rotations)

    def remove_instance(self, index:Number, model_identifier:str):
        """Remove an instance at position from the specified model. Returns True if removed, False if not found."""
        if model_identifier in self.instanedmodels:
            return self.instanedmodels[model_identifier].remove_instance(index)

    def remove_instances(self, positions:Sequence[Vec3 | Sequence[Number]] | np.ndarray, model_identifier:str, upload=True):
        return self.instanedmodels[model_identifier].remove_instances(positions, upload=upload)

    def render_one(self, identifier:str):
        animation = self.animated_models.get(identifier)
        if animation is not None:
            animation.update()
        self.instanedmodels[identifier].render()

    def render(self):
        for identifier in self.instanedmodels.keys():
            self.render_one(identifier)

def get_key(window, key):
    return glfw.get_key(window, key)

def do_thing(x):
    for idx, y in enumerate(x):
        if y > 0:
            x[idx] = 1 - y

        elif y < 0:
            x[idx] = - (1 - abs(y))

    return x

def do_thing2(x):
    if x > 0:
        x = 1 - x

    elif x < 0:
        x = - (1 - abs(x))

    return x

class Camera:
    def __init__(self, position, render: Render):
        self.render = render

        self.position = Vec3(*(float(value) for value in position))

        self.start_pos = self.position.copy()

        self.yaw = 0.0
        self.pitch = 0.0

        self.eye_height = 1.8

        self.last_x = 0
        self.last_y = 0

        self.dx = 0
        self.dy = 0

        self.sensitivity = 0.2
        self.speed = 5

        self.gravity = 0.5

        self.fly = False

        self.do = False

        self.max_jumps = 1

        self.jump_strenght = 18

        self.jumps = 0

        self.trust_me = True

        self.front = Vec3(1.0, 0.0, 0.0)
        self.right = Vec3(0.0, 0.0, -1.0)
        self.up = Vec3(0.0, 1.0, 0.0)

        self.vel_y = 0.0
        self.vel_x = 0.0
        self.vel_z = 0.0
        self.on_ground = False

        self.eye_pos = self.position + Vec3(0, self.eye_height, 0)

        self.view = Matrix44.look_at(
            self.eye_pos,
            self.eye_pos + self.front,
            self.up
        )

    def cursor_move(self, w, x, y):
        self.dx = x - self.last_x
        self.dy = y - self.last_y

        if self.fly and self.do:
            if self.up[1] > 0:
                self.dx *= 1
            else:
                self.dx *= -1

        self.yaw += self.dx * self.sensitivity
        self.pitch -= self.dy * self.sensitivity

        self.last_x = x
        self.last_y = y

    def update(self, occupied, world=None):

        point_to_world_center = Vec3(0, -1, 0)
        world_up = Vec3(0, 1, 0)
        if world is not None:
            point_to_world_center = Vec3(*world.origin) - self.position

            distance_to_world_center = np.linalg.norm(point_to_world_center.xyz)
            if distance_to_world_center > 0:
                point_to_world_center /= distance_to_world_center
                world_up = -point_to_world_center

        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)

        reference_forward = Vec3(1, 0, 0)
        reference_forward -= world_up * np.dot(reference_forward.xyz, world_up.xyz)
        reference_length = np.linalg.norm(reference_forward.xyz)
        if reference_length < 1e-8:
            reference_forward = Vec3(0, 0, 1)
            reference_forward -= world_up * np.dot(reference_forward.xyz, world_up.xyz)
            reference_length = np.linalg.norm(reference_forward.xyz)
        reference_forward /= reference_length

        reference_right = Vec3(*np.cross(world_up.xyz, reference_forward.xyz))
        go = reference_forward * math.cos(yaw) - reference_right * math.sin(yaw)
        front = go * math.cos(pitch) + world_up * math.sin(pitch)
        right = Vec3(*np.cross(world_up.xyz, go.xyz))
        front /= np.linalg.norm(front.xyz)

        right /= np.linalg.norm(right.xyz)
        go /= np.linalg.norm(go.xyz)

        up = Vec3(*np.cross(front.xyz, right.xyz))
        up /= np.linalg.norm(up.xyz)

        self.front = front
        self.right = right
        self.go = go
        self.up = up

        # --------------------
        # Movement
        # --------------------

        move = Vec3(0.0, 0.0, 0.0)

        self.sprint = get_key(self.render.window, glfw.KEY_LEFT_CONTROL)
        self.fly = get_key(self.render.window, glfw.KEY_F)

        self.speed = (
            13 if self.sprint else 30 if self.fly else 7
        )        

        if get_key(self.render.window, glfw.KEY_W):
            move += (self.go if not self.fly else self.front) * self.render.dt * self.speed

        if get_key(self.render.window, glfw.KEY_S):
            move -= (self.go if not self.fly else self.front) * self.render.dt * self.speed

        if get_key(self.render.window, glfw.KEY_A):
            move += self.right * self.render.dt * self.speed

        if get_key(self.render.window, glfw.KEY_D):
            move -= self.right * self.render.dt * self.speed

        # Don't move vertically
        if not self.fly:
            move[1] = 0

        if self.on_ground:
            self.jumps = 0
            self.trust_me = True

        physics_dt = max(self.render.dt, 0.0)
        # Match the legacy damping/gravity at 60 FPS while integrating by elapsed time.
        drag_rate = -60.0 * math.log(0.95)
        decay = math.exp(-drag_rate * physics_dt)
        gravity_acceleration = point_to_world_center * (
            self.gravity * drag_rate / (1.0 - 0.95)
        )
        velocity = Vec3(self.vel_x, self.vel_y, self.vel_z)
        velocity_decay = (1.0 - decay) / drag_rate
        gravity_displacement = (
            physics_dt / drag_rate
            - (1.0 - decay) / (drag_rate * drag_rate)
        )
        displacement = (
            velocity * velocity_decay
            + gravity_acceleration * gravity_displacement
        )
        velocity = (
            velocity * decay
            + gravity_acceleration * velocity_decay
        )

        if get_key(self.render.window, glfw.KEY_SPACE) and (self.on_ground or self.jumps < self.max_jumps) and self.trust_me:
            velocity = world_up * self.jump_strenght
            displacement = (
                velocity * velocity_decay
                + gravity_acceleration * gravity_displacement
            )
            velocity = (
                velocity * decay
                + gravity_acceleration * velocity_decay
            )
            self.vel_x, self.vel_y, self.vel_z = velocity
            self.jumps += 1
            self.trust_me = False
        else:
            self.vel_x, self.vel_y, self.vel_z = velocity

        if get_key(self.render.window, glfw.KEY_SPACE) != glfw.PRESS: self.trust_me = True

        if self.fly:
            displacement = Vec3(0.0, 0.0, 0.0)
            self.vel_x = 0
            self.vel_y = 0
            self.vel_z = 0

        move += displacement

        prev_pos = self.position.copy()

        #collision
        self.try_move(move, occupied)

        moved_by = self.position - prev_pos

        self.bps = round(sum(abs(component) for component in moved_by) / self.render.dt, 2)

        # --------------------
        # View matrix
        # --------------------

        self.eye_pos = self.position + Vec3(0, self.eye_height, 0)

        self.view = Matrix44.look_at(
            self.eye_pos,
            self.eye_pos + self.front,
            self.up
        )

    def collides(self, new_pos, occupied):
        thing = tuple(round(float(value)) for value in new_pos)
        return thing in occupied

    def collides_h(self, new_pos, occupied, height=2):
        a_pos = new_pos.copy()
        for h in range(height):
            if self.collides(a_pos, occupied):
                return True
            a_pos[1] += 1

        return False

    def try_move(self, new_position, occupied):
        self.position[0] += new_position[0]
        if self.collides_h(self.position, occupied):
            # print("colliding x")
            self.position[0] -= new_position[0]

        self.position[2] += new_position[2]
        if self.collides_h(self.position, occupied):
            # print("colliding z")
            self.position[2] -= new_position[2]

        self.position[1] += new_position[1]
        if self.collides_h(self.position, occupied):
            # print("colliding y")
            self.position[1] -= new_position[1]
            self.vel_y = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

def load_obj(file_path:str):
    positions = []
    normals = []
    uvs = []
    vertices = []
    indices = []
    vertex_map = {}
    idx = 0

    with open(file_path) as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()
                positions.append([float(x), float(y), float(z)])
            elif line.startswith("vn "):
                _, x, y, z = line.split()
                normals.append([float(x), float(y), float(z)])
            elif line.startswith("vt "):
                _, u, v = line.split()
                uvs.append([float(u), float(v)])
            elif line.startswith("f "):
                face = []
                for part in line.split()[1:]:
                    vals = part.split("/")

                    p = int(vals[0]) - 1

                    t = int(vals[1]) - 1 if len(vals) > 1 and vals[1] else 0

                    n = int(vals[2]) - 1 if len(vals) > 2 and vals[2] else 0
                    key = (p, t, n)
                    if key not in vertex_map:
                        px, py, pz = positions[p]
                        if len(normals) > 0:
                            nx, ny, nz = normals[n]
                        else:
                            nx, ny, nz = (0.0, 1.0, 0.0)
                        u, v = uvs[t]
                        v = 1 - v
                        vertices.extend([px, py, pz, nx, ny, nz, u, 1-v])
                        vertex_map[key] = idx
                        idx += 1
                    face.append(vertex_map[key])
                for i in range(1, len(face)-1):
                    indices.extend([face[0], face[i], face[i+1]])

    return [np.array(vertices, dtype='f8'), np.array(indices, dtype='i4')]

CUBE_MODEL_INFO = load_obj("assets/models/block.obj")

CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890:!? .-"

class InstancedText:
    def __init__(self, **kwargs):
        """
        args:
            render: Render instance
            charset: charset
            !ONLY USED BY HUDText! is_hud_text
        """

        self.ctx = kwargs["render"].ctx
        self.is_hud_text = kwargs.get("is_hud_text", False)
        self.program = kwargs["render"].HUDText_program if self.is_hud_text else kwargs["render"].text_program
        self.charset_lookup = {}
        for idx, key in enumerate(kwargs["charset"]):
            self.charset_lookup[key] = idx

        #quad facing X-
        self.vertices = np.array([
            # position              # normal          # uv
            0.0, 0.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 0.0,
            0.0, 1.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 1.0,
            0.0, 1.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 1.0,

            0.0, 1.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 1.0,
            0.0, 0.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 0.0,
            0.0, 0.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 0.0,
        ], dtype="f8")



        self.indices = np.array([
            0, 1, 2,

            3, 4, 5
        ], dtype="i4")


        self.vbo = self.ctx.buffer(np.asarray(self.vertices, dtype="f4").tobytes())
        self.ibo = self.ctx.buffer(self.indices.tobytes())

        self.instance_buffer = self.ctx.buffer(reserve=64 * 1024)
        self.layer_buffer = self.ctx.buffer(reserve=4 * 1024)

        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (
                    self.vbo,
                    '3f 3f 2f',
                    'in_position',
                    'in_normal',
                    'in_uv'
                ),
                (
                    self.instance_buffer,
                    '16f8/i',
                    'instance_model'
                ),
                (
                    self.layer_buffer,
                    '1i/i',
                    'instance_layer'
                ),
            ],
            self.ibo
        )

        self.instances = np.zeros((0, 4, 4), dtype="f8")
        self.tex_insta = np.zeros((0,), dtype="f8")

        self.texts = {}
        self._text_entries = []

    def _upload_text_instances(self):
        self.instance_buffer.orphan(max(self.instances.nbytes, 1))
        if self.instances.size:
            self.instance_buffer.write(self.instances.tobytes())

        layer_bytes = self.tex_insta.astype("i4").tobytes()
        self.layer_buffer.orphan(max(len(layer_bytes), 1))
        if layer_bytes:
            self.layer_buffer.write(layer_bytes)

    def _rebuild_text_instances(self):
        instances = []
        textures = []

        for entry in self._text_entries:
            text, position = entry["text"], entry["position"]
            valid_character_count = sum(character in self.charset_lookup for character in text.upper())
            # Autocenter: anchor is the middle of the drawn glyphs.
            # centered=False keeps legacy left-aligned (anchor = first glyph).
            center_offset = -valid_character_count / 2 if entry.get("centered", True) else 0
            ya_know = 0
            for character_index, character in enumerate(text.upper()):
                tex = self.charset_lookup.get(character, None)

                if tex is None:
                    print("Carachter not found:", character)
                    ya_know += 1
                    continue

                model = np.eye(4, dtype="f8")
                model[3, 0] = position[0]
                model[3, 1] = position[1]
                model[3, 2] = position[2] + center_offset + character_index - ya_know
                instances.append(model)
                textures.append(tex)

        self.instances = np.asarray(instances, dtype="f8").reshape((-1, 4, 4))
        self.tex_insta = np.asarray(textures, dtype="f8")
        self._upload_text_instances()

    @staticmethod
    def _normalize_centered(centered, count):
        if isinstance(centered, bool):
            return [centered] * count
        flags = list(centered)
        if len(flags) != count:
            raise ValueError("centered must match the number of texts")
        return [bool(f) for f in flags]

    def add_texts(self, texts, positions, identifiers=None, centered=True):
        if len(texts) != len(positions):
            raise ValueError("texts and positions must have the same length")

        if identifiers is None:
            identifiers = [None] * len(texts)
        elif len(identifiers) != len(texts):
            raise ValueError("identifiers must match the number of texts")

        centered_flags = self._normalize_centered(centered, len(texts))

        for text, position, identifier, center in zip(texts, positions, identifiers, centered_flags):
            if len(position) != 3:
                raise ValueError("text positions must be [x, y, z]")
            if identifier is not None and identifier in self.texts:
                raise ValueError(f"text identifier already exists: {identifier}")

            entry = {
                "text": text,
                "position": position.copy() if isinstance(position, Vec3) else Vec3(*position),
                "identifier": identifier,
                "centered": center,
            }
            self._text_entries.append(entry)
            if identifier is not None:
                self.texts[identifier] = entry

        self._rebuild_text_instances()

    def update_text(self, identifier: str, text=None, position=None, centered=None):
        if identifier not in self.texts:
            raise KeyError(f"unknown text identifier: {identifier}")

        entry = self.texts[identifier]
        if text is not None:
            entry["text"] = text
        if position is not None:
            if len(position) != 3:
                raise ValueError("text positions must be [x, y, z]")
            entry["position"] = position.copy() if isinstance(position, Vec3) else Vec3(*position)
        if centered is not None:
            entry["centered"] = bool(centered)

        self._rebuild_text_instances()

    def remove_text(self, identifier: str):
        if identifier not in self.texts:
            return False

        entry = self.texts.pop(identifier)
        self._text_entries.remove(entry)
        self._rebuild_text_instances()
        return True
            

    def set_visible(self, visible):
        """Show/hide switch (mobile parity, see InstancedModel)."""
        self._hidden = not bool(visible)

    def render(self):
        if getattr(self, "_hidden", False):
            return
        if len(self.instances) == 0: return
        self.vao.render(instances=len(self.instances))


class Collectible:
    _VERTEX_SHADER = """
        #version 330
        in vec2 in_position;
        in vec2 in_uv;
        in vec2 instance_position;
        in float instance_layer;

        uniform vec2 screen_size;
        uniform float TEXTURE_W;
        uniform float TEXTURE_H;
        uniform float ATLAS_W;
        uniform float ATLAS_H;

        out vec2 v_uv;

        void main() {
            vec2 pixel_position = instance_position + in_position * vec2(TEXTURE_W, TEXTURE_H);
            vec2 clip_position = vec2(
                pixel_position.x / screen_size.x * 2.0 - 1.0,
                1.0 - pixel_position.y / screen_size.y * 2.0
            );
            gl_Position = vec4(clip_position, 0.0, 1.0);

            float columns = max(floor(ATLAS_W / TEXTURE_W), 1.0);
            float rows = max(floor(ATLAS_H / TEXTURE_H), 1.0);
            float column = mod(instance_layer, columns);
            float row = floor(instance_layer / columns);
            vec2 tile_size = vec2(TEXTURE_W / ATLAS_W, TEXTURE_H / ATLAS_H);
            vec2 half_texel = 0.5 / vec2(TEXTURE_W, TEXTURE_H);
            vec2 local_uv = clamp(
                vec2(in_uv.x, 1.0 - in_uv.y),
                half_texel,
                vec2(1.0) - half_texel
            );
            v_uv = (vec2(column, row) + local_uv) * tile_size;
        }
    """
    _FRAGMENT_SHADER = """
        #version 330
        in vec2 v_uv;
        uniform sampler2DArray atlasArray;
        out vec4 fragColor;

        void main() {
            vec4 texel = texture(atlasArray, vec3(v_uv, 0.0));
            if (texel.a < 0.1)
                discard;
            fragColor = texel;
        }
    """

    def __init__(self, render):
        self.render_ = render
        self.ctx = render.ctx
        self.program = self.ctx.program(
            vertex_shader=self._VERTEX_SHADER,
            fragment_shader=self._FRAGMENT_SHADER,
        )
        self.program["atlasArray"].value = 2
        self.program["TEXTURE_W"].value = ITEM_W
        self.program["TEXTURE_H"].value = ITEM_H
        self.program["ATLAS_W"].value = ITEMS_W
        self.program["ATLAS_H"].value = ITEMS_H

        vertices = np.array([
            0, 0, 0, 0,
            0, 1, 0, 1,
            1, 1, 1, 1,
            1, 1, 1, 1,
            1, 0, 1, 0,
            0, 0, 0, 0,
        ], dtype="f8")
        self.vbo = self.ctx.buffer(np.asarray(vertices, dtype="f4").tobytes())
        self.instance_buffer = self.ctx.buffer(reserve=3 * 4)
        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (self.vbo, "2f 2f", "in_position", "in_uv"),
                (self.instance_buffer, "2f 1f/i", "instance_position", "instance_layer"),
            ],
        )
        self.instances = np.zeros((0, 4, 4), dtype="f8")
        self.tex_insta = np.zeros((0,), dtype="f8")

    def _upload(self):
        instance_data = np.column_stack(
            (self.instances[:, 3, :2], self.tex_insta)
        ).astype("f4", copy=False)
        self.instance_buffer.orphan(max(instance_data.nbytes, 1))
        if instance_data.size:
            self.instance_buffer.write(instance_data.tobytes())

    def add_collectibles(
        self,
        positions: list[Vec3],
        textures: list[int],
    ):
        positions = np.asarray(positions, dtype="f8")
        if positions.ndim == 1:
            positions = positions.reshape(1, -1)
        if positions.ndim != 2 or positions.shape[1] < 2:
            raise ValueError("collectible positions must contain x and y coordinates")
        if len(positions) != len(textures):
            raise ValueError("positions and textures must have the same length")

        new_models = np.repeat(
            np.eye(4, dtype="f8").reshape(1, 4, 4),
            len(positions),
            axis=0,
        )
        new_models[:, 3, 0] = positions[:, 0]
        new_models[:, 3, 1] = positions[:, 1]
        self.instances = np.concatenate((self.instances, new_models))
        self.tex_insta = np.concatenate(
            (self.tex_insta, np.asarray(textures, dtype="f8"))
        )
        self._upload()
    
    def remove_all(self):

        del self.instances
        del self.tex_insta

        self.instances = np.zeros((0, 4, 4), dtype="f8")
        self.tex_insta = np.zeros((0,), dtype="f8")

        self._upload()

    def render(self):
        if len(self.instances) == 0:
            return
        screen_width, screen_height = self.render_.get_window_size()
        if screen_width <= 0 or screen_height <= 0:
            return
        self.program["screen_size"].value = (screen_width, screen_height)
        self.render_.items_texture.use(location=2)
        self.ctx.disable(moderngl.DEPTH_TEST)
        try:
            self.vao.render(instances=len(self.instances))
        except Exception as e:
            print("Error while rendering blok items!!!!!!!")
            print(e)

        self.ctx.enable(moderngl.DEPTH_TEST)

class HUDText(InstancedText):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, is_hud_text=True)

        self.screen_size = kwargs.get("screen_size", (WIDTH, HEIGHT))

        self.program["atlasArray"] = kwargs.get("texture_unit", 1)
        self.program["screenSize"].value = self.screen_size
        self.program["TEXTURE_W"] = kwargs.get("texture_width", CHR_W)
        self.program["TEXTURE_H"] = kwargs.get("texture_height", CHR_H)
        self.program["ATLAS_W"] = kwargs.get("atlas_width", CHAR_W)
        self.program["ATLAS_H"] = kwargs.get("atlas_height", CHAR_H)

        self._render = kwargs["render"]
        self.callbacks = {}
        self._mouse_was_pressed = False

    def add_texts(self, texts, positions, identifiers=None, callbacks=None, centered=True):
        if callbacks is None:
            callbacks = [None] * len(texts)
        elif len(callbacks) != len(texts):
            raise ValueError("callbacks must match the number of texts")

        hud_positions = []
        for position in positions:
            if len(position) != 2:
                raise ValueError("HUD text positions must be [x, y] pixel coordinates")
            hud_positions.append(Vec3(position[0], position[1], 0))

        super().add_texts(texts, hud_positions, identifiers, centered=centered)
        added_entries = self._text_entries[-len(texts):] if texts else []
        for entry, callback in zip(added_entries, callbacks):
            entry["callback"] = callback
            if entry["identifier"] is not None and callback is not None:
                self.callbacks[entry["identifier"]] = callback

    def update_text(self, identifier: str, text=None, position=None, centered=None):
        hud_position = None
        if position is not None:
            if len(position) != 2:
                raise ValueError("HUD text positions must be [x, y] pixel coordinates")
            hud_position = Vec3(position[0], position[1], 0)

        super().update_text(identifier, text, hud_position, centered=centered)

    def remove_text(self, identifier: str):
        removed = super().remove_text(identifier)
        if removed:
            self.callbacks.pop(identifier, None)
        return removed

    def get_text(self, identifier: str):
        return self.texts[identifier]

    def _handle_click(self):
        mouse_pressed = self._render.get_mouse_button(self._render.MOUSE_BUTTON_LEFT) == self._render.PRESS
        if mouse_pressed and not self._mouse_was_pressed:
            cursor_x, cursor_y = self._render.get_cursor_pos()
            window_width, window_height = self._render.get_window_size()
            if window_width > 0 and window_height > 0:
                cursor_x *= self.screen_size[0] / window_width
                cursor_y *= self.screen_size[1] / window_height

                for entry in reversed(self._text_entries):
                    callback = entry.get("callback")
                    if callback is None:
                        continue

                    x, y, _ = entry["position"]
                    text_width = sum(
                        character in self.charset_lookup
                        for character in entry["text"].upper()
                    ) * CHR_W
                    # Same span the rebuild draws: centered anchors sit in
                    # the middle, left-aligned (centered=False) at the start.
                    if entry.get("centered", True):
                        box_x0, box_x1 = x - text_width / 2, x + text_width / 2
                    else:
                        box_x0, box_x1 = x, x + text_width
                    if box_x0 <= cursor_x < box_x1 and y <= cursor_y < y + CHR_H:
                        callback()
                        break

        self._mouse_was_pressed = mouse_pressed

    def render(self):
        if getattr(self, "_hidden", False):
            return
        self._handle_click()
        if len(self.instances) == 0:
            return

        self.ctx.disable(moderngl.DEPTH_TEST)
        try:
            super().render()
        finally:
            self.ctx.enable(moderngl.DEPTH_TEST)

last_invscr = 4

class INVSCR:
    _VERTEX_SHADER = """
        #version 330
        in vec2 in_position;
        in vec2 in_uv;

        uniform vec2 screen_size;
        uniform vec2 position;
        uniform vec2 size;

        out vec2 texture_uv;

        void main() {
            vec2 pixel_position = position + in_position * size;
            vec2 clip_position = vec2(
                pixel_position.x / screen_size.x * 2.0 - 1.0,
                1.0 - pixel_position.y / screen_size.y * 2.0
            );
            gl_Position = vec4(clip_position, 0.0, 1.0);
            texture_uv = in_uv;
        }
    """
    _FRAGMENT_SHADER = """
        #version 330
        in vec2 texture_uv;
        uniform sampler2D inventory_texture;
        out vec4 frag_color;

        void main() {
            frag_color = texture(inventory_texture, texture_uv);
        }
    """

    def __init__(
        self,
        render: Render,
        image_,
        pos_x,
        pos_y,
        scale=1.0,
    ):

        global last_invscr

        width, height = image_.size
        
        if width <= 0 or height <= 0:
            raise ValueError("inventory scroll width and height must be positive")
        if scale <= 0:
            raise ValueError("inventory scroll scale must be positive")

        self.render_context = render
        self.ctx = render.ctx
        self.scale = float(scale)
        self.width = float(width) * self.scale
        self.height = float(height) * self.scale

        self.tex_thing = last_invscr

        last_invscr += 1

        image = image_.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        self.texture = self.ctx.texture(image.size, 4, image.tobytes())
        self.texture.filter = (moderngl.NEAREST, moderngl.NEAREST)

        self.program = self.ctx.program(
            vertex_shader=self._VERTEX_SHADER,
            fragment_shader=self._FRAGMENT_SHADER,
        )
        self.program["inventory_texture"].value = self.tex_thing

        self.pos_x = pos_x 
        self.pos_y = pos_y

        # Winding is counter-clockwise after the pixel-to-clip Y flip.
        vertices = np.array([
            0, 0, 0, 1,
            0, 1, 0, 0,
            1, 1, 1, 0,
            0, 0, 0, 1,
            1, 1, 1, 0,
            1, 0, 1, 1,
        ], dtype="f4")
        self.vertex_buffer = self.ctx.buffer(vertices.tobytes())
        self.vao = self.ctx.vertex_array(
            self.program,
            [(self.vertex_buffer, "2f 2f", "in_position", "in_uv")],
        )

    def render(self):
        screen_width, screen_height = self.render_context.get_window_size()
        if screen_width <= 0 or screen_height <= 0:
            return

        if self.pos_x == "center":
            calc_x = (screen_width - self.width) / 2
        elif self.pos_x == "left":
            calc_x = 0
        elif self.pos_x == "right":
            calc_x = screen_width - self.width
        else:
            raise ValueError("pos_x argument must be center, left or right")

        if self.pos_y == "center":
            calc_y = (screen_height - self.height) / 2
        elif self.pos_y == "top":
            calc_y = 0
        elif self.pos_y == "bottom":
            calc_y = screen_height - self.height
        else:
            raise ValueError("pos_y argument must be center, top or bottom")


        self.program["screen_size"].value = (screen_width, screen_height)
        self.program["size"].value = (self.width, self.height)
        self.program["position"].value = (
            calc_x,
            calc_y
        )

        self.texture.use(location=self.tex_thing)
        self.ctx.disable(moderngl.DEPTH_TEST)
        try:
            self.vao.render()
        finally:
            self.ctx.enable(moderngl.DEPTH_TEST)


if __name__ == "__main__":
    def init(render:Render):
        GRASS = 0

        render.camera = Camera([0, 0, 0], render)

        glfw.set_cursor_pos_callback(render.window, render.camera.cursor_move)

        FOV = 60
        
        PROJECTION = np.array(Matrix44.perspective_projection(FOV, WIDTH/HEIGHT, 0.1, 1000), dtype='f8')


        render.blocks_program["atlasArray"] = 0
        render.blocks_program["projection"].write(PROJECTION)
        render.blocks_program["frame"] = 0
        render.blocks_program["chance"] = -1
        render.blocks_program["TEXTURE_W"] = TEXTURE_W
        render.blocks_program["TEXTURE_H"] = TEXTURE_H
        render.blocks_program["ATLAS_W"] = ATLAS_W
        render.blocks_program["ATLAS_H"] = ATLAS_H

        render.text_program["atlasArray"] = 1
        render.text_program["projection"].write(PROJECTION)
        render.text_program["frame"] = 0
        render.text_program["chance"] = -1
        render.text_program["TEXTURE_W"] = CHR_W
        render.text_program["TEXTURE_H"] = CHR_H
        render.text_program["ATLAS_W"] = CHAR_W
        render.text_program["ATLAS_H"] = CHAR_H

        render.MODEL = Model(render)

        render.MODEL.add_model("block", vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1])
       # render.MODEL.add_instances([[10, 1.8, 0]], [GRASS], "block")

        render.text = InstancedText(ctx=render.ctx, program=render.text_program, charset=CHARSET)
        print(render.text_program)


        render.text.add_texts(["A"], [Vec3(5, 1.8, 0)])
        print("instances:", render.text.instances)
        print("textures:", render.text.tex_insta)
        print("instance buffer:", render.text.instance_buffer.size)
        print("layer buffer:", render.text.layer_buffer.size)


    def update(render:Render):
        render.ctx.clear(0, 0, 0)
        render.camera.update(set())

        render.blocks_program["view"].write(render.camera.view.astype("f8").tobytes())
        render.blocks_program["viewPos"].write(render.camera.position.xyz.astype('f8').tobytes())

        render.text_program["view"].write(render.camera.view.astype("f8").tobytes())
        render.text_program["lightPos"].value = (0, 0, 0)
        render.text_program["viewPos"].write(render.camera.position.xyz.astype('f8').tobytes())


        render.MODEL.render()
        render.text.render()

    render = Render(init, update)
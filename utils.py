import math
from random import Random
import random
from typing import Callable
from decorators import cache

# Structure blueprints loaded once (was open()+readlines()+strip per tree
# placement; @cache key str(x,y,z,...) never hit since positions unique and
# leaked every placement forever).
_STRUCTURE_BLUEPRINTS: dict[tuple[str, str], tuple] = {}

def _load_structure_blueprint(type: str, folder: str):
    key = (folder, type)
    hit = _STRUCTURE_BLUEPRINTS.get(key)
    if hit is not None:
        return hit
    try:
        with open(f"{folder}/structures/{type}.txt", "r") as f:
            content = [line.strip() for line in f]
    except Exception:
        _STRUCTURE_BLUEPRINTS[key] = ()
        return ()
    # Pack as flat tuple of (dx, dy, dz, block_name) to avoid per-call split.
    out = []
    for i in range(0, len(content) - 3, 4):
        try:
            out.append((int(content[i]), int(content[i + 1]),
                        int(content[i + 2]), content[i + 3]))
        except (ValueError, IndexError):
            continue
    blueprint = tuple(out)
    _STRUCTURE_BLUEPRINTS[key] = blueprint
    return blueprint


def generate_tree(x: int, y: int, z: int, type: str, folder: str):
    blueprint = _load_structure_blueprint(type, folder)
    if not blueprint:
        return {"positions": [], "textures": []}
    # Localize list appends; offsets applied here (no file IO).
    positions = []
    textures = []
    _papp = positions.append
    _tapp = textures.append
    _y1 = y + 1
    for dx, dy, dz, block_name in blueprint:
        _papp((dx + x, dy + _y1, dz + z))
        _tapp(block_name)
    return {"positions": positions, "textures": textures}

from math import floor, hypot
from Block import Block

def chunk_time(label, t0):
    """Env-gated stage timing for chunk-pipeline diagnosis.

    Set OMEFEG_CHUNK_TIMING=1 to print per-stage milliseconds (worker
    bakes, main-thread finalizes, occupancy, evicts, dummy rebuilds).
    ~1 microsecond and allocation-free when off: run it, reproduce the
    stutter, and the slowest stage names itself.
    """
    import os as _os
    import time as _t
    try:
        if _os.environ.get("OMEFEG_CHUNK_TIMING") != "1":
            return
    except Exception:
        return
    try:
        print(f"[chunk-time] {label}: {(_t.perf_counter() - t0) * 1000.0:.1f}ms",
              flush=True)
    except Exception:
        pass

MIN_WORLD_Y = -64

def generate_terrain(size=10, height_map=None, biomes_map=None, offsett=[0, 0, 0], rules_:dict[str, int | list[int] | str]={}, random_seed:random.Random=random.Random(random.randint(0, 9_223_372_036_854_775_807)), biomes=True, sin_world=False) -> list[Block]:
    """
    Generates terrain as a list of [x, y, z] block positions.
    height_map: optional function f(x, z) -> y
    rules: a list of terrain generation rules

    NOTE: no @cache on purpose. The old cache key stringified the entire
    rules dict + heightmap objects per chunk (KBs of str() per call),
    never hit (offsets are unique), leaked every chunk forever, and was
    wrong when random structures were involved.
    """
    blocks: list[Block] = []
    trees = []
    can_generate = True
    if biomes:
        # Single HeightMap lookup per chunk (pure function of the coords:
        # frozen bands, no expansion, no locks).
        bom = rules_["all"][biomes_map[offsett[0], offsett[2]]]
        rules = rules_[bom]["rules"]
        vegetation = rules_[bom]
    else:
        bom = "plains"
        rules = rules_[bom]["rules"]
        rules["structures"] = []
        vegetation = rules_[bom]

    # Hoisted loop invariants (were re-fetched per column before).
    _formula = rules["generationFormula"] if not sin_world else None
    _structures_rules = rules["structures"]  # type: ignore
    _water_rules = rules["water"]  # type: ignore
    _terrain_thickness = rules["terrain_height"]  # type: ignore
    _water_level = int(_water_rules["level"])  # type: ignore
    _water_depth = int(_water_rules["depth"])  # type: ignore
    _all_water_ys = [-(i + _water_level) for i in range(_water_depth)]
    _water_set = set(_all_water_ys)
    _top_block = vegetation["topBlock"]  # type: ignore
    _bottom_block = vegetation["bottomBlock"]  # type: ignore
    _ox, _oy, _oz = offsett[0], offsett[1], offsett[2]
    _use_heightmap = height_map is not None
    # Branch once on formula (was `match` string compare per column).
    # 0=perlinNoise*5, 1=flat, 2=perlinFlat, 3=cone, 4=sin/raw*5.
    if _formula is None:
        _fid = 4
    elif _formula == "perlinNoise":
        _fid = 0
    elif _formula == "flat":
        _fid = 1
    elif _formula == "perlinFlat":
        _fid = 2
    elif _formula == "cone":
        _fid = 3
    else:
        _fid = 4
    # Cone center hoisted (was recomputed per column).
    _cone_h = _ox + size / 2
    _cone_j = _oz + size / 2
    # Structure chances pre-parsed (was float() per column per rule).
    _struct_probs = []
    for _sr in _structures_rules:
        try:
            _struct_probs.append((
                _sr["name"], _sr["folder"],
                float(_sr["chance"]) / 100.0,
                ("tree" in _sr["name"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    _has_structs = bool(_struct_probs)
    # Resolve constructors once per chunk (was a dict lookup per block,
    # ~6700 lookups of the same 2-4 names). Fail fast on unknown names:
    # the old code printed a warning per block and appended None, leaving
    # garbage in the chunk that only exploded downstream.
    _top_ctor = _BLOCK_CTOR_BY_NAME.get(_top_block)
    _bottom_ctor = _BLOCK_CTOR_BY_NAME.get(_bottom_block)
    _stone_ctor = _BLOCK_CTOR_BY_NAME.get("stone")
    _water_ctor = _BLOCK_CTOR_BY_NAME.get("water")
    if (_top_ctor is None or _bottom_ctor is None
            or _stone_ctor is None or _water_ctor is None):
        raise ValueError(
            f"unknown block in worldgen rules: top={_top_block!r} "
            f"bottom={_bottom_block!r}")
    # Hot-loop locals (avoid global/attr lookups per block).
    _gen_tree = generate_tree
    _floor = floor
    _hm = height_map
    _bappend = blocks.append
    # Deterministic per-chunk RNG (the passed seed is derived per chunk,
    # so the same chunk always grows the same structures in the same
    # order, on workers and on the sync path alike). Anything else (a
    # fresh seed per column, let alone per thread) desyncs multiplayer
    # worlds and makes output depend on scheduling.
    _rnd = random_seed.random
    _sqrt = math.sqrt
    _x0, _x1 = offsett[0], size + offsett[0]
    _z0, _z1 = offsett[2], size + offsett[2]
    _thick = _terrain_thickness
    _low = MIN_WORLD_Y

    # One sequential pass (see above on threading): per column, surface,
    # dirt cap, stone fill down to the bedrock floor. Branch order and
    # append order match block-for-block so output (and RNG consumption)
    # is identical for identical inputs.
    for x in range(_x0, _x1):
        _xf = x / 10
        for z in range(_z0, _z1):
            if _fid == 0:
                y = _hm(_xf, z / 10) * 5 if _use_heightmap else 0
            elif _fid == 1:
                y = _oy
            elif _fid == 2:
                y = _hm(_xf, z / 10) if _use_heightmap else 0
            elif _fid == 3:
                _dx = x - _cone_h
                _dz = z - _cone_j
                y = -(_sqrt(_dx * _dx + _dz * _dz) / 0.5 - 15)
            else:
                y = _hm(_xf, z / 10) * 5 if _use_heightmap else 0

            y = _floor(y) + _oy

            if y in _water_set:
                for a in _all_water_ys:
                    if a != y:
                        _bappend(_water_ctor([x, a, z]))
                _bappend(_water_ctor([x, y, z]))
            else:
                if can_generate and _has_structs:
                    #generate structures
                    for _sname, _sfolder, _prob, _is_tree in _struct_probs:
                        if _rnd() < _prob:
                            if not _is_tree:
                                trees.clear()
                                can_generate = False
                            trees.append(_gen_tree(x, y, z, _sname, _sfolder))

                _bappend(_top_ctor([x, y, z]))
                for i in range(1, _thick + 1):
                    _bappend(_bottom_ctor([x, y - i, z]))
                for i in range(_low + 1, y - _thick):
                    _bappend(_stone_ctor([x, i, z]))
                # Bedrock floor: plain stone. It is unbreakable because
                # World.destroy_block refuses y <= MIN_WORLD_Y, so no
                # separate block type is needed (a new type would require
                # a texture id, an atlas tile and a save-format entry).
                _bappend(_stone_ctor([x, _low, z]))

    # Structures resolve names per block (few hundred, varied types).
    _get_block = get_block
    for i in trees:
        for j, k in zip(i["positions"], i["textures"]):
            _bappend(_get_block(k, j))

    return blocks

try:
    import openal

except Exception as _e:
    # Android / missing recipe: audio is optional, playsound() below
    # degrades to a no-op dummy instead of crashing the import.
    print(f"[utils] openal unavailable, loading kivy: {_e}")
    openal = None  # type: ignore

    try:
        from kivy.core.audio import SoundLoader
    except Exception as _e:
        print(f"[utils] kivy.core.audio is unavailable, audio is disabled: {_e}")

        SoundLoader = None

from Number import Number


class SoundPlayer:
    def __init__(self):
        self.playing = False
        self.source = None
        self.dt = 0

    def playsound(self, sound:str, position:tuple[Number, Number, Number]=(0, 0, 0), sound_position:tuple[Number, Number, Number]=(0, 0, 0), orientation:tuple[Number, Number, Number, Number, Number, Number]=(0, 0, -1, 0, 1, 0), loop:bool=False):
        self.dt = 0

        if openal:
            listener = openal.oalGetListener()
            listener.set_position(position)
            listener.set_orientation(orientation)

            source = openal.oalOpen(sound)
            source.set_position(sound_position)
            source.set_looping(loop)
            source.play()
            
            self.source = source

        elif SoundLoader:
            source = SoundLoader.load(sound)

            source.play()

            self.source = source

    def stop(self):
        if self.source: self.source.stop()
        self.source = None

    def __check_sound(self):
        if self.source.state == "play":
            if self.dt < self.source.length + 100:
                return True

            else:
                self.source.stop()
                return False

    def is_playing(self, dt):
        self.dt += dt
        if self.source:
            if openal is not None:
                if self.source.get_state() == openal.AL_PLAYING:
                    return True
                else:
                    return False
            
            elif SoundLoader is not None:
                return self.__check_sound()
            
        else:
            return False

import asyncio
try:
    from desktop_notifier import DesktopNotifier, Icon
    from pathlib import Path

    notifier = DesktopNotifier()
    notifier.app_icon = Icon(path=Path("assets/icon.png").resolve())
    notifier.app_name = "Game"
except Exception as _e:
    # Android has no desktop notifier; fall back to log output.
    print(f"[utils] desktop_notifier unavailable, notifications disabled: {_e}")
    DesktopNotifier = None  # type: ignore
    Icon = None  # type: ignore
    Path = None  # type: ignore
    notifier = None

async def main(title, message):
    if notifier is None:
        print(f"[notification] {title}: {message}")
        return
    await notifier.send(title, message)

def notification(title, message):
    if notifier is None:
        print(f"[notification] {title}: {message}")
        return
    asyncio.run(main(title, message))

try:
    import requests
except Exception as _e:
    print(f"[utils] requests unavailable: {_e}")
    requests = None  # type: ignore

@cache
def get_username_and_uuid(username, password):
    if requests is None:
        return "network disabled on this build"
    url = "https://tombenax.pythonanywhere.com/login"

    data = {
        "username": username,
        "password": password,
        "client": "game"
    }

    r = requests.post(url, data=data)
    res = r.json()

    if res["status"] == "valid":
        return res["token"]
    elif res["status"] == "error":
        return "invalid credentials"
    elif res["status"] == "disabled":
        return "account disabled"

@cache
def closest_range(start:int, stop:int, step:int=1) -> list[int]:
    final_range = []
    middle = int((stop+start)/2)
    final_range.append(middle)
    for iteration in range(1, len(range(start, stop+1, step))+1):
        final_range.append(middle-step*iteration)
        final_range.append(middle+step*iteration)
    
    return final_range

@cache
def square_range(center, layers: int, step: int = 1) -> list[list[int]]:
    cx, _, cy = center
    result = [[cx, cy]]

    for r in range(layers + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r:
                    result.append([
                        cx + dx * step,
                        cy + dy * step
                    ])

    return result

# Conservative chunk visibility for render culling (pure math, no GL).
# A chunk column is 10 wide; voxels span MIN_WORLD_Y..~+30 with the
# tallest structures (conservative top). Chunks are only skipped when
# provably outside the view (plus a 5-degree margin that can only keep
# more, never cull a visible chunk). When in doubt the functions return
# "visible": the worst failure mode is drawing a chunk, not a hole.
_CHUNK_HALF_XZ = 8.0  # > 5*sqrt(2): corner distance from column center
_CHUNK_Y0 = float(MIN_WORLD_Y)
_CHUNK_Y1 = 30.0
_CULL_MARGIN_RAD = math.radians(5.0)
_CULL_NEAR_XZ = 12.0  # within this horizontal distance: always visible

def camera_frustum(camera, fov_deg=60.0, aspect=16.0 / 9.0):
    """Extract culling params from a camera, or None when unusable.

    Returns (eye, front, pitch_rad, half_h, half_v). Any missing/garbled
    attribute yields None (caller draws everything, like before).
    """
    try:
        eye = camera.eye_pos
        front = camera.front
        pitch = math.radians(float(camera.pitch))
        fov = math.radians(float(fov_deg))
    except (AttributeError, TypeError, ValueError):
        return None
    try:
        aspect = float(aspect)
        if not (aspect > 0):
            raise ValueError
    except (TypeError, ValueError):
        aspect = 16.0 / 9.0
    half_v = fov / 2.0
    half_h = math.atan(math.tan(half_v) * aspect)
    return (eye, front, pitch, half_h, half_v)

def chunk_visible_from(eye, front, pitch_rad, half_h, half_v, chunk_pos):
    """True unless the chunk provably cannot be seen. See above."""
    try:
        ex, ey, ez = float(eye[0]), float(eye[1]), float(eye[2])
        fx, fz = float(front[0]), float(front[2])
        cx = float(chunk_pos[0]) + 5.0
        cz = float(chunk_pos[2]) + 5.0
        pitch_rad = float(pitch_rad)
        half_h = float(half_h)
        half_v = float(half_v)
    except (TypeError, IndexError, ValueError):
        return True
    dx, dz = cx - ex, cz - ez
    d = math.hypot(dx, dz)
    if d < _CULL_NEAR_XZ:
        return True
    fl = math.hypot(fx, fz)
    if fl > 1e-6:
        # Horizontal bearing outside halfH (+ corner extent + margin).
        cosang = (dx * fx + dz * fz) / (d * fl)
        if cosang > 1.0:
            cosang = 1.0
        elif cosang < -1.0:
            cosang = -1.0
        extra = math.asin(min(1.0, _CHUNK_HALF_XZ / d))
        if math.acos(cosang) > half_h + extra + _CULL_MARGIN_RAD:
            return False
    # Vertical wedge vs the voxel band (looking up/down is handled here,
    # including the straight-up case where the bearing above is void).
    e0 = math.atan2(_CHUNK_Y0 - ey, d)
    e1 = math.atan2(_CHUNK_Y1 - ey, d)
    lo = pitch_rad - half_v - _CULL_MARGIN_RAD
    hi = pitch_rad + half_v + _CULL_MARGIN_RAD
    if e1 < lo or e0 > hi:
        return False
    return True

import numpy as np

# Face order matches block.obj triangulation groups (see Render.load_obj):
# each cube contributes 24 verts = 6 faces x 4 verts, so face f owns rows
# f*4:(f+1)*4 with local indices [0,1,2,0,2,3]. Verified against the
# shipped asset: normals per group are -Z,+X,+Z,-X,+Y,-Y in order.
_FACE_OFFSETS = ((0, 0, -1), (1, 0, 0), (0, 0, 1), (-1, 0, 0), (0, 1, 0), (0, -1, 0))
# == allBlocks.WATER. Water never occludes (faces touching it stay visible
# so terrain shows through), but water-water interiors are culled.
_WATER_TEX = 10

def export_and_load_chunk(models: list[list[int | float]], _layers_, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y):
    """
    Face-culled chunk mesh builder.

    Only emits cube faces touching air (or water, for opaque blocks):
    fully buried stone contributes zero vertices, so a deep
    MIN_WORLD_Y fill costs RAM/disk/physics but (almost) no GPU vertex
    load. Culling is chunk-local -- neighbours in other chunks count as
    air -- so border walls are kept and no holes can appear at chunk
    seams (no cross-chunk rebuild tracking needed).

    Water rule: an opaque face next to water is kept (visible through
    it); a water face next to opaque is culled (hidden inside it);
    water next to water is culled (interior).

    Merges the visible faces without the old (N, V, 8) 3D temporary
    and without the 4x np.where tile-row remap passes. Final row is
    exactly ``layer // TEXTURES_X`` (the old flip of a flip), computed
    once.

    NOTE: no @cache on purpose. The old cache key stringified the full
    positions/textures lists plus the cube arrays per build (MBs of str()),
    never hit for new chunks, and pinned every chunk mesh in RAM forever.
    Thread workers call this directly (pure NumPy + local set/dict, no
    shared state).
    """

    if models is None or _layers_ is None:
        return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')
    try:
        if len(models) == 0:
            return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')
    except TypeError:
        return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')

    # Parse voxel coords ONCE as int32 (C-speed object parsing), then
    # derive the float32 render offsets with a cheap C cast. The old
    # float-first order paid full Python-object parsing twice (once per
    # dtype) on this ~20k-int hot path.
    pi = np.asarray(models, dtype=np.int32)
    if pi.ndim == 1:
        pi = pi.reshape(1, 3)
    positions = pi.astype(np.float32)
    layers = np.asarray(_layers_, dtype=np.int32).reshape(-1)

    n = min(int(positions.shape[0]), int(layers.shape[0]))
    if n == 0:
        return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')
    if int(positions.shape[0]) != n:
        positions = positions[:n]
    if int(layers.shape[0]) != n:
        layers = layers[:n]

    # Views, not copies (CUBE_MODEL_INFO is already f4/i4).
    base_vertices = np.asarray(CUBE_MODEL_INFO[0]).reshape(-1, 8)
    if base_vertices.dtype != np.float32:
        base_vertices = base_vertices.astype(np.float32, copy=False)

    v_count = int(base_vertices.shape[0])
    if v_count == 0:
        return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')
    if v_count != 24:
        # Unexpected cube layout (not 6x4 verts): fall back to the old
        # unculled per-cube merge rather than emitting garbage.
        base_indices = np.asarray(CUBE_MODEL_INFO[1]).reshape(-1)
        if base_indices.dtype != np.int32:
            base_indices = base_indices.astype(np.int32, copy=False)
        i_count = int(base_indices.shape[0])
        if n == 0 or i_count == 0:
            return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')
        base_pos = base_vertices[:, 0:3]
        base_nor = base_vertices[:, 3:6]
        base_uv = base_vertices[:, 6:8]
        merged = np.empty((n * v_count, 8), dtype=np.float32)
        merged[:, 0:3] = np.tile(base_pos, (n, 1))
        merged[:, 0:3] += np.repeat(positions, v_count, axis=0)
        merged[:, 3:6] = np.tile(base_nor, (n, 1))
        inv_tx = 1.0 / float(TEXTURES_X)
        inv_ty = 1.0 / float(TEXTURES_Y)
        bx = (layers % TEXTURES_X).astype(np.float32, copy=False) * inv_tx
        by = (layers // TEXTURES_X).astype(np.float32, copy=False) * inv_ty
        tu = np.tile(base_uv[:, 0], n) * inv_tx
        tv = np.tile(base_uv[:, 1], n) * inv_ty
        merged[:, 6] = tu + np.repeat(bx, v_count)
        merged[:, 7] = tv + np.repeat(by, v_count)
        merged_indices = np.tile(base_indices, n) + np.repeat(
            np.arange(n, dtype=np.int32) * np.int32(v_count), i_count)
        return merged, merged_indices.astype(np.int32, copy=False)

    # Chunk-local occupancy -> visible (block, face) pairs. Primary path
    # is a dense bit-grid with a 1-cell halo (fully vectorized neighbour
    # lookups, no per-block Python loop: the loop version cost ~25ms per
    # 6700-block chunk on the main-thread _update_dummy / save-load
    # paths). Out-of-chunk neighbours read as air (halo), so border walls
    # are kept and no seam holes can appear.
    # `pi` (int32 voxel coords) is reused directly: no second conversion.
    mn = pi.min(axis=0)
    mx = pi.max(axis=0)
    sx, sy, sz = (int(mx[0]) - int(mn[0]) + 1,
                  int(mx[1]) - int(mn[1]) + 1,
                  int(mx[2]) - int(mn[2]) + 1)
    # Fixed cell cap (4M cells = 4MB): real chunks are ~10x70x10 plus
    # small structures (biggest asset is 8x8x8), so they always take the
    # dense path; only pathological spreads fall back.
    if sx * sy * sz <= 4_000_000:
        gx = pi[:, 0] - int(mn[0]) + 1
        gy = pi[:, 1] - int(mn[1]) + 1
        gz = pi[:, 2] - int(mn[2]) + 1
        occ = np.zeros((sx + 2, sy + 2, sz + 2), dtype=np.bool_)
        occ[gx, gy, gz] = True
        is_water = layers == _WATER_TEX
        not_water = ~is_water
        # One combined gather for all 6 neighbours (face-major rows):
        # f0 -Z, f1 +X, f2 +Z, f3 -X, f4 +Y, f5 -Y. A single fancy
        # index beats 6-12 separate gathers (per-call overhead dominates
        # on these tiny grids).
        NX = np.concatenate((gx, gx + 1, gx, gx - 1, gx, gx))
        NY = np.concatenate((gy, gy, gy, gy, gy + 1, gy - 1))
        NZ = np.concatenate((gz - 1, gz, gz + 1, gz, gz, gz))
        occ_n = occ[NX, NY, NZ].reshape(6, n)
        if bool(is_water.any()):
            wat = np.zeros_like(occ)
            wat[gx[is_water], gy[is_water], gz[is_water]] = True
            vis = ~occ_n | (wat[NX, NY, NZ].reshape(6, n) & not_water)
        else:
            # No water in this chunk: skip the water grid AND its gather.
            vis = ~occ_n
        face_id, face_block = np.where(vis)
        face_block = face_block.astype(np.int32, copy=False)
        face_id = face_id.astype(np.int32, copy=False)
        face_count = int(face_block.shape[0])
        if face_count == 0:
            return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')
    else:
        # Sparse/scattered input (grid would blow up): set-based fallback
        # with the same visibility rule.
        pos_keys = [(int(pi[i, 0]), int(pi[i, 1]), int(pi[i, 2]))
                    for i in range(n)]
        tex_by_pos = {}
        for i, k in enumerate(pos_keys):
            tex_by_pos[k] = int(layers[i])
        _get = tex_by_pos.get
        face_blocks = []
        face_ids = []
        _bapp = face_blocks.append
        _fapp = face_ids.append
        for i in range(n):
            x, y, z = pos_keys[i]
            cur_is_water = int(layers[i]) == _WATER_TEX
            for f, (ox, oy, oz) in enumerate(_FACE_OFFSETS):
                nt = _get((x + ox, y + oy, z + oz))
                if nt is None or (nt == _WATER_TEX and not cur_is_water):
                    _bapp(i); _fapp(f)
        if not face_blocks:
            return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')
        face_block = np.asarray(face_blocks, dtype=np.int32)
        face_id = np.asarray(face_ids, dtype=np.int32)
        face_count = int(face_block.shape[0])

    base_faces = base_vertices.reshape(6, 4, 8)

    pos_f = positions[face_block]  # (F, 3)
    lay_f = layers[face_block]  # (F,)

    # Atlas remap: column = layer % TX, row-from-top = layer // TX.
    inv_tx = 1.0 / float(TEXTURES_X)
    inv_ty = 1.0 / float(TEXTURES_Y)
    bx = (lay_f % TEXTURES_X).astype(np.float32, copy=False) * inv_tx
    by = (lay_f // TEXTURES_X).astype(np.float32, copy=False) * inv_ty

    fpos = base_faces[face_id, :, 0:3]  # (F, 4, 3)
    fnor = base_faces[face_id, :, 3:6]  # (F, 4, 3)
    fuv = base_faces[face_id, :, 6:8]  # (F, 4, 2)

    merged = np.empty((face_count * 4, 8), dtype=np.float32)
    merged[:, 0:3] = (fpos + pos_f[:, None, :]).reshape(-1, 3)
    merged[:, 3:6] = fnor.reshape(-1, 3)
    merged[:, 6] = (fuv[:, :, 0] * inv_tx + bx[:, None]).reshape(-1)
    merged[:, 7] = (fuv[:, :, 1] * inv_ty + by[:, None]).reshape(-1)

    # Every face shares local pattern [0,1,2,0,2,3].
    merged_indices = (
        np.tile(np.array([0, 1, 2, 0, 2, 3], dtype=np.int32), face_count)
        + np.repeat(np.arange(face_count, dtype=np.int32) * 4, 6)
    )

    return merged, merged_indices.astype(np.int32, copy=False)


from allBlocks import *
from colorama import Fore, Style


# Dict/tuple lookup (was `match` per block; ~600 lookups per chunk on the
# hot terrain + save-load paths). Tables built once after allBlocks import.
_BLOCK_CTOR_BY_NAME: dict[str, type] = {
    "grass": Grass,
    "dirt": Dirt,
    "stone": Stone,
    "birch_leave": Birch_Leave,
    "birch_log": Birch_Log,
    "oak_leave": Oak_Leave,
    "oak_log": Oak_Log,
    "sand": Sand,
    "water": Water,
    "cobblestone": Cobblestone,
    "oak_planks": Oak_Planks,
    "unbrekable": Unbrekable,
}
# Index matches allBlocks texture ids 0..11 (see save format).
TEXTURE_CTORS: tuple[type, ...] = (
    Birch_Leave,   # 0
    Birch_Log,     # 1
    Cobblestone,   # 2
    Dirt,          # 3
    Grass,         # 4
    Oak_Leave,     # 5
    Oak_Log,       # 6
    Oak_Planks,    # 7
    Sand,          # 8
    Stone,         # 9
    Water,         # 10
    Unbrekable,    # 11
)


def get_block(name: str, position: list[float | int]):
    # No @cache on purpose: positions are unique per block, so the cache
    # never hit and pinned every Block ever created in RAM forever (plus
    # a str() key built per block). Plain factory is faster overall.
    ctor = _BLOCK_CTOR_BY_NAME.get(name)
    if ctor is not None:
        return ctor(position)

    print(Fore.YELLOW + f"Unrecognized block: {name}")
    print(Style.RESET_ALL)
    return None

def get_texture(idx: int, x, y, z):
    # Tuple index (was match per block on the save-load hot path).
    try:
        ctor = TEXTURE_CTORS[idx]
    except (IndexError, TypeError):
        ctor = None
    if ctor is not None:
        return ctor([x, y, z])

    print(Fore.YELLOW + f"Unrecognized idx: {idx}")
    print(Style.RESET_ALL)
    return None


@cache
def sum_list(list1, list2):
    return [x+y for x, y in zip(list1, list2)]

@cache
def min_list(list1, list2):
    return [x-y for x, y in zip(list1, list2)]

import hashlib

@cache
def string_to_fixed_number(s, digits=10):
    # Create a hash (SHA-256 is common and stable)
    h = hashlib.sha256(s.encode()).hexdigest()
    
    # Convert hex string to integer
    num = int(h, 16)
    
    # Limit to a fixed number of digits
    return num % (10 ** digits)

from Number import Number

@cache
def clip(value:Number, max_:Number, min_:Number) -> Number:
    return max(min(value, max_), min_)

@cache
def distance(first:list[Number], second:list[Number]):
    return hypot(first[0]-second[0], first[1]-second[1], first[2]-second[2])

def get_accurate_block(pos:list[Number]) -> tuple[Number]:
    return tuple([floor(axis + 0.5) for axis in pos])

@cache
def raycast(occupied, start, front, max_iterations=10):

    pos = start.copy()

    last = start.copy()

    for iteration in range(max_iterations):
        pos += front

        round_ = get_accurate_block(pos)

        if round_ in occupied:
            previous_block = get_accurate_block(last)
            block_delta = np.asarray(round_) - np.asarray(previous_block)

            if not np.any(block_delta):
                axis = int(np.argmax(np.abs(front)))
                normal = np.zeros(3, dtype=int)
                normal[axis] = -1 if front[axis] > 0 else 1
            else:
                normal = np.zeros(3, dtype=int)
                axis = int(np.argmax(np.abs(block_delta)))
                normal[axis] = -1 if block_delta[axis] > 0 else 1

            return np.array(round_), np.array(normal)

        last = pos.copy()

from pathlib import Path
import sys

import os

def _save_dir():
    """Writable save folder on both PC and Android.

    Desktop keeps the old %APPDATA%/OMEFEG location. On Android
    (python-for-android) saves go to the app's private files dir
    (e.g. .../files/OMEFEG), which is always writable. Uses
    makedirs (not mkdir) so missing parents don't crash.
    """
    if hasattr(sys, "getandroidapilevel"):
        base = os.environ.get("ANDROID_PRIVATE") or os.getcwd()
        d = os.path.abspath(os.path.join(base, os.pardir, "OMEFEG"))
    else:
        homedir = os.path.expanduser("~")
        d = os.path.join(homedir, "AppData", "Roaming", "OMEFEG")
    os.makedirs(d, exist_ok=True)
    return d

def save(filename:str, data):
    d = _save_dir()

    with open(os.path.join(d, filename), "wb") as f:
        f.write(data)

def open_save_file(filename:str, callback:Callable):
    d = _save_dir()

    if not Path(os.path.join(d, filename)).exists():
        return None

    with open(os.path.join(d, filename), "rb") as f:
        readed = f.read()

    return callback(readed)

import requests
import time
import webbrowser


# ============================================================
# CONFIG
# ============================================================

GITHUB_CLIENT_ID = "Ov23liEq6lhdqtrbibGf"

OMEFEG_SERVER = (
    "https://Tombenax.pythonanywhere.com"
)


# ============================================================
# START GITHUB DEVICE LOGIN
# ============================================================

def login_with_github():

    # --------------------------------------------------------
    # STEP 1
    #
    # Ask GitHub for a device code.
    # --------------------------------------------------------

    response = requests.post(
        "https://github.com/login/device/code",

        data={
            "client_id":
                GITHUB_CLIENT_ID,

            # We only need to identify the user.
            "scope":
                "read:user user:email"
        },

        headers={
            "Accept":
                "application/json"
        },

        timeout=10
    )


    if response.status_code != 200:

        print(
            "Unable to start GitHub login."
        )

        print(
            response.text
        )

        return None


    data = response.json()


    device_code = data[
        "device_code"
    ]

    user_code = data[
        "user_code"
    ]

    verification_uri = data[
        "verification_uri"
    ]

    expires_in = data[
        "expires_in"
    ]

    interval = data.get(
        "interval",
        5
    )


    # --------------------------------------------------------
    # STEP 2
    #
    # Tell the player what to do.
    # --------------------------------------------------------

    print()
    print(
        "=============================="
    )
    print(
        "       GITHUB LOGIN"
    )
    print(
        "=============================="
    )

    print()

    print(
        "Open:"
    )

    print(
        verification_uri
    )

    print()

    print(
        "Enter this code:"
    )

    print()

    notification(
        "OMEFEG",
        f"Put in the browser this code: \"{user_code}\""
    )

    print()

    print(
        f"You have about "
        f"{expires_in // 60} minutes."
    )

    print()


    # Open browser automatically.
    try:

        webbrowser.open(
            verification_uri
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # STEP 3
    #
    # Poll GitHub until the user authorizes.
    #
    # GitHub requires us to respect the interval returned
    # above. Otherwise GitHub can return slow_down.
    # --------------------------------------------------------

    start_time = time.time()

    while True:

        # Stop after GitHub's expiration time.
        if (
            time.time() - start_time
            >= expires_in
        ):

            print(
                "GitHub login expired."
            )

            return None


        notification(
            "OMEFEG",
            f"Put in the browser this code: \"{user_code}\""
        )

        time.sleep(
            interval
        )


        token_response = requests.post(
            "https://github.com/login/oauth/access_token",

            data={
                "client_id":
                    GITHUB_CLIENT_ID,

                "device_code":
                    device_code,

                "grant_type":
                    "urn:ietf:params:oauth:grant-type:device_code"
            },

            headers={
                "Accept":
                    "application/json"
            },

            timeout=10
        )


        if token_response.status_code != 200:

            print(
                "GitHub token request failed."
            )

            return None


        token_data = (
            token_response.json()
        )


        # ----------------------------------------------------
        # User hasn't entered the code yet.
        # ----------------------------------------------------

        if (
            token_data.get("error")
            == "authorization_pending"
        ):

            print(
                "Waiting for GitHub authorization..."
            )

            continue


        # ----------------------------------------------------
        # GitHub says we're polling too quickly.
        # ----------------------------------------------------

        if (
            token_data.get("error")
            == "slow_down"
        ):

            interval += 5

            continue


        # ----------------------------------------------------
        # User rejected the login.
        # ----------------------------------------------------

        if (
            token_data.get("error")
            == "access_denied"
        ):

            print(
                "GitHub login was cancelled."
            )

            return None


        # ----------------------------------------------------
        # Code expired.
        # ----------------------------------------------------

        if (
            token_data.get("error")
            == "expired_token"
        ):

            print(
                "GitHub login expired."
            )

            return None


        # ----------------------------------------------------
        # Something else went wrong.
        # ----------------------------------------------------

        if "error" in token_data:

            print(
                "GitHub error:",
                token_data["error"]
            )

            return None


        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        access_token = token_data.get(
            "access_token"
        )


        if access_token:

            print(
                "GitHub authorization successful!"
            )

            break


    # --------------------------------------------------------
    # STEP 4
    #
    # Send the GitHub access token to YOUR server.
    # --------------------------------------------------------

    server_response = requests.post(
        f"{OMEFEG_SERVER}/api/login/github",

        json={
            "access_token":
                access_token
        },

        timeout=10
    )


    # --------------------------------------------------------
    # Server didn't accept the login.
    # --------------------------------------------------------

    if server_response.status_code not in (
        200,
        401,
        404
    ):

        print(
            "OMEFEG server error:"
        )

        print(
            server_response.text
        )

        return None


    result = server_response.json()


    # --------------------------------------------------------
    # Not registered on OMEFEG.
    # --------------------------------------------------------

    if (
        result.get("status")
        == "not_registered"
    ):

        print(
            "This GitHub account is not "
            "registered with OMEFEG."
        )

        return None


    # --------------------------------------------------------
    # OMEFEG account disabled.
    # --------------------------------------------------------

    if (
        result.get("status")
        == "disabled"
    ):

        print(
            "Your OMEFEG account is disabled."
        )

        return "disabled"


    # --------------------------------------------------------
    # Invalid GitHub token.
    # --------------------------------------------------------

    if (
        result.get("status")
        == "invalid"
    ):

        print(
            "GitHub authentication failed."
        )

        return None


    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    if (
        result.get("status")
        == "success"
    ):

        return {
            "username":
                result["username"],

            "uuid":
                result["uuid"],

            "status":
                result["account_status"],

            # Keep this if your game needs to make
            # authenticated GitHub API calls later.
            "github_access_token":
                access_token
        }


    return None

if __name__ == "__main__":
    #put tests here
    # ============================================================
    # EXAMPLE
    # ============================================================

    result = login_with_github()


    if result == "disabled":

        print(
            "ACCESS DENIED: account disabled."
        )


    elif result is None:

        print(
            "LOGIN FAILED."
        )


    else:

        print(
            "Logged in!"
        )

        print(
            "Username:",
            result["username"]
        )

        print(
            "UUID:",
            result["uuid"]
        )

        print(
            "Status:",
            result["status"]
        )

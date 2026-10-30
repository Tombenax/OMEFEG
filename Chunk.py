from random import Random

import time

from utils import generate_terrain, export_and_load_chunk, chunk_time
from Block import Block
from allBlocks import *
import os
import sys

# True on PC, False on Android phones. Override with OMEFEG_DESKTOP=0/1.
DESKTOP = os.environ.get("OMEFEG_DESKTOP")
if DESKTOP is None:
    DESKTOP = not hasattr(sys, "getandroidapilevel")
else:
    DESKTOP = DESKTOP == "1"

if DESKTOP:
    from Render import *
else:
    from MobileRender import *
from lists import *
from Number import Number
from typing import Callable, Any

class Chunk:
    def __init__(self, render, position:list[Number], seed:Random, heightmap:Callable, biomes_map:Callable, rules:dict[Any, Any], **kwargs):
        self.blocks = BlocksList()

        self.position = position

        self.render = render

        if not kwargs.get("empty"):
            terrain = generate_terrain(height_map=heightmap, biomes_map=biomes_map, offsett=position, rules_=rules, random_seed=seed, sin_world=True if kwargs.get("sin_world") else False, biomes=True if kwargs.get("biomes") else False)

            self.blocks.extend(terrain)

        self.model:Model = Model(self.render)
        self.model.add_model("block", vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1])

        # Block instances upload lazily (see ensure_block_instances):
        # only the chunk the player stands in ever draws them, so the
        # ~0.5MB instance upload for every other chunk is deferred until
        # first enter/edit. Refs, not copies (live lists).
        self._deferred_block_instances = None
        self._block_instances_ready = True

        if not kwargs.get("empty"):
            if self.blocks.positions and self.blocks.textures:
                self._deferred_block_instances = (
                    self.blocks.positions, self.blocks.textures)
                self._block_instances_ready = False

            vertices, indices = export_and_load_chunk(self.blocks.positions, self.blocks.textures, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y)

            self.model.add_model("dummy", vertices = vertices, indices = indices, is_chunk_dummy=True)

            self.model.add_instances([[0, 0, 0]], [0], "dummy")

        self.is_player_in = False

        self.prev_is_player_in = False

        # Save dirty flag: True only when RAM voxels differ from what
        # regeneration (fresh terrain) or the save file (disk loads)
        # would produce -- i.e. after edits. Fresh chunks start clean
        # because regen is bit-stable (frozen biome bands + per-chunk
        # RNG), so evicting pristine terrain never touches the disk.
        # Fail-safe default: unknown chunks are treated as dirty.
        self._save_dirty = False

        # Dummy mesh is rebuilt lazily: edits set _dummy_dirty, render_mesh
        # rebuilds at most once (old code rebuilt the full merged mesh
        # EVERY FRAME while the player stood in the chunk, even though the
        # dummy isn't even drawn then).
        self._dummy_dirty = False

    @classmethod
    def from_payload(cls, render, position, payload):
        """Build a chunk from worker-thread output without re-running
        terrain generation. GL objects are created here, so call this on
        the main (GL context) thread only."""
        chunk = cls.__new__(cls)
        chunk.blocks = BlocksList()
        chunk.position = list(position)
        chunk.render = render
        # Workers index the list off-thread: adopt it instead of re-walking
        # ~6700 blocks on the main thread. Legacy payloads without one
        # fall back to extend.
        _bl = payload.get("blocks_list")
        if _bl is not None:
            chunk.blocks = _bl
        else:
            chunk.blocks.extend(payload["blocks"])
        # Adopt worker-computed voxel bounds for the occupancy volume
        # (see update_block_occupancy). Edits invalidate it below.
        try:
            chunk._occ_bounds = payload.get("bounds")
        except AttributeError:
            chunk._occ_bounds = None
        chunk.model = Model(render)
        chunk.model.add_model("block", vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1])
        # Reuse worker-built numpy arrays when present (avoids a second
        # list->ndarray conversion of the same ~600 positions/textures).
        # Upload itself is deferred (see ensure_block_instances).
        _pos = payload.get("positions")
        _tex = payload.get("textures")
        if _pos is None:
            _pos = chunk.blocks.positions
        if _tex is None:
            _tex = chunk.blocks.textures
        chunk._deferred_block_instances = None
        chunk._block_instances_ready = True
        try:
            _has = len(_pos) > 0 and len(_tex) > 0
        except TypeError:
            _has = False
        if _has:
            chunk._deferred_block_instances = (_pos, _tex)
            chunk._block_instances_ready = False
        chunk.model.add_model(
            "dummy",
            vertices=payload["dummy_vertices"],
            indices=payload["dummy_indices"],
            is_chunk_dummy=True,
        )
        chunk.model.add_instances([[0, 0, 0]], [0], "dummy")
        chunk.is_player_in = False
        chunk.prev_is_player_in = False
        chunk._dummy_dirty = False
        # Fresh payloads are clean by default: worker bakes regenerate
        # bit-identically, and from_save bytes are already on disk.
        # Edits mark dirty (see _flush_placements/destroy_block).
        chunk._save_dirty = False
        return chunk

    @classmethod
    def from_blocks(cls, render, position, blocks):
        """Build a GL-ready chunk from already-loaded Block objects.

        Fast path for save-file loads: single extend + single instance
        upload + single dummy mesh (the old _build_chunk_from_blocks did
        extend, then add_instances(list->ndarray), then _update_dummy
        which re-converted the same lists a second time).
        """
        from utils import export_and_load_chunk as _export
        chunk = cls.__new__(cls)
        chunk.blocks = BlocksList()
        chunk.position = list(position)
        chunk.render = render
        chunk.model = Model(render)
        chunk.model.add_model("block", vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1])
        chunk._deferred_block_instances = None
        chunk._block_instances_ready = True
        if blocks:
            chunk.blocks.extend(blocks)
            _positions = chunk.blocks.positions
            _textures = chunk.blocks.textures
            if _positions and _textures:
                chunk._deferred_block_instances = (_positions, _textures)
                chunk._block_instances_ready = False
            _verts, _inds = _export(
                _positions, _textures, CUBE_MODEL_INFO,
                TEXTURES_X, TEXTURES_Y)
            chunk.model.add_model(
                "dummy", vertices=_verts, indices=_inds,
                is_chunk_dummy=True)
            chunk.model.add_instances([[0, 0, 0]], [0], "dummy")
        chunk.is_player_in = False
        chunk.prev_is_player_in = False
        chunk._dummy_dirty = False
        # from_blocks is only used for disk loads: bytes already on disk.
        chunk._save_dirty = False
        return chunk

    def release(self):
        """Free GPU resources so an unloaded chunk leaves no GL trace.

        Desktop builds hold moderngl buffers/vaos per InstancedModel;
        mobile builds hold Kivy canvas objects (detach_gl). Either way
        the chunk becomes inert and safe to drop from RAM.
        """
        try:
            models = list(getattr(self.model, "instanedmodels", {}).values())
        except Exception:
            models = []
        for m in models:
            detach = getattr(m, "detach_gl", None)
            if callable(detach):
                try:
                    detach()
                except Exception:
                    pass
            else:
                for resource in ("vao", "vbo", "ibo",
                                 "instance_buffer", "layer_buffer"):
                    try:
                        getattr(m, resource).release()
                    except Exception:
                        pass
        try:
            self.model.instanedmodels.clear()
        except Exception:
            pass

    def mark_dummy_dirty(self):
        self._dummy_dirty = True

    def ensure_block_instances(self):
        """Upload deferred block instances. Main (GL) thread only.

        Chunks are built with the instance upload deferred (only the
        player's own chunk ever draws them); the first enter or the
        first edit materializes them from the live position/texture
        lists. No-op when already uploaded or when legacy state is
        missing (fail-safe: behaves like the old eager upload path by
        doing nothing extra).
        """
        if getattr(self, "_block_instances_ready", True):
            return
        self._block_instances_ready = True
        deferred = getattr(self, "_deferred_block_instances", None)
        self._deferred_block_instances = None
        if not deferred:
            return
        try:
            pos, tex = deferred
            if pos is None or tex is None:
                return
            if len(pos) == 0 or len(tex) == 0:
                return
            self.model.add_instances(pos, tex, "block")
        except Exception:
            pass

    def _update_dummy(self):
        _dt0 = time.perf_counter()

        vertices, indices = export_and_load_chunk(self.blocks.positions, self.blocks.textures, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y)

        self.model.remove_instance(0, "dummy")

        self.model.add_model("dummy", vertices = vertices, indices = indices, is_chunk_dummy=True)

        self.model.add_instances([[0, 0, 0]], [0], "dummy")

        self._dummy_dirty = False
        chunk_time("dummy-rebuild", _dt0)

    def render_mesh(self):
        if self.is_player_in != self.prev_is_player_in:
            self.prev_is_player_in = self.is_player_in

        if self.is_player_in and self.prev_is_player_in:
            # Player is inside: dummy isn't drawn, so only rebuild if an
            # edit dirtied it (keeps it fresh for when the player leaves).
            if self._dummy_dirty:
                self._update_dummy()

        if self.is_player_in:
            try:
                self.ensure_block_instances()
            except Exception:
                pass
            self.model.render_one("block")
        else:
            if "dummy" in self.model.instanedmodels and not self._dummy_dirty:
                self.model.render_one("dummy")
            else:
                self._update_dummy()
                self.model.render_one("dummy")

    def _update_blocks(self):
        self.model.add_instances(self.blocks.positions, self.blocks.textures, "block")

    def get_y_at(self, x:Number, z:Number) -> Number:
        return self.get_block_pos_at(x, z)[1] + 1

    def get_block_pos_at(self, x:Number, z:Number) -> list[Number]:
        try:
            arr = np.array(self.blocks.positions)
            return list(arr[(arr[:, 0] == x) & (arr[:, 2] == z)][0])
        except IndexError:
            return [x, 100, z]

    def get_block_at(self, position:list[Number]):
        try:
            return self.blocks.positions_blocks[tuple(position)]
        except:
            return None
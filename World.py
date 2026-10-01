from numpy import empty

from Chunk import Chunk
from Block import Block
import collections
import os
import sys
import time

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
from utils import export_and_load_chunk, square_range
if DESKTOP:
    from Render import *
else:
    from MobileRender import *

class HeightMap:
    def __init__(self, noise, width, depth, N, scale=10):
        import threading as _th
        self.noise = noise
        self.width = width
        self.depth = depth
        self.N = N
        self.scale = scale

        self._values = {}
        self._thresholds = []
        # Chunk workers sample this map; guard values/size/thresholds.
        self._lock = _th.Lock()

        self._generate_initial()

    def _noise(self, x, z):
        """Get and cache a noise value."""
        key = (x, z)

        with self._lock:
            if key not in self._values:
                self._values[key] = self.noise(
                    (x / self.scale) + 0.1,
                    (z / self.scale) + 0.1
                )

            return self._values[key]

    def _generate_initial(self):
        """Generate the initial area."""
        for x in range(self.width):
            for z in range(self.depth):
                self._noise(x, z)

        self._calculate_thresholds()

    def _calculate_thresholds(self):
        """Recalculate percentile thresholds."""
        values = sorted(self._values.values())

        if not values:
            self._thresholds = []
            return

        self._thresholds = [
            values[int(len(values) * i / self.N)]
            for i in range(1, self.N)
        ]

    def _get_height(self, x, z):
        """Convert a noise value into a discrete height."""
        value = self._noise(x, z)

        height = 0

        while (
            height < len(self._thresholds)
            and value >= self._thresholds[height]
        ):
            height += 1

        return height

    def ensure_range(self, x0, x1, z0, z1):
        """Expand once to cover a rectangle (one threshold recalc).

        Bulk terrain gen calls this per chunk instead of up to 100
        per-column expands (each re-sorting every value) via __getitem__.
        """
        xs = [abs(v) for v in (x0, x1)]
        zs = [abs(v) for v in (z0, z1)]
        need_x = max(xs) + 1
        need_z = max(zs) + 1
        with self._lock:
            if need_x <= self.width and need_z <= self.depth:
                return
            old_width = self.width
            old_depth = self.depth
            new_width = max(self.width, need_x)
            new_depth = max(self.depth, need_z)
            for new_x in range(old_width, new_width):
                for new_z in range(new_depth):
                    key = (new_x, new_z)
                    if key not in self._values:
                        self._values[key] = self.noise(
                            (new_x / self.scale) + 0.1,
                            (new_z / self.scale) + 0.1
                        )
            for new_z in range(old_depth, new_depth):
                for new_x in range(old_width):
                    key = (new_x, new_z)
                    if key not in self._values:
                        self._values[key] = self.noise(
                            (new_x / self.scale) + 0.1,
                            (new_z / self.scale) + 0.1
                        )
            self.width = new_width
            self.depth = new_depth
            self._calculate_thresholds()

    def _expand(self, x, z):
        """Generate enough data to include x, z."""
        if x < 0 or z < 0:
            x, z = abs(x), abs(z)
        self.ensure_range(0, x, 0, z)

    def __getitem__(self, position):
        """
        Get height using:

            heightmap[x, z]

        Automatically expands the heightmap if necessary.
        """
        x, z = position

        if x < 0 or z < 0:
            x = abs(x)
            z = abs(z)

        if x >= self.width or z >= self.depth:
            self._expand(x, z)

        return self._get_height(x, z)

def _build_chunk_payload(seed, heightmap, biomes_map, rules, chunk_kwargs, position, gen_lock):
    """Worker-thread chunk bake: terrain Blocks + merged dummy mesh.

    Pure CPU/NumPy (no GL calls), so it runs off the main thread.
    Shared worldgen state (HeightMap cache, Random sequence) is used
    under gen_lock.
    """
    from utils import generate_terrain, export_and_load_chunk
    if DESKTOP:
        from Render import CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y
    else:
        from MobileRender import CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y
    with gen_lock:
        # Single biome lookup per chunk (one expand + one threshold
        # recalc at most, same as the sync path). Only the chunk origin
        # is sampled, so no rect prefetch: neighbor origins are 10 apart
        # and would not reuse it, it would only add noise evals early.
        terrain = generate_terrain(
            height_map=heightmap, biomes_map=biomes_map,
            offsett=list(position), rules_=rules, random_seed=seed,
            sin_world=True if chunk_kwargs.get("sin_world") else False,
            biomes=True if chunk_kwargs.get("biomes") else False,
        )
    positions = [list(b.position) for b in terrain]
    textures = [b.texture for b in terrain]
    dummy_vertices, dummy_indices = export_and_load_chunk(
        positions, textures, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y
    )
    return {
        "blocks": terrain,
        "dummy_vertices": dummy_vertices,
        "dummy_indices": dummy_indices,
    }


class World:
    # Max chunk GL uploads per frame: bounds main-thread hitch when many
    # workers finish at once (each upload = buffer allocs + occupancy
    # stamp). Kept at 2: walking crosses a chunk border every ~1.4s and
    # adds one row (~7 chunks at R=3), which drains in ~4 frames.
    UPLOADS_PER_FRAME = 2

    # Extra ring kept in RAM beyond what is generated/rendered. With
    # keep_extra=1 only square(RENDER_DISTANCE+1) stays loaded; anything
    # outside is saved to disk and evicted, then re-loaded on return.
    KEEP_EXTRA = 1
    CHUNK_STEP = 10

    def __init__(self, render, seed, heightmap, rules, **kwargs):
        import threading as _th
        import queue as _queue
        from concurrent.futures import ThreadPoolExecutor as _Pool
        import os as _os
        self.render = render
        self.seed = seed
        self.heightmap = heightmap
        self.rules = rules
        # persistent=False (multiplayer) keeps everything in RAM like
        # before; persistent=True streams chunks through per-chunk files.
        self.persistent = kwargs.pop("persistent", True)
        self.kwargs = kwargs
        self.biomes_map = HeightMap(heightmap, 10, 10, 3, 10)

        self.chunks:ChunksList = ChunksList()

        # Per-chunk save dir (<save_dir>/chunks/chunk_X_Z.bin). Only the
        # RENDER_DISTANCE+1 square lives in RAM; the rest lives here.
        self._chunk_dir = None
        if self.persistent:
            try:
                from utils import _save_dir as _get_save_dir
                base = _get_save_dir()
                self._chunk_dir = os.path.join(base, "chunks")
                os.makedirs(self._chunk_dir, exist_ok=True)
            except Exception:
                self._chunk_dir = None
                self.persistent = False

        # Time-sliced update() queue (see place_block/poll_update_queue).
        self.update_queue = collections.deque()
        self.update_waiting = collections.deque()
        self._queued_positions = set()
        self._last_queue_time = time.time()

        # Threaded pipeline: workers bake payloads, main thread uploads.
        self._gen_lock = _th.Lock()
        workers = max(1, min(4, (_os.cpu_count() or 2)))
        self._executor = _Pool(max_workers=workers, thread_name_prefix="chunk")
        self._pending = {}  # (x, 0, z) -> Future, guarded by _pending_lock
        self._pending_lock = _th.Lock()
        self._ready = _queue.Queue()

    def shutdown_threads(self, wait=False):
        try:
            self._executor.shutdown(wait=wait, cancel_futures=True)
        except TypeError:
            # Older Python without cancel_futures.
            self._executor.shutdown(wait=wait)
        except Exception:
            pass

    @property
    def pending_chunk_count(self):
        with self._pending_lock:
            return len(self._pending)

    def request_chunk_at(self, position):
        """Submit a chunk bake if missing and not already pending.

        Returns True when a new job was submitted. Never touches GL.
        Refuses when a save exists (load it from disk instead, so workers
        never bake fresh terrain over the player's edits).
        """
        key = (position[0], 0, position[2])
        if key in self.chunks.positions_blocks:
            return False
        if self.persistent and self._chunk_dir is not None:
            try:
                if self.has_saved_chunk(key):
                    return False
            except Exception:
                pass
        with self._pending_lock:
            if key in self._pending:
                return False
            fut = self._executor.submit(
                _build_chunk_payload,
                self.seed, self.heightmap, self.biomes_map,
                self.rules, self.kwargs, list(position), self._gen_lock,
            )
            self._pending[key] = (list(position), fut)
            return True

    def _finalize_payload(self, position, payload, update_occupancy=True):
        chunk = Chunk.from_payload(self.render, position, payload)
        self.chunks.add(chunk)
        if update_occupancy:
            self.render.update_block_occupancy(self)
        return chunk

    def poll_completed(self, camera_pos=None, budget=UPLOADS_PER_FRAME):
        """Upload finished worker payloads (main thread only).

        Collects done jobs, nearest-first to the camera, finalizes up to
        `budget` of them, and refreshes block occupancy ONCE if any were
        added (old code rebuilt occupancy per chunk: O(world) each).
        Returns the number of chunks added.
        """
        done = []
        with self._pending_lock:
            for key, (pos, fut) in list(self._pending.items()):
                if fut.done():
                    done.append((key, pos, fut))
        if not done:
            return 0
        if camera_pos is not None:
            cx, cz = camera_pos[0], camera_pos[2]
            done.sort(key=lambda item: (item[1][0] - cx) ** 2 + (item[1][2] - cz) ** 2)
        added = 0
        for key, pos, fut in done:
            if added >= budget:
                break
            with self._pending_lock:
                self._pending.pop(key, None)
            try:
                payload = fut.result()
            except Exception:
                continue
            if tuple(key) in self.chunks.positions_blocks:
                continue
            # A save may have landed while the worker baked (e.g. the
            # chunk was evicted+saved after submission). The file holds
            # the player's edits, so it wins over fresh terrain.
            if self.persistent and self._chunk_dir is not None:
                try:
                    if self.has_saved_chunk(key):
                        blocks = self.load_saved_blocks(key)
                        if blocks is not None:
                            try:
                                chunk = self._build_chunk_from_blocks(list(pos), blocks)
                                self.chunks.add(chunk)
                                added += 1
                                continue
                            except Exception:
                                pass
                except Exception:
                    pass
            chunk = Chunk.from_payload(self.render, pos, payload)
            self.chunks.add(chunk)
            added += 1
        if added:
            try:
                self.render.update_block_occupancy(self)
            except Exception:
                pass
        return added

    # ------------------------------------------------------------------
    # Chunk streaming: only square(radius + KEEP_EXTRA) lives in RAM.
    # ------------------------------------------------------------------
    def _chunk_path_for(self, key):
        if not self._chunk_dir:
            return None
        try:
            return os.path.join(
                self._chunk_dir,
                f"chunk_{int(key[0])}_{int(key[2])}.bin",
            )
        except (TypeError, IndexError, ValueError):
            return None

    def has_saved_chunk(self, key):
        path = self._chunk_path_for(key)
        if path is None:
            return False
        try:
            return os.path.isfile(path)
        except Exception:
            return False

    def save_chunk(self, chunk):
        """Persist one loaded chunk to its per-chunk file (atomic)."""
        if not self.persistent or not self._chunk_dir:
            return False
        try:
            key = (int(chunk.position[0]), 0, int(chunk.position[2]))
        except (TypeError, IndexError, ValueError, AttributeError):
            return False
        path = self._chunk_path_for(key)
        if path is None:
            return False
        try:
            import struct as _struct
            buf = bytearray()
            for block in chunk.blocks.blocks_list:
                try:
                    buf += _struct.pack(
                        ">qqqB",
                        int(block.position[0]),
                        int(block.position[1]),
                        int(block.position[2]),
                        int(block.texture) & 0xFF,
                    )
                except (TypeError, IndexError, AttributeError, ValueError):
                    continue
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(buf)
            os.replace(tmp, path)
            return True
        except Exception:
            return False

    def load_saved_blocks(self, key):
        """Read a per-chunk file. None = no save, [] = saved empty."""
        path = self._chunk_path_for(key)
        if path is None:
            return None
        try:
            if not os.path.isfile(path):
                return None
        except Exception:
            return None
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            return None
        if len(data) == 0:
            return []
        # Truncate a torn tail instead of failing the whole chunk.
        if len(data) % 25 != 0:
            data = data[:len(data) // 25 * 25]
            if not data:
                return []
        try:
            from utils import get_texture
        except Exception:
            return None
        blocks = []
        idx = 0
        n = len(data)
        while idx + 25 <= n:
            x = int.from_bytes(data[idx:idx + 8], signed=True)
            idx += 8
            y = int.from_bytes(data[idx:idx + 8], signed=True)
            idx += 8
            z = int.from_bytes(data[idx:idx + 8], signed=True)
            idx += 8
            t = int.from_bytes(data[idx:idx + 1])
            idx += 1
            try:
                block = get_texture(t, x, y, z)
            except Exception:
                continue
            if block is not None:
                blocks.append(block)
        return blocks

    def _build_chunk_from_blocks(self, position, blocks):
        """Build a GL-ready chunk from saved blocks (main thread only)."""
        chunk = Chunk(
            self.render, list(position), self.seed,
            self.heightmap, self.biomes_map, self.rules,
            **dict(self.kwargs, empty=True),
        )
        if blocks:
            chunk.blocks.extend(blocks)
            chunk.model.add_instances(
                chunk.blocks.positions, chunk.blocks.textures, "block")
            chunk._update_dummy()
        return chunk

    def unload_chunk(self, key, save=None):
        """Save (optional) + free GL + drop one chunk from RAM.

        Also cancels a still-baking worker job for the same key.
        Returns True when anything was dropped.
        """
        if save is None:
            save = bool(self.persistent and self._chunk_dir)
        dropped = False
        with self._pending_lock:
            item = self._pending.pop(tuple(key), None)
            if item is not None:
                dropped = True
                try:
                    _, fut = item
                    try:
                        fut.cancel()
                    except Exception:
                        pass
                except Exception:
                    pass
        chunk = self.chunks.positions_blocks.get(tuple(key))
        if chunk is None:
            return dropped
        if save:
            try:
                self.save_chunk(chunk)
            except Exception:
                pass
        try:
            release = getattr(chunk, "release", None)
            if callable(release):
                release()
        except Exception:
            pass
        try:
            self.chunks.remove(chunk)
        except Exception:
            pass
        return True

    def evict_far_chunks(self, center, keep_radius, step=10, save=None):
        """Unload every RAM chunk outside square(center, keep_radius).

        Called every frame from ensure_chunks_around; the keep set is
        built with plain loops (not the cached square_range) so walking
        forever doesn't grow the global function cache.
        Returns the number of evicted chunks + cancelled jobs.
        """
        if save is None:
            save = bool(self.persistent and self._chunk_dir)
        try:
            cx = int(center[0])
            cz = int(center[2])
            keep_radius = int(keep_radius)
            step = int(step)
        except (TypeError, IndexError, ValueError):
            return 0
        keep = set()
        for ix in range(-keep_radius, keep_radius + 1):
            for iz in range(-keep_radius, keep_radius + 1):
                keep.add((cx + ix * step, 0, cz + iz * step))
        evicted = 0
        for key in list(self.chunks.positions_blocks.keys()):
            if key not in keep:
                try:
                    if self.unload_chunk(key, save=save):
                        evicted += 1
                except Exception:
                    continue
        with self._pending_lock:
            for key in list(self._pending.keys()):
                if key not in keep:
                    try:
                        _, fut = self._pending.pop(key)
                        try:
                            fut.cancel()
                        except Exception:
                            pass
                        evicted += 1
                    except Exception:
                        continue
        if evicted:
            try:
                self.render.update_block_occupancy(self)
            except Exception:
                pass
        return evicted

    def save_all_loaded_chunks(self):
        """Persist every RAM chunk. Used at shutdown (no eviction)."""
        if not self.persistent or not self._chunk_dir:
            return 0
        saved = 0
        for chunk in list(self.chunks.blocks_list):
            try:
                if self.save_chunk(chunk):
                    saved += 1
            except Exception:
                continue
        return saved

    def clear_saved_chunks(self):
        """Delete all per-chunk files (starting a brand-new world)."""
        if not self._chunk_dir:
            return 0
        removed = 0
        try:
            for name in os.listdir(self._chunk_dir):
                if name.startswith("chunk_") and name.endswith(".bin"):
                    try:
                        os.remove(os.path.join(self._chunk_dir, name))
                        removed += 1
                    except Exception:
                        continue
                elif name.endswith(".tmp"):
                    try:
                        os.remove(os.path.join(self._chunk_dir, name))
                    except Exception:
                        pass
        except Exception:
            pass
        return removed

    def count_saved_chunks(self):
        if not self._chunk_dir:
            return 0
        try:
            return sum(
                1 for name in os.listdir(self._chunk_dir)
                if name.startswith("chunk_") and name.endswith(".bin")
            )
        except Exception:
            return 0

    def ensure_chunks_around(self, center, radius, step=10,
                             budget=UPLOADS_PER_FRAME, keep_extra=KEEP_EXTRA):
        """Stream chunks around the player with disk spillover.

        * Only square(center, radius + keep_extra) stays in RAM; chunks
          outside it are saved to per-chunk files and evicted.
        * Missing chunks inside square(center, radius) are loaded from
          disk first (budgeted, nearest-first) and only generated on
          workers when no save exists.
        * When the player moves, far chunks unload+save automatically
          and returning reloads the saved (edited) voxels.

        Call once per frame. Returns (submitted, added).
        """
        try:
            keep_radius = int(radius) + (int(keep_extra) if keep_extra else 0)
        except (TypeError, ValueError):
            keep_radius = radius
        try:
            self.evict_far_chunks(center, keep_radius, step=step)
        except Exception:
            pass
        from utils import square_range
        submitted = 0
        loaded = 0
        disk_budget = max(1, int(budget))
        try:
            with self._pending_lock:
                pending_keys = set(self._pending.keys())
        except Exception:
            pending_keys = set()
        for x, z in square_range(center, radius, step):
            key = (x, 0, z)
            if key in self.chunks.positions_blocks or key in pending_keys:
                continue
            if self.persistent and self._chunk_dir is not None:
                try:
                    has_save = self.has_saved_chunk(key)
                except Exception:
                    has_save = False
                if has_save:
                    if loaded >= disk_budget:
                        # Budget hit: leave for the next frames. Never
                        # send saved chunks to workers (they would bake
                        # fresh terrain over the player's edits).
                        continue
                    try:
                        blocks = self.load_saved_blocks(key)
                    except Exception:
                        blocks = None
                    if blocks is not None:
                        try:
                            chunk = self._build_chunk_from_blocks([x, 0, z], blocks)
                            self.chunks.add(chunk)
                            pending_keys.add(key)
                            loaded += 1
                            continue
                        except Exception:
                            pass
                    # Unreadable save: fall through and regenerate.
            try:
                if self.request_chunk_at([x, 0, z]):
                    submitted += 1
                    pending_keys.add(key)
            except Exception:
                continue
        added = 0
        try:
            added = self.poll_completed(camera_pos=center, budget=budget)
        except Exception:
            added = 0
        if loaded:
            try:
                self.render.update_block_occupancy(self)
            except Exception:
                pass
            added += loaded
        return submitted, added

    def generate_chunk_at(self, position:list[Number], **kwargs):
        update_occupancy = kwargs.pop("update_occupancy", True)
        chunk = Chunk(self.render, position, self.seed, self.heightmap, self.biomes_map, self.rules, **self.kwargs, empty=True if kwargs.get("empty") else False)
        self.chunks.add(chunk)
        if update_occupancy:
            self.render.update_block_occupancy(self)
        return chunk

        
    def get_y_at(self, x:Number, z:Number) -> Number:
        chunk_pos = [x // 10 * 10, 0, z // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]
            return chunk.get_y_at(x, z)
        else:
            return None

    def get_block_pos_at(self, x:Number, z:Number) -> list[Number]:
        chunk_pos = [x // 10 * 10, 0, z // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]
            return chunk.get_block_pos_at(x, z)
        else:
            return None

    # Time-sliced Block.update() queue: products of an update() are not
    # placed immediately but every UPDATE_QUEUE_INTERVAL seconds, so a big
    # spread (water flood) streams in over frames instead of hitching one.
    UPDATE_QUEUE_INTERVAL = 0.2
    # Max queue placements per drain (frame hitch bound) and max queued
    # entries (overflow drops the newest). Spreads are intentionally
    # unbounded ("infinite" water keeps creeping); termination comes from
    # voxels filling up, and memory from these caps plus WAITING_MAX.
    UPDATE_QUEUE_PER_TICK = 256
    UPDATE_QUEUE_MAX = 5000
    # Entries aimed at not-yet-streamed chunks wait here instead of being
    # dropped, so a spread survives chunk borders; retried every drain.
    WAITING_MAX = 1000

    # 6-neighbourhood sampled for Block.update().
    _NEIGHBOUR_OFFSETS = (
        (1, 0, 0), (-1, 0, 0),
        (0, 1, 0), (0, -1, 0),
        (0, 0, 1), (0, 0, -1),
    )

    def _get_loaded_block_at(self, position):
        """Block lookup that never generates chunks (unlike get_block_at)."""
        try:
            chunk_pos = (position[0] // 10 * 10, 0, position[2] // 10 * 10)
        except (TypeError, IndexError):
            return None
        chunk = self.chunks.positions_blocks.get(chunk_pos)
        if chunk is None:
            return None
        return chunk.get_block_at(position)

    def _neighbours_of(self, position):
        """{absolute_position: Block} for loaded 6-neighbours.

        Keys are absolute voxel tuples, so `neighbours.get(
        (x, y - 1, z))` reads the block below. A missing key means air
        or an unloaded chunk (which is never generated for this).
        """
        px, py, pz = position[0], position[1], position[2]
        out = {}
        for off in self._NEIGHBOUR_OFFSETS:
            abs_pos = (px + off[0], py + off[1], pz + off[2])
            neighbour = self._get_loaded_block_at(
                [abs_pos[0], abs_pos[1], abs_pos[2]])
            if neighbour is not None:
                out[abs_pos] = neighbour
        return out

    @staticmethod
    def _update_results(value):
        """Normalize a Block.update() return into a tuple of Blocks."""
        if value is None:
            return ()
        if isinstance(value, Block):
            return (value,)
        if isinstance(value, (list, tuple)):
            good = []
            for item in value:
                if not isinstance(item, Block):
                    continue
                try:
                    pos = tuple(item.position)
                    if len(pos) != 3:
                        continue
                    float(pos[0]) + float(pos[1]) + float(pos[2])
                except (TypeError, ValueError, IndexError):
                    continue
                good.append(item)
            return tuple(good)
        return ()

    def _refresh_occupancy_for(self, chunk):
        # Single-chunk re-stamp (O(chunk)) instead of a full world rescan.
        # Falls back to the full path when the render has no volume yet
        # (or on renders without incremental support, e.g. mobile stub
        # without the method... which does have it; getattr for safety).
        refresh = getattr(self.render, "refresh_chunk_occupancy", None)
        if refresh is not None:
            try:
                if refresh(chunk):
                    return
            except Exception:
                pass
        self.render.update_block_occupancy(self)

    def _enqueue_updates(self, results):
        """Stage update() products for the next queue drain."""
        for new_block in self._update_results(results):
            try:
                key = tuple(new_block.position)
            except (TypeError, IndexError, AttributeError):
                continue
            if key in self._queued_positions:
                continue
            if len(self.update_queue) >= self.UPDATE_QUEUE_MAX:
                return
            self.update_queue.append(new_block)
            self._queued_positions.add(key)

    def _wait_for_chunk(self, new_block):
        """Hold an entry aimed at an unstreamed chunk for a later drain."""
        try:
            key = tuple(new_block.position)
        except (TypeError, IndexError, AttributeError):
            return
        while len(self.update_waiting) >= self.WAITING_MAX:
            old = self.update_waiting.popleft()
            try:
                self._queued_positions.discard(tuple(old.position))
            except (TypeError, IndexError, AttributeError):
                pass
        self.update_waiting.append(new_block)

    def place_block(self, block:Block, run_update=True):
        """Place one block now; its update() products go to the queue.

        The placed block is updated immediately with its 6-neighbourhood,
        but Blocks the update returns are only staged in update_queue and
        placed by poll_update_queue() every UPDATE_QUEUE_INTERVAL seconds
        (each drained block is updated in turn, re-queueing at depth+1).

        Returns [block] when newly placed, [] otherwise. run_update=False
        skips the update for inbound network updates (the sender already
        ran it; replaying could diverge and duplicates the work).

        Placement is idempotent by position: re-applied echoes are no-ops
        instead of stacking duplicate instances on the same voxel.
        """
        placed = []
        try:
            chunk_pos = [block.position[0] // 10 * 10, 0,
                         block.position[2] // 10 * 10]
            key = tuple(block.position)
        except (TypeError, IndexError, AttributeError):
            return placed
        chunk = self.chunks.positions_blocks.get(tuple(chunk_pos))
        if chunk is None or key in chunk.blocks.positions_blocks:
            return placed
        chunk.blocks.add(block)
        chunk.model.add_instances([block.position], [block.texture], "block")
        placed.append(block)

        if run_update:
            try:
                results = block.update(self._neighbours_of(block.position))
            except Exception:
                results = None
            self._enqueue_updates(results)

        self._flush_placements({tuple(chunk_pos): chunk})
        return placed

    def poll_update_queue(self):
        """Place + update queued blocks. Call once per frame.

        Returns the newly placed Blocks (for network sync) every
        UPDATE_QUEUE_INTERVAL seconds, [] otherwise. Each drain handles
        exactly one wave: the entries queued at drain start. Products
        made during the drain wait for the next tick, so spreads advance
        one generation per 0.2s. Bounded by UPDATE_QUEUE_PER_TICK
        placements per drain; entries whose chunk is missing or voxel
        got filled meanwhile are dropped.
        """
        now = time.time()
        if now - self._last_queue_time < self.UPDATE_QUEUE_INTERVAL:
            return []
        self._last_queue_time = now
        # Retry waiting entries whose chunk has streamed in since; they
        # rejoin the queue (positions still marked, so no duplicates).
        if self.update_waiting:
            still_waiting = collections.deque()
            while self.update_waiting:
                new_block = self.update_waiting.popleft()
                try:
                    cpos = [new_block.position[0] // 10 * 10, 0,
                            new_block.position[2] // 10 * 10]
                except (TypeError, IndexError, AttributeError):
                    try:
                        self._queued_positions.discard(
                            tuple(new_block.position))
                    except (TypeError, IndexError, AttributeError):
                        pass
                    continue
                if tuple(cpos) in self.chunks.positions_blocks:
                    self.update_queue.append(new_block)
                else:
                    still_waiting.append(new_block)
            self.update_waiting = still_waiting
        if not self.update_queue:
            return []
        placed = []
        touched = {}
        budget = self.UPDATE_QUEUE_PER_TICK
        wave = len(self.update_queue)
        while self.update_queue and wave > 0 and len(placed) < budget:
            wave -= 1
            new_block = self.update_queue.popleft()
            try:
                key = tuple(new_block.position)
            except (TypeError, IndexError, AttributeError):
                continue
            self._queued_positions.discard(key)
            try:
                chunk_pos = [new_block.position[0] // 10 * 10, 0,
                             new_block.position[2] // 10 * 10]
            except (TypeError, IndexError, AttributeError):
                continue
            chunk = self.chunks.positions_blocks.get(tuple(chunk_pos))
            if chunk is None:
                # Chunk not streamed yet: wait for it instead of dropping
                # the spread at the border.
                self._queued_positions.add(key)
                self._wait_for_chunk(new_block)
                continue
            if key in chunk.blocks.positions_blocks:
                continue
            chunk.blocks.add(new_block)
            chunk.model.add_instances(
                [new_block.position], [new_block.texture], "block")
            touched[tuple(chunk_pos)] = chunk
            placed.append(new_block)
            try:
                results = new_block.update(
                    self._neighbours_of(new_block.position))
            except Exception:
                results = None
            self._enqueue_updates(results)
        self._flush_placements(touched)
        return placed

    def _flush_placements(self, touched):
        """Rebuild dummy meshes + occupancy once per touched chunk."""
        if not touched:
            return
        for chunk in touched.values():
            try:
                chunk._update_dummy()
            except Exception:
                pass
            try:
                self._refresh_occupancy_for(chunk)
            except Exception:
                pass

    def destroy_block(self, block:Block):
        if block == None:
            return
        chunk_pos = [block.position[0] // 10 * 10, 0, block.position[2] // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]

            if block in chunk.blocks.blocks_list:
                chunk.blocks.remove(block)
                chunk.model.remove_instances([block.position], "block")

                chunk._update_dummy()
                self._refresh_occupancy_for(chunk)


    def render_chunks(self, camera_chunk_position, RENDER_DISTANCE):
        for x, z in square_range(camera_chunk_position, RENDER_DISTANCE, 10):
            chunk = self.chunks.positions_blocks.get((x, 0, z))
            if chunk is None:
                continue
            chunk.is_player_in = (camera_chunk_position == chunk.position)
            chunk.render_mesh()

    def get_chunk_at(self, chunk_pos:list[Number], **kwargs) -> Chunk:
        #chunk_pos = [chunk_pos[0] // 10 * 10, 0, chunk_pos[2] // 10 * 10]
        key = tuple(chunk_pos)
        chunk = self.chunks.positions_blocks.get(key)
        if chunk is not None:
            return chunk
        # Don't leave a stale worker baking the same key behind.
        with self._pending_lock:
            item = self._pending.pop(key, None)
            if item is not None:
                try:
                    item[1].cancel()
                except Exception:
                    pass
        # Prefer the saved (edited) voxels over fresh terrain.
        if self.persistent and self._chunk_dir is not None:
            try:
                blocks = self.load_saved_blocks(key)
            except Exception:
                blocks = None
            if blocks is not None:
                try:
                    chunk = self._build_chunk_from_blocks(list(chunk_pos), blocks)
                    self.chunks.add(chunk)
                    try:
                        self.render.update_block_occupancy(self)
                    except Exception:
                        pass
                    return chunk
                except Exception:
                    pass
        self.generate_chunk_at(chunk_pos, **kwargs)
        return self.chunks.positions_blocks.get(tuple(chunk_pos))

    def get_block_at(self, position:list[Number]):
        chunk_pos = [position[0] // 10 * 10, 0, position[2] // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]
            return chunk.get_block_at(position)
        else:
            chunk = self.get_chunk_at(chunk_pos)
            if chunk is None:
                return None
            return chunk.get_block_at(position)
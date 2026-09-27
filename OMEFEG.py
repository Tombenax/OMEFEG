import datetime
from itertools import cycle
from Cooldown import Cooldown
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
from Chunk import Chunk       
from Block import Block
from World import World
from allBlocks import *
from perlineNoise import PerlinNoiseFactory
from lists import *
from utils import *
from network import Network
import threading
import argparse
import struct

argParser = argparse.ArgumentParser()
argParser.add_argument("--multiplayer")
argParser.add_argument("--not_move_window")
argParser.add_argument("--load_world")

parsedArgs = argParser.parse_args()

MULTIPLAYER = parsedArgs.multiplayer
if MULTIPLAYER:
    spl = MULTIPLAYER.split(":")
    PORT = int(spl[1])
    MULTIPLAYER = spl[0]

MOVE_WINDOW = not parsedArgs.not_move_window

LOAD_WORLD = parsedArgs.load_world


class sin:
    def __init__(self) -> None:
        pass

    def __call__(self, x, y):
        return math.sin(math.radians(x + y)) * 100

class Flat:
    def __init__(self) -> None:
        pass

    def __call__(self, x, y) -> float:
        return 0.0
            
seed = string_to_fixed_number(str(0), 10)
random_seed = Random(seed)

FLAT = True

generate_sin_world = False


if FLAT:
    heightmap = Flat()
    sin_world = False
else:
    if generate_sin_world:
        heightmap = sin()
        sin_world = True
    else:
        if MULTIPLAYER:
            heightmap = PerlinNoiseFactory(octaves=1, seed=seed)
            sin_world = False
        else:
            if random.random() * 100 < 99:
                heightmap = PerlinNoiseFactory(octaves=1, seed=seed)
                sin_world = False
            else:
                heightmap = sin()
                sin_world = True
    

with open("worldgeneration/worldGeneration.json", "r") as f:
    rules = json.load(f)

def convert_to_blocks(data):
    blocks = []
    idx = 0
    while idx < len(data):
        x = int.from_bytes(data[idx:idx+8], signed=True)
        idx += 8

        y = int.from_bytes(data[idx:idx+8], signed=True)
        idx += 8

        z = int.from_bytes(data[idx:idx+8], signed=True)
        idx += 8

        t = int.from_bytes(data[idx:idx+1])
        idx += 1

        blocks.append(get_texture(t, x, y, z))

    return blocks

mods_names = []

def load_mods():
    if not os.path.isdir("mods"):
        # Empty/missing mods dir in the APK (e.g. Android): nothing to load.
        return
    for mod in os.listdir("mods"):
        print(f"Loading mod: {mod}")

        exec(f"import mods.{mod}.Mod", globals())

        mods_names.append(mod)

def colletced(render):
    render.CAMERA.max_jumps += 1
    pos = None
    while pos is None:
        x, z = random.randrange(min_x, max_x), random.randrange(min_y, max_y)
        pos = WORLD.get_block_pos_at(x, z)
    pos[1] += 1
    coll.add_collectibles([pos], [0], [colletced])

send_thread = None

result = None
def worker(data, network):
    global result
    result = network.send(data)

def send_data_to_server(data, network: Network):
    network.send(data)

    return network.receive()

max_x, min_x, max_y, min_y = 0, 0, 0, 0

def load_player(data):
    return list(struct.unpack(">ddd", data[:24]))

def init(render):
    global TEXT, coll, WORLD, RENDER_DISTANCE, NETWORK, PLAYERS, min_x, max_x, min_y, max_y, hud, SLECTED

    WORLD = World(render, random_seed, heightmap, rules, sin_world=sin_world, biomes = not FLAT)

    RENDER_DISTANCE = 3

    if  LOAD_WORLD:
        render.CAMERA.position = np.array(open_save_file("player.bin", load_player), dtype="f4")

        world = open_save_file("world.bin", convert_to_blocks)

        if world:
            grouped = {}
            for block in world:
                chunk_pos = (block.position[0]//10*10, 0, block.position[2]//10*10)
                grouped.setdefault(chunk_pos, []).append(block)

            for chunk_pos, blocks in grouped.items():
                chunk = WORLD.get_chunk_at(list(chunk_pos), empty=True)
                chunk.blocks.clear()
                for block in blocks:
                    chunk.blocks.add(block)
                chunk._update_blocks()
                chunk._update_dummy()

            render.update_block_occupancy(WORLD)

        else:
            notification("World Not Found", "Your worl file was not found, if the file 'world.bin' is in %appdata%/OMEFEG then idk what the heck is happening, else just make a world")

            render.set_window_should_close(True)

            return
        
    else:
        # Threaded startup gen: workers bake in parallel, main thread
        # uploads with a per-iteration budget so the window stays alive.
        # Dict lookup instead of O(n) list scan.
        for x, z in square_range([0, 0, 0], RENDER_DISTANCE, 10):
            if (x, 0, z) not in WORLD.chunks.positions_blocks:
                WORLD.request_chunk_at([x, 0, z])
        import time as _chunk_time
        _deadline = _chunk_time.time() + 30.0
        while WORLD.pending_chunk_count and _chunk_time.time() < _deadline:
            WORLD.poll_completed(camera_pos=[0, 0, 0], budget=8)
            _chunk_time.sleep(0.001)
        # Any stragglers (worker error): fall back to sync gen.
        for x, z in square_range([0, 0, 0], RENDER_DISTANCE, 10):
            if (x, 0, z) not in WORLD.chunks.positions_blocks:
                WORLD.generate_chunk_at([x, 0, z])
        for pos in WORLD.chunks.positions_blocks:
            min_x = min(min_x, pos[0])
            max_x = max(max_x, pos[0])
            min_y = min(min_y, pos[0])
            max_y = max(max_y, pos[0])

    TEXT = InstancedText(render=render, charset=CHARSET)

    higher = -float("inf")

    for i in range(len("Welcome to OMEFEG")):
        higher = max(WORLD.get_y_at(i, 0), higher)


    TEXT.add_texts(["Welcome to OMEFEG"], [[0, higher, 0]])
    

    if MULTIPLAYER:
        NETWORK = Network(
            MULTIPLAYER,
            PORT
        )



        PLAYERS = Model(render)
        v, i = load_obj("assets/models/player.obj")
        PLAYERS.add_model("player", vertices=v, indices=i)

    SLECTED = Model(render)
    v, i = load_obj("assets/models/block.obj")
    SLECTED.add_model("selected", vertices=v, indices=i)
    SLECTED.add_instances([[0, 0, 0]], [12], "selected")

    coll = Collectible(render)

    pos = WORLD.get_block_pos_at(5, 0)
    pos[1] += 1

    coll.add_collectibles([pos], [0], [colletced])

    hud = HUDText(
    render=render,
    charset=CHARSET
    )

    hud.add_texts(["FPS: negative Infinity", "SELECTED BLOCK: birch leave"], [[0, 0], [0, 30]], ["FPS", "sb"])

    render.set_window_size_callback(lambda x,y,z: render.resized(y,z))

    render.set_lights([(0, 50, 0)], [(1, 1, 1, 1)])

    load_mods()

    for name in mods_names:
        exec(f"globals()['mods'].{name}.Mod.init(globals(), locals())", globals(), locals())

posses, rotations = [], []
block_updates = []

# --- Multiplayer: single persistent net thread @ fixed tick rate ---
# Old code spawned a new thread every frame that did 4 serial RTTs
# (setData/getData/setBlock/getBlock) with 5s blocking receives and
# shared lists with no locking. New code: one daemon thread at 20Hz,
# one combined tick RTT, all shared state under _mp_lock.
import time as _mp_time
import socket as _mp_socket
import collections as _mp_collections

MP_TICK_INTERVAL = 0.05  # 20 Hz: bounds packets/s per client
MP_OUTGOING_CAP = 500  # same cap as update()'s append guards
# Max block updates per tick: the server caps a packet at
# MAX_BLOCK_UPDATE_BATCH (200) and silently drops the rest, so never send
# more (leftovers ride the next ticks). 200/tick = 4000 blocks/s.
MP_BLOCKS_PER_TICK = 200
_mp_lock = threading.Lock()
_mp_thread = None
thr = None  # back-compat alias for mods importing `thr`
is_process_finished = True  # back-compat; no longer spawn-per-frame
_mp_stop = False
_mp_started = False
_mp_own_id = None
_mp_state = {"coords": [0, 2, 0], "yaw": 0, "pitch": 0}
_mp_backoff_until = 0.0
_mp_use_legacy = False
# Updates we sent and expect back as echo. The server broadcasts history
# to everyone including the sender (who already applied them locally), so
# without this every placed block would be added twice. Net thread only.
_mp_unacked = _mp_collections.deque(maxlen=200)
# Block updates whose chunk isn't streamed in yet (late-join snapshot can
# reference far chunks). Retried each frame; main thread only.
_mp_deferred = []
MP_DEFERRED_CAP = 1000


def _mp_echo_key(bu):
    # Normalize sent tuples vs JSON-decoded lists for comparison.
    if isinstance(bu, tuple):
        return [list(v) if isinstance(v, tuple) else v for v in bu]
    return bu


def _mp_requeue_outgoing(outgoing, blocks_placed_ref, blocks_broken_ref):
    """Put unsent updates back at the front of the outgoing queues.

    Used when a tick is lost (timeout) or refused-but-retryable, so
    send-once block updates aren't silently dropped. Bounded: drops the
    newest overflow instead of growing forever.
    """
    if not outgoing:
        return
    with _mp_lock:
        room_p = max(0, MP_OUTGOING_CAP - len(blocks_placed_ref))
        room_b = max(0, MP_OUTGOING_CAP - len(blocks_broken_ref))
        head_p = [b for b in outgoing if len(b) == 2][:room_p]
        head_b = [b for b in outgoing if len(b) == 3][:room_b]
        blocks_placed_ref[:0] = head_p
        blocks_broken_ref[:0] = head_b


def _mp_apply_snapshot(playerdata_players, incoming_blocks):
    """Update shared posses/rotations/block_updates under lock."""
    global posses, rotations, block_updates
    new_posses, new_rotations = [], []
    own = _mp_own_id
    try:
        own = NETWORK.id
    except (AttributeError, NameError):
        pass
    for p in playerdata_players or []:
        try:
            if p.get("id") == own:
                continue
            new_posses.append(p["position"])
            new_rotations.append((p["pitch"], p["yaw"] - 90, 0))
        except (KeyError, TypeError):
            continue
    fresh_blocks = []
    for bu in incoming_blocks or []:
        # Skip our own echo (already applied locally when clicked).
        try:
            _mp_unacked.remove(_mp_echo_key(bu))
            continue
        except ValueError:
            pass
        fresh_blocks.append(bu)
    with _mp_lock:
        posses[:] = new_posses
        rotations[:] = new_rotations
        # Accumulate (don't overwrite): render thread drains each frame,
        # so a fast net thread can't drop updates a slow frame hasn't seen.
        block_updates.extend(fresh_blocks)


def _mp_legacy_once(outgoing):
    """Fallback for old servers without the combined tick.

    Raises socket.timeout/OSError on loss: callers re-queue `outgoing`
    (it was already drained from the shared queues).
    """
    st = _mp_state
    send_data_to_server(NETWORK.tag({
        "setData": True,
        "coords": st["coords"],
        "yaw": st["yaw"],
        "pitch": st["pitch"],
    }), NETWORK)
    playerdata = send_data_to_server(NETWORK.tag({"getData": True}), NETWORK)
    if outgoing:
        send_data_to_server(NETWORK.tag({"setBlockData": True, "block update": outgoing}), NETWORK)
        try:
            for bu in outgoing:
                _mp_unacked.append(_mp_echo_key(bu))
        except Exception:
            pass
    resp = send_data_to_server(NETWORK.tag({"getBlockData": True}), NETWORK)
    _mp_apply_snapshot(playerdata.get("players", []), resp.get("block_updates", []))


def _mp_fetch_snapshot():
    """Late-join catch-up: pull the server's edit overlay.

    Edits made before we connected are invisible to the delta flow (our
    cursor starts at the head), so queue the overlay pages as block
    updates first. Overlap with later live deltas is idempotent on apply.
    Runs once on the net thread; old servers answer "Unknown message
    type" and we skip straight to ticks.
    """
    offset = 0
    fails = 0
    while not _mp_stop:
        try:
            resp = NETWORK.request(
                NETWORK.tag({"getSnapshot": True, "offset": offset}))
        except (_mp_socket.timeout, OSError):
            fails += 1
            if fails > 5:
                return
            _mp_time.sleep(0.1)
            continue
        except (ValueError, KeyError, AttributeError):
            return
        fails = 0
        if not isinstance(resp, dict):
            return
        if resp.get("error") == "Unknown message type":
            return
        if not resp.get("ok"):
            return
        page = resp.get("block_updates", [])
        if page:
            with _mp_lock:
                block_updates.extend(page)
        if resp.get("done", True):
            return
        try:
            offset = int(resp.get("next_offset", offset))
        except (TypeError, ValueError):
            return


def _mp_take_outgoing(blocks_placed_ref, blocks_broken_ref):
    """Take up to MP_BLOCKS_PER_TICK updates for one tick, in order.

    Leftovers stay queued for following ticks (the server truncates
    oversized packets, so sending more would silently lose blocks).
    Returns (state_snapshot, outgoing). Callers hold no lock; taken here.
    """
    with _mp_lock:
        st = dict(_mp_state)
        take_p = min(len(blocks_placed_ref), MP_BLOCKS_PER_TICK)
        outgoing = blocks_placed_ref[:take_p]
        del blocks_placed_ref[:take_p]
        room = MP_BLOCKS_PER_TICK - take_p
        if room and blocks_broken_ref:
            outgoing = outgoing + blocks_broken_ref[:room]
            del blocks_broken_ref[:room]
    return st, outgoing


def _multiplayer_loop(blocks_placed_ref, blocks_broken_ref):
    global _mp_backoff_until, _mp_use_legacy
    _mp_fetch_snapshot()
    while not _mp_stop:
        tick_start = _mp_time.time()
        # Back off after rate-limit/timeout instead of hot-spinning.
        if tick_start < _mp_backoff_until:
            _mp_time.sleep(min(0.05, _mp_backoff_until - tick_start))
            continue
        # Snapshot camera + outgoing blocks under lock (no cross-thread
        # mutation of the render-thread lists while iterating).
        st, outgoing = _mp_take_outgoing(blocks_placed_ref, blocks_broken_ref)
        try:
            if _mp_use_legacy:
                try:
                    _mp_legacy_once(outgoing)
                except (_mp_socket.timeout, OSError):
                    _mp_requeue_outgoing(outgoing, blocks_placed_ref, blocks_broken_ref)
            else:
                resp = NETWORK.tick(
                    NETWORK.id, st["coords"], st["yaw"], st["pitch"], outgoing,
                )
                if resp is None:
                    # Packet loss (common over tunnels): the server never
                    # saw these, so re-queue instead of dropping them.
                    # Positions resend anyway; blocks are send-once.
                    _mp_requeue_outgoing(outgoing, blocks_placed_ref, blocks_broken_ref)
                elif resp.get("error") == "rate_limited":
                    _mp_backoff_until = _mp_time.time() + 0.25
                    # Re-queue outgoing so rate-limited blocks aren't lost.
                    if outgoing:
                        with _mp_lock:
                            blocks_placed_ref.extend(
                                [b for b in outgoing if len(b) == 2]
                            )
                            blocks_broken_ref.extend(
                                [b for b in outgoing if len(b) == 3]
                            )
                elif resp.get("error") == "Unknown message type":
                    _mp_use_legacy = True
                    if outgoing:
                        with _mp_lock:
                            blocks_placed_ref[:0] = [b for b in outgoing if len(b) == 2]
                            blocks_broken_ref[:0] = [b for b in outgoing if len(b) == 3]
                elif resp.get("ok"):
                    # Server stored our blocks: expect them back as echo and
                    # skip them on arrival (already applied locally).
                    if outgoing:
                        try:
                            for bu in outgoing:
                                _mp_unacked.append(_mp_echo_key(bu))
                        except Exception:
                            pass
                    _mp_apply_snapshot(resp.get("players", []), resp.get("block_updates", []))
                    if resp.get("has_more"):
                        # Server paginated: don't wait a full tick for the rest.
                        continue
                # Cap outgoing per tick so one frame can't build a giant datagram.
                # (Snapshot already taken; excess stays for next tick because
                #  update() appends faster than we drain only in bursts.)
        except (OSError, ValueError, KeyError, AttributeError):
            pass
        elapsed = _mp_time.time() - tick_start
        _mp_time.sleep(max(0.0, MP_TICK_INTERVAL - elapsed))


def multiplayer_thread(blocks_placed, blocks_broken):
    # Back-compat entry: old mods may call this directly. Run one tick
    # of the legacy path instead of the old 4-RTT blocking sequence.
    try:
        _mp_legacy_once(list(blocks_placed) + list(blocks_broken))
    except (_mp_socket.timeout, OSError, KeyError):
        pass
    try:
        blocks_placed.clear()
        blocks_broken.clear()
    except AttributeError:
        pass


def process_multiplayer(PLAYERS, blocks_placed, blocks_broken, camera=None):
    global _mp_thread, thr, _mp_started, is_process_finished
    # Publish current camera snapshot for the net thread (main thread owns
    # the camera; net thread never touches it directly).
    # NOTE: camera must be passed explicitly. The module-global `render`
    # is only bound AFTER Render(init, update) returns (i.e. after the
    # game loop ends), so reading global `render` here raised NameError
    # every frame and _mp_state stayed at spawn forever.
    if camera is not None:
        with _mp_lock:
            _mp_state["coords"] = camera.position.tolist()
            _mp_state["yaw"] = camera.yaw
            _mp_state["pitch"] = camera.pitch
    else:
        try:
            with _mp_lock:
                _mp_state["coords"] = render.CAMERA.position.tolist()
                _mp_state["yaw"] = render.CAMERA.yaw
                _mp_state["pitch"] = render.CAMERA.pitch
        except (AttributeError, NameError):
            pass
    if not _mp_started:
        _mp_started = True
        _mp_thread = threading.Thread(
            target=_multiplayer_loop, args=(blocks_placed, blocks_broken), daemon=True,
        )
        _mp_thread.start()
        thr = _mp_thread
    # Drain inbound under lock, apply outside the lock (render calls).
    # Previously deferred entries (chunk not streamed in yet) retry first.
    with _mp_lock:
        local_posses = list(posses)
        local_rotations = list(rotations)
        pending = list(block_updates)
        block_updates.clear()
    pending = _mp_deferred + pending
    _mp_deferred[:] = []
    still_deferred = []
    try:
        PLAYERS.instanedmodels["player"].instances = np.zeros(
            (0, 4, 4),
            dtype="f4"
        )

        PLAYERS.instanedmodels["player"].tex_insta = np.zeros(
            (0,),
            dtype="f4"
        )

        PLAYERS.instanedmodels["player"]._upload()

        if local_posses:
            PLAYERS.add_instances(
                local_posses,
                [11] * len(local_posses),
                "player",
                local_rotations
            )

        for bu in pending:
            try:
                n = len(bu)
            except TypeError:
                print(f"BLOCK UPDATE ERROR: UNKOWN BLOCK UPDATE:", bu)
                continue
            if n == 2:
                pos = bu[1]
            elif n == 3:
                pos = bu
            else:
                print(f"BLOCK UPDATE ERROR: UNKOWN BLOCK UPDATE:", bu)
                continue
            try:
                chunk_key = (pos[0] // 10 * 10, 0, pos[2] // 10 * 10)
            except (TypeError, IndexError):
                continue
            # Snapshot/delta for a chunk we haven't streamed in yet: hold
            # it for a later frame instead of generating the chunk here
            # (sync worldgen on the render thread = hitch) or dropping it.
            if chunk_key not in WORLD.chunks.positions_blocks:
                if len(still_deferred) < MP_DEFERRED_CAP:
                    still_deferred.append(bu)
                continue
            try:
                if n == 2:
                    # No cascade here: the sender already ran update()
                    # and synced every product as its own entry.
                    WORLD.place_block(get_block(*bu), run_update=False)
                else:
                    WORLD.destroy_block(WORLD.get_block_at(bu))
            except (AttributeError, KeyError, TypeError, IndexError):
                continue
        _mp_deferred[:] = still_deferred
    except (AttributeError, KeyError):
        # PLAYERS/WORLD not ready yet (early frames).
        _mp_deferred[:] = still_deferred
        with _mp_lock:
            block_updates[:0] = pending
    is_process_finished = True


def stop_multiplayer_thread():
    global _mp_stop
    _mp_stop = True

source = None

frames_passed = 0
start_second = time.time()

blocks_textures = ["birch_leave", "birch_log", "cobblestone", "dirt", "grass", "oak_leave", "oak_log", "oak_planks", "sand", "stone", "water"]
generator = cycle(blocks_textures)
selected_block = next(generator)
pressed = False
cooldown = Cooldown(0.2)
cooldown2 = Cooldown(0.2)
cooldown3 = Cooldown(0.2)

pause = False

blocks_placed, blocks_broken = [], []

start_pos = None

def update(render):
    global coll, min_x, max_x, min_y, max_y, PLAYERS, playerdata, source, hud, frames_passed, start_second, SLECTED, selected_block, pressed,blocks_placed, blocks_broken, pause, start_pos

    if render.get_key(render.KEY_ESCAPE) == render.PRESS and cooldown3.is_active:
        pause = not pause
        if pause == True:
            if source is not None:
                try:
                    source.stop()
                except Exception:
                    pass
            render.set_input_mode(render.CURSOR,render.CURSOR_NORMAL)
        else:
            render.set_input_mode(render.CURSOR,render.CURSOR_DISABLED)

    if pause:
        return

    #play EPIC music
    try:
        _al_playing = getattr(openal, "AL_PLAYING", object()) if openal is not None else object()
        _is_playing = source is not None and source.get_state() == _al_playing
    except Exception:
        _is_playing = False
    if source is None or not _is_playing:
        source = playsound(f"assets/songs/{random.choice(["PEAK-SONG-mono.wav", "Song2-mono.wav", "Song3-mono.wav"])}", sound_position=(0, 3, 0))

    render.ctx.clear(0, 0, 0)

    listed_camera = render.CAMERA.position.tolist()
    # floor, not int(): int() truncates toward zero, so e.g. x=-0.5 mapped
    # to chunk 0 while the blocks there belong to chunk -10 (which then
    # renders a stale dummy under the player's feet).
    inted_camera = list(map(math.floor, listed_camera))
    camera_chunk_pos = [inted_camera[0]//10*10, 0, inted_camera[2]//10*10]

    # Threaded streaming: submit missing chunks to workers, upload at
    # most UPLOADS_PER_FRAME finished ones (one occupancy refresh).
    # Frame cost stays bounded no matter how fast the player moves;
    # distant chunks pop in over following frames instead of freezing.
    _submitted, _added = WORLD.ensure_chunks_around(
        camera_chunk_pos, RENDER_DISTANCE
    )
    if _added:
        for pos in WORLD.chunks.positions_blocks:
            if pos[0] < min_x:
                min_x = pos[0]
            if pos[0] > max_x:
                max_x = pos[0]
            if pos[0] < min_y:
                min_y = pos[0]
            if pos[0] > max_y:
                max_y = pos[0]


    all_sets = [
        WORLD.chunks.positions_blocks[(x, 0, z)].blocks.occupied
        for x, z in square_range(camera_chunk_pos, 1, 10)
        if (x, 0, z) in WORLD.chunks.positions_blocks
    ]
    last = set().union(*all_sets)

    render.CAMERA.update(last)
    coll.update(inted_camera)
    coll.render()
    block_placed, block_removed = None, None

    if result := raycast(last, render.CAMERA.eye_pos, render.CAMERA.front): #eye_pos bc ray starts from eyes
        position, normal = result
    
        a = Matrix44.from_scale([1.02, 1.02, 1.02]) @ Matrix44.from_translation(position)

        SLECTED.instanedmodels["selected"].instances[0] = a

        SLECTED.instanedmodels["selected"]._upload()

        if render.get_mouse_button(render.MOUSE_BUTTON_LEFT) == render.PRESS and cooldown.is_active:
            # place_block cascades Block.update() products; sync every
            # placed block so remotes reproduce the same result.
            # (block_placed keeps its old meaning for mods: the clicked block.)
            block_placed = (selected_block, (position + normal).tolist())
            for new_block in WORLD.place_block(get_block(*block_placed)):
                # Cap outgoing queue: if the net thread stalls, don't let
                # an unbounded list build up (old code grew forever).
                with _mp_lock:
                    if len(blocks_placed) < 500:
                        blocks_placed.append(
                            (new_block.block, list(new_block.position)))

        if render.get_mouse_button(render.MOUSE_BUTTON_RIGHT) == render.PRESS and cooldown2.is_active:
            WORLD.destroy_block(WORLD.get_block_at(position.tolist()))
            block_removed = position.tolist()
            with _mp_lock:
                if len(blocks_broken) < 500:
                    blocks_broken.append(block_removed)



    # Time-sliced block updates: every 0.2s the queued products of
    # Block.update() are placed (+ updated in turn). Returned blocks are
    # synced like clicked ones in multiplayer. The 2000 cap covers ~10s
    # of fully stalled network (sends drain 200/tick); beyond it newest
    # entries drop rather than growing forever.
    for queue_block in WORLD.poll_update_queue():
        if MULTIPLAYER:
            with _mp_lock:
                if len(blocks_placed) < 2000:
                    blocks_placed.append(
                        (queue_block.block, list(queue_block.position)))

    if MULTIPLAYER:
        process_multiplayer(PLAYERS, blocks_placed, blocks_broken, render.CAMERA)

    for name in mods_names:
        exec(f"globals()['mods'].{name}.Mod.update(globals(), locals())", globals(), locals())

    WORLD.render_chunks(camera_chunk_pos, RENDER_DISTANCE)

    if MULTIPLAYER:
        PLAYERS.render()

    TEXT.render()


    if MOVE_WINDOW:
        x = datetime.datetime.now()

        if x.minute == 46:
            if start_pos is None:
                start_pos = render.get_window_pos()

            render.set_window_pos(random.randrange(0, 700), random.randrange(0, 700))

        elif x.minute == 47 and start_pos is not None:
            render.set_window_pos(*start_pos)
            start_pos = None


    if render.get_key(render.KEY_LEFT_ALT) == render.PRESS and not pressed:
        selected_block = next(generator)
        pressed = True
        hud.update_text("sb", f"SELECTED BLOCK: {selected_block.replace("_", " ")}", [0, 30])
        
    elif render.get_key(render.KEY_LEFT_ALT) != render.PRESS and pressed:
        pressed = False


    hud.render()

    if result:
        SLECTED.render()

    if time.time() - start_second >= 1:
        hud.update_text("FPS", f"FPS: {frames_passed}", [0, 0])
        frames_passed = 0
        start_second = time.time()

    frames_passed += 1
    

render = Render(init, update)

try:
    WORLD.shutdown_threads(wait=False)
except (AttributeError, NameError):
    pass

source.stop()

if MULTIPLAYER:
    try:
        stop_multiplayer_thread()
    except NameError:
        pass
    try:
        # Best-effort disconnect: don't hang shutdown on a lost packet.
        NETWORK.socket.settimeout(0.5)
        NETWORK.send(NETWORK.tag({"disconnect": True}))
    except Exception:
        pass
    try:
        NETWORK.close()
    except Exception:
        pass

if not MULTIPLAYER:
    print("Saving world")
    data = bytes()
    for chunk in WORLD.chunks.blocks_list:
        for block in chunk.blocks.blocks_list:            
            data += struct.pack('>qqqB', *block.position, block.texture)

    save("world.bin", data)

    data = struct.pack(">ddd", *(render.CAMERA.position.tolist()))

    save("player.bin", data)

    print("Saved world")

    

print("Stopped executing game.")
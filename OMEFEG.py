import datetime
from itertools import cycle
from Cooldown import Cooldown
import os
import sys
import time
import math
import random as _random_module  # explicit: was previously relying on star-import
import importlib as _importlib
from random import Random  # explicit: was via `from Render import *`
import json

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
import struct


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
        
    

with open("worldgeneration/worldGeneration.json", "r") as f:
    rules = json.load(f)

def convert_to_blocks(data):
    # struct.iter_unpack in C (was Python int.from_bytes per field per
    # block). Truncates torn tail like World.load_saved_blocks.
    if not data:
        return []
    _n = len(data) // 25 * 25
    if _n != len(data):
        data = data[:_n]
    blocks = []
    _append = blocks.append
    try:
        for x, y, z, t in struct.iter_unpack('>qqqB', data):
            try:
                b = get_texture(t, x, y, z)
            except Exception:
                continue
            if b is not None:
                _append(b)
    except Exception:
        # Fallback to the old byte-wise path on struct failure.
        idx = 0
        while idx + 25 <= len(data):
            try:
                x = int.from_bytes(data[idx:idx+8], signed=True)
                idx += 8
                y = int.from_bytes(data[idx:idx+8], signed=True)
                idx += 8
                z = int.from_bytes(data[idx:idx+8], signed=True)
                idx += 8
                t = int.from_bytes(data[idx:idx+1])
                idx += 1
                _append(get_texture(t, x, y, z))
            except Exception:
                break
    return blocks

mods_names = []
# Cached mod entry points: avoids per-frame exec() recompile (was
# exec(f"...Mod.update...") for every mod on every frame).
mods_update_funcs = []
mods_init_funcs = []

# Hoisted per-frame constants (were rebuilt as list literals each frame).
_SONGS = os.listdir("assets/songs")
# 3x3 chunk neighbourhood offsets around the camera chunk (10-block step).
# Replaces square_range(camera, 1, 10) alloc per frame in update().
_CHUNK_NEIGHBOUR_OFFSETS = tuple(
    (dx * 10, dz * 10) for dx in (-1, 0, 1) for dz in (-1, 0, 1)
)
# Collision-set cache: update() rebuilt set().union(*9 chunk sets) every
# frame (~5k tuple allocs). Rebuilt only when membership changes.
_occ_cache = set()
_occ_cache_sig = None
# Selection-highlight cache: skip Matrix44 alloc + full buffer upload when
# the raycast target did not move.
_selected_cache_pos = None
_selected_cache_normal = None
# Multiplayer PLAYERS cache: skip zero+re-upload when nobody moved.
_mp_last_posses_sig = None
# Multiplayer address-box cache: update_text() rebuilds ALL glyph
# instances, so only call it when the buffer actually changed.
_mp_address_cache = None

def load_mods():
    if not os.path.isdir("mods"):
        # Empty/missing mods dir in the APK (e.g. Android): nothing to load.
        return
    for mod in os.listdir("mods"):
        print(f"Loading mod: {mod}")
        try:
            module = _importlib.import_module(f"mods.{mod}.Mod")
        except Exception as e:
            print(f"Failed to load mod {mod}: {e}")
            continue
        mods_names.append(mod)
        try:
            _mod_obj = getattr(module, "Mod", module)
            _init = getattr(_mod_obj, "init", None)
            _update = getattr(_mod_obj, "update", None)
            if callable(_init):
                mods_init_funcs.append(_init)
            if callable(_update):
                mods_update_funcs.append(_update)
        except Exception:
            pass

def colletced(render):
    render.CAMERA.max_jumps += 1
    pos = None
    while pos is None:
        x, z = random.randrange(min_x, max_x), random.randrange(min_y, max_y)
        pos = WORLD.get_block_y_at(x, z)

    pos += 1

    coll.add_collectibles([x, pos, z], [0], [colletced])

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
    return list(struct.unpack(">dddff", data))


class Menus:
    def __init__(self, render):
        self.indexis = {}
        self.active = set()
        self._render = render

    def load_template(self, idx_or_name, filename, callbacks_lookup):

        if idx_or_name in self.indexis:
            raise KeyError(f"{idx_or_name} already exists!!")

        text = HUDText(render=self._render, charset=CHARSET)

        with open(filename, "r") as f:
            content = json.load(f)

        for index, element in enumerate(content.get("elements", [])):
            callback = callbacks_lookup.get(element.get("callback"))
            identifier = element.get("id", f"{idx_or_name}:{index}")
            text_value = element.get("text", "No text component found")
            # NOTE: no manual x-shift here. InstancedText already
            # autocenters every entry on its anchor, and the click box
            # uses the same centered span; shifting here would cancel the
            # centering (and misalign clicks). Anchors live in the JSONs.
            position = list(element.get("pos", (30, 30)))
            text.add_texts(
                [text_value],
                [position],
                [identifier],
                [callback],
            )

        self.indexis[idx_or_name] = text

    def activate(self, idx_or_name):
        self.active.add(idx_or_name)
        # Visibility follows activation: desktop redraws every frame so
        # this is a no-op there, but mobile canvases keep drawing
        # everything ever attached -- without this, deactivated menus
        # stay on screen forever.
        try:
            self.indexis[idx_or_name].set_visible(True)
        except (KeyError, AttributeError):
            pass

    def deactivate(self, idx_or_name):
        self.active.discard(idx_or_name)
        try:
            self.indexis[idx_or_name].set_visible(False)
        except (KeyError, AttributeError):
            pass

    def render(self):
        # Snapshot: button callbacks activate/deactivate menus
        # mid-iteration; iterating a copy keeps the switch deterministic
        # (next frame draws exactly the new set).
        for up in tuple(self.active):
            self.indexis[up].render()

def set_variable(value):
    global selected

    selected = value

def load_settings(data):
    return [True if i else False for i in data]

settings_loaded = open_save_file("preferences.bin", load_settings)

settings = {
    "audio": settings_loaded[0] if settings_loaded else True,
    "shaders": settings_loaded[1] if settings_loaded else False
}

def save_settings():
    global settings

    data = [settings["audio"], settings["shaders"]]

    save("preferences.bin", bytes(data))

def toggle_audio():
    global menus, settings

    settings["audio"] = not settings["audio"]

    menus.indexis["settings"].update_text("audio", "Audio: " + ("ON" if settings["audio"] else "OFF"))

    save_settings()

def toggle_shaders():
    global menus, settings

    settings["shaders"] = not settings["shaders"]

    menus.indexis["settings"].update_text("shaders", "Shaders: " + ("ON" if settings["shaders"] else "OFF"))

    save_settings()

def back_from_settings():
    global menus

    menus.deactivate("settings")
    menus.activate("esc_screen")

def to_settings():
    global menus

    menus.deactivate("esc_screen")
    menus.activate("settings")

def remove_esc_screen(render):
    global pause

    pause = False

    render.set_input_mode(render.CURSOR,render.CURSOR_DISABLED)

    menus.deactivate("esc_screen")
    menus.deactivate("settings")

def hide_esc_screen():

    menus.deactivate("esc_screen")

CHUNK_GENERATION_THREADS = 5

def init(render):
    global TEXT, coll, WORLD, RENDER_DISTANCE, NETWORK, PLAYERS, min_x, max_x, min_y, max_y, hud, SLECTED, menus, selected, MULTIPLAYER, LOAD_WORLD

    RENDER_DISTANCE = 15

    menus = Menus(render)


    menus.load_template("mainscreen", "assets/layouts/main_screen.json", {"load_world": lambda: set_variable("load_world"), "erase_world": lambda: set_variable("erase_world"), "multiplayer": lambda: set_variable("multiplayer")})
    menus.activate("mainscreen")

    menus.load_template("multiplayer", "assets/layouts/multiplayer_ask.json", {"done": lambda: set_variable("done")})

    menus.load_template("esc_screen", "assets/layouts/esc_screen.json", {"done": lambda: set_variable("done"), "open_settings": to_settings, "close_esc_screen": lambda: remove_esc_screen(render), "save_and_quit": lambda: render.set_window_should_close(True), "hide":hide_esc_screen})

    menus.load_template("settings", "assets/layouts/settings.json", {"toggle_audio": toggle_audio, "toggle_shaders": toggle_shaders, "back": back_from_settings})

    menus.indexis["settings"].update_text("shaders", "Shaders: " + ("ON" if settings["shaders"] else "OFF"))
    menus.indexis["settings"].update_text("audio", "Audio: " + ("ON" if settings["audio"] else "OFF"))

    selected = None

    render.set_input_mode(render.CURSOR,render.CURSOR_NORMAL)

    print("Showing main menu")

    while selected is None and not render.window_should_close():

        render.poll_events()

        render.ctx.clear()

        menus.render()

        render.swap_buffers()


    menus.deactivate("mainscreen")

    print("Selected:", selected)

    MULTIPLAYER, LOAD_WORLD = False, False

    ADDRESS = ""

    if selected == "multiplayer":
        MULTIPLAYER = True
    elif selected == "load_world":
        LOAD_WORLD = True

    # Temporary diagnostic switch (env OMEFEG_NOSAVE=1): keep every chunk
    # in RAM, never touch per-chunk save files (no reads, no writes, no
    # directories). Loading an old world makes no sense without them, so
    # it is forced to a fresh world. Revert by unsetting the variable
    # (default off). Anything evicted is regenerated on return and edits
    # outside RAM are lost, so don't build anything you love in this mode.
    NO_SAVE = os.environ.get("OMEFEG_NOSAVE") == "1"
    if NO_SAVE:
        LOAD_WORLD = False
        print("OMEFEG_NOSAVE=1: chunk persistence DISABLED (RAM only, nothing is saved)")

    if MULTIPLAYER:
        selected = None

        menus.activate("multiplayer")

    render.set_text_buffer("")

    global _mp_address_cache
    _mp_address_cache = None
    while selected is None and not render.window_should_close():

        render.poll_events()

        render.ctx.clear()

        # update_text() rebuilds ALL glyph instances + full GPU upload, so
        # only call it when the typed buffer actually changed (was: every
        # frame while the address box was open).
        _buf = render.request_text_buffer()
        if _buf != _mp_address_cache:
            _mp_address_cache = _buf
            menus.indexis["multiplayer"].update_text("address", _buf)

        menus.render()

        render.swap_buffers()

    ADDRESS = render.request_text_buffer().lower()

    render.set_text_buffer("")

    # The address prompt would otherwise stay rendered (and clickable) over
    # gameplay forever, like any menu left in `active`.
    menus.deactivate("multiplayer")

    render.set_input_mode(render.CURSOR,render.CURSOR_DISABLED)

    if selected is None:
        return


    seed = string_to_fixed_number(str(0), 10)
    random_seed = Random(seed)

    FLAT = False

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
                result = login_with_github()

                if result == "disabled":
                    notification("OMEFEG", "Your OMEFEG account is disabled, go to https://tombenax.pythonanywhere.com and enable the account")
                elif result is None:
                    notification("OMEFEG", "You don't have an OMEFEG account, go to https://tombnax.pythonanywhere.com and login with Github")
                else:
                    print("Username is", result)


            else:
                if random.random() * 100 < 99:
                    heightmap = PerlinNoiseFactory(octaves=1, seed=seed)
                    sin_world = False
                else:
                    heightmap = sin()
                    sin_world = True

    WORLD = World(render, 1000, [0, 0, 0], 100) #, random_seed, heightmap, rules, sin_world=sin_world, biomes = not FLAT, persistent=(not MULTIPLAYER and not NO_SAVE))

    render.CAMERA.position[1] = WORLD.radius+5
    render.CAMERA.position += np.array(WORLD.origin, dtype="f4")

    #render.CAMERA.position[0] = 0
    #render.CAMERA.position[1] = 0
    #render.CAMERA.position[2] = 0

    if LOAD_WORLD:
        saved_player = open_save_file("player.bin", load_player)
        if saved_player is not None:
            try:
                render.CAMERA.position = np.array(saved_player[0:3], dtype="f4")
                render.CAMERA.yaw = float(saved_player[3])
                render.CAMERA.pitch = float(saved_player[4])
                print(saved_player, render.CAMERA.position, render.CAMERA.yaw, render.CAMERA.pitch)
            except Exception:
                pass

    min_x = 0
    max_x = 1
    min_y = 0
    max_y = 1

    TEXT = InstancedText(render=render, charset=CHARSET)

    # Single-pass max-Y (was 16x get_y_at() -> 16 full position-array
    # scans via Chunk.get_block_pos_at). One dict scan over the chunks
    # that actually contain x in [0, 15], z == 0.
    higher = -float("inf")
    try:
        _need_xs = set(range(len("Welcome to OMEFEG")))
        for _ckey, _chunk in WORLD.chunks.positions_blocks.items():
            _cx = _ckey[0]
            if _cx > 15 or _cx + 9 < 0:
                continue
            for _bpos in _chunk.blocks.positions:
                try:
                    if _bpos[2] == 0 and _bpos[0] in _need_xs:
                        _y1 = _bpos[1] + 1
                        if _y1 > higher:
                            higher = _y1
                except (TypeError, IndexError):
                    continue
        if higher == -float("inf"):
            higher = 0
    except Exception:
        higher = 0
        for i in range(len("Welcome to OMEFEG")):
            try:
                _y = WORLD.get_y_at(i, 0)
                if _y is not None and _y > higher:
                    higher = _y
            except Exception:
                continue


    TEXT.add_texts(["Welcome to OMEFEG"], [[0, higher, 0]])
    

    if MULTIPLAYER:
        NETWORK = Network(
            ADDRESS,
            44699,
            result
        )



        PLAYERS = Model(render)
        v, i = load_obj("assets/models/player.obj")
        PLAYERS.add_model("player", vertices=v, indices=i)

    SLECTED = Model(render)
    v, i = load_obj("assets/models/block.obj")
    SLECTED.add_model("selected", vertices=v, indices=i)
    SLECTED.add_instances([[0, 0, 0]], [12], "selected")

    coll = Collectible(render)

    pos = WORLD.get_block_y_at(render.CAMERA.position[0]+5, render.CAMERA.position[2])
    pos += 1

    coll.add_collectibles([render.CAMERA.position[0]+5, pos, render.CAMERA.position[2]], [0], [colletced])

    hud = HUDText(
    render=render,
    charset=CHARSET
    )

    # Top-left status texts stay left-aligned (centered would push them
    # half off-screen); menus default to centered.
    hud.add_texts(
        ["FPS: negative Infinity", "SELECTED BLOCK: birch leave", "X: HELL NAH Y: NEGATIVE INFINITY Z: EASTER EGGS BE LIKE", "BPS: FUCK MYSELF"],
        [[0, 0], [0, 30], [WIDTH, 0], [WIDTH, 30]],
        ["FPS", "sb", "XYZ", "bps"],
        centered=False,
    )

    render.set_window_size_callback(lambda x,y,z: render.resized(y,z))

    render.set_lights([(0, 50, 0)], [(1, 1, 1, 1)])

    load_mods()

    # Cached init funcs (was exec() per mod with string recompile).
    for _init_fn in list(mods_init_funcs):
        try:
            _init_fn(globals(), locals())
        except Exception as _e:
            print(f"Mod init failed: {_e}")

    

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
        # Skip zero+re-upload when nobody moved (was 2 full buffer
        # orphan+write per frame even with zero players). Signature is
        # cheap: lengths + first/last positions.
        global _mp_last_posses_sig
        try:
            _sig = (len(local_posses),
                    tuple(local_posses[0]) if local_posses else None,
                    tuple(local_posses[-1]) if local_posses else None,
                    len(local_rotations))
        except Exception:
            _sig = None
        if _sig != _mp_last_posses_sig:
            _mp_last_posses_sig = _sig
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

sound_player = SoundPlayer()

ASK_EVERY = 1 #frames

last_asked = 0


def update(render):
    global coll, min_x, max_x
    global min_y, max_y, PLAYERS
    global playerdata, hud, frames_passed
    global start_second, SLECTED, selected_block
    global pressed,blocks_placed, blocks_broken
    global pause, start_pos, MULTIPLAYER
    global LOAD_WORLD, sound_player, last_asked

    last_asked += 1

    if render.get_key(render.KEY_ESCAPE) == render.PRESS and cooldown3.is_active:
        pause = not pause
        if pause == True:
            sound_player.stop()
            render.set_input_mode(render.CURSOR,render.CURSOR_NORMAL)

            menus.activate("esc_screen")
        else:
            render.set_input_mode(render.CURSOR,render.CURSOR_DISABLED)

            menus.deactivate("esc_screen")
            menus.deactivate("settings")

    menus.render()

    if pause:
        return

    if render.get_key(render.KEY_R):
        render.CAMERA.position[1] = WORLD.origin[1] + WORLD.radius

    #play EPIC music
    if not sound_player.is_playing(render.dt) and settings["audio"]:
        sound_player.playsound(f"assets/songs/{_random_module.choice(_SONGS)}", sound_position=(0, 3, 0))

    elif not sound_player.is_playing(render.dt) and not settings["audio"]:
        sound_player.stop()

    listed_camera = render.CAMERA.position.tolist()
    # floor, not int(): int() truncates toward zero, so e.g. x=-0.5 mapped
    # to chunk 0 while the blocks there belong to chunk -10 (which then
    # renders a stale dummy under the player's feet).
    inted_camera = list(map(math.floor, listed_camera))
    camera_chunk_pos = [int(str(inted_camera[0])[0:-1]+"0"), int(str(inted_camera[1])[0:-1]+"0"), int(str(inted_camera[2])[0:-1]+"0")]   #[inted_camera[0]//10*10, 0, inted_camera[2]//10*10]

    if last_asked >= ASK_EVERY:
        last_asked = 0
        for x, z in square_range(camera_chunk_pos, RENDER_DISTANCE, 10):
            WORLD.generate_chunk(x, inted_camera[1], z)

    render.CAMERA.update(WORLD.blocks.occupied, WORLD)
    coll.update(inted_camera)
    coll.render()
    block_placed, block_removed = None, None

    if result := raycast(WORLD.blocks.occupied, render.CAMERA.eye_pos, render.CAMERA.front): #eye_pos bc ray starts from eyes
        position, normal = result

        # Skip Matrix44 allocs + full buffer upload when the highlight did
        # not move (was every frame while aiming at any block).
        global _selected_cache_pos, _selected_cache_normal
        try:
            _pos_t = tuple(position.tolist())
        except Exception:
            _pos_t = tuple(position)
        try:
            _nor_t = tuple(normal.tolist())
        except Exception:
            _nor_t = tuple(normal)
        if _pos_t != _selected_cache_pos or _nor_t != _selected_cache_normal:
            _selected_cache_pos = _pos_t
            _selected_cache_normal = _nor_t
            a = Matrix44.from_scale([1.02, 1.02, 1.02]) @ Matrix44.from_translation(position)

            SLECTED.instanedmodels["selected"].instances[0] = a

            SLECTED.instanedmodels["selected"]._upload()

        if render.get_mouse_button(render.MOUSE_BUTTON_LEFT) == render.PRESS and cooldown.is_active:
            # place_block cascades Block.update() products; sync every
            # placed block so remotes reproduce the same result.
            # (block_placed keeps its old meaning for mods: the clicked block.)
            block_placed = (selected_block, (position + normal).tolist())
            _new_blocks = WORLD.place_block(get_block(*block_placed))
            if _new_blocks:
                # Single lock acquisition for the whole batch (was one
                # lock per block).
                with _mp_lock:
                    _room = 500 - len(blocks_placed)
                    if _room > 0:
                        for new_block in _new_blocks[:_room]:
                            blocks_placed.append(
                                (new_block.block, list(new_block.position)))

        if render.get_mouse_button(render.MOUSE_BUTTON_RIGHT) == render.PRESS and cooldown2.is_active:
            WORLD.destroy_block(WORLD.get_block_at(position.tolist()))
            block_removed = position.tolist()
            with _mp_lock:
                if len(blocks_broken) < 500:
                    blocks_broken.append(block_removed)

    if MULTIPLAYER:
        process_multiplayer(PLAYERS, blocks_placed, blocks_broken, render.CAMERA)

    # Cached mod funcs (was exec() string recompile per mod per frame).
    _g = globals()
    _l = locals()
    for _update_fn in mods_update_funcs:
        try:
            _update_fn(_g, _l)
        except Exception:
            continue

    WORLD.update()
    WORLD.render_blocks()

    if MULTIPLAYER:
        PLAYERS.render()

    TEXT.render()

    # Single datetime call per frame (was 3x per frame).
    _now = datetime.datetime.now()
    if _now.day == 1 and _now.month == 4:
        x = _now

        if x.minute == 46:
            if start_pos is None:
                start_pos = render.get_window_pos()

            render.set_window_pos(_random_module.randrange(0, 700), _random_module.randrange(0, 700))

        elif x.minute == 47 and start_pos is not None:
            render.set_window_pos(*start_pos)
            start_pos = None


    if render.get_key(render.KEY_LEFT_ALT) == render.PRESS and not pressed:
        selected_block = next(generator)
        pressed = True
        selected_text = "SELECTED BLOCK: " + selected_block.replace("_", " ")
        hud.update_text("sb", selected_text, [0, 30])
        
    elif render.get_key(render.KEY_LEFT_ALT) != render.PRESS and pressed:
        pressed = False

    hud.update_text("XYZ", f"X: {round(render.CAMERA.position.tolist()[0])} Y: {round(render.CAMERA.position.tolist()[1])} Z: {round(render.CAMERA.position.tolist()[2])}", [0, 60])

    hud.update_text("bps", f"BPS: {render.CAMERA.bps}", [WIDTH-200, 0])

    hud.render()

    if result:
        SLECTED.render()

    if time.time() - start_second >= 1:
        fps_text = f"FPS: {frames_passed}"
        hud.update_text("FPS", fps_text, [0, 0])
        frames_passed = 0
        start_second = time.time()

    frames_passed += 1
    

render = Render(init, update, settings)

try:
    WORLD.shutdown_threads(wait=False)
except (AttributeError, NameError):
    pass

if sound_player.is_playing:
    sound_player.stop()

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

try:
    _should_save = not MULTIPLAYER
except NameError:
    _should_save = False
if _should_save:
    print("Saving world")
    try:
        saved_chunks = WORLD.save_all_loaded_chunks()
    except (AttributeError, NameError):
        saved_chunks = 0
    print(f"Saved {saved_chunks} chunks around the player (far chunks were already saved on unload)")

    try:
        data = struct.pack(">dddff", *render.CAMERA.position.tolist(), render.CAMERA.yaw, render.CAMERA.pitch)

        save("player.bin", data)
    except (AttributeError, NameError):
        pass

    print("Saved world")

    

print("Stopped executing game.")
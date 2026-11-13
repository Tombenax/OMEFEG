import check_and_install_packages

del check_and_install_packages

import datetime
from Cooldown import Cooldown
import os
import sys
import time
import math
import random as _random_module
import importlib as _importlib
from random import Random 
import json

from Entity import Entitys
from Player import Player

from BehaviurScript import *

from BlenderModel import attach_blender_model

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
from Vec3 import Vec3

from Items3D import Items3D

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
                b = get_block(t, Vec3(x, y, z))
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
                _append(get_block(t, Vec3(x, y, z)))
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

    coll.add_collectibles([Vec3(x, pos, z)], [0], [colletced])

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

def load_world(data):
    posess = []
    texxes = []

    for i in range(0, len(data), 25):
        d = list(struct.unpack(">dddb", data[i:i+25]))
        x = d[0]
        y = d[1]
        z = d[2]
        t = d[3]

        posess.append([x, y, z])
        texxes.append(t)

    return posess, texxes

def load_chunks(data):
    chunks = set()

    for i in range(0, len(data), 24):
        d = list(struct.unpack(">ddd", data[i:i+24]))
        x = d[0]
        y = d[1]
        z = d[2]

        chunks.add((x, y, z))

    return chunks

        


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

PLAYER = None

NPCS = None

IS_BENCH_OPENED = False

def init(render):
    global TEXT, coll, WORLD
    global RENDER_DISTANCE, NETWORK, PLAYERS
    global min_x, max_x, min_y, max_y, hud
    global SLECTED, menus, selected, MULTIPLAYER
    global LOAD_WORLD, PLAYER, NPCS, TEST_ENTITY
    global ITEMS, coldbar, body_slots, bench_gui

    PLAYER = Player(render)

    RENDER_DISTANCE = 15

    menus = Menus(render)

    NPCS = Model(render)

    attach_blender_model(NPCS, "NPC", "assets/models/NPC.omefeg", (10, 1001, 0), 15)

    NPCS.play_animation("NPC", "Idle")

    ITEMS = Items3D(render)

    coldbar = INVSCR(render, INVSCR_IMAGE, pos_x="center", pos_y="bottom", scale=2.5)

    body_slots = INVSCR(render, BODY_SLOTS, pos_x="left", pos_y="center", scale=2.5)

    bench_gui = INVSCR(render, BENCH_IMG, pos_x="center", pos_y="center", scale=10)

    ITEMS.add_item(Vec3(5, 1_000_001, 0), "assets/models/Backpack.obj", BACKPACK)

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

    WORLD = World(render, 1_000_000, [0, 0, 0], 100) #, random_seed, heightmap, rules, sin_world=sin_world, biomes = not FLAT, persistent=(not MULTIPLAYER and not NO_SAVE))

    WORLD.place_block(get_block(BENCH, Vec3(5, WORLD.radius+1, 0)))

    PLAYER.set_pos(Vec3(0, WORLD.radius+1, 0))

    TEST_ENTITY = Entitys(render)

    BS = BehaviurScript({ # not b***s**t
        "init":[
        ],

        "update":[
            START_ANIMATION("Idle", True),
            RANDOM_NUMBER(1, 3, "RAND_TIME_IDLE"),
            MULT_VEC("RAND_TIME_IDLE", 2, "RAND_TIME_IDLE"),
            WAIT("RAND_TIME_IDLE"),

            START_ANIMATION("IdleToWalk", False),
            WAIT(2),

            START_ANIMATION("Walk", True),

            SET_VARIABLE("PLAYER_POS", PLAYER.pos),
            RANDOM_NUMBER(1, 10, "RAND_TIME_MOVE"),

            #calculate direction

            MIN_VEC("position", "PLAYER_POS", "DIR_VECT"),

            MULT_VEC("DIR_VECT", Vec3(1, 0, 1)),
            MULT_VEC("DIR_VECT", Vec3(-1, 0, -1)),

            #MUL_VEC_INT("RAND_VECT", "RAND_TIME_MOVE"),

            ROTATE_FROM_DIRECTION_VECTOR("DIR_VECT", 90),
            MOVE("DIR_VECT", "RAND_TIME_MOVE"),
        ]
    })

    TEST_ENTITY.add_entity("assets/models/cat.omefeg", Vec3(3, WORLD.radius+1, 0), BS, CAT)

    if LOAD_WORLD:
        saved_player = open_save_file("player.bin", load_player)
        saved_world = open_save_file("world.bin", load_world)
        saved_chunks = open_save_file("chunks.bin", load_chunks)

        PLAYER.set_pos(Vec3(*saved_player[0:3]))
        PLAYER.camera.yaw = float(saved_player[3])
        PLAYER.camera.pitch = float(saved_player[4])

        WORLD.generated_chunks = saved_chunks

        WORLD.place_blocks(saved_world[0], saved_world[1])


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


    TEXT.add_texts(["Welcome to OMEFEG"], [Vec3(0, higher, 0)])
    

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
    SLECTED.add_instances([Vec3(0, 0, 0)], [SELECTED], "selected")

    pos = WORLD.get_block_y_at(PLAYER.pos[0]+5, PLAYER.pos[2])
    pos += 1

    hud = HUDText(
    render=render,
    charset=CHARSET
    )

    hud.add_texts(
        ["FPS: negative Infinity", "X: HELL NAH Y: NEGATIVE INFINITY Z: EASTER EGGS BE LIKE", "BPS: F**K MYSELF"],
        [[0, 0], [0, 30], [WIDTH, 0]],
        ["FPS", "XYZ", "bps"],
        centered=False,
    )

    render.set_window_size_callback(lambda x,y,z: render.resized(y,z))

    render.set_lights([Vec3(0, 50, 0)], [(1, 1, 1, 1)])

    render.set_cursor_pos(WIDTH/2, HEIGHT/2)

    load_mods()

    for _init_fn in list(mods_init_funcs):
        try:
            _init_fn(globals(), locals())
        except Exception as _e:
            print(f"Mod init failed: {_e}")


frames_passed = 0
start_second = time.time()

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


def update(render:Render):
    global coll, min_x, max_x
    global min_y, max_y, PLAYERS
    global playerdata, hud, frames_passed
    global start_second, SLECTED, selected_block
    global pressed,blocks_placed, blocks_broken
    global pause, start_pos, MULTIPLAYER
    global LOAD_WORLD, sound_player, last_asked
    global TEST_ENTITY, ITEMS, coldbar, body_slots
    global bench_gui, IS_BENCH_OPENED

    last_asked += 1

    if IS_BENCH_OPENED:
        bench_gui.render()
        coldbar.render()
        PLAYER.render_2D_stuff()

        #print(x, y)

        slot1 = "empty"
        slot2 = "empty"
        slot3 = "empty"
        slot4 = "empty"

        for pos, name in zip(PLAYER.invitems.all_posses, PLAYER.inventory_list):
            x = pos.x
            y = pos.y

            if 20 <= x and 148 >= x:
                if 290 <= y and 418 >= y:
                    slot1 = get_block_name_from_texture(name)

            elif 220 <= x and 348 >= x:
                if 290 <= y and 418 >= y:
                    slot2 = get_block_name_from_texture(name)

            elif 420 <= x and 548 >= x:
                if 290 <= y and 418 >= y:
                    slot3 = get_block_name_from_texture(name)

            elif 620 <= x and 748 >= x:
                if 290 <= y and 418 >= y:
                    slot4 = get_block_name_from_texture(name)

        print(slot1, slot2, slot3, slot4)

        render.set_input_mode(render.CURSOR,render.CURSOR_NORMAL)

        pause = True

    if render.get_key(render.KEY_ESCAPE) == render.PRESS and cooldown3.is_active:
        pause = not pause
        if pause == True:
            sound_player.stop()
            render.set_input_mode(render.CURSOR,render.CURSOR_NORMAL)

            menus.activate("esc_screen")
        else:
            if IS_BENCH_OPENED: IS_BENCH_OPENED = False; PLAYER.rebuild_inv()
            render.set_input_mode(render.CURSOR,render.CURSOR_DISABLED)

            menus.deactivate("esc_screen")
            menus.deactivate("settings")

    splitted_buffer:list[str] = render.request_text_buffer().split(" ") 
    if (
    "tp" in splitted_buffer
    ):
        PLAYER.set_pos(Vec3(1001, 0, 0))

        render.set_text_buffer("")
        

    menus.render()

    if pause:
        return

    if render.get_key(render.KEY_R):
        PLAYER.set_pos(Vec3(0, WORLD.radius+1, 0))

    #play EPIC music
    if not sound_player.is_playing(render.dt) and settings["audio"]:
        sound_player.playsound(f"assets/songs/{_random_module.choice(_SONGS)}", sound_position=(0, 3, 0))

    elif not sound_player.is_playing(render.dt) and not settings["audio"]:
        sound_player.stop()

    inted_camera = Vec3(*(math.floor(coord) for coord in PLAYER.pos))
    camera_chunk_pos = inted_camera // 10 * 10

    if last_asked >= ASK_EVERY and not WORLD.generate_all_chunks:
        last_asked = 0
        for x, z in square_range_3_layers(camera_chunk_pos, 10):
            WORLD.generate_chunk(x, camera_chunk_pos.y, z)

    if a := PLAYER.update(WORLD):
        ITEMS.add_item(PLAYER.pos + Vec3(2, 0.5, 0), "assets/models/backpack.obj" if a == BACKPACK else "assets/models/block.obj", a)

    block_placed = None

    if result := raycast(WORLD.get_neighbours_extened_in_circle(PLAYER.pos, 10), render.CAMERA.eye_pos, render.CAMERA.front): #eye_pos bc ray starts from eyes
        position, normal = result

        a = Matrix44.from_scale([1.02, 1.02, 1.02]) @ Matrix44.from_translation(position)

        SLECTED.instanedmodels["selected"].active_instances[0] = a

        SLECTED.instanedmodels["selected"]._upload()


        if render.get_mouse_button(render.MOUSE_BUTTON_LEFT) == render.PRESS and cooldown.is_active:
            block_placed = (PLAYER.get_selcted_block(), position + normal)

            print(WORLD.get_block_at(position))

            if WORLD.get_block_at(position).block == "bench":
                IS_BENCH_OPENED = True
            else:
                if block_placed[0] is not None:
                    WORLD.place_block(get_block(*block_placed))

        if render.get_mouse_button(render.MOUSE_BUTTON_RIGHT) == render.PRESS and cooldown2.is_active:
            block = WORLD.get_block_at(position)
            WORLD.destroy_block(block)
            ITEMS.add_item(position, "assets/models/block.obj", block.texture)

    if MULTIPLAYER:
        process_multiplayer(PLAYERS, blocks_placed, blocks_broken, PLAYER.camera)

    _g = globals()
    _l = locals()
    for _update_fn in mods_update_funcs:
        try:
            _update_fn(_g, _l)
        except Exception:
            continue

    WORLD.update()
    WORLD.render_blocks()

    if result: SLECTED.render()

    ITEMS.update(render.dt, PLAYER)
    ITEMS.render()

    TEST_ENTITY.update(render.dt)
    TEST_ENTITY.render_entities()

    if MULTIPLAYER:
        PLAYERS.render()

    TEXT.render()

    coldbar.render()

    body_slots.render()

    PLAYER.render_2D_stuff()

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
        
    elif render.get_key(render.KEY_LEFT_ALT) != render.PRESS and pressed:
        pressed = False

    hud.update_text("XYZ", f"X: {round(PLAYER.pos.tolist()[0])} Y: {round(PLAYER.pos.tolist()[1])} Z: {round(PLAYER.pos.tolist()[2])}", [0, 30])

    hud.update_text("bps", f"BPS: {render.CAMERA.bps}", [WIDTH-200, 0])

    hud.render()

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

should_save = not MULTIPLAYER

if should_save:
    print("Saving world")

    world_data = bytes()

    lbl = len(WORLD.blocks.blocks_list)

    for idx, block in enumerate(WORLD.blocks.blocks_list):

        print(f"Save: {round((idx+1)/lbl*100, 2)}%")

        world_data += struct.pack(">dddb", *block.position, block.texture)

    save("world.bin", world_data)

    chunks_data = bytes()

    for chunk in WORLD.generated_chunks:

        chunks_data += struct.pack(">ddd", *chunk)

    save("chunks.bin", chunks_data)

    data = struct.pack(">dddff", *PLAYER.pos.tolist(), render.CAMERA.yaw, render.CAMERA.pitch)

    save("player.bin", data)

    print("Saved world")

openal.oalQuit()

print("Stopped executing game.")
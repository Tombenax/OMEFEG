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

        else:
            notification("World Not Found", "Your worl file was not found, if the file 'world.bin' is in %appdata%/OMEFEG then idk what the heck is happening, else just make a world")

            render.set_window_should_close(True)

            return
        
    else:
        for x, z in square_range([0, 0, 0], RENDER_DISTANCE, 10):
            if not [x, 0, z] in WORLD.chunks.positions:
                WORLD.generate_chunk_at([x, 0, z])
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, x)
                max_y = max(max_y, x)

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

    render.set_window_size_callback(lambda x,y,z: render.resized(render,y,z))

    load_mods()

    for name in mods_names:
        exec(f"globals()['mods'].{name}.Mod.init(globals(), locals())", globals(), locals())

posses, rotations = [], []
block_updates = []

def multiplayer_thread(blocks_placed, blocks_broken):

    global is_process_finished, posses, rotations, block_updates

    is_process_finished = False

    send_data_to_server({
        "setData": True,
        "id": NETWORK.id,
        "coords":render.CAMERA.position.tolist(),
        "yaw":render.CAMERA.yaw,
        "pitch": render.CAMERA.pitch
    }, NETWORK)

    playerdata = send_data_to_server({
        "getData": True
    }, NETWORK)

    block_update = []
    block_update.extend(blocks_placed)
    block_update.extend(blocks_broken)

    blocks_placed.clear()
    blocks_broken.clear()

    send_data_to_server({
        "setBlockData": True,
        "block update": block_update
    }, NETWORK)

    block_updates = send_data_to_server({
        "getBlockData": True,
        "id": NETWORK.id
    }, NETWORK)["block_updates"]


    posses.clear()
    rotations.clear()


    for p in playerdata["players"]:
        if p["id"] == NETWORK.id:
            continue

        posses.append(
            p["position"]
        )

        rotations.append(
            (
                p["pitch"],
                p["yaw"] - 90,
                0
            )
        )


is_process_finished = True

thr = None

def process_multiplayer(PLAYERS, blocks_placed, blocks_broken):
    global is_process_finished, thr, block_updates
    if is_process_finished:
        thr = threading.Thread(target=multiplayer_thread, args=(blocks_placed, blocks_broken), daemon=True)
        thr.start()
    elif not thr.is_alive():
        PLAYERS.instanedmodels["player"].instances = np.zeros(
            (0, 4, 4),
            dtype="f4"
        )

        PLAYERS.instanedmodels["player"].tex_insta = np.zeros(
            (0,),
            dtype="f4"
        )

        PLAYERS.instanedmodels["player"]._upload()

        if posses:
            PLAYERS.add_instances(
                posses,
                [11] * len(posses),
                "player",
                rotations
            )

        for bu in block_updates:
            if len(bu) == 2:
                WORLD.place_block(get_block(*bu))
            elif len(bu) == 3:
                WORLD.destroy_block(WORLD.get_block_at(bu))
            else:
                print(f"BLOCK UPDATE ERROR: UNKOWN BLOCK UPDATE:", bu)

        is_process_finished = True

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
            render.set_input_mode(render.CURSOR,render.CURSOR_NORMAL)
            source.stop()
        else:
            render.set_input_mode(render.CURSOR,render.CURSOR_DISABLED)

    if pause:
        return

    #play EPIC music
    if source is None or not source.get_state() == openal.AL_PLAYING:
        source = playsound(f"assets/songs/{random.choice(["PEAK-SONG-mono.wav", "Song2-mono.wav", "Song3-mono.wav"])}", sound_position=(0, 3, 0))

    render.ctx.clear(0, 0, 0)

    listed_camera = render.CAMERA.position.tolist()
    inted_camera = list(map(int, listed_camera))
    camera_chunk_pos = [inted_camera[0]//10*10, 0, inted_camera[2]//10*10]


    for x, z in square_range(camera_chunk_pos, RENDER_DISTANCE, 10):
        if not [x, 0, z] in WORLD.chunks.positions:
            WORLD.generate_chunk_at([x, 0, z])
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, x)
            max_y = max(max_y, x)


    all_sets = [WORLD.get_chunk_at([x, 0, z]).blocks.occupied for x, z in square_range(camera_chunk_pos, 1, 10)]
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
            WORLD.place_block(get_block(selected_block, (position + normal).tolist()))
            block_placed = (selected_block, (position + normal).tolist())
            blocks_placed.append(block_placed)

        if render.get_mouse_button(render.MOUSE_BUTTON_RIGHT) == render.PRESS and cooldown2.is_active:
            WORLD.destroy_block(WORLD.get_block_at(position.tolist()))
            block_removed = position.tolist()
            blocks_broken.append(block_removed)



    if MULTIPLAYER:
        process_multiplayer(PLAYERS, blocks_placed, blocks_broken)

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

source.stop()

if MULTIPLAYER:
    send_data_to_server({"disconnect": True, "id": NETWORK.id}, NETWORK)
    NETWORK.close()

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
import importlib
from itertools import cycle
from math import radians

from Cooldown import Cooldown
from Render import *
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

argParser = argparse.ArgumentParser()
argParser.add_argument("--multiplayer")
argParser.add_argument("--not_move_window")

parsedArgs = argParser.parse_args()

MULTIPLAYER = parsedArgs.multiplayer
if MULTIPLAYER:
    spl = MULTIPLAYER.split(":")
    PORT = int(spl[1])
    MULTIPLAYER = spl[0]

MOVE_WINDOW = not parsedArgs.not_move_window


CAMERA:Camera = None


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
            
seed = string_to_fixed_number(str(0), 256)
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

def generat_chunk_at(render, position:list[Number]):
    global max_x, min_x, max_y, min_y

    max_x = max(max_x, position[0]+10)
    min_x = min(min_x, position[0])
    max_y = max(max_y, position[2]+10)
    min_y = min(min_y, position[2])

    return Chunk(render, position, random_seed, heightmap, rules, sin_world=sin_world, biomes = not FLAT)


FOV = 60

PROJECTION = np.array(Matrix44.perspective_projection(FOV, WIDTH/HEIGHT, 0.1, 1000), dtype='f4')

mods_names = []

def load_mods():
    for mod in os.listdir("mods"):
        print(f"Loading mod: {mod}")

        exec("import mods.TestMod.Mod", globals())

        mods_names.append(mod)





def init_programs(render):
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

    render.item_program["atlasArray"] = 2
    render.item_program["projection"].write(PROJECTION)
    render.item_program["frame"] = 0
    render.item_program["chance"] = -1
    render.item_program["TEXTURE_W"] = ITEM_W
    render.item_program["TEXTURE_H"] = ITEM_H
    render.item_program["ATLAS_W"] = ITEMS_W
    render.item_program["ATLAS_H"] = ITEMS_H

    render.chunk_program["atlasArray"] = 0
    render.chunk_program["projection"].write(PROJECTION)

    render.HUDText_program["atlasArray"] = 1
    render.HUDText_program["screenSize"].value = (WIDTH, HEIGHT)
    render.HUDText_program["TEXTURE_W"] = CHR_W
    render.HUDText_program["TEXTURE_H"] = CHR_H
    render.HUDText_program["ATLAS_W"] = CHAR_W
    render.HUDText_program["ATLAS_H"] = CHAR_H

def colletced():
    CAMERA.max_jumps += 1
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

def init(render):
    global CAMERA, TEXT, coll, WORLD, RENDER_DISTANCE, NETWORK, PLAYERS, min_x, max_x, min_y, max_y, hud, SLECTED

    init_programs(render)

    CAMERA = Camera([0, 2, 0], render)

    WORLD = World(render, random_seed, heightmap, rules, sin_world=sin_world, biomes = not FLAT)

    RENDER_DISTANCE = 3

    for x, z in square_range([0, 0, 0], RENDER_DISTANCE, 10):
        if not [x, 0, z] in WORLD.chunks.positions:
            WORLD.generate_chunk_at([x, 0, z])
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, x)
            max_y = max(max_y, x)

    TEXT = InstancedText(ctx=render.ctx, program=render.text_program, charset=CHARSET)

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
        PLAYERS.add_model("player", program=render.blocks_program, vertices=v, indices=i)

    SLECTED = Model(render)
    v, i = load_obj("assets/models/block.obj")
    SLECTED.add_model("selected", program=render.blocks_program, vertices=v, indices=i)
    SLECTED.add_instances([[0, 0, 0]], [12], "selected")

    coll = Collectible(render, ctx=render.ctx, program=render.item_program)

    pos = WORLD.get_block_pos_at(5, 0)
    pos[1] += 1

    coll.add_collectibles([pos], [0], [colletced])

    hud = HUDText(
    ctx=render.ctx,
    program=render.HUDText_program,
    charset=CHARSET,
    )

    hud.add_texts(["FPS: negative Infinity", "SELECTED BLOCK: water"], [[0, 0], [0, 30]], ["FPS", "sb"])

    glfw.set_cursor_pos_callback(render.window, CAMERA.cursor_move)

    load_mods()

    for name in mods_names:
        exec(f"globals()['mods'].{name}.Mod.init(globals())", globals())

def numpy_to_list(array):
    output = []
    output.extend(array)
    return output

def update_programs(render, **kwargs):
    render.blocks_program["view"].write(kwargs["view"])
    render.blocks_program["lightPos"].value = kwargs["lightPos"]
    render.blocks_program["viewPos"].write(kwargs["viewPos"])

    render.text_program["view"].write(kwargs["view"])
    render.text_program["lightPos"].value = kwargs["lightPos"]
    render.text_program["viewPos"].write(kwargs["viewPos"])

    render.chunk_program["view"].write(kwargs["view"])
    render.chunk_program["lightPos"].value = kwargs["lightPos"]
    render.chunk_program["viewPos"].write(kwargs["viewPos"])

    render.item_program["view"].write(kwargs["view"])
    render.item_program["lightPos"].value = kwargs["lightPos"]
    render.item_program["viewPos"].write(kwargs["viewPos"])

posses, rotations = [], []
block_updates = []

def multiplayer_thread(blocks_placed, blocks_broken):

    global is_process_finished, posses, rotations, block_updates

    is_process_finished = False

    send_data_to_server({
        "setData": True,
        "id": NETWORK.id,
        "coords":CAMERA.position.tolist(),
        "yaw":CAMERA.yaw,
        "pitch": CAMERA.pitch
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

blocks_placed, blocks_broken = [], []

def update(render):
    global CAMERA, coll, min_x, max_x, min_y, max_y, PLAYERS, playerdata, source, hud, frames_passed, start_second, SLECTED, selected_block, pressed,blocks_placed, blocks_broken

    #play EPIC music
    if source is None or not source.get_state() == openal.AL_PLAYING:
        source = playsound(f"assets/songs/{random.choice(["PEAK-SONG-mono.wav", "Song2-mono.wav", "Song3-mono.wav"])}")

    render.ctx.clear(0, 0, 0)

    listed_camera = numpy_to_list(CAMERA.position)
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

    CAMERA.update(last)
    coll.update(inted_camera)
    coll.render()
    block_placed, block_removed = None, None

    if result := raycast(last, CAMERA.eye_pos, CAMERA.front): #eye_pos bc ray starts from eyes
        position, normal = result
    
        a = Matrix44.from_scale([1.02, 1.02, 1.02]) @ Matrix44.from_translation(position)

        SLECTED.instanedmodels["selected"].instances[0] = a

        SLECTED.instanedmodels["selected"]._upload()

        if glfw.get_mouse_button(render.window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS and cooldown.is_active:
            WORLD.place_block(get_block(selected_block, (position + normal).tolist()))
            block_placed = (selected_block, (position + normal).tolist())
            blocks_placed.append(block_placed)

        if glfw.get_mouse_button(render.window, glfw.MOUSE_BUTTON_RIGHT) == glfw.PRESS and cooldown2.is_active:
            WORLD.destroy_block(WORLD.get_block_at(position.tolist()))
            block_removed = position.tolist()
            blocks_broken.append(block_removed)



    if MULTIPLAYER:
        process_multiplayer(PLAYERS, blocks_placed, blocks_broken)

    update_programs(render, view=CAMERA.view.astype("f4").tobytes(), lightPos=(9, 50, 9), viewPos=CAMERA.position.astype("f4").tobytes())

    for name in mods_names:
        exec(f"globals()['mods'].{name}.Mod.update()")

    WORLD.render_chunks(camera_chunk_pos, RENDER_DISTANCE)

    if MULTIPLAYER:
        PLAYERS.render()

    TEXT.render()


    if MOVE_WINDOW:
        if random.random() * 100 > 99.99:
            glfw.set_window_pos(render.window, random.randrange(0, 700), random.randrange(0, 700))

    if glfw.get_key(render.window, glfw.KEY_LEFT_ALT) == glfw.PRESS and not pressed:
        selected_block = next(generator)
        pressed = True
        hud.update_text("sb", f"SELECTED BLOCK: {selected_block.replace("_", " ")}", [0, 30])
        
    elif glfw.get_key(render.window, glfw.KEY_LEFT_ALT) != glfw.PRESS and pressed:
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

print("Stopped executing game.")
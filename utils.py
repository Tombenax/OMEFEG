import math
from random import Random
import random
import threading
from typing import Callable
from decorators import cache

@cache
def generate_tree(x:int, y:int, z:int, type:str, folder:str):
    with open(f"{folder}/structures/{type}.txt", "r") as f:
        content = f.readlines()
    for j, k in enumerate(content):
        content[j] = k.strip()
    tree_blocks = {"positions":[], "textures":[]}
    for i in range(0, len(content), 4):
        offsett_x = int(content[i])
        offsett_y = int(content[i+1])
        offsett_z = int(content[i+2])
        block = content[i+3]
        model_x = offsett_x+x
        model_y = offsett_y+y+1
        model_z = offsett_z+z
        block_name = block
        tree_blocks["positions"].append((model_x, model_y, model_z))
        tree_blocks["textures"].append(block_name)
    return tree_blocks

from math import floor, hypot
from Block import Block


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
    blocks:list[Block] = []
    trees = []
    can_generate = True
    if biomes:
        # Single HeightMap lookup per chunk (may expand + re-threshold
        # once; guarded by World._gen_lock on threaded builds).
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

    for x in range(offsett[0], size+offsett[0]):
        for z in range(offsett[2], size+offsett[2]):
            if _formula is not None:
                match _formula:
                    case "perlinNoise":
                        y = height_map(x/10, z/10) if _use_heightmap else 0
                        y *= 5

                    case "flat":
                        y = _oy

                    case "perlinFlat":
                        y = height_map(x/10, z/10) if _use_heightmap else 0

                    case "cone":
                        h, j = _ox + size/2, _oz + size/2 #get center of the chunk and apply it to the offsett
                        K = 0.5
                        H = 15
                        try:
                            y = -(math.sqrt((x-h) ** 2 + (z-j) ** 2) / K - H)
                        except ValueError:
                            y = 0
            else:
                y = height_map(x/10, z/10) if _use_heightmap else 0
                y *= 5

            y = floor(y)
            y += _oy

            block_type = _top_block
            if y in _water_set:
                block_type = "water"
                for a in _all_water_ys:
                    if y != a:
                        blocks.append(get_block(block_type, [x, a, z]))

            else:
                if can_generate:
                    #generate structures
                    for i in _structures_rules:
                        if random_seed.random() * 100 < float(i["chance"]): # type: ignore
                            if not "tree" in i["name"]: # type: ignore
                                trees.clear()
                                can_generate = False
                            trees.append(generate_tree(x, y, z, i["name"], i["folder"])) # type: ignore

            blocks.append(get_block(block_type, [x, y, z]))
            if block_type == _top_block:
                for i in range(1, _terrain_thickness+1): # type: ignore
                    blocks.append(get_block(_bottom_block, [x, y-i, z]))

    for i in trees:
        for j, k in zip(i["positions"], i["textures"]):
            blocks.append(get_block(k, j))

    return blocks

try:
    import openal
except Exception as _e:
    # Android / missing recipe: audio is optional, playsound() below
    # degrades to a no-op dummy instead of crashing the import.
    print(f"[utils] openal unavailable, audio disabled: {_e}")
    openal = None  # type: ignore
from Number import Number


class _DummySound:
    def play(self, *args, **kwargs):
        pass

    def stop(self, *args, **kwargs):
        pass

    def get_state(self, *args, **kwargs):
        return None


def playsound(sound:str, position:tuple[Number, Number, Number]=(0, 0, 0), sound_position:tuple[Number, Number, Number]=(0, 0, 0), orientation:tuple[Number, Number, Number, Number, Number, Number]=(0, 0, -1, 0, 1, 0), loop:bool=False):
    if openal is None:
        print(f"[audio disabled] would play: {sound}")
        return _DummySound()
    listener = openal.oalGetListener()
    listener.set_position(position)
    listener.set_orientation(orientation)

    source = openal.oalOpen(sound)
    source.set_position(sound_position)
    source.set_looping(loop)
    source.play()
    
    return source



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
    result = []

    for r in range(layers + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r:
                    result.append([
                        cx + dx * step,
                        cy + dy * step
                    ])

    return result

import numpy as np

def export_and_load_chunk(models:list[list[int | float]], _layers_, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y):
    """
    Fast chunk mesh builder.

    This version keeps the same cube vertex/index layout, but it avoids all
    per-block OBJ string generation and re-parsing. It performs the merge in
    NumPy so the chunk export stays cheap even when a lot of blocks need to be
    packed into one mesh.

    NOTE: no @cache on purpose. The old cache key stringified the full
    positions/textures lists plus the cube arrays per build (MBs of str()),
    never hit for new chunks, and pinned every chunk mesh in RAM forever.
    Thread workers call this directly (pure NumPy, no shared state).
    """

    if not models:
        return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')

    positions = np.asarray(models, dtype=np.float32)
    layers = np.asarray(_layers_, dtype=np.int32)

    if positions.ndim == 1:
        positions = positions.reshape(1, 3)

    base_vertices = CUBE_MODEL_INFO[0].reshape(-1, 8).astype(np.float32)
    base_indices = CUBE_MODEL_INFO[1].astype(np.int32)

    block_count = len(positions)

    translated = np.repeat(base_vertices[None, :, :], block_count, axis=0)
    translated[:, :, 0] += positions[:, 0][:, None]
    translated[:, :, 1] += positions[:, 1][:, None]
    translated[:, :, 2] += positions[:, 2][:, None]

    # Atlas remap from the base-cube UVs (broadcast, no full-tensor copy).
    bx = layers % TEXTURES_X
    by = TEXTURES_Y - 1 - (layers // TEXTURES_X)

    # for idx in range(TEXTURES_Y):
        # by[np.where(by == (TEXTURES_Y - idx))] = idx

    temp_by = by.copy()

    by[np.where(temp_by == 3)] = 0
    by[np.where(temp_by == 2)] = 1
    by[np.where(temp_by == 1)] = 2
    by[np.where(temp_by == 0)] = 3

    base_u = base_vertices[:, 6][None, :]
    base_v = base_vertices[:, 7][None, :]

    translated[:, :, 6] = base_u / TEXTURES_X + (bx[:, None] / TEXTURES_X)
    translated[:, :, 7] = base_v / TEXTURES_Y + (by[:, None] / TEXTURES_Y)

    merged_vertices = translated.reshape(-1, 8)

    vertex_offsets = np.arange(block_count, dtype=np.int32) * len(base_vertices)
    merged_indices = np.repeat(base_indices[None, :], block_count, axis=0) + vertex_offsets[:, None]
    merged_indices = merged_indices.reshape(-1)

    return merged_vertices.astype('f4'), merged_indices.astype('i4')


from allBlocks import *
from colorama import Fore, Style


def get_block(name:str, position:list[float | int]):
    # No @cache on purpose: positions are unique per block, so the cache
    # never hit and pinned every Block ever created in RAM forever (plus
    # a str() key built per block). Plain factory is faster overall.
    match name:
        case "grass":
            return Grass(position)

        case "dirt":
            return Dirt(position)

        case "stone":
            return Stone(position)

        case "birch_leave":
            return Birch_Leave(position)

        case "birch_log":
            return Birch_Log(position)

        case "oak_leave":
            return Oak_Leave(position)

        case "oak_log":
            return Oak_Log(position)

        case "sand":
            return Sand(position)

        case "water":
            return Water(position)

        case "cobblestone":
            return Cobblestone(position)

        case "oak_planks":
            return Oak_Planks(position)

    print(Fore.YELLOW + f"Unrecognized block: {name}")
    print(Style.RESET_ALL)

def get_texture(idx:int, x, y, z):
    match idx:
        case 0:
            return Birch_Leave([x, y, z])
        case 1:
            return Birch_Log([x, y, z])
        case 2:
            return Cobblestone([x, y, z])
        case 3:
            return Dirt([x, y, z])
        case 4:
            return Grass([x, y, z])
        case 5:
            return Oak_Leave([x, y, z])
        case 6:
            return Oak_Log([x, y, z])
        case 7:
            return Oak_Planks([x, y, z])
        case 8:
            return Sand([x, y, z])
        case 9:
            return Stone([x, y, z])
        case 10:
            return Water([x, y, z])

    print(Fore.YELLOW + f"Unrecognized idx: {idx}")
    print(Style.RESET_ALL)


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

def distance(first:list[Number], second:list[Number]):
    return hypot(first[0]-second[0], first[1]-second[1], first[2]-second[2])

def get_accurate_block(pos:list[Number]) -> tuple[Number]:
    return tuple([floor(axis + 0.5) for axis in pos])

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

def notification_github(user_code, start_time, max_time):

    global STOP_EXCLAMATION_MARK_EXCLAMATION_MARK

    while (not STOP_EXCLAMATION_MARK_EXCLAMATION_MARK) or (time.time() - start_time >= max_time):
        notification(
            "OMEFEG",
            f"Put in the browser this code: \"{user_code}\""
        )

        time.sleep(10)

def login_with_github():

    global STOP_EXCLAMATION_MARK_EXCLAMATION_MARK

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

    print(f"Put in the browser this code: \"{user_code}\"")

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

    STOP_EXCLAMATION_MARK_EXCLAMATION_MARK = False

    th = threading.Thread(target=notification_github, args=(user_code, start_time, expires_in), daemon=True)
    th.start()

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

    STOP_EXCLAMATION_MARK_EXCLAMATION_MARK = True

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

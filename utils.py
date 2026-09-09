import math
from random import Random
import random
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


@cache
def generate_terrain(size=10, height_map=None, biomes_map=None, offsett=[0, 0, 0], rules_:dict[str, int | list[int] | str]={}, random_seed:random.Random=random.Random(random.randint(0, 9_223_372_036_854_775_807)), biomes=True, sin_world=False) -> list[Block]:
    """
    Generates terrain as a list of [x, y, z] block positions.
    height_map: optional function f(x, z) -> y
    rules: a list of terrain generation rules
    """
    blocks:list[Block] = []
    trees = []
    can_generate = True
    if biomes:
        bom = rules_["all"][biomes_map[offsett[0], offsett[2]]]
        rules = rules_[bom]["rules"]
        vegetation = rules_[bom]
    else:
        bom = "plains"
        rules = rules_[bom]["rules"]
        rules["structures"] = []
        vegetation = rules_[bom]


    for x in range(offsett[0], size+offsett[0]):
        for z in range(offsett[2], size+offsett[2]):
            if not sin_world:
                match rules["generationFormula"]:
                    case "perlinNoise":
                        y = height_map(x/10, z/10) if height_map else 0
                        y *= 5

                    case "flat":
                        y = offsett[1]

                    case "perlinFlat":
                        y = height_map(x/10, z/10) if height_map else 0

                    case "cone":
                        h, j = offsett[0] + size/2, offsett[2] + size/2 #get center of the chunk and apply it to the offsett
                        K = 0.5
                        H = 15
                        try:
                            y = -(math.sqrt((x-h) ** 2 + (z-j) ** 2) / K - H)
                        except ValueError:
                            y = 0
            else:
                y = height_map(x/10, z/10) if height_map else 0
                y *= 5

            y = floor(y)
            y += offsett[1]

            structures_rules = rules["structures"] # type: ignore
            water_rules = rules["water"] # type: ignore
            terrain_tickness = rules["terrain_height"] # type: ignore
            all_water_ys = [-(i+int(water_rules["level"])) for i in range(int(water_rules["depth"]))] # type: ignore

            block_type = vegetation["topBlock"] # type: ignore
            if y in all_water_ys:
                block_type = "water"
                for a in all_water_ys:
                    if y != a:
                        blocks.append(get_block(block_type, [x, a, z]))

            else:
                if can_generate:
                    #generate structures
                    for i in structures_rules:
                        if random_seed.random() * 100 < float(i["chance"]): # type: ignore
                            if not "tree" in i["name"]: # type: ignore
                                trees.clear()
                                can_generate = False
                            trees.append(generate_tree(x, y, z, i["name"], i["folder"])) # type: ignore
            
            blocks.append(get_block(block_type, [x, y, z]))
            if block_type == vegetation["topBlock"]:
                for i in range(1, terrain_tickness+1): # type: ignore
                    blocks.append(get_block(vegetation["bottomBlock"], [x, y-i, z]))

    for i in trees:
        for j, k in zip(i["positions"], i["textures"]):
            blocks.append(get_block(k, j))

    return blocks

import openal
from Number import Number

def playsound(sound:str, position:tuple[Number, Number, Number]=(0, 0, 0), sound_position:tuple[Number, Number, Number]=(0, 0, 0), orientation:tuple[Number, Number, Number, Number, Number, Number]=(0, 0, -1, 0, 1, 0), loop:bool=False):
    listener = openal.oalGetListener()
    listener.set_position(position)
    listener.set_orientation(orientation)

    source = openal.oalOpen(sound)
    source.set_position(sound_position)
    source.set_looping(loop)
    source.play()
    
    return source



import asyncio
from desktop_notifier import DesktopNotifier, Icon
from pathlib import Path

notifier = DesktopNotifier()
notifier.app_icon = Icon(path=Path("assets/icon.png").resolve())
notifier.app_name = "Game"

async def main(title, message):
    await notifier.send(title, message)

def notification(title, message):
    asyncio.run(main(title, message))

import requests

@cache
def get_username_and_uuid(username, password):
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

@cache
def export_and_load_chunk(models:list[list[int | float]], _layers_, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y):
    """
    Fast chunk mesh builder.

    This version keeps the same cube vertex/index layout, but it avoids all
    per-block OBJ string generation and re-parsing. It performs the merge in
    NumPy so the chunk export stays cheap even when a lot of blocks need to be
    packed into one mesh.
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

    uvs = translated[:, :, 6:8].copy()
    atlas_u = uvs[:, :, 0]
    atlas_v = uvs[:, :, 1]

    bx = layers % TEXTURES_X
    by = TEXTURES_Y - 1 - (layers // TEXTURES_X)

    # for idx in range(TEXTURES_Y):
        # by[np.where(by == (TEXTURES_Y - idx))] = idx

    temp_by = by.copy()

    by[np.where(temp_by == 3)] = 0
    by[np.where(temp_by == 2)] = 1
    by[np.where(temp_by == 1)] = 2
    by[np.where(temp_by == 0)] = 3


    atlas_u = atlas_u / TEXTURES_X + (bx[:, None] / TEXTURES_X)
    atlas_v = atlas_v / TEXTURES_Y + (by[:, None] / TEXTURES_Y)

    translated[:, :, 6] = atlas_u
    translated[:, :, 7] = atlas_v

    merged_vertices = translated.reshape(-1, 8)

    vertex_offsets = np.arange(block_count, dtype=np.int32) * len(base_vertices)
    merged_indices = np.repeat(base_indices[None, :], block_count, axis=0) + vertex_offsets[:, None]
    merged_indices = merged_indices.reshape(-1)

    return merged_vertices.astype('f4'), merged_indices.astype('i4')


from allBlocks import *
from colorama import Fore, Style


@cache
def get_block(name:str, position:list[float | int]):
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

    return Block(name, position, name, {0:place, 1:destroy}, True)

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


import base64
import getpass
import json
import os

from argon2.low_level import hash_secret_raw, Type
from cryptography.fernet import Fernet


FILE = "account.dat"


def derive_key(master_password, salt):
    key = hash_secret_raw(
        secret=master_password.encode(),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        type=Type.ID,
    )

    return base64.urlsafe_b64encode(key)


def create_account(username, password, master):
    # Random salt for Argon2id
    salt = os.urandom(16)

    # Derive encryption key from master password
    key = derive_key(master, salt)

    cipher = Fernet(key)

    data = {
        "username": username,
        "password": password
    }

    # Encrypt the username and password
    encrypted = cipher.encrypt(
        json.dumps(data).encode()
    )

    # Store salt + encrypted data
    vault = {
        "salt": base64.b64encode(salt).decode(),
        "data": encrypted.decode()
    }

    with open(FILE, "w") as f:
        json.dump(vault, f)


def load_account(master):
    with open(FILE, "r") as f:
        vault = json.load(f)

    salt = base64.b64decode(vault["salt"])
    encrypted = vault["data"].encode()

    key = derive_key(master, salt)
    cipher = Fernet(key)

    try:
        decrypted = cipher.decrypt(encrypted)
    except Exception:
        print("Wrong master password or corrupted file.")
        return

    data = json.loads(decrypted.decode())

    return data

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

            


if __name__ == "__main__":
    #put tests here
    pass
























































#This software was made by teh owner of the gmail account of "Tombenax@gmail.com", any attempt of selling or distributing will result in legal actions.
#If someone presents this software as they'rs just know that it's not
#IF THIS COMMENT ARE MISSING OR MODIFY THE SOFTwARE HAS BEEN STOLEN
from random import Random

def generate_tree(x:int, y:int, z:int, type:str):
    with open(f"structures/{type}.txt", "r") as f:
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

from math import floor
from Block import Block
from proprieties_functions import *

def generate_terrain(size=10, height_map=None, offsett:list=[0, 0, 0], rules:dict={"structures":[{"chance":97, "size":"oak_small_tree"}, {"chance":93, "size":"oak_medium_tree"}], "water":{"level":1, "depth":5}, "terrain_height":5}, random_seed:Random=Random()) -> list[Block]:
    """
    Generates terrain as a list of [x, y, z] block positions.
    height_map: optional function f(x, z) -> y
    rules: a list of terrain generation rules
    """
    blocks:list[Block] = []
    trees = []
    structures_rules = rules["structures"]
    water_rules = rules["water"]
    terrain_tickness = rules["terrain_height"]
    all_water_ys = [-(i+int(water_rules["level"])) for i in range(int(water_rules["depth"]))]
    can_generate = True
    for x in range(offsett[0], size+offsett[0]):
        for z in range(offsett[2], size+offsett[2]):
            y = height_map(x/10, z/10) if height_map else 0
            y *= 5
            y = floor(y)
            y += offsett[1]
            block_type = "grass"
            if y in all_water_ys:
                block_type = "water_1"
                for a in all_water_ys:
                    if y != a:
                        blocks.append(Block(block_type, [x, a, z], block_type, {0:place, 1:destroy}, False))

            else:
                if can_generate:
                    #generate structures
                    for i in structures_rules:
                        if random_seed.randint(1, 1001) >= float(i["chance"]):
                            if not "tree" in i["name"]:
                                trees.clear()
                                can_generate = False
                            trees.append(generate_tree(x, y, z, i["name"]))
            
            blocks.append(Block(block_type, [x, y, z], block_type, {0:place, 1:destroy}, False if block_type == "water_1" else True))
            if block_type == "grass":
                for i in range(1, terrain_tickness+1):
                    blocks.append(Block("dirt", [x, y-i, z], "dirt", {0:place, 1:destroy}, True))

    for i in trees:
        for j, k in zip(i["positions"], i["textures"]):
            blocks.append(Block(k, j, k, {0:place, 1:destroy}, True)) 

    return blocks

from pygame import mixer
mixer.init()

_sound_cache = {}
_channels = {}

def playsound(path: str):
    if path not in _sound_cache:
        _sound_cache[path] = mixer.Sound(path)

    channel = _channels.get(path)

    if channel is None or not channel.get_busy():
        _channels[path] = _sound_cache[path].play()


import asyncio
from desktop_notifier import DesktopNotifier, Icon
from pathlib import Path

notifier = DesktopNotifier()
notifier.app_icon = Icon(path=Path("assets/icon.png").resolve())
notifier.app_name = "Game"

async def main(title, message):
    await notifier.send(title, message)

def notification(message):
    asyncio.run(main("Game Ban Notification", message))

import requests

def get_username_and_uuid(username, password):
    get_token = False
    with open("token.txt", "r") as f:
        if f.read().strip() == "":
            get_token = True
    
    if get_token:
        url = "https://tombenax.pythonanywhere.com/login"

        data = {
            "username": username,
            "password": password,
            "client": "game"
        }

        r = requests.post(url, data=data)
        res = r.json()

        if res["status"] == "valid":
            with open("token.txt", "w") as f:
                f.write(res["token"])
        elif res["status"] == "error":
            return "invalid credentials"
        elif res["status"] == "disabled":
            return "account disabled"
    else:
        verify_url = "https://tombenax.pythonanywhere.com/verify"

        with open("token.txt", "r") as f:
            r = requests.post(verify_url, data={"token": f.read().strip(), "username":username})
        res = r.json()

        if res["status"] == "invalid":
            return "invalid credentials"
        elif res["status"] == "disabled":
            return "account disabled"
    
    return res["token"]


def closest_range(start:int, stop:int, step:int=1) -> list[int]:
    final_range = []
    middle = int((stop+start)/2)
    final_range.append(middle)
    for iteration in range(1, len(range(start, stop+1, step))+1):
        final_range.append(middle-step*iteration)
        final_range.append(middle+step*iteration)
    
    return final_range

def square_range(center: list[int], layers: int, step: int = 1) -> list[list[int]]:
    cx, cy = center
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

def load_obj_mesh(file_path):
    vertices = []
    uvs = []
    normals = []
    faces = []

    with open(file_path, "r") as f:
        for line in f:

            if line.startswith("v "):
                _, x, y, z = line.split()
                vertices.append((float(x), float(y), float(z)))

            elif line.startswith("vt "):
                _, u, v = line.split()
                uvs.append((float(u), float(v)))

            elif line.startswith("vn "):
                _, x, y, z = line.split()
                normals.append((float(x), float(y), float(z)))

            elif line.startswith("f "):
                face = []
                for p in line.split()[1:]:
                    v, vt, vn = p.split("/")
                    face.append((
                        int(v) - 1,
                        int(vt) - 1,
                        int(vn) - 1
                    ))
                faces.append(face)

    return (
        np.array(vertices, dtype=np.float32),
        np.array(uvs, dtype=np.float32),
        np.array(normals, dtype=np.float32),
        faces
    )

def bake_instanced_obj(
    obj_path,
    instanced_model,
    get_uv,
    atlas_blocks
):

    base_v, base_uv, base_n, base_f = load_obj_mesh(obj_path)

    out_vertices = []
    out_indices = []

    vertex_offset = 0

    for i, mat in enumerate(instanced_model.models):

        if not instanced_model.active[i]:
            continue

        block_id = instanced_model.layers[i]

        for face in base_f:

            face_verts = []

            for v_idx, vt_idx, vn_idx in face:

                v = base_v[v_idx]

                vec = np.array([v[0], v[1], v[2], 1.0], dtype=np.float32)
                t = vec @ mat

                u, v_uv = base_uv[vt_idx]
                u, v_uv = get_uv(u, v_uv, block_id, atlas_blocks)

                face_verts.append([
                    t[0], t[1], t[2],
                    base_n[vn_idx][0],
                    base_n[vn_idx][1],
                    base_n[vn_idx][2],
                    u, v_uv
                ])

            # triangle 1
            out_vertices.extend([
                face_verts[0],
                face_verts[1],
                face_verts[2],
            ])

            # triangle 2
            out_vertices.extend([
                face_verts[0],
                face_verts[2],
                face_verts[3],
            ])

            out_indices.extend([
                vertex_offset,
                vertex_offset + 1,
                vertex_offset + 2,
                vertex_offset + 3,
                vertex_offset + 4,
                vertex_offset + 5,
            ])

            vertex_offset += 6

    vertices = np.array(out_vertices, dtype=np.float32).ravel()
    indices = np.array(out_indices, dtype=np.uint32)

    return vertices, indices

if __name__ == "__main__":
    #put tests here
    pass
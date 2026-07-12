import copy

import glfw
import moderngl
import numpy as np
from pyrr import Matrix44
import time
import math
from PIL import Image, ImageDraw, ImageFont
from utils import playsound, notification, get_username_and_uuid, square_range
import os
import random
from key import Key
from Block import Block
import json
from proprieties_functions import *
from interact_function_conversion import INTERACT_FUNCTION_CONVERSION, REVERSE_INTERACT_FUNCTION_CONVERSION
from perlineNoise import PerlinNoiseFactory
from network import Network
import hashlib
import threading
from Chunk import Chunk
from icecream import ic
from InstancedModel import InstancedModel
from AnimationHandler import AnimationHandler
#from ControllerHandler import ControllerHandler
from ast import literal_eval
from Renders.DesktopRender import *


WIDTH = 1280
HEIGHT = 720

generation_queue = []
generating = False
waiting_for_thread_finish = False

def string_to_fixed_number(s, digits=10):
    # Create a hash (SHA-256 is common and stable)
    h = hashlib.sha256(s.encode()).hexdigest()
    
    # Convert hex string to integer
    num = int(h, 16)
    
    # Limit to a fixed number of digits
    return num % (10 ** digits)

seed = random.Random(string_to_fixed_number("IfYOOOUFIND OUTABOUTTHESEEDIMKILLINGYOU", 256))
heightmap = PerlinNoiseFactory(dimension=2, octaves=1, seed=seed)
#ilands: waterlevel = 0
#lakes = 3
#larger islands = 1
rules = {"structures":[{"chance":970, "name":"oak_small_tree"}, {"chance":930, "name":"oak_medium_tree"}, {"chance":999, "name":"temple"}], "water":{"level":1, "depth":5}, "terrain_height":5}

# -------------------------
# CAMERA
# -------------------------

class Camera:
    def __init__(self, pos, ctx, prog, text_prog, TEXTURE_INDICES, font_texture, charset:str, multiplayer:bool=False, serveraddress=None, serverport=None, window=None):
        self.position = np.array(pos, dtype='f4')
        self.prev_pos = self.position

        self.front = np.array([0, 0, -1], dtype='f4')
        self.up = np.array([0, 1, 0], dtype='f4')

        self.yaw = -90
        self.pitch = 0

        self.speed = 5
        self.sensitivity = 0.1

        self.vel_y = 0.0
        self.on_ground = False
        self.placed = False
        self.destroyed = False

        # physics
        self.gravity = 20
        self.jump_strength = 8
        self.max_fall = -30

        # player size (VERY IMPORTANT)
        self.height = 1.8
        self.eye_height = 1.6
        self.width = 0.3

        self.enabled = True

        self.first_mouse = True
        self.last_x = WIDTH / 2
        self.last_y = HEIGHT / 2

        self.multiplayer = multiplayer

        self.chat = InstancedText(ctx, text_prog, font_texture, charset)

        self.is_in_water = False

        if self.multiplayer:
            with open("data.txt", "r") as f:
                content = f.readlines()
                username = content[0].strip()
                password = content[1].strip()
            self.playername = username
            self.uuid = get_username_and_uuid(username, password)
            if self.uuid == "invalid credentials":
                notification("It seems like your credentials are invalid, please restart the game and re-write them.")
                with open("data.txt", "w") as f:
                    f.write("")
                glfw.set_window_should_close(window, True)
            elif self.uuid == "account disabled":
                notification("It seems like your account is disabled, if you want to play online re-enable it at https://tombenax.pythonanywhere.com/account/login")
                glfw.set_window_should_close(window, True)
            self.network = Network({"x":float(self.position[0]), "y":float(self.position[1]), "z":float(self.position[2]), "name":self.playername, "uuid":str(self.uuid)}, serveraddress, serverport)
            print("Initialized network with id of:", self.network.id)
            vertices, indices = load_obj_for_moderngl("assets/models/player.obj")
            self.players = InstancedModel(ctx,prog,vertices,indices,TEXTURE_INDICES)
            self.already_seen_placed = []
            self.already_seen_destroyed = []

    def get_world(self):
        if self.multiplayer:
            bytes_lenght = int(self.network.client.recv(2048).decode())

            _data_ = self.network.send("PLEASE,IWANTTHEWORLDPOSITIONS", recive_size=bytes_lenght)

            models = json.loads(_data_)

            bytes_lenght = int(self.network.client.recv(2048).decode())

            _data_ = self.network.send("PLEASE,IWANTTHEWORLDTEXTURES", recive_size=bytes_lenght)
            
            layers = json.loads(_data_)

            bytes_lenght = int(self.network.client.recv(2048).decode())

            _data_ = self.network.send("PLEASE,IWANTTHEWORLDATTRIBUTES", recive_size=bytes_lenght)
            
            proprieties = json.loads(_data_)

            for idx, propriety in enumerate(proprieties):
                new_dict = {}
                for i in [0, 1]:
                    new_dict[i] = INTERACT_FUNCTION_CONVERSION[propriety[i]]
                proprieties[idx] = new_dict

            return models, layers, proprieties

    # -------------------------
    # VIEW
    # -------------------------
    def get_view(self):
        eye_pos = self.position + np.array([0, self.eye_height, 0], dtype='f4')
        return Matrix44.look_at(eye_pos, eye_pos + self.front, self.up)
    # -------------------------
    # MOUSE
    # -------------------------
    def process_mouse(self, xpos, ypos):
        if not self.enabled:
            return

        if self.first_mouse:
            self.last_x = xpos
            self.last_y = ypos
            self.first_mouse = False

        xoffset = (xpos - self.last_x) * self.sensitivity
        yoffset = (self.last_y - ypos) * self.sensitivity

        self.last_x = xpos
        self.last_y = ypos

        self.yaw += xoffset
        self.pitch += yoffset
        self.pitch = max(-89, min(89, self.pitch))

        front = np.array([
            math.cos(math.radians(self.yaw)) * math.cos(math.radians(self.pitch)),
            math.sin(math.radians(self.pitch)),
            math.sin(math.radians(self.yaw)) * math.cos(math.radians(self.pitch))
        ], dtype='f4')

        self.front = front / np.linalg.norm(front)
              
    # -------------------------
    # KEYBOARD INPUT
    # -------------------------
    def process_keyboard(self, window, delta, occupied):
        if not self.enabled:
            return

        move = np.zeros(3, dtype='f4')

        right = np.cross(self.front, self.up)
        right /= np.linalg.norm(right)

        # WASD (no Y movement)
        if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
            move += self.front
        if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
            move -= self.front
        if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS:
            move -= right
        if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS:
            move += right

        move[1] = 0

        if np.linalg.norm(move) > 0:
            move = move / np.linalg.norm(move)

        speed = 10 if glfw.get_key(window, glfw.KEY_LEFT_CONTROL) == glfw.PRESS else 5
        move *= speed * delta

        # 🔥 MOVE X AND Z SEPARATELY
        self.move_axis(move[0], 0, occupied)
        self.move_axis(0, move[2], occupied)

        # 🔥 JUMP
        if (self.on_ground or self.is_in_water) and glfw.get_key(window, glfw.KEY_SPACE) == glfw.PRESS:
            self.vel_y = self.jump_strength
            self.on_ground = False

    # -------------------------
    # PHYSICS UPDATE
    # -------------------------
    def update(self, window, delta, occupied, hit, normal, block, selected_block, blocks, block_index, message_to_send:str, in_block:Block):
        if not self.multiplayer:
            if not self.enabled:
                return
        
        temp_pos = self.position.copy()
        temp_pos[1] = 0
        temp_prev_pos = self.prev_pos.copy()
        temp_prev_pos[1] = 0

        if not (temp_pos == temp_prev_pos).all():
            playsound("assets/sounds/grass.mp3")
            self.prev_pos = self.position


        blocks_broken_positions = []
        blocks_placed_positions = []

        if in_block is not None:
            if in_block.block == "water_1":
                self.gravity = 8
                self.max_fall = -2
                self.is_in_water = True
                self.jump_strength = 2
            else:
                self.gravity = 20
                self.max_fall = -30
                self.is_in_water = False
                self.jump_strength = 8
        else:
            self.gravity = 20
            self.max_fall = -30
            self.is_in_water = False
            self.jump_strength = 8
        # -------------------------
        # 🧱 BLOCK INTERACTION (RESTORED)
        # -------------------------
        if block_index is not None:
            # PLACE
            if not self.placed:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_RIGHT) == glfw.PRESS:
                    if hit and normal is not None:
                        blocks[block_index].proprieties[0](
                            block, normal, occupied, hit, blocks, selected_block, self.position
                        )
                        self.placed = True
                        blocks_placed_positions.append([(int(hit[0]), int(hit[1]), int(hit[2])), selected_block, '{0:destroy, 1:place}'])
            else:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_RIGHT) != glfw.PRESS:
                    self.placed = False

            # DESTROY
            if not self.destroyed:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS:
                    if hit:
                        blocks[block_index].proprieties[1](
                            block, normal, occupied, hit, blocks, selected_block, self.position
                        )
                        self.destroyed = True
                        blocks_broken_positions.append([(int(hit[0]), int(hit[1]), int(hit[2])), selected_block, '{0:destroy, 1:place}'])
            else:
                if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) != glfw.PRESS:
                    self.destroyed = False
            
        if glfw.get_key(window, glfw.KEY_R) == glfw.PRESS:
            self.position = np.array((0, 1, 0), dtype='f4')

        if self.multiplayer:

            recived = self.network.send("gimmietheDATA")
            if recived == "too bad idiot, your banned!!!":
                notification("I'm sorry, it seems like you have been banned, ask the server managers for the appeal")
                return "ban"
            
            alldata = json.loads(recived)
            
            packet = {
                    "network id": self.network.id,
                    "position": [float(self.position[0]), float(self.position[1]), float(self.position[2])],
                    "orientation": [float(self.yaw), float(self.pitch)],
                    "username": self.playername,
                    "blocks broken at": blocks_broken_positions,
                    "blocks placed at": blocks_placed_positions,
                    "chat message": message_to_send
                      }

            response = self.network.send(json.dumps(packet))
            if response != "recived":
                print("the server has something")

            playersdata = alldata[0]
            chat_data = alldata[1]
            blockdata_placed = alldata[2]
            blockdata_destroyed = alldata[3]


            for blo in blockdata_placed:
                if blo in self.already_seen_placed: continue
                if not tuple(blo[0]) in occupied:
                    blocks.append(Block(blo[1], blo[0], blo[1], {0:destroy, 1:place}, block))
                    occupied.add(tuple(blo[0]))

                self.already_seen_placed.append(blo)
                if len(self.already_seen_placed) > 20:
                    self.already_seen_placed.pop(0)

            for blo in blockdata_destroyed:
                if blo in self.already_seen_destroyed: continue
                if tuple(blo[0]) in occupied:
                    removal_index = block.remove_instance(tuple(blo[0]))
                    occupied.discard(tuple(blo[0]))
                    blocks.pop(removal_index)

                self.already_seen_destroyed.append(blo)
                if len(self.already_seen_destroyed) > 20:
                    self.already_seen_destroyed.pop(0)

                    
            
            self.players.models = np.zeros((0,4,4), dtype='f4')

            for playerdata in playersdata:
                self.players.add_instances(positions=[[playerdata[0], playerdata[1], playerdata[2]]], texture_names=["player"], rotations=[[math.radians(playerdata[4]), math.radians(playerdata[3]-90), 0]]) #+ALWAYS USE Z+ = FORWARD IN MODELS

            chat_owners = tuple(reversed(chat_data[0]))
            chat_messages = tuple(reversed(chat_data[1]))

            for idx in range(len(chat_owners)):
                if len(self.chat.strings) > idx:
                    self.chat.update_string(new_text=f"|{chat_owners[idx]}|:{chat_messages[idx]}", string_id=idx, pos=(-0.9, -0.9+idx/10))
                else:
                    self.chat.add_string(text=f"|{chat_owners[idx]}|:{chat_messages[idx]}", string_id=idx, pos=(-0.9, -0.9+idx/10))     


        # -------------------------
        # 🌍 PHYSICS (NEW SYSTEM)
        # -------------------------
        self.vel_y -= self.gravity * delta
        if self.vel_y < self.max_fall:
            self.vel_y = self.max_fall

        dy = self.vel_y * delta
        self.move_vertical(dy, occupied)

    # -------------------------
    # COLLISION HELPERS
    # -------------------------
    def is_blocked(self, x, y, z, occupied):
        return (int(x), int(y), int(z)) in occupied
    
    def collides(self, pos, occupied):
        px, py, pz = pos

        # player bounds
        min_x = px - self.width
        max_x = px + self.width
        min_y = py
        max_y = py + self.height
        min_z = pz - self.width
        max_z = pz + self.width

        # For blocks centered at (x, y, z), their min/max in world coords are (x-0.5, x+0.5)
        # So we adjust only x and z, not y
        x_start = int(np.floor(min_x + 0.5))
        x_end   = int(np.floor(max_x + 0.5))
        y_start = int(np.floor(min_y+0.5))
        y_end   = int(np.floor(max_y+0.5))
        z_start = int(np.floor(min_z + 0.5))
        z_end   = int(np.floor(max_z + 0.5))

        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                for z in range(z_start, z_end + 1):
                    if (x, y, z) in occupied:
                        return True

        return False

    # -------------------------
    # AXIS MOVEMENT (X/Z)
    # -------------------------
    def move_axis(self, dx, dz, occupied):
        new_pos = self.position + np.array([dx, 0, dz], dtype='f4')

        if not self.collides(new_pos, occupied):
            self.position = new_pos

    # -------------------------
    # VERTICAL MOVEMENT
    # -------------------------
    def move_vertical(self, dy, occupied):
        new_pos = self.position + np.array([0, dy, 0], dtype='f4')

        if dy < 0:  # falling
            if self.collides(new_pos, occupied):
                self.vel_y = 0
                self.on_ground = True
                return
        else:  # jumping
            if self.collides(new_pos, occupied):
                self.vel_y = 0
                return

        self.position = new_pos
        self.on_ground = False

    # -------------------------
    def enable(self, window):
        glfw.set_input_mode(window,glfw.CURSOR,glfw.CURSOR_DISABLED)
        self.enabled = True

    def disable(self, window):
        glfw.set_input_mode(window,glfw.CURSOR,glfw.CURSOR_NORMAL)
        self.enabled = False


# -------------------------
# OBJ LOADER
# -------------------------

def load_obj_for_moderngl(file_path):
    positions = []
    normals = []
    uvs = []
    vertices = []
    indices = []
    vertex_map = {}
    idx = 0

    with open(file_path) as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()
                positions.append([float(x), float(y), float(z)])
            elif line.startswith("vn "):
                _, x, y, z = line.split()
                normals.append([float(x), float(y), float(z)])
            elif line.startswith("vt "):
                _, u, v = line.split()
                uvs.append([float(u), float(v)])
            elif line.startswith("f "):
                face = []
                for part in line.split()[1:]:
                    vals = part.split("/")

                    p = int(vals[0]) - 1

                    t = int(vals[1]) - 1 if len(vals) > 1 and vals[1] else 0

                    n = int(vals[2]) - 1 if len(vals) > 2 and vals[2] else 0
                    key = (p, t, n)
                    if key not in vertex_map:
                        px, py, pz = positions[p]
                        if len(normals) > 0:
                            nx, ny, nz = normals[n]
                        else:
                            nx, ny, nz = (0.0, 1.0, 0.0)
                        u, v = uvs[t]
                        v = 1 - v
                        vertices.extend([px, py, pz, nx, ny, nz, u, 1-v])
                        vertex_map[key] = idx
                        idx += 1
                    face.append(vertex_map[key])
                for i in range(1, len(face)-1):
                    indices.extend([face[0], face[i], face[i+1]])

    return np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')

cube_v, cube_i = load_obj_for_moderngl("assets/models/block.obj")

def load_obj_for_moderngl_no_file(file_content:list[str]):
    positions = []
    normals = []
    uvs = []
    vertices = []
    indices = []
    vertex_map = {}
    idx = 0

    for line in file_content:
        if line.startswith("v "):
            _, x, y, z = line.split()
            positions.append([float(x), float(y), float(z)])
        elif line.startswith("vn "):
            _, x, y, z = line.split()
            normals.append([float(x), float(y), float(z)])
        elif line.startswith("vt "):
            _, u, v = line.split()
            uvs.append([float(u), float(v)])
        elif line.startswith("f "):
            face = []
            for part in line.split()[1:]:
                vals = part.split("/")

                p = int(vals[0]) - 1

                t = int(vals[1]) - 1 if len(vals) > 1 and vals[1] else 0

                n = int(vals[2]) - 1 if len(vals) > 2 and vals[2] else 0
                key = (p, t, n)
                if key not in vertex_map:
                    px, py, pz = positions[p]
                    if len(normals) > 0:
                        nx, ny, nz = normals[n]
                    else:
                        nx, ny, nz = (0.0, 1.0, 0.0)
                    u, v = uvs[t]
                    v = 1 - v
                    vertices.extend([px, py, pz, nx, ny, nz, u, 1-v])
                    vertex_map[key] = idx
                    idx += 1
                face.append(vertex_map[key])
            for i in range(1, len(face)-1):
                indices.extend([face[0], face[i], face[i+1]])

    return np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')


# -------------------------
# TEXTURE ARRAY LOADER
# -------------------------

def load_texture_array(ctx:moderngl.Context, textures):
    width, height = textures[0].size
    depth = len(textures)
    data = b''.join([img.convert('RGBA').transpose(Image.FLIP_TOP_BOTTOM).tobytes() for img in textures])
    tex_array = ctx.texture_array((width, height, depth), 4, data)
    tex_array.filter = (moderngl.NEAREST, moderngl.NEAREST)
    #tex_array.build_mipmaps()
    return tex_array

# -------------------------
# INSTANCED TEXT
# -------------------------
class InstancedText:
    def __init__(self, ctx, prog, font_texture, charset:str, grid_size=16):
        self.ctx = ctx
        self.prog = prog
        self.font_texture = font_texture
        self.charset = charset
        self.grid_size = grid_size

        # Quad (pos + uv)
        vertices = np.array([
            [-0.5, -0.5, 0, 0],
            [ 0.5, -0.5, 1, 0],
            [ 0.5,  0.5, 1, 1],
            [-0.5,  0.5, 0, 1],
        ], dtype='f4')

        indices = np.array([0,1,2, 0,2,3], dtype='i4')

        self.vbo = ctx.buffer(vertices.tobytes())
        self.ibo = ctx.buffer(indices.tobytes())

        # instance: pos(2) + scale(2) + uv(4) + color(3)
        self.instance_data = np.zeros((0, 11), dtype='f4')
        self.instance_buffer = ctx.buffer(reserve=256 * 11 * 4)

        self.vao = ctx.vertex_array(
            prog,
            [
                (self.vbo, '2f 2f', 'in_pos', 'in_uv'),
                (self.instance_buffer, '2f 2f 4f 3f/i',
                 'instance_pos', 'instance_scale', 'instance_uv', 'instance_color')
            ],
            self.ibo
        )

        # 🔑 Track strings: {id: (start_index, length)}
        self.strings = {}

    # 🔧 Upload to GPU
    def _upload(self):
        self.instance_buffer.orphan(self.instance_data.nbytes)
        if len(self.instance_data) > 0:
            self.instance_buffer.write(self.instance_data.tobytes())

    # 🔑 Get UV of a character
    def get_char_uv(self, char):
        idx = self.charset.find(char)
        if idx == -1:
            idx = 0

        grid = self.grid_size
        cell = 1.0 / grid

        col = idx % grid
        row = idx // grid

        u0 = col * cell
        u1 = u0 + cell

        v0 = 1.0 - (row + 1) * cell
        v1 = 1.0 - row * cell

        return (u0, v0, u1, v1)

    # ➕ Add string
    def add_string(self, text, string_id,
                   pos=(-0.9, 0.9),
                   scale=(0.12, 0.18),
                   color=(1,1,1),
                   spacing=0.05):

        # If ID exists → replace
        if string_id in self.strings:
            self.remove_string(string_id)

        x, y = pos
        start_index = len(self.instance_data)
        length = len(text)

        new_data = []

        for i, char in enumerate(text):
            u0, v0, u1, v1 = self.get_char_uv(char)

            new_data.append([
                x + i * spacing, y,
                scale[0], scale[1],
                u0, v0, u1, v1,
                color[0], color[1], color[2]
            ])

        if new_data:
            new_array = np.array(new_data, dtype='f4')
            self.instance_data = np.vstack((self.instance_data, new_array))

        self.strings[string_id] = (start_index, length)

        self._upload()

    # ❌ Remove string by ID
    def remove_string(self, string_id):
        if string_id not in self.strings:
            return

        start, length = self.strings[string_id]

        # Remove slice
        self.instance_data = np.delete(
            self.instance_data,
            np.s_[start:start+length],
            axis=0
        )

        del self.strings[string_id]

        # 🔄 Fix indices of remaining strings
        for key in list(self.strings.keys()):
            s, l = self.strings[key]
            if s > start:
                self.strings[key] = (s - length, l)

        self._upload()

    # 🔄 Update string
    def update_string(self, string_id, new_text, **kwargs):
        self.remove_string(string_id)
        ctx.clear()
        self.add_string(new_text, string_id, **kwargs)

    # 🧹 Clear all
    def clear(self):
        self.instance_data = np.zeros((0, 11), dtype='f4')
        self.strings.clear()
        self._upload()

    # 🎨 Render
    def render(self):
        if len(self.instance_data) > 0:
            self.font_texture.use(location=0)
            self.vao.render(instances=len(self.instance_data))

class InstancedGui:
    def __init__(self, ctx, prog):
        self.ctx = ctx
        self.prog = prog

        vertices = np.array([
            [-0.5, -0.5],
            [ 0.5, -0.5],
            [ 0.5,  0.5],
            [-0.5,  0.5],
        ], dtype='f4')

        indices = np.array([0,1,2, 0,2,3], dtype='i4')

        self.vbo = ctx.buffer(vertices.tobytes())
        self.ibo = ctx.buffer(indices.tobytes())

        self.instance_data = np.zeros((0, 7), dtype='f4')
        self.instance_buffer = ctx.buffer(reserve=100 * 7 * 4)

        self.vao = ctx.vertex_array(
            prog,
            [
                (self.vbo, '2f', 'in_pos'),
                (self.instance_buffer, '2f 2f 3f/i',
                 'instance_pos', 'instance_size', 'instance_color')
            ],
            self.ibo
        )

        # 🔥 SAME IDEA AS TEXT
        self.elements = {}   # id -> index
        self.callbacks = []

    # 🔄 Upload
    def _upload(self):
        self.instance_buffer.orphan(self.instance_data.nbytes)
        if len(self.instance_data) > 0:
            self.instance_buffer.write(self.instance_data.tobytes())

    # ➕ ADD (WITH ID)
    def add(self, element_id, pos, size, color, callback=None):
        # Replace if exists
        if element_id in self.elements:
            self.remove(element_id)

        new = np.array([[pos[0], pos[1], size[0], size[1],
                         color[0], color[1], color[2]]], dtype='f4')

        index = len(self.instance_data)

        self.instance_data = np.vstack((self.instance_data, new))
        self.callbacks.append(callback)

        self.elements[element_id] = index

        self._upload()

    # ❌ REMOVE BY ID
    def remove(self, element_id):
        if element_id not in self.elements:
            return

        index = self.elements[element_id]

        self.instance_data = np.delete(self.instance_data, index, axis=0)
        self.callbacks.pop(index)

        del self.elements[element_id]

        # 🔥 FIX INDICES (like text system)
        for key in list(self.elements.keys()):
            if self.elements[key] > index:
                self.elements[key] -= 1

        self._upload()

    # 🔄 UPDATE
    def update(self, element_id, **kwargs):
        if element_id not in self.elements:
            return

        index = self.elements[element_id]

        px, py, sx, sy, r, g, b = self.instance_data[index]

        pos = kwargs.get("pos", (px, py))
        size = kwargs.get("size", (sx, sy))
        color = kwargs.get("color", (r, g, b))
        callback = kwargs.get("callback", self.callbacks[index])

        self.instance_data[index] = [
            pos[0], pos[1],
            size[0], size[1],
            color[0], color[1], color[2]
        ]

        self.callbacks[index] = callback

        self._upload()

    # 🎯 CLICK
    def handle_click(self, mouse_x, mouse_y, width, height):
        x = (mouse_x / width) * 2 - 1
        y = 1 - (mouse_y / height) * 2

        for i, inst in enumerate(self.instance_data):
            px, py, sx, sy = inst[:4]

            if (px - sx/2 <= x <= px + sx/2 and
                py - sy/2 <= y <= py + sy/2):

                if self.callbacks[i]:
                    self.callbacks[i]()
                break

    # 🎨 RENDER
    def render(self):
        if len(self.instance_data) > 0:
            self.vao.render(instances=len(self.instance_data))


class Background:
    def __init__(self, ctx):
        self.ctx = ctx
        self.backgrounds = {}   # id -> texture
        self.current = None

        self.prog = ctx.program(
            vertex_shader=BACKGROUND_VERTEX,
            fragment_shader=BACKGROUND_FRAGMENT
        )

        # Fullscreen quad
        quad = np.array([
            [-1, -1],
            [ 1, -1],
            [ 1,  1],
            [-1,  1],
        ], dtype='f4')

        indices = np.array([0,1,2, 0,2,3], dtype='i4')

        self.vbo = ctx.buffer(quad.tobytes())
        self.ibo = ctx.buffer(indices.tobytes())

        self.vao = ctx.vertex_array(
            self.prog,
            [(self.vbo, '2f', 'in_pos')],
            self.ibo
        )

    # ➕ add background
    def add(self, bg_id, image_path):
        img = Image.open(image_path).convert("RGBA")
        img = img.transpose(Image.FLIP_TOP_BOTTOM)

        tex = self.ctx.texture(img.size, 4, img.tobytes())
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

        self.backgrounds[bg_id] = tex

    # 🔄 set active background
    def set(self, bg_id):
        if bg_id in self.backgrounds:
            self.current = bg_id

    # 🎨 render
    def render(self):
        if self.current is None:
            return

        self.ctx.disable(moderngl.DEPTH_TEST)

        tex = self.backgrounds[self.current]
        tex.use(location=0)
        self.prog['bg_texture'] = 0

        self.vao.render()

        self.ctx.enable(moderngl.DEPTH_TEST)

# -------------------------
# RAYCAST
# -------------------------

def raycast(camera: Camera, occupied, max_dist=10):
    origin = (camera.position + np.array([0, camera.eye_height, 0], dtype='f4')).astype('f4')
    direction = camera.front.astype('f4')
    direction /= np.linalg.norm(direction)
    origin = origin + direction * 0.001
    grid_origin = origin + np.array([0.5,0.5,0.5], dtype='f4')
    voxel = np.floor(grid_origin).astype(int)
    step = np.sign(direction).astype(int)
    inv_dir = np.where(direction != 0, 1.0 / direction, 1e10)
    tDelta = np.abs(inv_dir)
    next_boundary = voxel + (step > 0)
    tMax = (next_boundary - grid_origin) * inv_dir
    normal = np.zeros(3, dtype='f4')
    dist = 0.0
    while dist <= max_dist:
        key = tuple(voxel)
        if key in occupied:
            return key, normal
        min_t = np.min(tMax)
        axes = np.where(np.abs(tMax - min_t) < 1e-6)[0]
        for axis in axes:
            voxel[axis] += step[axis]
            normal[:] = 0
            normal[axis] = -step[axis]
            tMax[axis] += tDelta[axis]
        dist = min_t
    return None, None

# -------------------------
# DRAW HOVERED CUBE (unchanged)
# -------------------------

def draw_hovered_cube(ctx, color_prog, projection, camera, hit_pos):
    vertices = np.array([
        [-0.5,-0.5,-0.5],[0.5,-0.5,-0.5],[0.5,0.5,-0.5],[-0.5,0.5,-0.5],
        [-0.5,-0.5,0.5],[0.5,-0.5,0.5],[0.5,0.5,0.5],[-0.5,0.5,0.5]
    ], dtype='f4')
    edges = np.array([
        [0,1],[1,2],[2,3],[3,0],
        [4,5],[5,6],[6,7],[7,4],
        [0,4],[1,5],[2,6],[3,7]
    ], dtype='i4')
    model = Matrix44.from_translation(hit_pos, dtype='f4')
    mvp = projection * camera.get_view() * model
    vbo = ctx.buffer(vertices.tobytes())
    ibo = ctx.buffer(edges.tobytes())
    vao = ctx.vertex_array(color_prog, [(vbo,'3f','in_pos')], index_buffer=ibo)
    color_prog['mvp'].write(mvp.astype('f4').tobytes())
    color_prog['color'].value = (0,0,0)
    vao.render(mode=moderngl.LINES)

text_buffer = ""
send = False

def char_callback(window, char):
    global text_buffer
    text_buffer += chr(char)

def key_callback(window, key, scancode, action, mods):
    global text_buffer,send

    if action == glfw.PRESS:
        if key == glfw.KEY_BACKSPACE:
            text_buffer = text_buffer[:-1]
        elif key == glfw.KEY_ENTER:
            send = True


def get_uv(u, v, block_id, ATLAS_BLOCKS):

    bx = block_id % ATLAS_BLOCKS
    by = ATLAS_BLOCKS - 1 - block_id // ATLAS_BLOCKS

    u /= ATLAS_BLOCKS
    v /= ATLAS_BLOCKS

    u += bx/ATLAS_BLOCKS
    v += by/ATLAS_BLOCKS

    return (u, v)


def export_and_load_chunk(models, _layers_, offsett, OPPOSITE_TEXTURE_INDICES):
    ATLAS_SIZE = 320
    BLOCK_SIZE = 64
    FACE_SIZE = 16
    ATLAS_BLOCKS = ATLAS_SIZE // BLOCK_SIZE


    _layers = list(_layers_)

    obj = []
    
    
    # -------------------------------------------------
    # LOAD CUBE
    # -------------------------------------------------

    base_vertices = []
    base_uvs = []
    base_normals = []
    base_faces = []

    with open("assets/models/block.obj", "r") as f:
        for line in f:

            if line.startswith("v "):
                _, x, y, z = line.split()
                base_vertices.append((float(x), float(y), float(z)))

            elif line.startswith("vt "):
                _, u, v = line.split()
                base_uvs.append((float(u), float(v)))

            elif line.startswith("vn "):
                _, x, y, z = line.split()
                base_normals.append((float(x), float(y), float(z)))

            elif line.startswith("f "):
                parts = line.strip().split()[1:]

                face = []
                for p in parts:
                    v, vt, vn = p.split("/")
                    face.append((int(v)-1, int(vt)-1, int(vn)-1))

                base_faces.append(face)

    base_vertices = np.array(base_vertices, dtype=np.float32)

    # -------------------------------------------------
    # OBJ
    # -------------------------------------------------

    v_offset = 1
    vt_offset = 1
    vn_offset = 1

    positions = []
    normals = []
    uvs = []
    vertices = []
    indices = []
    vertex_map = {}
    idx = 0

    for model_index, model in enumerate(models):

        obj.append(f"g block_{model_index}")

        block_id = int(_layers.pop(0))

        mat = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], list(model)+[1.0]], dtype=np.float32)

        # -------------------------------------------------
        # TRANSFORM VERTICES
        # -------------------------------------------------

        transformed = []
        for v in base_vertices:
            vec = np.array([v[0], v[1], v[2], 1.0], dtype=np.float32)
            t = vec.dot(mat)
            positions.append(t[:3])

        # normals (unchanged per cube)
        for n in base_normals:
            normals.append(n)

        # -------------------------------------------------
        # UV + FACES
        # -------------------------------------------------

        for face in base_faces:

            # quad -> triangulate
            v0, v1, v2, v3 = face

            uv_indices = []

            for corner_i, (v_idx, vt_idx, vn_idx) in enumerate(face):

                base_u, base_v = base_uvs[vt_idx]

                u, v = get_uv(
                    base_u,
                    base_v,
                    block_id,
                    ATLAS_BLOCKS
                )

                uvs.append([u, v])

                uv_indices.append(vt_offset)
                vt_offset += 1

            # triangle 1
            obj.append(
                f"f "
                f"{v0[0]+v_offset}/{uv_indices[0]}/{v0[2]+vn_offset} "
                f"{v1[0]+v_offset}/{uv_indices[1]}/{v1[2]+vn_offset} "
                f"{v2[0]+v_offset}/{uv_indices[2]}/{v2[2]+vn_offset}"
            )

            face = []
            for part in line.split()[1:]:
                vals = part.split("/")

                p = int(vals[0]) - 1

                t = int(vals[1]) - 1 if len(vals) > 1 and vals[1] else 0

                n = int(vals[2]) - 1 if len(vals) > 2 and vals[2] else 0
                key = (p, t, n)
                if key not in vertex_map:
                    px, py, pz = positions[p]
                    if len(normals) > 0:
                        nx, ny, nz = normals[n]
                    else:
                        nx, ny, nz = (0.0, 1.0, 0.0)
                    u, v = uvs[t]
                    v = 1 - v
                    vertices.extend([px, py, pz, nx, ny, nz, u, 1-v])
                    vertex_map[key] = idx
                    idx += 1
                face.append(vertex_map[key])
            for i in range(1, len(face)-1):
                indices.extend([face[0], face[i], face[i+1]])

            # triangle 2
            obj.append(
                f"f "
                f"{v0[0]+v_offset}/{uv_indices[0]}/{v0[2]+vn_offset} "
                f"{v2[0]+v_offset}/{uv_indices[2]}/{v2[2]+vn_offset} "
                f"{v3[0]+v_offset}/{uv_indices[3]}/{v3[2]+vn_offset}"
            )

        v_offset += len(base_vertices)
        vn_offset += len(base_normals)


    for line in obj:
        if line.startswith("v "):
            _, x, y, z = line.split()
            positions.append([float(x), float(y), float(z)])
        elif line.startswith("vn "):
            _, x, y, z = line.split()
            normals.append([float(x), float(y), float(z)])
        elif line.startswith("vt "):
            _, u, v = line.split()
            uvs.append([float(u), float(v)])
        elif line.startswith("f "):
            face = []
            for part in line.split()[1:]:
                vals = part.split("/")

                p = int(vals[0]) - 1

                t = int(vals[1]) - 1 if len(vals) > 1 and vals[1] else 0

                n = int(vals[2]) - 1 if len(vals) > 2 and vals[2] else 0
                key = (p, t, n)
                if key not in vertex_map:
                    px, py, pz = positions[p]
                    if len(normals) > 0:
                        nx, ny, nz = normals[n]
                    else:
                        nx, ny, nz = (0.0, 1.0, 0.0)
                    u, v = uvs[t]
                    v = 1 - v
                    vertices.extend([px, py, pz, nx, ny, nz, u, 1-v])
                    vertex_map[key] = idx
                    idx += 1
                face.append(vertex_map[key])
            for i in range(1, len(face)-1):
                indices.extend([face[0], face[i], face[i+1]])

    return np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')


    #v, i = load_obj_for_moderngl_no_file(obj)

    #return v, i

v, i, pos, tex, ogterrain = None, None, None, None, None

generate_new_chunk = None

def generate_chunk_at(offsett:list, generated_chunks, chunks, heightmap, rules, TEXTURE_INDICES, OPPOSITE_TEXTURE_INDICES, thread_part, cube_prog):
    global generating, waiting_for_thread_finish, generate_new_chunk, v, i, pos, tex, ogterrain
    generating = True

    def generate_blocks_and_return_blocks(offsett, heightmap, rules, chunks:list[Chunk], tex_mapping:dict[str:int], opp_tex_mapping:dict[int:str]): 
            global v, i, pos, tex, ogterrain
            new_chunk = Chunk(offsett, heightmap, rules, seed=seed)
            result = new_chunk.get_blocks()
            new_textures = []
            new_positions = []
            for i in result:
                new_textures.append(tex_mapping[i.texture])
                new_positions.append(i.position)
            vi, ogterrain = export_and_load_chunk(new_positions, new_textures, tuple(offsett), opp_tex_mapping), new_chunk.get_blocks()
            v, i = vi
    if thread_part:
        v, i, ogterrain = None, None, None

        generate_new_chunk = threading.Thread(target=generate_blocks_and_return_blocks, args=(offsett, heightmap, rules, chunks, TEXTURE_INDICES, OPPOSITE_TEXTURE_INDICES), daemon=True)
        generate_new_chunk.start()

    waiting_for_thread_finish = True
    if not generate_new_chunk.is_alive():
        new_chunk = Chunk(
            offsett,
            None,
            None,
            True,
            ogterrain,
            False,
            ctx,
            cube_prog,
            cube_v,
            cube_i,
            TEXTURE_INDICES,
            seed,
            InstancedModel(
                ctx,
                chunk_prog,
                v,
                i,
                {"texture":0},
                True
            )
        )
        chunks.append(new_chunk)
        waiting_for_thread_finish = False
        generated_chunks.append(offsett)
        generating = False


# -------------------------
# MAIN
# -------------------------

def main(chunks_:dict,worldName,save_path,multiplayer:bool=False,address="", gen_cnk:list[list[int]]=[[0, 0, 0]]):
    global window,ctx,gui,menu_stuff,text_buffer,send,generating,chunk_prog

    generated_chunks:list[list[int]] = gen_cnk
    chunks = list[Chunk]()

    frame_passed = 0
    selected_block = "grass"
    available_blocks = []

    occupied:set[tuple[float, float, float]]=set()
    blocks:list[Block] = []

    if not multiplayer:
        if chunks_ == None:
            new_chunk = Chunk([0, 0, 0], heightmap, rules, ctx=ctx, prog=prog, v=cube_v, i=cube_i, tex_mapping=TEXTURE_INDICES, seed=seed)
            chunks.append(new_chunk)
            generated_chunks = [[0, 0, 0]]
            print("generated chunk at [0, 0, 0]")
        else:
            for cnk in chunks_.items():
                models = cnk[1]["p"]
                layers = cnk[1]["t"]
                proprieties = cnk[1]["pr"]
                occ = set()
                bl:list[Block] = []
                for idx in range(len(models)):
                    occ.add(tuple(models[idx]))
                    bl.append(Block(layers[idx], list(models[idx]), layers[idx], proprieties[idx], False if layers[idx] == "water_1" else True))
                chunks.append(Chunk(cnk[0], None, None, True, bl, False, None, seed=seed, ctx=ctx, prog=prog, v=cube_v, i=cube_i, tex_mapping=TEXTURE_INDICES))
                blocks.extend(bl)
                chunks[-1].occupied.update(occ)

    camera=Camera([0,1,0], ctx, prog, text_prog, TEXTURE_INDICES, font_tex, CHARSET, multiplayer, address, 5000, window)

    if multiplayer:
        #TODO REDO
        models, layers, proprieties = camera.get_world()
        print("finished")
        for idx in range(len(models)):
            occupied.add(models[idx])
            blocks.append(Block(layers[idx], list(models[idx]), layers[idx], proprieties[idx]))

    glfw.set_cursor_pos_callback(window,lambda w,x,y:camera.process_mouse(x,y))
    projection = np.array(Matrix44.perspective_projection(60, WIDTH/HEIGHT, 0.1, 1000), dtype='f4')
    view = np.array(camera.get_view(), dtype='f4')

    chunk_prog["projection"].write(projection.tobytes())
    chunk_prog["view"].write(view.tobytes())

    aspect=WIDTH/HEIGHT
    size=0.02
    cross_vertices=np.array([-size,0,size,0,0,-size*aspect,0,size*aspect],dtype='f4')
    cross_vbo=ctx.buffer(cross_vertices.tobytes())
    cross_vao=ctx.vertex_array(cross_prog, [(cross_vbo,'2f','in_pos')])

    last=time.time()
    last_last = time.time()

    #define keys handlers
    change_block = Key(window, glfw.KEY_LEFT_ALT)
    get_block = Key(window, glfw.MOUSE_BUTTON_MIDDLE, True)
    chat_key = Key(window, glfw.KEY_C, toggle=True)
    esc_key = Key(window, glfw.KEY_ESCAPE, False, True)
    
    menu_stuff.add_string("FPS: your computer is potato", 0, pos=(-0.9, 0.9), color=(1, 1, 1))

    menu_stuff.add_string("Selected Block: grass", 1, pos=(-0.9, 0.75))

    prev_x = 0
    prev_z = 0

    curr_frame = 0

    enable_funky_shaders = False
    prog["enable_funky_shaders"] = enable_funky_shaders

    prev_cnk_pos = None

    while not glfw.window_should_close(window):
        now=time.time()
        delta=now-last
        last=now
        glfw.poll_events()
        rounded_position = tuple(map(int, np.round(camera.position)))
        cnk_position = [rounded_position[0]//10*10, 0, rounded_position[2]//10*10]

        if prev_cnk_pos is not cnk_position:
            for ajk in chunks:
                if cnk_position == ajk.position:
                    curr_cnk = ajk
            prev_cnk_pos = cnk_position

        hit,normal=raycast(camera,curr_cnk.occupied)
        if hit is not None: index=list(curr_cnk.occupied).index(hit)
        else:index = None
        msg_to_snd=""
        if send:
            msg_to_snd=text_buffer
            text_buffer = ""
        cam_in_block = None
        listed_camera_position = list(map(int, np.round(camera.position)))
        listed_camera_position[1] += 1
        blocks_poss = list(map(lambda x: list(x.position), blocks))
        
        if listed_camera_position in blocks_poss:
            cam_in_block = blocks[blocks_poss.index(listed_camera_position)]
        else:
            listed_camera_position[1] -= 1
            if listed_camera_position in blocks_poss:
                cam_in_block = blocks[blocks_poss.index(listed_camera_position)]

        if camera.update(window,delta,curr_cnk.occupied,hit,normal,curr_cnk.blocksinstmodel,selected_block,curr_cnk.blocks,index,message_to_send=msg_to_snd,in_block=cam_in_block) == "ban":
            return
        camera.process_keyboard(window,delta,curr_cnk.occupied)
        landing_chunk = list(np.round(camera.front.copy()))
        landing_chunk[0] *= 10
        landing_chunk[0] += cnk_position[0]
        landing_chunk[1] *= 10
        landing_chunk[1] += cnk_position[1]
        landing_chunk[2] *= 10
        landing_chunk[2] += cnk_position[2]
        
        send=False

        if not multiplayer:
            generated_chunk_this_frame = False
            for x, z in square_range([cnk_position[0], cnk_position[2]], 40, 10):
                if generated_chunk_this_frame and not waiting_for_thread_finish: break
                if waiting_for_thread_finish:
                    generate_chunk_at([prev_x, 0, prev_z], generated_chunks, chunks, heightmap, rules, TEXTURE_INDICES, OPPOSITE_TEXTURE_INDICES, False, prog)
                    OBJECTSTORENDER.append(chunks[-1])
                elif not [x, 0, z] in generated_chunks:
                    #blocks/tot_blocks*100=percentage
                    generate_chunk_at([x, 0, z], generated_chunks, chunks, heightmap, rules, TEXTURE_INDICES, OPPOSITE_TEXTURE_INDICES, True, prog)
                    prev_x = x
                    prev_z = z
                    generated_chunk_this_frame = True



        #check if a button is pressed
        if not camera.enabled:
            if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS:
                mx, my = glfw.get_cursor_pos(window)
                gui.handle_click(mx, my, WIDTH, HEIGHT)

        ctx.clear(0.1,0.1,0.12)
        prog["projection"].write(projection.astype('f4').tobytes())
        prog["view"].write(camera.get_view().astype('f4').tobytes())
        prog["lightPos"].value = (camera.position[0], 50, camera.position[2])
        prog["viewPos"].write(camera.position.astype('f4').tobytes())
        if enable_funky_shaders:
            prog["frame"] = curr_frame
            prog["chance"] = curr_frame / 1000
        else:
            prog["frame"] = curr_frame
            prog["chance"] = -1
        chunk_prog["projection"].write(projection.astype('f4').tobytes())
        chunk_prog["view"].write(camera.get_view().astype('f4').tobytes())
        chunk_prog["lightPos"].value = (camera.position[0], 50, camera.position[2])
        chunk_prog["viewPos"].write(camera.position.astype('f4').tobytes())

        if hit:
            draw_hovered_cube(ctx, color_prog, projection, camera, hit)

        if change_block.is_pressed:
            try:
                selected_block = available_blocks[available_blocks.index(selected_block)+1]
            except:
                selected_block = available_blocks[0]
            
            menu_stuff.update_string(1, f"Selected Block: {selected_block.replace('_', ' ')}", pos=(-0.9, 0.75))
        
        if get_block.is_pressed:
            for idx, model in enumerate(curr_cnk.blocksinstmodel.models):
                pos = tuple(map(int, model[3][:3]))
                if pos == hit:
                    selected_block = available_blocks[curr_cnk.blocksinstmodel.layers[idx]]
                    break

            menu_stuff.update_string(1, f"Selected Block: {selected_block.replace('_', ' ')}", pos=(-0.9, 0.75))

        for cnk in chunks:
            if cnk.position == cnk_position:
                cnk.is_player_in = True
            else:
                cnk.is_player_in = False

        render()

        if hasattr(camera, "players"):
            camera.players.render()

        ctx.disable(moderngl.DEPTH_TEST)
        cross_prog["color"].value=(1, 1, 1)
        cross_vao.render(moderngl.LINES)
        camera.chat.render()
        gui.render()
        if esc_key.is_pressed:
            gui.add(element_id="quit_button", pos=(0, 0), size=(0.7, 0.2), color=(0, 0, 0), callback=lambda:glfw.set_window_should_close(window, True))
            menu_stuff.add_string("Save & Quit", 2, pos=(-0.23, -0.04))
            camera.disable(window)
        else:
            menu_stuff.remove_string(2)
            gui.remove("quit_button")
            camera.enable(window)
        

        if chat_key.is_pressed:
            camera.disable(window)
            menu_stuff.add_string(text_buffer, 3, pos=(-0.9, -0.9), color=(1, 1, 1))
            gui.add(element_id="chat_bk", pos=(0.00, -0.95), size=(2.00, 0.5), color=(0,0,0))
        else:
            if not esc_key.is_pressed:
                camera.enable(window)
            
            text_buffer = ""

            menu_stuff.remove_string(3)
            gui.remove("chat_bk")

        menu_stuff.render()
        ctx.enable(moderngl.DEPTH_TEST)

        glfw.swap_buffers(window)
        frame_passed += 1
        if time.time() - last_last >= 1:
            last_last = time.time()
            menu_stuff.update_string(0, f"FPS: {frame_passed}")
            frame_passed = 0

        curr_frame += 1

    if not multiplayer:
        ctx.disable(moderngl.DEPTH_TEST)
        background.set("titlescreen")
        background.render()
        menu_stuff.add_string("Saving World...", 5, (0, 0))
        menu_stuff.render()
        ctx.enable(moderngl.DEPTH_TEST)
        #save_path = "saves"
        #worldName = "testSave"
        if worldName in os.listdir(save_path):
            print("found")
        else:
            print("not found")
            os.makedirs(save_path+"/"+worldName)

        for cnk in chunks:
            with open(save_path+"/"+worldName+"/"+str(cnk.position)+"positions.chunkdata", "wb") as f:
                for block_ in cnk.get_blocks():
                    f.write(str.encode(str(block_.position)))
                    f.write(bytes([255]))

            with open(save_path+"/"+worldName+"/"+str(cnk.position)+"textures.chunkdata", "wb") as f:
                for block_ in cnk.get_blocks():
                    f.write(str.encode(block_.texture))
                    f.write(bytes([255]))

            with open(save_path+"/"+worldName+"/"+str(cnk.position)+"proprieties.chunkdata", "wb") as f:
                for block_ in cnk.get_blocks():
                    new_dict = {}
                    for i in range(len(block_.proprieties)):
                        new_dict[i] = REVERSE_INTERACT_FUNCTION_CONVERSION[block_.proprieties[i]]
                    block_.proprieties = new_dict

                    f.write(str.encode(str(block_.proprieties)))
                    f.write(bytes([255]))
        
        with open(save_path+"/"+worldName+"/"+"gen_cnk.txt", "w") as f:
            f.write(json.dumps(generated_chunks))
    
    glfw.terminate()
    #block.export_chunk("chunks/chunk.obj", "chunks/texture.png")

def load_files(worldName,save_path):
    """Takes a world name and save path and transforms them into models and textures (layers) and block proprieties"""
    gn_cnk = []
    chunks:dict[dict[list]] = {}

    files:list[str] = os.listdir(save_path+"/"+worldName)

    with open(save_path+"/"+worldName+"/"+"gen_cnk.txt", "r") as f:
        gn_cnk = json.loads(f.read())


    counter = 0
    

    for file in files:
        if file == "gen_cnk.txt":
            continue

        if counter == 0:
            chunks[literal_eval(file.split(")")[0]+")")] = {"p":None, "t":None, "pr":None}
            counter += 1
        elif counter == 2:
            counter = 0
        else:
            counter += 1
        
        if "positions" in file:
            with open(save_path+"/"+worldName+"/"+file, "rb") as f: 
                content = f.read()
                new_content = content.split(b"\xFF")
                strings = [literal_eval(p.decode("utf-8")) for p in new_content if p]
                chunks[literal_eval(file.split(")")[0]+")")]["p"] = strings

        elif "textures" in file:
            with open(save_path+"/"+worldName+"/"+file, "rb") as f:
                content = f.read()
                new_content = content.split(b"\xFF") 
                strings = [p.decode("utf-8") for p in new_content if p]
                chunks[literal_eval(file.split(")")[0]+")")]["t"] = strings

        elif "proprieties" in file:
            with open(save_path+"/"+worldName+"/"+file, "rb") as f:
                content = f.read()
                new_content = content.split(b"\xFF") 
                strings = [literal_eval(p.decode("utf-8")) for p in new_content if p]
                for string_ in strings:
                    for string in string_:
                        string_[string] = INTERACT_FUNCTION_CONVERSION[string_[string]]
                chunks[literal_eval(file.split(")")[0]+")")]["pr"] = strings

    return chunks, gn_cnk

if __name__=="__main__":
    #text parameters init
    CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:.;,_-!? */€$%&£!ì^'()|="

    GRID_SIZE = 16  # 16x16 grid
    CELL_SIZE = 32  # pixels per character

    font = ImageFont.truetype("assets/PressStart2P-Regular.ttf", 16)

    img = Image.new("RGBA", (GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE), (0,0,0,0))
    draw = ImageDraw.Draw(img)

    for i, char in enumerate(CHARSET):
        x = (i % GRID_SIZE) * CELL_SIZE
        y = (i // GRID_SIZE) * CELL_SIZE

        draw.text((x + 4, y + 2), char, font=font, fill=(255,255,255,255))

    # 🔥 flip for OpenGL
    img = img.transpose(Image.FLIP_TOP_BOTTOM)

    font_tex = ctx.texture(img.size, 4, img.tobytes())
    font_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)

    gui = InstancedGui(ctx, gui_prog)
    menu_stuff = InstancedText(ctx, text_prog, font_tex, CHARSET)
    background = Background(ctx)
    background.add("title screen", "assets/backgrounds/title_screen.png")
    background.set("title screen")

    go_on = False
    load = False
    multi = False

    def set_variable_to_true(_load, multi_=False):
        global go_on, load, multi

        go_on = True
        load = _load
        multi = multi_

        # 🔥 REMOVE UI IMMEDIATELY
        gui.remove("load_world")
        gui.remove("erase_world")
        gui.remove("multiplayer")
        menu_stuff.clear()
        
    mouse_pressed_last = False

    gui.add(element_id="load_world", pos=(0, 0.3), size=(0.7, 0.2), color=(0, 0, 0), callback=lambda:set_variable_to_true(True))
    menu_stuff.add_string("load world", 0, pos=(-0.21, 0.27))

    gui.add(element_id="erase_world", pos=(0, 0), size=(0.7, 0.2), color=(0, 0, 0), callback=lambda:set_variable_to_true(False))
    menu_stuff.add_string("erase world", 1, pos=(-0.23, -0.03))

    gui.add(element_id="multiplayer", pos=(0, -0.3), size=(0.7, 0.2), color=(0, 0, 0), callback=lambda:set_variable_to_true(False, True))
    menu_stuff.add_string("multiplayer", 2, pos=(-0.23, -0.33))

    while not go_on and not glfw.window_should_close(window):
        glfw.poll_events()

        mouse_now = glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS

        if mouse_now and not mouse_pressed_last:
            mx, my = glfw.get_cursor_pos(window)
            gui.handle_click(mx, my, WIDTH, HEIGHT)

        mouse_pressed_last = mouse_now
        
        background.render()
        ctx.disable(moderngl.DEPTH_TEST)
        gui.render()
        menu_stuff.render()
        ctx.enable(moderngl.DEPTH_TEST)
        
        glfw.swap_buffers(window)
    
    gui.remove("load_world")
    gui.remove("erase_world")
    gui.remove("multiplayer")
    menu_stuff.clear()
    ctx.clear(0, 0, 0)
    glfw.swap_buffers(window)
    ctx.clear()


    worldName = "testSave"
    save_path = "saves"
    chunks,gen_cnk = None, None

    if load:
        chunks,gen_cnk = load_files(worldName,save_path)

    if multi:
        with open("data.txt", "r") as f:
            if f.read().strip() == "":
                ask = True
            else:
                ask = False
        if ask:
            menu_stuff.add_string("", 0, (0, 0))
            menu_stuff.add_string("Input your Game Account:", 1)
            menu_stuff.add_string("If you want to know why go to:", 2, (-0.9, 0.75))
            menu_stuff.add_string("http://tombenax.pythonanywhere.com", 3, (-0.9, 0.60))
            menu_stuff.add_string("/account/reason", 4, (-0.9, 0.45))
            while True and not glfw.window_should_close(window):
                glfw.poll_events()
                menu_stuff.update_string(0, text_buffer, pos=(-0.5, 0))
                if send:
                    send = False
                    break

                background.render()
                ctx.disable(moderngl.DEPTH_TEST)
                gui.render()
                menu_stuff.render()
                ctx.enable(moderngl.DEPTH_TEST)
                
                glfw.swap_buffers(window)
            
            playernaim = text_buffer
            text_buffer = ""

            menu_stuff.update_string(1, "Input your password:")
            while True and not glfw.window_should_close(window):
                glfw.poll_events()
                menu_stuff.update_string(0, text_buffer, pos=(-0.5, 0))
                if send:
                    send = False
                    break

                background.render()
                ctx.disable(moderngl.DEPTH_TEST)
                gui.render()
                menu_stuff.render()
                ctx.enable(moderngl.DEPTH_TEST)
                
                glfw.swap_buffers(window)
            
            password = text_buffer
            text_buffer = ""

            with open("data.txt", "w") as f:
                f.write(playernaim)
                f.write("\n")
                f.write(password)
        
        menu_stuff.update_string(1, "Input the server IPv4 address:")
        while True and not glfw.window_should_close(window):
            glfw.poll_events()
            menu_stuff.update_string(0, text_buffer, pos=(-0.5, 0))
            if send:
                send = False
                break

            background.render()
            ctx.disable(moderngl.DEPTH_TEST)
            gui.render()
            menu_stuff.render()
            ctx.enable(moderngl.DEPTH_TEST)
            
            glfw.swap_buffers(window)
    
    menu_stuff.clear()

    if not glfw.window_should_close(window):
        main(chunks,worldName,save_path, multi, text_buffer, gen_cnk)
        text_buffer = ""
    else:
        glfw.terminate()
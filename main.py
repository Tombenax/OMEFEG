import copy
import glfw
import moderngl
import numpy as np
from pyrr import Matrix44
import time
import math
from PIL import Image, ImageDraw, ImageFont
from wakepy import Method
from utils import playsound, notification, get_username_and_uuid, square_range, find_distance_between_squares_2D
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
import queue
import threading
from Chunk import Chunk
from icecream import ic
from InstancedModel import InstancedModel
from AnimationHandler import AnimationHandler
#from ControllerHandler import ControllerHandler
from ast import literal_eval
from Renders.DesktopRender import *
from concurrent.futures import ThreadPoolExecutor


WIDTH = 1280
HEIGHT = 720

RENDER_DISTANCE = 10
MAX_FRAME_TIME = 1.0 / 30.0
MAX_CHUNKS_TO_START_PER_FRAME = 1
MAX_CHUNK_CLASSES_TO_BUILD_PER_FRAME = 1

generation_queue = []
generating = False
waiting_for_thread_finish = False
chunk_lookup = {}
visible_chunk_positions = set()

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
            return load_files("testSave", "saves")

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


            for playerdata in playersdata:
                playerdata = literal_eval(playerdata)
                if len(self.players.models) > len(playerdata):
                    self.players.add_instances(positions=[[0, 0, 0]], texture_names=["player"]) #+ALWAYS USE Z+ = FORWARD IN MODELS
                self.players.move_instance(playerdata["id"], playerdata["pos"])
                self.players.rotate_instance(playerdata["id"], [math.radians(playerdata["pitch"]), math.radians(playerdata["yaw"]-90), 0])
                

            chat_owners = tuple(reversed(chat_data[0]))
            chat_messages = tuple(reversed(chat_data[1]))

            for idx, (owner, message) in enumerate(zip(chat_owners, chat_messages)):
                if len(self.chat.strings) > idx:
                    self.chat.update_string(new_text=f"|{owner}|:{message}", string_id=idx, pos=(-0.9, -0.9+idx/10))
                else:
                    self.chat.add_string(text=f"|{owner}|:{message}", string_id=idx, pos=(-0.9, -0.9+idx/10))     


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
        ALLOFGUI.append(self)

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
                   spacing=None,
                   auto_center=False):

        # If ID exists → replace
        if string_id in self.strings:
            self.remove_string(string_id)

        x, y = pos
        length = len(text)

        spac_mult = 0.50

        if spacing is None:
            spacing = -scale[0] * spac_mult
        elif isinstance(spacing, str) and spacing.lower() == "auto":
            spacing = -scale[0] * spac_mult

        glyph_width = scale[0]
        glyph_step = glyph_width + spacing
        total_width = (length * glyph_width) + max(length - 1, 0) * spacing

        start_index = len(self.instance_data)
        new_data = []

        if auto_center and length > 0:
            x = x - ((length - 1) * glyph_step / 2.0)
            x += 0.019 # Adjust for better centering

        for i, char in enumerate(text):
            u0, v0, u1, v1 = self.get_char_uv(char)

            new_data.append([
                x + i * glyph_step, y,
                scale[0], scale[1],
                u0, v0, u1, v1,
                color[0], color[1], color[2]
            ])

        if new_data:
            new_array = np.array(new_data, dtype='f4')
            self.instance_data = np.vstack((self.instance_data, new_array))

        self.strings[string_id] = (start_index, length)

        self._upload()

        return total_width, scale[1]

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
        ALLOFGUI.append(self)

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
    def add(self, element_id, pos, size, color, callback=None, anchor="center"):
        # Replace if exists
        if element_id in self.elements:
            self.remove(element_id)

        if anchor == "top_left":
            pos = (pos[0] + size[0] / 2, pos[1] + size[1] / 2)

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
        if glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS:
            mx, my = glfw.get_cursor_pos(window)
            gui.handle_click(mx, my, WIDTH, HEIGHT)

        if len(self.instance_data) > 0:
            self.vao.render(instances=len(self.instance_data))


class Background:
    def __init__(self, ctx):
        self.ctx = ctx
        self.backgrounds = {}   # id -> texture
        self.current = None
        ALLOFGUI.append(self)

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


def get_uv(u, v, block_id, ATLAS_BLOCKS):
    bx = block_id % ATLAS_BLOCKS
    by = ATLAS_BLOCKS - 1 - block_id // ATLAS_BLOCKS

    u /= ATLAS_BLOCKS
    v /= ATLAS_BLOCKS

    u += bx / ATLAS_BLOCKS
    v += by / ATLAS_BLOCKS

    return (u, v)


_CUBE_MODEL_CACHE = {}


def _load_base_cube_data(obj_path="assets/models/block.obj"):
    if obj_path in _CUBE_MODEL_CACHE:
        return _CUBE_MODEL_CACHE[obj_path]

    positions = []
    uvs = []
    normals = []
    faces = []

    with open(obj_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("v "):
                _, x, y, z = line.split()
                positions.append((float(x), float(y), float(z)))
            elif line.startswith("vt "):
                _, u, v = line.split()
                uvs.append((float(u), float(v)))
            elif line.startswith("vn "):
                _, x, y, z = line.split()
                normals.append((float(x), float(y), float(z)))
            elif line.startswith("f "):
                face = []
                for p in line.split()[1:]:
                    vals = p.split("/")
                    face.append(
                        (
                            int(vals[0]) - 1,
                            int(vals[1]) - 1 if len(vals) > 1 and vals[1] else 0,
                            int(vals[2]) - 1 if len(vals) > 2 and vals[2] else 0,
                        )
                    )
                faces.append(face)

    data = (
        np.array(positions, dtype=np.float32),
        np.array(uvs, dtype=np.float32),
        np.array(normals, dtype=np.float32),
        faces,
    )
    _CUBE_MODEL_CACHE[obj_path] = data
    return data

def add(x, y, z):
    return x+y+z

def wrap_around(number, upper_limit):
    if number > upper_limit:
        number -= upper_limit - 1
    
    return number

def export_and_load_chunk(models:list[list[int]], _layers_):
    """
    Fast chunk mesh builder.

    This version keeps the same cube vertex/index layout, but it avoids all
    per-block OBJ string generation and re-parsing. It performs the merge in
    NumPy so the chunk export stays cheap even when a lot of blocks need to be
    packed into one mesh.
    """
    if not models:
        return np.zeros((0, 8), dtype='f4'), np.zeros((0,), dtype='i4')

    ATLAS_SIZE = 320
    BLOCK_SIZE = 64
    ATLAS_BLOCKS = ATLAS_SIZE // BLOCK_SIZE

    positions = np.asarray(models, dtype=np.float32)
    layers = np.asarray(_layers_, dtype=np.int32)

    if positions.ndim == 1:
        positions = positions.reshape(1, 3)

    base_vertices = cube_v.reshape(-1, 8).astype(np.float32)
    base_indices = cube_i.astype(np.int32)

    block_count = len(positions)

    translated = np.repeat(base_vertices[None, :, :], block_count, axis=0)
    translated[:, :, 0] += positions[:, 0][:, None]
    translated[:, :, 1] += positions[:, 1][:, None]
    translated[:, :, 2] += positions[:, 2][:, None]

    uvs = translated[:, :, 6:8].copy()
    atlas_u = uvs[:, :, 0]
    atlas_v = uvs[:, :, 1]

    bx = layers % ATLAS_BLOCKS
    by = ATLAS_BLOCKS - 1 - (layers // ATLAS_BLOCKS)

    atlas_u = atlas_u / ATLAS_BLOCKS + (bx[:, None] / ATLAS_BLOCKS)
    atlas_v = atlas_v / ATLAS_BLOCKS + (by[:, None] / ATLAS_BLOCKS)

    translated[:, :, 6] = atlas_u
    translated[:, :, 7] = atlas_v

    merged_vertices = translated.reshape(-1, 8)

    vertex_offsets = np.arange(block_count, dtype=np.int32) * len(base_vertices)
    merged_indices = np.repeat(base_indices[None, :], block_count, axis=0) + vertex_offsets[:, None]
    merged_indices = merged_indices.reshape(-1)

    return merged_vertices.astype('f4'), merged_indices.astype('i4')

v, i, pos, tex, ogterrain = None, None, None, None, None

generate_new_chunk = None
chunk_work_queue = queue.Queue()
chunk_worker_thread = None
chunk_work_pending = set()


def generate_chunk_class(offsett, terrain, ctx, cube_prog, chunk_prog, v, i, TEXTURE_INDICES, chunks):
    global chunk_lookup, seed
    new_chunk = Chunk(
        offsett,
        None,
        None,
        True,
        terrain,
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
            TEXTURE_INDICES,
            True
        )
    )
    new_chunk.should_render = False
    chunks.append(new_chunk)
    chunk_lookup[tuple(new_chunk.position)] = new_chunk
    OBJECTSTORENDER.append(new_chunk)

cnkdata = []

def generate_chunk_at(offsett, chunks, heightmap, rules, TEXTURE_INDICES, cube_prog, ctx, chunk_prog):
    try:
        new_chunk = Chunk(offsett, heightmap, rules, seed=seed)
        result = new_chunk.get_blocks()
        new_textures = []
        new_positions = []
        for block in result:
            new_textures.append(TEXTURE_INDICES[block.texture])
            new_positions.append(block.position)

        mesh_vertices, mesh_indices = export_and_load_chunk(new_positions, new_textures)
        ogterrain = new_chunk.get_blocks()
        cnkdata.append((offsett, ogterrain, ctx, cube_prog, chunk_prog, mesh_vertices, mesh_indices, TEXTURE_INDICES, chunks))
    except Exception as e:
        print(f"Error generating chunk at {offsett}: {e}")


class Menu:
    def __init__(self, ctx, text_prog, gui_prog, bk_prog, font_tex, CHARSET, active, callbacks:dict[str, callable]):
        self.ctx = ctx
        self.text_prog = text_prog
        self.gui_prog = gui_prog
        self.bk_prog = bk_prog
        self.font_tex = font_tex
        self.CHARSET = CHARSET
        self._active = active
        self.prev_active = active
        self.callbacks = callbacks
    
    def load_layout(self, filename:str):
        with open(f"assets/layouts/{filename}.json", "r") as f:
            layout = json.load(f)

        self.layout = layout
        if self._active:
            self._add_layout_elements(layout)

    def _add_layout_elements(self, layout):
        buttons = []
        buttons_ids = []
        texts = []
        for element in layout.get("elements", []):
            element_type = element.get("type")
            element_id = element.get("id")
            pos = tuple(element.get("pos", (0, 0)))
            size = tuple(element.get("size", (None, 0)))
            color = tuple(element.get("color", (1, 1, 1)))
            text = element.get("text", "")
            callback_name = element.get("callback")

            callback = None
            if callback_name:
                callback = self.callbacks[callback_name]

            if element_type == "button":
                buttons.append((element_id, pos, size, color, callback))
                buttons_ids.append(size[0])
            elif element_type == "text":

                w, h = menu_stuff.add_string(text, element_id, pos=pos, scale=size, color=color, auto_center=True)

                if element_id in buttons_ids:
                    buttons_list_idx = buttons_ids.index(element_id)
                    button = buttons[buttons_list_idx]
                    
                    gui.add(button[0], button[1], [w+button[2][1], h+button[2][1]], button[3], button[4])


    def active(self, value):
        self._active = value
        if self._active != self.prev_active:
            self.prev_active = self._active
            if self._active:
                self._add_layout_elements(self.layout)
            else:
                for element in self.layout.get("elements", []):
                    element_id = element.get("id")
                    if element.get("type") == "button":
                        gui.remove(element_id)
                    elif element.get("type") == "text":
                        menu_stuff.remove_string(element_id)

esc_menu = None
esc_key = None


#callbacks functions for esc_menu
def resume_game():
    global esc_menu, esc_key
    esc_menu.active(False)
    esc_key.deactivate()

save_quit = False

def save_and_quit():
    global save_quit
    save_quit = True


# -------------------------
# MAIN
# -------------------------

def main(chunks_:dict,worldName,save_path,multiplayer:bool=False,address="", gen_cnk:list[list[int]]=[[0, 0, 0]]):
    global window,ctx,gui,menu_stuff,text_buffer,send,generating,chunk_prog, esc_menu, esc_key, save_quit, cnkdata, chunk_lookup, visible_chunk_positions

    generated_chunks:list[list[int]] = gen_cnk
    chunks = list[Chunk]()
    chunk_lookup = {}
    visible_chunk_positions = set()

    frame_passed = 0
    selected_block = "grass"

    occupied:set[tuple[float, float, float]]=set()
    blocks:list[Block] = []

    if not multiplayer:
        if chunks_ == None:
            #new_chunk = Chunk([0, 0, 0], heightmap, rules, ctx=ctx, prog=prog, v=cube_v, i=cube_i, tex_mapping=TEXTURE_INDICES, seed=seed)
            generate_chunk_at([0, 0, 0], chunks, heightmap, rules, TEXTURE_INDICES, prog, ctx, chunk_prog)
            generate_chunk_class(cnkdata[0][0], cnkdata[0][1], cnkdata[0][2], cnkdata[0][3], cnkdata[0][4], cnkdata[0][5], cnkdata[0][6], cnkdata[0][7], cnkdata[0][8])
            cnkdata.pop(0)
            generated_chunks = [[0, 0, 0]]
            print("generated chunk at [0, 0, 0]")
        else:
            for cnk in chunks_.items():
                cnk_pos = list[cnk[0]]
                models = cnk[1]["p"]
                layers = cnk[1]["t"]
                proprieties = cnk[1]["pr"]
                occ = set()
                bl:list[Block] = []
                for idx in range(len(models)):
                    bl.append(Block(layers[idx], models[idx], layers[idx], proprieties[idx], False if layers[idx] == "water_1" else True))
                    if bl[-1].collides:
                        occ.add(models[idx])
                mesh_vertices, mesh_indices = export_and_load_chunk(models, [TEXTURE_INDICES[layer] for layer in layers])
                generate_chunk_class(cnk_pos, bl, ctx, prog, chunk_prog, mesh_vertices, mesh_indices, TEXTURE_INDICES, chunks)
                generated_chunks.append(cnk_pos)
                #chunks.append(Chunk(list(cnk[0]), None, None, True, bl, False, seed=seed, ctx=ctx, prog=prog, v=cube_v, i=cube_i, tex_mapping=TEXTURE_INDICES, should_render=False))
                #blocks.extend(bl)
                
    if address == '': address = "0.0.0.0:0000"
    a = address.split(":")
    camera=Camera([0,1,0], ctx, prog, text_prog, TEXTURE_INDICES, font_tex, CHARSET, multiplayer, a[0], int(a[1]), window)
    print("Created camera")

    if multiplayer:
        chunks_, gn_chunks = camera.get_world()
        for cnk in chunks_.items():
            cnk_pos = list[cnk[0]]
            models = cnk[1]["p"]
            layers = cnk[1]["t"]
            proprieties = cnk[1]["pr"]
            occ = set()
            bl:list[Block] = []
            for idx in range(len(models)):
                bl.append(Block(layers[idx], models[idx], layers[idx], proprieties[idx], False if layers[idx] == "water_1" else True))
                if bl[-1].collides:
                    occ.add(models[idx])
            mesh_vertices, mesh_indices = export_and_load_chunk(models, [TEXTURE_INDICES[layer] for layer in layers])
            generate_chunk_class(cnk_pos, bl, ctx, prog, chunk_prog, mesh_vertices, mesh_indices, TEXTURE_INDICES, chunks)
            generated_chunks.append(cnk_pos)

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
    last_chunk_activation = 0.0

    #define keys handlers
    change_block = Key(window, glfw.KEY_LEFT_ALT)
    get_block = Key(window, glfw.MOUSE_BUTTON_MIDDLE, True)
    chat_key = Key(window, glfw.KEY_C, toggle=True, only_activate=True)
    esc_key = Key(window, glfw.KEY_ESCAPE, False, True, True)
    chat_exit = Key(window, glfw.KEY_ESCAPE, False, False)
    
    menu_stuff.add_string("FPS: your computer is potato", 0, pos=(-0.9, 0.9), color=(1, 1, 1))

    menu_stuff.add_string("Selected Block: grass", 1, pos=(-0.9, 0.75))

    now_generating = None

    curr_frame = 0

    enable_funky_shaders = False
    prog["enable_funky_shaders"] = enable_funky_shaders

    prev_cnk_pos = None

    window_should_close = render()[-1]

    esc_menu = Menu(ctx, text_prog, gui_prog, bk_prog, font_tex, CHARSET, False, {
        "back_to_game": resume_game,
        "save_and_quit": save_and_quit
    })
    esc_menu.load_layout("esc_screen")

    generate_chunks_time_taken = 0

    bk_vao = ctx.vertex_array(
            prog,
            [],
            None
        )

    worker = ThreadPoolExecutor()

    square_range_lookup:dict = {}

    while not window_should_close:
        if save_quit:
            break
        now=time.time()
        delta = min(max(now - last, 0.0), MAX_FRAME_TIME)
        last=now
        
        rounded_position = list(map(int, np.round(camera.position)))
        cnk_position = [rounded_position[0]//10*10, 0, rounded_position[2]//10*10]

        if prev_cnk_pos != cnk_position:
            curr_cnk = chunk_lookup.get(tuple(cnk_position))
            if curr_cnk is None and chunks:
                curr_cnk = chunks[0]
            prev_cnk_pos = cnk_position

        hit,normal=raycast(camera,curr_cnk.occupied)
        if hit is not None: index=list(curr_cnk.occupied).index(hit)
        else:index = None
        msg_to_snd=""
        if send:
            msg_to_snd=text_buffer
            set_textbuffer("")
        cam_in_block = None
        listed_camera_position = list(map(int, np.round(camera.position)))
        listed_camera_position[1] += 1
        blocks_poss = list(map(lambda x: x.position, blocks))
        
        if listed_camera_position in blocks_poss:
            cam_in_block = blocks[blocks_poss.index(listed_camera_position)]
        else:
            listed_camera_position[1] -= 1
            if listed_camera_position in blocks_poss:
                cam_in_block = blocks[blocks_poss.index(listed_camera_position)]

        if camera.update(window,delta,curr_cnk.occupied,hit,normal,curr_cnk.blocksinstmodel,selected_block,curr_cnk.blocks,index,message_to_send=msg_to_snd,in_block=cam_in_block) == "ban":
            return
        camera.process_keyboard(window,delta,curr_cnk.occupied)
        
        send=False

        if not multiplayer:
            generate_chunks_time_taken = time.time()

            if len(cnkdata) > 0:
                generate_chunk_class(cnkdata[0][0], cnkdata[0][1], cnkdata[0][2], cnkdata[0][3], cnkdata[0][4], cnkdata[0][5], cnkdata[0][6], cnkdata[0][7], cnkdata[0][8])
                cnkdata.pop(0)

            params = (tuple(cnk_position), RENDER_DISTANCE, 10)

            if not params in square_range_lookup:
                sqr = square_range(params[0], params[1], params[2])
                square_range_lookup[params] = sqr
            else:
                sqr = square_range_lookup[params]

            for x, z in sqr:
                chunk_pos = [x, 0, z]
                if chunk_pos in generated_chunks:
                    continue

                generated_chunks.append(chunk_pos)

                worker.submit(generate_chunk_at, chunk_pos, chunks, heightmap, rules, TEXTURE_INDICES, prog, ctx, chunk_prog)

            generate_chunks_time_taken = time.time() - generate_chunks_time_taken

        upate_parameters(
            (0.1, 0.1, 0.12),
            projection.astype('f4').tobytes(),
            camera.get_view().astype('f4').tobytes(),
            (camera.position[0], 50, camera.position[2]),
            camera.position.astype('f4').tobytes(),
            enable_funky_shaders,
            projection.astype('f4').tobytes(),
            camera.get_view().astype('f4').tobytes(),
            (camera.position[0], 50, camera.position[2]),
            camera.position.astype('f4').tobytes(),
            curr_frame
        )

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

        nearby_positions = set()

        for x, z in sqr:
            nearby_positions.add((x, 0, z))

        for old_pos in visible_chunk_positions - nearby_positions:
            old_chunk = chunk_lookup.get(old_pos)
            if old_chunk is not None:
                old_chunk.should_render = False
                old_chunk.is_player_in = False

        for new_pos in nearby_positions:
            new_chunk = chunk_lookup.get(new_pos)
            if new_chunk is None:
                continue
            new_chunk.should_render = True
            new_chunk.is_player_in = new_chunk.position == cnk_position

        visible_chunk_positions = nearby_positions

        if hasattr(camera, "players"):
            camera.players.render()

        cross_prog["color"].value=(1, 1, 1)
        cross_vao.render(moderngl.LINES)
        gui.render()
        if esc_key.is_pressed:
            esc_menu.active(True)
        

        if chat_key.is_pressed:
            menu_stuff.add_string(text_buffer, 3, pos=(-0.9, -0.9), color=(1, 1, 1))
            gui.add(element_id="chat_bk", pos=(0.00, -0.95), size=(2.00, 0.5), color=(0,0,0))
            if chat_exit.is_pressed:
                chat_key.deactivate()
                esc_key.deactivate()
                esc_menu.active(False)
        else:            
            set_textbuffer("")

            menu_stuff.remove_string(3)
            gui.remove("chat_bk")

        if chat_key.is_pressed or esc_key.is_pressed:
            camera.disable(window)

        elif not esc_key.is_pressed and not chat_key.is_pressed:
            camera.enable(window)

        elif esc_key.is_pressed and glfw.get_key(window, glfw.KEY_C) == glfw.PRESS:
            esc_key.pressed = False

        elif chat_key.is_pressed and glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS:
            chat_key.pressed = False

        if not camera.enabled:
            bk_vao.render(mode=moderngl.TRIANGLE_STRIP, vertices=4)

        frame_passed += 1
        if time.time() - last_last >= 1:
            last_last = time.time()
            menu_stuff.update_string(0, f"FPS: {frame_passed}")
            frame_passed = 0

        curr_frame += 1

        text_buffer, send, window_should_close = render()

    if not multiplayer:
        #background.set("titlescreen")
        #background.render()
        ctx.clear()
        menu_stuff.add_string("Saving World...", 5, (0, 0))
        menu_stuff.render()
        #save_path = "saves"
        #worldName = "testSave"
        if worldName in os.listdir(save_path):
            print("found")
        else:
            print("not found")
            os.makedirs(save_path+"/"+worldName)

        all_ = []
        for cnk in chunks:
            blocks_ = []
            for block_ in cnk.get_blocks():
                new_dict = {}
                for i in range(len(block_.proprieties)):
                    new_dict[i] = REVERSE_INTERACT_FUNCTION_CONVERSION[block_.proprieties[i]]
                data = {"position":block_.position, "texture":block_.texture, "proprieties":new_dict}
                blocks_.append(data)
            all_.append({"chunk" : list(cnk.position), "blocks" : blocks_})
            print(list(cnk.position), "saved")

        print("writing data...")
        start = time.time()
        with open(save_path+"/"+worldName+"/"+"data.json", "w") as f:
            json.dump({"data" : all_}, f)

        end = time.time() - start
        sr = end // 60
        s = end % 60
        mr = sr // 60
        m = sr % 60
        h = mr % 60

        print(f"Done!! in h:{h}, m:{m}, s:{s}")

    worker.shutdown()


def load_files(worldName,save_path):
    """Takes a world name and save path and transforms them into models and textures (layers) and block proprieties"""
    gn_cnk = []
    chunks = {}

    with open(save_path+"/"+worldName+"/"+"data.json", "r") as f:
        data = json.loads(f.read())["data"]
        for chunk in data:
            for block in chunk["blocks"]:
                new_dict = {}
                for i in range(len(block["proprieties"])):
                    new_dict[i] = INTERACT_FUNCTION_CONVERSION[block["proprieties"][str(i)]]
                if tuple(chunk["chunk"]) not in chunks:
                    chunks[tuple(chunk["chunk"])] = {"p":[], "t":[], "pr":[]}
                chunks[tuple(chunk["chunk"])]["p"].append(block["position"])
                chunks[tuple(chunk["chunk"])]["t"].append(block["texture"])
                chunks[tuple(chunk["chunk"])]["pr"].append(new_dict)

    return chunks, gn_cnk

multi = False
def multiplayer():
    global multi
    multi = True

load = False
def load_world():
    global load
    load = True

erase = False
def erase_world():
    global erase
    erase = True

if __name__=="__main__":

    TEXTURE_INDICES, OPPOSITE_TEXTURE_INDICES, available_blocks, ctx, prog, color_prog, cross_prog, gui_prog, text_prog, chunk_prog, bk_prog, window = init_all(char_callback, key_callback)

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
    ALLOFGUI.append(menu_stuff)
    #background = Background(ctx)
    #background.add("title screen", "assets/backgrounds/title_screen.png")
    #background.set("title screen")

    main_screen = Menu(ctx, text_prog, gui_prog, bk_prog, font_tex, CHARSET, True, {"load_world": load_world, "erase_world": erase_world, "multiplayer": multiplayer})
    main_screen.load_layout("main_screen")

    mouse_pressed_last = False

    multi = False
    load = False
    erase = False
    save_quit = False

    while True:
        glfw.set_window_should_close(window, False)
        window_should_close = False
        save_quit = False
        multi = False
        erase = False
        load = False
        while not window_should_close and not erase and not load:
            
            """
            mouse_now = glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS

            if mouse_now and not mouse_pressed_last:
                mx, my = glfw.get_cursor_pos(window)
                gui.handle_click(mx, my, WIDTH, HEIGHT)

            mouse_pressed_last = mouse_now
            """
            
            text_buffer, send, window_should_close = render()
        
        main_screen.active(False)
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
                while True and not window_should_close:
                    menu_stuff.update_string(0, text_buffer, pos=(-0.5, 0))
                    if send:
                        send = False
                        break

                    text_buffer, send, window_should_close = render()
                
                playernaim = text_buffer
                set_textbuffer("")

                menu_stuff.update_string(1, "Input your password:")
                while True and not window_should_close:
                    menu_stuff.update_string(0, text_buffer, pos=(-0.5, 0))
                    if send:
                        send = False
                        break

                    text_buffer, send, window_should_close = render()
                
                password = text_buffer
                set_textbuffer("")

                with open("data.txt", "w") as f:
                    f.write(playernaim)
                    f.write("\n")
                    f.write(password)
            
            menu_stuff.update_string(1, "Input the server IPv4 address:")
            while True and not window_should_close:
                
                menu_stuff.update_string(0, text_buffer, pos=(-0.5, 0))
                if send:
                    send = False
                    break

                text_buffer, send, window_should_close = render()
        
        menu_stuff.clear()

        if not window_should_close:
            set_textbuffer("")
            print("Entering main")
            main(chunks,worldName,save_path, multi, text_buffer, gen_cnk)
            break
        else:
            break

print("succesfully exited game")

glfw.terminate()

print("terminated GLFW window")
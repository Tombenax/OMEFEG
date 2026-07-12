import glfw
import moderngl
import numpy as np
from pyrr import Matrix44
import time
import math
from PIL import Image, ImageDraw, ImageFont
from utils import generate_terrain, playsound, notification, get_username_and_uuid
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
from ControllerHandler import ControllerHandler
import ast


WIDTH = 1280
HEIGHT = 720

generation_queue = []
generating = False
waiting_for_thread_finish = False

# -------------------------
# WORLD SHADERS (with texture array)
# -------------------------

VERTEX_SHADER = """
#version 330
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in mat4 instance_model;
in int instance_layer;

uniform mat4 projection;
uniform mat4 view;

out vec3 v_normal;
out vec3 v_fragPos;
out vec2 v_uv;
flat out int v_layer;

void main() {
    vec4 worldPos = instance_model * vec4(in_position,1.0);
    gl_Position = projection * view * worldPos;

    v_fragPos = worldPos.xyz;
    v_normal = mat3(transpose(inverse(instance_model))) * in_normal;
    v_uv = in_uv;
    v_layer = instance_layer;
}
"""

FRAGMENT_SHADER = """
#version 330

in vec3 v_normal;
in vec3 v_fragPos;
in vec2 v_uv;
flat in int v_layer;

out vec4 fragColor;

uniform sampler2DArray atlasArray;
uniform vec3 lightPos;
uniform vec3 viewPos;

void main() {
    // Sample full RGBA texture
    vec4 tex = texture(atlasArray, vec3(v_uv, v_layer));

    // Discard fully transparent pixels (fixes black background)
    if (tex.a < 0.1)
        discard;

    vec3 color = tex.rgb;
    vec3 norm = normalize(v_normal);

    // Lighting
    vec3 lightDir = normalize(lightPos - v_fragPos);
    float diff = max(dot(norm, lightDir), 0.0);

    vec3 ambient = 0.4 * color;
    vec3 diffuse = diff * color;

    vec3 viewDir = normalize(viewPos - v_fragPos);
    vec3 reflectDir = reflect(-lightDir, norm);
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 16.0);

    // Final color with alpha preserved
    fragColor = vec4(ambient + diffuse + spec, tex.a);
}
"""

CHUNK_VERTEX_SHADER="""
#version 330
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in mat4 instance_model;
in int instance_layer;

uniform mat4 projection;
uniform mat4 view;

out vec3 v_normal;
out vec3 v_fragPos;
out vec2 v_uv;
flat out int v_layer;

void main() {
    vec4 worldPos = instance_model * vec4(in_position,1.0);
    gl_Position = projection * view * worldPos;

    v_fragPos = worldPos.xyz;
    v_normal = mat3(transpose(inverse(instance_model))) * in_normal;
    v_uv = in_uv;
    v_layer = instance_layer;
}
"""

CHUNK_FRAGMENT_SHADER="""
#version 330

in vec3 v_normal;
in vec3 v_fragPos;
in vec2 v_uv;
flat in int v_layer;

out vec4 fragColor;

uniform sampler2DArray atlasArray;
uniform vec3 lightPos;
uniform vec3 viewPos;

void main() {
    // Sample full RGBA texture
    vec4 tex = texture(atlasArray, vec3(v_uv, v_layer));

    // Discard fully transparent pixels (fixes black background)
    if (tex.a < 0.1)
        discard;

    vec3 color = tex.rgb;
    vec3 norm = normalize(v_normal);

    // Lighting
    vec3 lightDir = normalize(lightPos - v_fragPos);
    float diff = max(dot(norm, lightDir), 0.0);

    vec3 ambient = 0.4 * color;
    vec3 diffuse = diff * color;

    vec3 viewDir = normalize(viewPos - v_fragPos);
    vec3 reflectDir = reflect(-lightDir, norm);
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 16.0);

    // Final color with alpha preserved
    fragColor = vec4(ambient + diffuse + spec, tex.a);
}
"""

# -------------------------
# SIMPLE COLOR SHADER
# -------------------------

COLOR_VERTEX = """
#version 330
in vec3 in_pos;
uniform mat4 mvp;
void main(){
    gl_Position = mvp * vec4(in_pos,1.0);
}
"""

COLOR_FRAGMENT = """
#version 330
uniform vec3 color;
out vec4 fragColor;
void main(){
    fragColor = vec4(color,1.0);
}
"""

# -------------------------
# CROSSHAIR SHADER
# -------------------------

CROSS_VERTEX = """
#version 330
in vec2 in_pos;
void main(){
    gl_Position = vec4(in_pos,0.0,1.0);
}
"""

CROSS_FRAGMENT = """
#version 330
uniform vec3 color;
out vec4 fragColor;
void main(){
    fragColor = vec4(color,1.0);
}
"""

# -------------------------
# INSTANCED TEXT SHADERS
# -------------------------
TEXT_VERTEX = """
#version 330

in vec2 in_pos;
in vec2 in_uv;

in vec2 instance_pos;
in vec2 instance_scale;
in vec4 instance_uv;
in vec3 instance_color;

out vec2 v_uv;
out vec3 v_color;

void main() {
    vec2 pos = in_pos * instance_scale + instance_pos;
    gl_Position = vec4(pos, 0.0, 1.0);

    v_uv = mix(instance_uv.xy, instance_uv.zw, in_uv);
    v_color = instance_color;
}
"""

TEXT_FRAGMENT = """
#version 330
in vec2 v_uv;
in vec3 v_color;
out vec4 fragColor;

uniform sampler2D textTexture;

void main() {
    vec4 sampled = texture(textTexture, v_uv);
    if (sampled.a < 0.1) discard;
    fragColor = vec4(v_color,1.0) * sampled;
}
"""

GUI_VERTEX = """
#version 330

in vec2 in_pos;

in vec2 instance_pos;
in vec2 instance_size;
in vec3 instance_color;

out vec2 v_size;
out vec3 v_color;
out vec2 v_local;

void main() {
    vec2 pos = in_pos * instance_size + instance_pos;
    gl_Position = vec4(pos, 0.0, 1.0);

    v_color = instance_color;
    v_local = in_pos;
    v_size = instance_size;
}
"""

GUI_FRAGMENT = """
#version 330

in vec3 v_color;
in vec2 v_local;
in vec2 v_size;

out vec4 fragColor;

uniform float outline_thickness;

void main() {
    vec2 scaled = v_local * v_size;

    float edge = min(
        min(abs(scaled.x - v_size.x * 0.5), abs(scaled.x + v_size.x * 0.5)),
        min(abs(scaled.y - v_size.y * 0.5), abs(scaled.y + v_size.y * 0.5))
    );

    if (edge < outline_thickness) {
        fragColor = vec4(1.0);
    } else {
        fragColor = vec4(v_color, 1.0);
    }
}
"""

BACKGROUND_VERTEX = """
#version 330
in vec2 in_pos;
out vec2 v_uv;

void main() {
    v_uv = (in_pos + 1.0) * 0.5; // map [-1,1] -> [0,1]
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

BACKGROUND_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 fragColor;

uniform sampler2D bg_texture;

void main() {
    fragColor = texture(bg_texture, v_uv);
}
"""

# -------------------------
# CAMERA
# -------------------------

class Camera:
    def __init__(self, pos, ctx, prog, text_prog, TEXTURE_INDICES, font_texture, charset:str, multiplayer:bool=False, serveraddress=None, serverport=None, window=None, controller=False, controller_handler:ControllerHandler=None):
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

        self.rotate_speed = 7

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

        self.controller = controller
        self.controller_handler = controller_handler

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
                print(propriety)
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
        
        if self.controller:
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
        #TODO:FUCK
        if not self.enabled:
            return

        if self.controller:
            move = np.zeros(3, dtype='f4')

            right = np.cross(self.front, self.up)
            right /= np.linalg.norm(right)

            # WASD (no Y movement)
            if "-LY" in self.updated_controller:
                move += self.front
            if "LY" in self.updated_controller:
                move -= self.front
            if "-LX" in self.updated_controller:
                move -= right
            if "LX" in self.updated_controller:
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
            if (self.on_ground or self.is_in_water) and "A" in self.updated_controller:
                self.vel_y = self.jump_strength
                self.on_ground = False
        else:
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
    def update(self, window, delta, occupied, hit, normal, block, selected_block, blocks, block_index, message_to_send:str, in_block:tuple):
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
        self.updated_controller = self.controller_handler.update()
        if self.controller:
            if block_index is not None:
                # PLACE
                if not self.placed:
                    if "R2" in self.updated_controller:
                        if hit and normal is not None:
                            blocks[block_index].proprieties[0](
                                block, normal, occupied, hit, blocks, selected_block, self.position
                            )
                            self.placed = True
                            blocks_placed_positions.append([(int(hit[0]), int(hit[1]), int(hit[2])), selected_block, '{0:destroy, 1:place}'])
                else:
                    if not "R2" in self.updated_controller:
                        self.placed = False

                # DESTROY
                if not self.destroyed:
                    if "L2" in self.updated_controller:
                        if hit:
                            blocks[block_index].proprieties[1](
                                block, normal, occupied, hit, blocks, selected_block, self.position
                            )
                            self.destroyed = True
                            blocks_broken_positions.append([(int(hit[0]), int(hit[1]), int(hit[2])), selected_block, '{0:destroy, 1:place}'])
                else:
                    if not "L2" in self.updated_controller:
                        self.destroyed = False
            #also process yaw and pitch
            xoffset = 0
            yoffset = 0
            #print(self.updated_controller)
            if "-RX" in self.updated_controller:
                xoffset -= self.rotate_speed * self.sensitivity
            elif "RX" in self.updated_controller:
                xoffset = self.rotate_speed * self.sensitivity
            if "RY" in self.updated_controller:
                yoffset -= self.rotate_speed * self.sensitivity
            elif "-RY" in self.updated_controller:
                yoffset = self.rotate_speed * self.sensitivity

            self.yaw += xoffset
            self.pitch += yoffset
            self.pitch = max(-89, min(89, self.pitch))

            front = np.array([
                math.cos(math.radians(self.yaw)) * math.cos(math.radians(self.pitch)),
                math.sin(math.radians(self.pitch)),
                math.sin(math.radians(self.yaw)) * math.cos(math.radians(self.pitch))
            ], dtype='f4')

            self.front = front / np.linalg.norm(front)
        else:
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


def string_to_fixed_number(s, digits=10):
    # Create a hash (SHA-256 is common and stable)
    h = hashlib.sha256(s.encode()).hexdigest()
    
    # Convert hex string to integer
    num = int(h, 16)
    
    # Limit to a fixed number of digits
    return num % (10 ** digits)

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
            transformed.append(t[:3])

        # write vertices
        for v in transformed:
            obj.append(f"v {v[0]} {v[1]} {v[2]}")

        # normals (unchanged per cube)
        for n in base_normals:
            obj.append(f"vn {n[0]} {n[1]} {n[2]}")

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

                obj.append(f"vt {u} {v}")

                uv_indices.append(vt_offset)
                vt_offset += 1

            # triangle 1
            obj.append(
                f"f "
                f"{v0[0]+v_offset}/{uv_indices[0]}/{v0[2]+vn_offset} "
                f"{v1[0]+v_offset}/{uv_indices[1]}/{v1[2]+vn_offset} "
                f"{v2[0]+v_offset}/{uv_indices[2]}/{v2[2]+vn_offset}"
            )

            # triangle 2
            obj.append(
                f"f "
                f"{v0[0]+v_offset}/{uv_indices[0]}/{v0[2]+vn_offset} "
                f"{v2[0]+v_offset}/{uv_indices[2]}/{v2[2]+vn_offset} "
                f"{v3[0]+v_offset}/{uv_indices[3]}/{v3[2]+vn_offset}"
            )

        v_offset += len(base_vertices)
        vn_offset += len(base_normals)

    global chunk_prog

    # -------------------------------------------------
    # OBJ parsing
    # -------------------------------------------------
    global_vertices = []
    global_normals = []

    block_vertex_lists = []
    block_normal_lists = []

    current_block_vertices = []
    current_block_normals = []

    for line in obj:

        # -------------------------------------------------
        # Vertex
        # -------------------------------------------------
        if line.startswith("v "):

            parts = line.split()

            global_vertices.append([
                float(parts[1]),
                float(parts[2]),
                float(parts[3])
            ])

        # -------------------------------------------------
        # Normal
        # -------------------------------------------------
        elif line.startswith("vn "):

            parts = line.split()

            global_normals.append([
                float(parts[1]),
                float(parts[2]),
                float(parts[3])
            ])

        # -------------------------------------------------
        # New block group
        # -------------------------------------------------
        elif line.startswith("g block_"):

            if current_block_vertices:
                block_vertex_lists.append(current_block_vertices)
                block_normal_lists.append(current_block_normals)

            current_block_vertices = []
            current_block_normals = []

        # -------------------------------------------------
        # Face
        # -------------------------------------------------
        elif line.startswith("f "):

            parts = line.strip().split()[1:]

            for p in parts:

                vals = p.split("/")

                v_idx = int(vals[0]) - 1
                vn_idx = int(vals[2]) - 1 if len(vals) > 2 else -1

                if 0 <= v_idx < len(global_vertices):
                    current_block_vertices.append(global_vertices[v_idx])

                if 0 <= vn_idx < len(global_normals):
                    current_block_normals.append(global_normals[vn_idx])

    # -------------------------------------------------
    # Append last block
    # -------------------------------------------------
    if current_block_vertices:
        block_vertex_lists.append(current_block_vertices)
        block_normal_lists.append(current_block_normals)

    # -------------------------------------------------
    # Compute positions
    # -------------------------------------------------
    positions = []

    for verts in block_vertex_lists:

        if not verts:
            continue

        pos = np.mean(verts, axis=0)

        rounded_pos = [
            round(pos[0]) + offsett[0],
            round(pos[1]) + offsett[1],
            round(pos[2]) + offsett[2]
        ]

        positions.append(rounded_pos)

    # -------------------------------------------------
    # Texture layers
    # -------------------------------------------------
    layers = []

    inv = OPPOSITE_TEXTURE_INDICES

    for tex_name in _layers:
        layers.append(inv[int(tex_name)])

    # -------------------------------------------------
    # Return chunk
    v, i = load_obj_for_moderngl_no_file(obj)

    return v, i

v, i, pos, tex, ogterrain = None, None, None, None, None

generate_new_chunk = None

def generate_chunk_at(offsett:tuple, generated_chunks, chunks, generation_queue, heightmap, rules, TEXTURE_INDICES, OPPOSITE_TEXTURE_INDICES, block:InstancedModel, thread_part):
    global generating, waiting_for_thread_finish, generate_new_chunk, v, i, pos, tex, ogterrain
    generating = True
    _offsett = list(offsett)
    if _offsett[0] > 0:
        _offsett[0] -= abs(_offsett[0])
    elif _offsett[0] < 0:
        _offsett[0] += abs(_offsett[0])
    if _offsett[2] > 0:
        _offsett[2] -= abs(_offsett[2])
    elif _offsett[2] < 0:
        _offsett[2] += abs(_offsett[2])
    _offsett = tuple(_offsett)

    def generate_blocks_and_return_blocks(offsett, heightmap, rules, chunks:list[Chunk], tex_mapping:dict[str:int], opp_tex_mapping:dict[int:str], block:InstancedModel): 
            global v, i, pos, tex, ogterrain
            new_chunk = Chunk(offsett, heightmap, rules)
            result = new_chunk.get_blocks()
            new_textures = list(map(lambda x:tex_mapping[x], result[2]))
            new_positions = result[0]
            for i in result[1]:
                new_textures.extend(list(map(lambda x:tex_mapping[x], i["textures"])))
                new_positions.extend(i["positions"])
            vi, pos, tex, ogterrain = export_and_load_chunk(new_positions, new_textures, tuple(offsett), opp_tex_mapping), new_positions, new_textures, (new_positions, new_chunk.get_blocks()[1], list(map(lambda x:opp_tex_mapping[x], new_textures)))
            v, i = vi
    if thread_part:
        v, i, pos, tex, ogterrain = None, None, None, None, None

        generate_new_chunk = threading.Thread(target=generate_blocks_and_return_blocks, args=(offsett, heightmap, rules, chunks, TEXTURE_INDICES, OPPOSITE_TEXTURE_INDICES, block), daemon=True)
        generate_new_chunk.start()

    waiting_for_thread_finish = True
    if not generate_new_chunk.is_alive():
        new_chunk = Chunk(
            offsett,
            None,
            None,
            True,
            pos,
            tex,
            True,
            InstancedModel(
                ctx,
                chunk_prog,
                v,
                i,
                {"texture":0},
                True
            ),
            len(block.models)
        )
        chunks.append(new_chunk)
        new_chunk.instancedmodel.add_instances([_offsett], ["texture"])
        generation_queue.append(("chunk_done", 0))
        generation_queue.append(("blocks", ogterrain))
        #generation_queue.append(("disable_chunk", new_chunk.block_indices))
        waiting_for_thread_finish = False
        generated_chunks.append(offsett)
        generating = False

use_blocks = False
def generation_queue_while_loop(block:InstancedModel, occupied, blocks):
    global generation_queue, use_blocks
    while not len(generation_queue) == 0:
        msg, data = generation_queue.pop(0)

        if msg == "chunk_done":
            use_blocks = False

        elif msg == "chunk_done_1":
            use_blocks = True

        elif msg == "blocks":
            if not use_blocks:
                ground, trees, blocks_types = data

                positions = []
                textures = []

                for g, btype in zip(ground, blocks_types):
                    pos = tuple(g)
                    if pos not in occupied:
                        new_block = Block(btype, g, btype, {0:place, 1:destroy}, block)
                        if not new_block in blocks:
                            blocks.append(new_block)
                            if btype != "water_1":
                                occupied.add(pos)
            
                positions += ground
                textures += blocks_types
                
                for tree in trees:
                    for pos, tex in zip(tree["positions"], tree["textures"]):
                        tpos = tuple(pos)
                        if tpos not in occupied:
                            new_block = Block(tex, pos, tex, {0:place, 1:destroy}, block)
                            if not new_block in blocks:    
                                blocks.append(new_block)
                                positions.append(pos)
                                textures.append(tex)
                                if tex != "water_1":
                                    occupied.add(tpos)
                
                
                #block.add_instances(positions, textures, [[math.radians(i), math.radians(i), math.radians(i)] for i in range(len(positions))])
                block.add_instances(positions, textures, active=False)
            else:
                ground, blocks_types, active = data

                for g, btype in zip(ground, blocks_types):
                    pos = tuple(g)
                    if pos not in occupied:
                        blocks.append(Block(btype, g, btype, {0:place, 1:destroy}, block))
                        if btype != "water_1":
                            occupied.add(pos)

                block.add_instances(ground, blocks_types, active=active)
                use_blocks = False
        
        elif msg == "disable_chunk":
            block.disable_instances(data)


# -------------------------
# MAIN
# -------------------------

def main(models,layers,proprieties,worldName,save_path,multiplayer:bool=False,address="", gen_cnk:list[tuple]=[(0, 0, 0)]):
    global window,ctx,gui,menu_stuff,text_buffer,send,generating,chunk_prog,block

    generated_chunks = gen_cnk
    chunks:list[Chunk] = []

    frame_passed = 0
    selected_block = "grass"
    available_blocks = []

    glfw.set_input_mode(window,glfw.CURSOR,glfw.CURSOR_DISABLED)

    prog=ctx.program(vertex_shader=VERTEX_SHADER,fragment_shader=FRAGMENT_SHADER)
    color_prog=ctx.program(vertex_shader=COLOR_VERTEX,fragment_shader=COLOR_FRAGMENT)
    cross_prog=ctx.program(vertex_shader=CROSS_VERTEX,fragment_shader=CROSS_FRAGMENT)
    text_prog["textTexture"] = 0

    # Load multiple textures
    #read textures
    textures = []
    TEXTURE_INDICES = {}
    directory = 'assets/textures'
    for idx, filename in enumerate(os.listdir(directory)):
        if filename.endswith('.png'):
            textures.append(Image.open(directory+"/"+filename))
            TEXTURE_INDICES[filename.removesuffix(".png")] = idx
            available_blocks.append(filename.removesuffix(".png"))

    OPPOSITE_TEXTURE_INDICES = {}
    for texture_number, texture_name in enumerate(TEXTURE_INDICES):
        OPPOSITE_TEXTURE_INDICES[texture_number] = texture_name

    tex_array = load_texture_array(ctx, textures)
    data = tex_array.read(alignment=1)
    width = tex_array.width
    height = tex_array.height
    tex_layers = tex_array.layers
    components = 4
    arr = np.frombuffer(data, dtype=np.uint8)
    arr = arr.reshape((tex_layers, height, width, components))
    tile_cols = math.ceil(math.sqrt(tex_layers))
    tile_rows = math.ceil(tex_layers / tile_cols)

    tile_w = width
    tile_h = height

    out = Image.new("RGBA", (tile_cols * tile_w, tile_rows * tile_h))

    for i in range(tex_layers):
        img = Image.fromarray(arr[i], mode="RGBA").transpose(Image.FLIP_TOP_BOTTOM)

        x = (i % tile_cols) * tile_w
        y = (i // tile_cols) * tile_h

        out.paste(img, (x, y))

    out.save("chunks/texture.png")

    tex_array.use(location=0)
    prog['atlasArray'] = 0
    chunk_tex = load_texture_array(ctx, [out])
    chunk_tex.use(location=1)
    chunk_prog['atlasArray'] = 1

    occupied=set()
    vertices, indices = load_obj_for_moderngl("assets/models/block.obj")
    block=InstancedModel(ctx,prog,vertices,indices,TEXTURE_INDICES)
    blocks = []

    heightmap = PerlinNoiseFactory(dimension=2, octaves=1, seed=string_to_fixed_number("IfYOOOUFIND OUTABOUTTHESEEDIMKILLINGYOU", 256))
    #ilands: waterlevel = 0
    #lakes = 3
    #larger islands = 1
    rules = {"structures":[{"chance":970, "name":"oak_small_tree"}, {"chance":930, "name":"oak_medium_tree"}, {"chance":999, "name":"temple"}], "water":{"level":1, "depth":5}, "terrain_height":5}

    if not multiplayer:
        if models == None or layers == None:
            new_chunk = Chunk((0, 0, 0), heightmap, rules)
            chunks.append(new_chunk)
            result = new_chunk.get_blocks()

            ground = result[0]
            trees = result[1]
            blocks_types = result[2]

            for g, btype in zip(ground, blocks_types):
                if tuple(g) not in occupied:
                    blocks.append(Block(btype, g, btype, {0:place, 1:destroy}, block, add_instances=True))
                    if btype != "water_1":
                        occupied.add(tuple(g))

            for tree in trees:
                for pos, tex in zip(tree["positions"], tree["textures"]):
                    if tuple(pos) not in occupied:
                        blocks.append(Block(tex, pos, tex, {0:place, 1:destroy}, block, add_instances=True))
                        if tex != "water_1":
                            occupied.add(tuple(pos))

            generated_chunks = [(0, 0, 0)]
            #block.export_chunk("chunks/chunk.obj", "chunks/texture.png")
        else:
            for idx in range(len(models)):
                occupied.add(models[idx])
                chunks.append(Chunk((0, 0, 0), None, None, True, models, textures))
                blocks.append(Block(layers[idx], list(models[idx]), layers[idx], proprieties[idx], block))
                generation_queue.append(("chunk_done_1", 0))
                generation_queue.append(("blocks", (models, layers, True)))

    test_controller = ControllerHandler(0)
    test_controller.one_shot = {"DU", "DD", "DL", "DR", "R1", "L1", "R3", "L3"}
    camera=Camera([0,1,0], ctx, prog, text_prog, TEXTURE_INDICES, font_tex, CHARSET, multiplayer, address, 5000, window, controller=True, controller_handler=test_controller)
    if multiplayer:
        models, layers, proprieties = camera.get_world()
        print("finished")
        for idx in range(len(models)):
            occupied.add(models[idx])
            blocks.append(Block(layers[idx], list(models[idx]), layers[idx], proprieties[idx], block))

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

    while not glfw.window_should_close(window):
        now=time.time()
        delta=now-last
        last=now
        place_blocks = threading.Thread(target=(generation_queue_while_loop), args=(block, occupied, blocks), daemon=True)
        place_blocks.start()
        glfw.poll_events()
        hit,normal=raycast(camera,occupied)
        if hit is not None: index=list(occupied).index(hit)
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

        if camera.update(window,delta,occupied,hit,normal,block,selected_block,blocks,index,message_to_send=msg_to_snd,in_block=cam_in_block) == "ban":
            return
        camera.process_keyboard(window,delta,occupied)
        send=False

        rounded_position = tuple(map(int, np.round(camera.position)))
        cnk_position = (rounded_position[0]//10*10, 0, rounded_position[2]//10*10)


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
        chunk_prog["projection"].write(projection.astype('f4').tobytes())
        chunk_prog["view"].write(camera.get_view().astype('f4').tobytes())
        chunk_prog["lightPos"].value = (camera.position[0], 50, camera.position[2])
        chunk_prog["viewPos"].write(camera.position.astype('f4').tobytes())

        if hit:
            draw_hovered_cube(ctx, color_prog, projection, camera, hit)
        if not test_controller:
            if change_block.is_pressed:
                try:
                    selected_block = available_blocks[available_blocks.index(selected_block)+1]
                except:
                    selected_block = available_blocks[0]
                
                menu_stuff.update_string(1, f"Selected Block: {selected_block.replace('_', ' ')}", pos=(-0.9, 0.75))
        else:
            if "R1" in camera.updated_controller:
                if available_blocks.index(selected_block)+1 != len(available_blocks):
                    selected_block = available_blocks[available_blocks.index(selected_block)+1]
                else:
                    selected_block = available_blocks[0]

                menu_stuff.update_string(1, f"Selected Block: {selected_block.replace('_', ' ')}", pos=(-0.9, 0.75))
                
        if not test_controller:
            if get_block.is_pressed:
                for idx, model in enumerate(block.models):
                    pos = tuple(map(int, model[3][:3]))
                    if pos == hit:
                        selected_block = available_blocks[block.layers[idx]]
                        break

                menu_stuff.update_string(1, f"Selected Block: {selected_block.replace('_', ' ')}", pos=(-0.9, 0.75))
        else:
            if "R3" in camera.updated_controller:
                for idx, model in enumerate(block.models):
                    pos = tuple(map(int, model[3][:3]))
                    if pos == hit:
                        selected_block = available_blocks[block.layers[idx]]
                        break

                menu_stuff.update_string(1, f"Selected Block: {selected_block.replace('_', ' ')}", pos=(-0.9, 0.75))
        
        if test_controller:
            if "GUIDE" in camera.updated_controller:
                glfw.set_window_should_close(window, True)


        for cnk in chunks:
            cnk.is_player_in = False
            if cnk.position == cnk_position:
                cnk.is_player_in = True
            
            if cnk.is_player_in:
                if not cnk.is_enabled:
                    block.enable_instances(cnk.block_indices)
                    cnk.is_enabled = True
            else:
                if cnk.is_enabled:
                    block.disable_instances(cnk.block_indices)
                    cnk.is_enabled = False
                cnk.render()
        
        block.render()

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

    if not multiplayer:
        ctx.disable(moderngl.DEPTH_TEST)
        background.set("titlescreen")
        background.render()
        ctx.enable(moderngl.DEPTH_TEST)
        menu_stuff.add_string("Saving World...", 5, (0, 0))
        menu_stuff.render()
        #save_path = "saves"
        #worldName = "testSave"
        if worldName in os.listdir(save_path):
            print("found")
        else:
            print("not found")
            os.makedirs(save_path+"/"+worldName)
        
        with open(save_path+"/"+worldName+"/"+"positions.txt", "w") as f:
            for block_ in block.models:
                f.write(str(block_[3][:3]))
                f.write("\n")

        with open(save_path+"/"+worldName+"/"+"textures.txt", "w") as f:
            for block_ in block.layers:
                f.write(str(OPPOSITE_TEXTURE_INDICES[block_]))
                f.write("\n")

        with open(save_path+"/"+worldName+"/"+"proprieties.txt", "w") as f:
            for block_ in blocks:
                new_dict = {}
                for i in range(len(block_.proprieties)):
                    new_dict[i] = REVERSE_INTERACT_FUNCTION_CONVERSION[block_.proprieties[i]]
                block_.proprieties = new_dict

                f.write(str(block_.proprieties))
                f.write("\n")
        
        with open(save_path+"/"+worldName+"/"+"gen_cnk.txt", "w") as f:
            f.write(json.dumps(generated_chunks))
    
    glfw.terminate()
    #block.export_chunk("chunks/chunk.obj", "chunks/texture.png")

def load_files(worldName,save_path):
    """Takes a world name and save path and transforms them into models and textures (layers) and block proprieties"""
    models = []
    layers = []
    proprieties = []
    gn_cnk = []

    with open(save_path+"/"+worldName+"/"+"positions.txt", "r") as f:
        for model in f.readlines():
            models.append(model.strip())

    with open(save_path+"/"+worldName+"/"+"textures.txt", "r") as f:
        for texture in f.readlines():
            layers.append(texture.strip())

    with open(save_path+"/"+worldName+"/"+"proprieties.txt", "r") as f:
        for proprieties_ in f.readlines():
            proprieties.append(ast.literal_eval(proprieties_.strip()))
    
    with open(save_path+"/"+worldName+"/"+"gen_cnk.txt", "r") as f:
        gn_cnk = json.loads(f.read())
    
    #transform str models into tuples
    for idx, model in enumerate(models):
        models[idx] = tuple(map(int, model.replace("[", "").replace("]", "").removesuffix(".").split(". ")))

    return models,layers,proprieties,gn_cnk

if __name__=="__main__":
    glfw.init()
    window=glfw.create_window(WIDTH,HEIGHT,"Voxel Engine",None,None)
    glfw.make_context_current(window)
    icon = Image.open("assets/icon.png").convert("RGBA")
    width, height = icon.size
    pixels = np.array(icon, dtype=np.uint8)
    glfw.set_window_icon(window, 1, [(width, height, pixels)])
    ctx=moderngl.create_context()
    glfw.set_char_callback(window, char_callback)
    glfw.set_key_callback(window, key_callback)
    ctx.enable(moderngl.DEPTH_TEST)
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

    gui_prog = ctx.program(vertex_shader=GUI_VERTEX, fragment_shader=GUI_FRAGMENT)
    text_prog=ctx.program(vertex_shader=TEXT_VERTEX, fragment_shader=TEXT_FRAGMENT)
    chunk_prog = ctx.program(vertex_shader=CHUNK_VERTEX_SHADER,fragment_shader=CHUNK_FRAGMENT_SHADER)
    gui_prog['outline_thickness'].value = 0.02
    

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
    models,layers,proprieties,gen_cnk = None, None, None, None

    if load:
        models,layers,proprieties,gen_cnk = load_files(worldName,save_path)
        
        #turn proprieties from strings into functions
        for idx, propriety in enumerate(proprieties):
            new_dict = {}
            for i in range(0, 2):
                new_dict[i] = INTERACT_FUNCTION_CONVERSION[propriety[i]]
            proprieties[idx] = new_dict

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
        main(models,layers,proprieties,worldName,save_path, multi, text_buffer, gen_cnk)
        text_buffer = ""
    else:
        glfw.terminate()
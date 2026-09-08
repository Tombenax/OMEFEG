import time
from typing import Any, Callable

import json
from pyrr import Matrix44

from Number import Number
import glfw
import moderngl
from PIL import Image
import numpy as np
import os
import random
from utils import distance


import math

glfw.init()

WIDTH, HEIGHT = 1280, 720

ATLAS = Image.open("assets/textures/texture.png")

ATLAS_W, ATLAS_H = ATLAS.size

TEXTURE_W, TEXTURE_H = 64, 64

TEXTURES_X, TEXTURES_Y = ATLAS_W // TEXTURE_W, ATLAS_H // TEXTURE_H

TEXTURES = (ATLAS_W // TEXTURE_W) * (ATLAS_H // TEXTURE_H)

CHAR = Image.open("assets/textures/charset.png")

CHAR_W, CHAR_H = CHAR.size

CHR_W, CHR_H = 16, 16

CHRS = (CHAR_W / CHR_W) * (CHAR_H / CHR_H)

ITEMS = Image.open("assets/textures/Items.png")

ITEMS_W, ITEMS_H = ITEMS.size

ITEM_W, ITEM_H = 16, 16

ITEMS_X, ITEMS_Y = ITEMS_W // ITEM_W, ITEMS_H // ITEM_H

ITEMS_COUNT = (ITEMS_W / ITEM_W) * (ITEMS_H / ITEM_H)




class Render:
    def __init__(self, init_function:Callable, update_function:Callable):
        self.init_function = init_function
        self.update_function = update_function

        self.window = glfw.create_window(WIDTH, HEIGHT, "OMEFEG", None, None)
        glfw.make_context_current(self.window)

        glfw.set_input_mode(self.window,glfw.CURSOR,glfw.CURSOR_DISABLED)

        icon = Image.open("assets/icon.png").convert("RGBA")
        width, height = icon.size
        pixels = np.array(icon, dtype=np.uint8)

        glfw.set_window_icon(self.window, 1, [(width, height, pixels)])

        self.ctx = moderngl.create_context()

        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        self.load_shaders("OPENGL shaders", os.listdir("OPENGL shaders"))

        self.create_programs()

        self.load_textures()

        self.init_function(self)

        self.update()

    
    def load_texture_array(self, atlas:Image.Image, atlas_h, teture_h, atlas_w, texture_w, show=False):
        new_atlas = atlas.copy()

        for i in range(int(atlas_h / teture_h)):
            Image.Image.paste(new_atlas, atlas.crop((0, i*teture_h, (atlas_w / texture_w) * texture_w, i*teture_h+teture_h)).transpose(Image.FLIP_TOP_BOTTOM), (0, i*teture_h))
            if show:
                atlas.crop((0, i*teture_h, (atlas_w / texture_w) * texture_w, i*teture_h+teture_h)).transpose(Image.FLIP_TOP_BOTTOM).show("a")
        if show:
            new_atlas.show("a")
        width, height = atlas.size
        depth = 1
        data = b''.join([new_atlas.convert('RGBA').tobytes()])
        tex_array = self.ctx.texture_array((width, height, depth), 4, data)
        tex_array.filter = (moderngl.NEAREST, moderngl.NEAREST)
        return tex_array


    def load_textures(self):
        self.blocks_texture = self.load_texture_array(ATLAS, ATLAS_H, TEXTURE_H, ATLAS_W, TEXTURE_W)
        self.blocks_texture.use(location=0)

        self.chars_texture = self.load_texture_array(CHAR, CHAR_H, CHR_H, CHAR_W, CHR_W)
        self.chars_texture.use(location=1)


        self.items_texture = self.load_texture_array(ITEMS, ITEMS_H, ITEM_H, ITEMS_W, ITEM_W)
        self.items_texture.use(location=2)



    def create_programs(self):
        for shader_name, shaders in self.shaders.items():
            setattr(self, shader_name+"_program", self.ctx.program(*shaders))


    def load_shader(self, shader_path):
        with open(shader_path, "r") as f:
            readed = f.read()
        return readed

    def load_shaders(self, shader_base_path, shader_names):
        self.shaders = {}
        for shader in shader_names:
            self.shaders[shader] = [
                self.load_shader(os.path.join(shader_base_path, shader, "vertex.glsl")),
                self.load_shader(os.path.join(shader_base_path, shader, "fragment.glsl"))
                ]

    def update(self):
        last = time.time()
        while not glfw.window_should_close(self.window):
            now = time.time()
            self.dt = now-last
            last = now

            glfw.poll_events()

            self.update_function(self)

            glfw.swap_buffers(self.window)

        glfw.terminate()

class InstancedModel:
    def __init__(self, **kwargs:dict[str, Any]):
        """
        aruments:
            ctx: moderngl context
            program: moderngl program,
            indices: model's indices
            vertices: model's vertices
        """

        self.ctx = kwargs["ctx"]
        self.program = kwargs["program"]

        self.indices = kwargs["indices"]
        self.vertices = kwargs["vertices"]

        self.vbo = self.ctx.buffer(self.vertices.tobytes())
        self.ibo = self.ctx.buffer(self.indices.tobytes())

        self.instance_buffer = self.ctx.buffer(reserve=64 * 1024)
        self.layer_buffer = self.ctx.buffer(reserve=4 * 1024)

        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (
                    self.vbo,
                    '3f 3f 2f',
                    'in_position',
                    'in_normal',
                    'in_uv'
                ),
                (
                    self.instance_buffer,
                    '16f/i',
                    'instance_model'
                ),
                (
                    self.layer_buffer,
                    '1i/i',
                    'instance_layer'
                ),
            ],
            self.ibo
        )

        self.instances = np.zeros((0, 4, 4), dtype="f4")
        self.tex_insta = np.zeros((0,), dtype="f4")

    def add_instances(self, positions:list[list[Number]], textures:list[int] | np.ndarray, rotations:list[list[Number]]=[]):

        if not isinstance(positions, np.ndarray):
            positions = np.asarray(positions, dtype='f4')

        if positions.ndim == 1:
            positions = positions.reshape(1, 3)

        new_models = np.eye(4, dtype='f4').reshape(1, 4, 4)
        new_models = np.repeat(new_models, len(positions), axis=0)
        new_models[:, 3, 0] = positions[:, 0]
        new_models[:, 3, 1] = positions[:, 1]
        new_models[:, 3, 2] = positions[:, 2]

        for idx, rotation in enumerate(rotations):
            x, y, z = [
                Matrix44.from_x_rotation(math.radians(rotation[0])),
                Matrix44.from_y_rotation(math.radians(rotation[1])),
                Matrix44.from_z_rotation(math.radians(rotation[2]))
            ]

            new_models[idx] = x @ y @ z @ new_models[idx]

        self.instances = np.concatenate((self.instances, new_models))

        self.tex_insta = np.concatenate((self.tex_insta, np.array(textures, dtype="f4")))

        self.instance_buffer.orphan(len(self.instances.tobytes()))
        self.instance_buffer.write(self.instances.tobytes())

        layer_bytes = self.tex_insta.astype('i4').tobytes()
        self.layer_buffer.orphan(len(layer_bytes))
        self.layer_buffer.write(layer_bytes)

    def remove_instance(self, i):
        """Remove an instance at the given indx"""
        self.instances = np.delete(self.instances, i, axis=0)
        self.tex_insta = np.delete(self.tex_insta, i, axis=0)

        self._upload()

    def remove_instances(self, positions):
        """Remove instances whose model translations match the given positions."""
        if len(positions) == 0:
            return 0

        positions = np.asarray(positions, dtype="f4")
        if positions.ndim == 1:
            positions = positions.reshape(1, 3)

        requested = {tuple(position) for position in positions}
        instance_positions = self.instances[:, 3, :3]
        remove_mask = np.array(
            [tuple(position) in requested for position in instance_positions],
            dtype=bool,
        )
        removed = int(np.count_nonzero(remove_mask))

        if removed:
            self.instances = self.instances[~remove_mask]
            self.tex_insta = self.tex_insta[~remove_mask]
            self._upload()

        return removed

    def _upload(self):
        self.instance_buffer.orphan(len(self.instances.tobytes()))
        self.instance_buffer.write(self.instances.tobytes())

        layer_bytes = self.tex_insta.astype('i4').tobytes()
        self.layer_buffer.orphan(len(layer_bytes))
        self.layer_buffer.write(layer_bytes)

    def _upload(self):
        self.instance_buffer.orphan(len(self.instances.tobytes()))
        self.instance_buffer.write(self.instances.tobytes())

        layer_bytes = self.tex_insta.astype('i4').tobytes()
        self.layer_buffer.orphan(len(layer_bytes))
        self.layer_buffer.write(layer_bytes)

    def render(self):
        if len(self.instances) == 0: return
        self.vao.render(instances=len(self.instances))


class Model:
    def __init__(self, renderer:Render):
        self.instanedmodels:dict[str, InstancedModel] = {}
        self.renderer = renderer

    def add_model(self, identifier:str, **kwargs:dict[str, Any]):
        """
        args:
            program: moderngl program
            vertices: model's vertices
            indices: model's indices
        """
        self.instanedmodels[identifier] = InstancedModel(
            ctx=self.renderer.ctx,
            program=kwargs["program"],
            indices = kwargs["indices"],
            vertices = kwargs["vertices"]
        )

    
    def add_instances(self, positions:list[list[Number]], textures:list[int], model_identifier:str, rotations:list[list[Number]]=[]):
        self.instanedmodels[model_identifier].add_instances(positions, textures, rotations)

    def remove_instance(self, index:Number, model_identifier:str):
        """Remove an instance at position from the specified model. Returns True if removed, False if not found."""
        return self.instanedmodels[model_identifier].remove_instance(index)

    def remove_instances(self, positions:list[list[Number]], model_identifier:str):
        return self.instanedmodels[model_identifier].remove_instances(positions)

    def render_one(self, identifier:str):
        self.instanedmodels[identifier].render()

    def render(self):
        for identifier in self.instanedmodels.keys():
            self.render_one(identifier)

class Camera:
    def __init__(self, position, render: Render):
        self.render = render

        self.position = np.array(position, dtype=float)

        self.start_pos = self.position.copy()

        self.yaw = 0.0
        self.pitch = 0.0

        self.eye_height = 1.8

        self.last_x = 0
        self.last_y = 0

        self.dx = 0
        self.dy = 0

        self.sensitivity = 0.1
        self.speed = 5

        self.gravity = 20

        self.fly = False

        self.do = False

        self.max_jumps = 1

        self.jump_strenght = 10

        self.jumps = 0

        self.trust_me = True

        self.front = np.array([1, 0, 0], dtype='f4')
        self.right = np.array([0, 0, -1], dtype='f4')
        self.up = np.array([0, 1, 0], dtype='f4')

        self.vel_y = 0.0
        self.on_ground = False

        self.eye_pos = self.position + np.array(
            [0, self.eye_height, 0],
            dtype=float
        )

        self.view = Matrix44.look_at(
            self.eye_pos,
            self.eye_pos + self.front,
            self.up
        )

    def cursor_move(self, w, x, y):
        self.dx = x - self.last_x
        self.dy = y - self.last_y

        if self.fly and self.do:
            if self.up[1] > 0:
                self.dx *= 1
            else:
                self.dx *= -1

        self.yaw += self.dx * self.sensitivity
        self.pitch -= self.dy * self.sensitivity

        self.last_x = x
        self.last_y = y

    def update(self, occupied):
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)

        # Forward direction
        front = np.array([
            math.cos(yaw) * math.cos(pitch),
            math.sin(pitch),
            math.sin(yaw) * math.cos(pitch)
        ], dtype='f4')

        front /= np.linalg.norm(front)

        # Right direction
        right = np.array([
            math.sin(yaw),
            0.0,
            -math.cos(yaw)
        ], dtype='f4')

        go = np.array([
            math.cos(yaw),
            math.sin(pitch),
            math.sin(yaw)
        ], dtype='f4')

        

        right /= np.linalg.norm(right)
        go /= np.linalg.norm(go)

        # Up direction
        up = np.cross(right, front)
        up /= np.linalg.norm(up)

        self.front = front
        self.right = right
        self.go = go
        self.up = -up

        # --------------------
        # Movement
        # --------------------

        move = np.zeros(3, dtype=float)


        self.sprint = glfw.get_key(self.render.window, glfw.KEY_LEFT_CONTROL)
        self.fly = glfw.get_key(self.render.window, glfw.KEY_F)

        self.speed = (
            13 if self.sprint else 30 if self.fly else 7
        )

        if glfw.get_key(self.render.window, glfw.KEY_R) == glfw.PRESS:
            self.position = self.start_pos.copy()
        

        if glfw.get_key(self.render.window, glfw.KEY_W) == glfw.PRESS:
            move += (self.go if not self.fly else self.front) * self.render.dt * self.speed

        if glfw.get_key(self.render.window, glfw.KEY_S) == glfw.PRESS:
            move -= (self.go if not self.fly else self.front) * self.render.dt * self.speed

        if glfw.get_key(self.render.window, glfw.KEY_A) == glfw.PRESS:
            move += self.right * self.render.dt * self.speed

        if glfw.get_key(self.render.window, glfw.KEY_D) == glfw.PRESS:
            move -= self.right * self.render.dt * self.speed

        # Don't move vertically
        if not self.fly:
            move[1] = 0

        if self.on_ground:
            self.jumps = 0
            self.trust_me = True

        self.vel_y -= self.gravity * self.render.dt

        if glfw.get_key(self.render.window, glfw.KEY_SPACE) == glfw.PRESS and (self.on_ground or self.jumps < self.max_jumps) and self.trust_me:
            self.vel_y = self.jump_strenght 
            self.jumps += 1
            self.trust_me = False

        if glfw.get_key(self.render.window, glfw.KEY_SPACE) != glfw.PRESS: self.trust_me = True

        dy = self.vel_y * self.render.dt

        if self.fly:
            dy = 0
            self.vel_y = 0

        move[1] += dy

        #collision
        self.try_move(move, occupied)

        # --------------------
        # View matrix
        # --------------------

        self.eye_pos = self.position + np.array(
            [0, self.eye_height, 0],
            dtype=float
        )

        self.view = Matrix44.look_at(
            self.eye_pos,
            self.eye_pos + self.front,
            self.up
        )

    def collides(self, new_pos, occupied):
        thing = np.round(new_pos)
        return tuple(thing) in occupied

    def collides_h(self, new_pos, occupied, height=2):
        a_pos = new_pos.copy()
        for h in range(height):
            if self.collides(a_pos, occupied):
                return True
            a_pos[1] += 1

        return False

    def try_move(self, new_position, occupied):
        self.position[0] += new_position[0]
        if self.collides_h(self.position, occupied):
            # print("colliding x")
            self.position[0] -= new_position[0]

        self.position[2] += new_position[2]
        if self.collides_h(self.position, occupied):
            # print("colliding z")
            self.position[2] -= new_position[2]

        self.position[1] += new_position[1]
        if self.collides_h(self.position, occupied):
            # print("colliding y")
            self.position[1] -= new_position[1]
            self.vel_y = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

        

        
def load_obj(file_path:str):
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

    return [np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')]

CUBE_MODEL_INFO = load_obj("assets/models/block.obj")

CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890:!? "

class InstancedText:
    def __init__(self, **kwargs):
        """
        args:
            ctx: moderngl context
            program: moderngl program
            charset: charset
        """

        self.ctx = kwargs["ctx"]
        self.program = kwargs["program"]
        self.charset_lookup = {}
        for idx, key in enumerate(kwargs["charset"]):
            self.charset_lookup[key] = idx

        #quad facing X-
        self.vertices = np.array([
            # position              # normal          # uv
            0.0, 0.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 0.0,
            0.0, 1.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 1.0,
            0.0, 1.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 1.0,

            0.0, 1.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 1.0,
            0.0, 0.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 0.0,
            0.0, 0.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 0.0,
        ], dtype="f4")



        self.indices = np.array([
            0, 1, 2,

            3, 4, 5
        ], dtype="i4")


        self.vbo = self.ctx.buffer(self.vertices.tobytes())
        self.ibo = self.ctx.buffer(self.indices.tobytes())

        self.instance_buffer = self.ctx.buffer(reserve=64 * 1024)
        self.layer_buffer = self.ctx.buffer(reserve=4 * 1024)

        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (
                    self.vbo,
                    '3f 3f 2f',
                    'in_position',
                    'in_normal',
                    'in_uv'
                ),
                (
                    self.instance_buffer,
                    '16f/i',
                    'instance_model'
                ),
                (
                    self.layer_buffer,
                    '1i/i',
                    'instance_layer'
                ),
            ],
            self.ibo
        )

        self.instances = np.zeros((0, 4, 4), dtype="f4")
        self.tex_insta = np.zeros((0,), dtype="f4")

        self.texts = {}
        self._text_entries = []

    def _upload_text_instances(self):
        self.instance_buffer.orphan(max(self.instances.nbytes, 1))
        if self.instances.size:
            self.instance_buffer.write(self.instances.tobytes())

        layer_bytes = self.tex_insta.astype("i4").tobytes()
        self.layer_buffer.orphan(max(len(layer_bytes), 1))
        if layer_bytes:
            self.layer_buffer.write(layer_bytes)

    def _rebuild_text_instances(self):
        instances = []
        textures = []

        for entry in self._text_entries:
            text, position = entry["text"], entry["position"]
            for character_index, character in enumerate(text.upper()):
                model = np.eye(4, dtype="f4")
                model[3, 0] = position[0]
                model[3, 1] = position[1]
                model[3, 2] = position[2] + character_index
                instances.append(model)
                textures.append(self.charset_lookup[character])

        self.instances = np.asarray(instances, dtype="f4").reshape((-1, 4, 4))
        self.tex_insta = np.asarray(textures, dtype="f4")
        self._upload_text_instances()

    def add_texts(self, texts, positions, identifiers=None):
        if len(texts) != len(positions):
            raise ValueError("texts and positions must have the same length")

        if identifiers is None:
            identifiers = [None] * len(texts)
        elif len(identifiers) != len(texts):
            raise ValueError("identifiers must match the number of texts")

        for text, position, identifier in zip(texts, positions, identifiers):
            if len(position) != 3:
                raise ValueError("text positions must be [x, y, z]")
            if identifier is not None and identifier in self.texts:
                raise ValueError(f"text identifier already exists: {identifier}")

            entry = {
                "text": text,
                "position": list(position),
                "identifier": identifier,
            }
            self._text_entries.append(entry)
            if identifier is not None:
                self.texts[identifier] = entry

        self._rebuild_text_instances()

    def update_text(self, identifier: str, text=None, position=None):
        if identifier not in self.texts:
            raise KeyError(f"unknown text identifier: {identifier}")

        entry = self.texts[identifier]
        if text is not None:
            entry["text"] = text
        if position is not None:
            if len(position) != 3:
                raise ValueError("text positions must be [x, y, z]")
            entry["position"] = list(position)

        self._rebuild_text_instances()

    def remove_text(self, identifier: str):
        if identifier not in self.texts:
            return False

        entry = self.texts.pop(identifier)
        self._text_entries.remove(entry)
        self._rebuild_text_instances()
        return True
            

    def render(self):
        if len(self.instances) == 0: return
        self.vao.render(instances=len(self.instances))


class Collectible:
    def __init__(self, render, **kwargs):
        """
        args:
            ctx: moderngl context
            program: moderngl program
        """
        #quad facing X-
        self.vertices = np.array([
            # position              # normal          # uv
            0.0, 0.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 0.0,
            0.0, 1.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 1.0,
            0.0, 1.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 1.0,

            0.0, 1.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 1.0,
            0.0, 0.0, 1.0,         -1.0, 0.0, 0.0,   1.0, 0.0,
            0.0, 0.0, 0.0,         -1.0, 0.0, 0.0,   0.0, 0.0,
        ], dtype="f4")

        self.indices = np.array([
            0, 1, 2,

            3, 4, 5
        ], dtype="i4")

        self.program = kwargs["program"]
        self.ctx = kwargs["ctx"]

        self.vbo = self.ctx.buffer(self.vertices.tobytes())
        self.ibo = self.ctx.buffer(self.indices.tobytes())

        self.instance_buffer = self.ctx.buffer(reserve=64 * 1024)
        self.layer_buffer = self.ctx.buffer(reserve=4 * 1024)

        self.render_ = render

        self.vao = self.ctx.vertex_array(
            self.program,
            [
                (
                    self.vbo,
                    '3f 3f 2f',
                    'in_position',
                    'in_normal',
                    'in_uv'
                ),
                (
                    self.instance_buffer,
                    '16f/i',
                    'instance_model'
                ),
                (
                    self.layer_buffer,
                    '1i/i',
                    'instance_layer'
                ),
            ],
            self.ibo
        )

        self.instances = np.zeros((0, 4, 4), dtype="f4")
        self.tex_insta = np.zeros((0,), dtype="f4")
        self.callbacks = []

    def add_collectibles(self, positions:list[list[Number]], textures:list[int], on_collect:list[callable]):
        self.callbacks.extend(on_collect)
        
        if not isinstance(positions, np.ndarray):
            positions = np.asarray(positions, dtype='f4')

        if positions.ndim == 1:
            positions = positions.reshape(1, 3)

        new_models = np.eye(4, dtype='f4').reshape(1, 4, 4)
        new_models = np.repeat(new_models, len(positions), axis=0)
        new_models[:, 3, 0] = positions[:, 0]
        new_models[:, 3, 1] = positions[:, 1]
        new_models[:, 3, 2] = positions[:, 2]

        self.instances = np.concatenate((self.instances, new_models))

        self.tex_insta = np.concatenate((self.tex_insta, np.array(textures, dtype="f4")))

        self.instance_buffer.orphan(len(self.instances.tobytes()))
        self.instance_buffer.write(self.instances.tobytes())

        layer_bytes = self.tex_insta.astype('i4').tobytes()
        self.layer_buffer.orphan(len(layer_bytes))
        self.layer_buffer.write(layer_bytes)

    def update(self, player_position:list[Number]):
        for i, instance in enumerate(self.instances):
            a = list(instance[3][:3])

            if distance(a, player_position) < 3:
                self.instances = np.delete(self.instances, i, axis=0)
                self.tex_insta = np.delete(self.tex_insta, i, axis=0)
                self.callbacks[i]()
                continue

            x = Matrix44.from_x_rotation(self.render_.dt)
            y = Matrix44.from_y_rotation(self.render_.dt)
            z = Matrix44.from_z_rotation(self.render_.dt)

            self.instances[i] = (x @ y @ z @ instance).astype("f4")

        self.instance_buffer.orphan(len(self.instances.tobytes()))
        self.instance_buffer.write(self.instances.tobytes())

        layer_bytes = self.tex_insta.astype('i4').tobytes()
        self.layer_buffer.orphan(len(layer_bytes))
        self.layer_buffer.write(layer_bytes)

    def render(self):
        if len(self.instances) == 0: return
        self.vao.render(instances=len(self.instances))

class HUDText(InstancedText):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.screen_size = kwargs.get("screen_size", (WIDTH, HEIGHT))

        self.program["atlasArray"] = kwargs.get("texture_unit", 1)
        self.program["screenSize"].value = self.screen_size
        self.program["TEXTURE_W"] = kwargs.get("texture_width", CHR_W)
        self.program["TEXTURE_H"] = kwargs.get("texture_height", CHR_H)
        self.program["ATLAS_W"] = kwargs.get("atlas_width", CHAR_W)
        self.program["ATLAS_H"] = kwargs.get("atlas_height", CHAR_H)

    def add_texts(self, texts, positions, identifiers=None):
        hud_positions = []
        for position in positions:
            if len(position) != 2:
                raise ValueError("HUD text positions must be [x, y] pixel coordinates")
            hud_positions.append([position[0], position[1], 0])

        super().add_texts(texts, hud_positions, identifiers)

    def update_text(self, identifier: str, text=None, position=None):
        hud_position = None
        if position is not None:
            if len(position) != 2:
                raise ValueError("HUD text positions must be [x, y] pixel coordinates")
            hud_position = [position[0], position[1], 0]

        super().update_text(identifier, text, hud_position)

    def render(self):
        if len(self.instances) == 0:
            return

        self.ctx.disable(moderngl.DEPTH_TEST)
        try:
            super().render()
        finally:
            self.ctx.enable(moderngl.DEPTH_TEST)


if __name__ == "__main__":
    def init(render:Render):
        GRASS = 0

        render.camera = Camera([0, 0, 0], render)

        glfw.set_cursor_pos_callback(render.window, render.camera.cursor_move)

        FOV = 60
        
        PROJECTION = np.array(Matrix44.perspective_projection(FOV, WIDTH/HEIGHT, 0.1, 1000), dtype='f4')

        for name in render.text_program:
            print(
                name,
                render.text_program[name]
            )


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

        render.MODEL = Model(render)

        render.MODEL.add_model("block", program=render.blocks_program, vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1])
       # render.MODEL.add_instances([[10, 1.8, 0]], [GRASS], "block")

        render.text = InstancedText(ctx=render.ctx, program=render.text_program, charset=CHARSET)
        print(render.text_program)


        render.text.add_texts(["A"], [[5, 1.8, 0]])
        print("instances:", render.text.instances)
        print("textures:", render.text.tex_insta)
        print("instance buffer:", render.text.instance_buffer.size)
        print("layer buffer:", render.text.layer_buffer.size)


    def update(render:Render):
        render.ctx.clear(0, 0, 0)
        render.camera.update(set())

        render.blocks_program["view"].write(render.camera.view.astype("f4").tobytes())
        render.blocks_program["lightPos"].value = (0, 0, 0)
        render.blocks_program["viewPos"].write(render.camera.position.astype('f4').tobytes())

        render.text_program["view"].write(render.camera.view.astype("f4").tobytes())
        render.text_program["lightPos"].value = (0, 0, 0)
        render.text_program["viewPos"].write(render.camera.position.astype('f4').tobytes())


        render.MODEL.render()
        render.text.render()

    render = Render(init, update)
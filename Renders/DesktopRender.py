import glfw
import moderngl
from PIL import Image
import numpy as np
import os
import math

WIDTH=1280
HEIGHT=720

window=None
ctx=None

text_buffer = ""
send = False

available_blocks = []

prog=None
color_prog=None
cross_prog=None
gui_prog=None
text_prog=None
chunk_prog=None

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

VERTEX_SHADER, FRAGMENT_SHADER, COLOR_VERTEX, COLOR_FRAGMENT, CROSS_VERTEX, CROSS_FRAGMENT, GUI_VERTEX, GUI_FRAGMENT, TEXT_VERTEX, TEXT_FRAGMENT, CHUNK_VERTEX_SHADER, CHUNK_FRAGMENT_SHADER = [None] * 12

def load_shaders():
    global VERTEX_SHADER, FRAGMENT_SHADER, COLOR_VERTEX, COLOR_FRAGMENT, CROSS_VERTEX, CROSS_FRAGMENT, GUI_VERTEX, GUI_FRAGMENT, TEXT_VERTEX, TEXT_FRAGMENT, CHUNK_VERTEX_SHADER, CHUNK_FRAGMENT_SHADER

    with open("shaders/vertex_shader.glsl", "r") as f:
        VERTEX_SHADER = f.read()
    
    with open("shaders/fragment_shader.glsl", "r") as f:
        FRAGMENT_SHADER = f.read()
    
    with open("shaders/color_vertex.glsl", "r") as f:
        COLOR_VERTEX = f.read()
    
    with open("shaders/color_fragment.glsl", "r") as f:
        COLOR_FRAGMENT = f.read()
    
    with open("shaders/cross_vertex.glsl", "r") as f:
        CROSS_VERTEX = f.read()
    
    with open("shaders/cross_fragment.glsl", "r") as f:
        CROSS_FRAGMENT = f.read()
    
    with open("shaders/gui_vertex.glsl", "r") as f: 
        GUI_VERTEX = f.read()
    
    with open("shaders/gui_fragment.glsl", "r") as f:
        GUI_FRAGMENT = f.read()
    
    with open("shaders/text_vertex.glsl", "r") as f:
        TEXT_VERTEX = f.read()
    
    with open("shaders/text_fragment.glsl", "r") as f:
        TEXT_FRAGMENT = f.read()
    
    with open("shaders/chunk_vertex.glsl", "r") as f:
        CHUNK_VERTEX_SHADER = f.read()
    
    with open("shaders/chunk_fragment.glsl", "r") as f:
        CHUNK_FRAGMENT_SHADER = f.read()

def load_texture_array(ctx:moderngl.Context, textures):
    width, height = textures[0].size
    depth = len(textures)
    data = b''.join([img.convert('RGBA').transpose(Image.FLIP_TOP_BOTTOM).tobytes() for img in textures])
    tex_array = ctx.texture_array((width, height, depth), 4, data)
    tex_array.filter = (moderngl.NEAREST, moderngl.NEAREST)
    #tex_array.build_mipmaps()
    return tex_array

def load_textures():
    #Load multiple textures
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

def init_all():
    global window,ctx,prog,color_prog,cross_prog,gui_prog,text_prog,chunk_prog
    glfw.init()
    window=glfw.create_window(WIDTH,HEIGHT,"OMEFEG",None,None)
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

    glfw.set_input_mode(window,glfw.CURSOR,glfw.CURSOR_DISABLED)

    prog=ctx.program(vertex_shader=VERTEX_SHADER,fragment_shader=FRAGMENT_SHADER)
    color_prog=ctx.program(vertex_shader=COLOR_VERTEX,fragment_shader=COLOR_FRAGMENT)
    cross_prog=ctx.program(vertex_shader=CROSS_VERTEX,fragment_shader=CROSS_FRAGMENT)
    text_prog["textTexture"] = 0
    gui_prog = ctx.program(vertex_shader=GUI_VERTEX, fragment_shader=GUI_FRAGMENT)
    text_prog=ctx.program(vertex_shader=TEXT_VERTEX, fragment_shader=TEXT_FRAGMENT)
    chunk_prog = ctx.program(vertex_shader=CHUNK_VERTEX_SHADER,fragment_shader=CHUNK_FRAGMENT_SHADER)
    gui_prog['outline_thickness'].value = 0.02

    load_textures()
    load_shaders()

init_all()

from InstancedModel import InstancedModel

OBJECTSTORENDER:list[InstancedModel] = []

def render():
    for model in OBJECTSTORENDER:
        model.render()
import json

from ursina import *
from ursina.prefabs.editor_camera import EditorCamera
import os
from PIL import Image

app = Ursina()

texture_folder = 'assets/textures'
atlas_path = os.path.join(texture_folder, 'texture.png')
atlas_tile_size = 64
block_texture_ids = {
    "birch_leave": 0,
    "birch_log": 1,
    "cobblestone": 2,
    "dirt": 3,
    "grass": 4,
    "oak_leave": 5,
    "oak_log": 6,
    "oak_planks": 7,
    "sand": 8,
    "stone": 9,
    "water": 10,
    "bench": 12,
    "unbrekable": 18,
}
textures = list(block_texture_ids)

with Image.open(atlas_path) as atlas:
    atlas = atlas.convert("RGBA")
    atlas_columns = atlas.width // atlas_tile_size
    if atlas.width % atlas_tile_size or atlas.height % atlas_tile_size:
        raise ValueError(f"{atlas_path} dimensions must be multiples of {atlas_tile_size}")

    texture_previews = {}
    for name, texture_id in block_texture_ids.items():
        column = texture_id % atlas_columns
        row = texture_id // atlas_columns
        tile = atlas.crop((
            column * atlas_tile_size,
            row * atlas_tile_size,
            (column + 1) * atlas_tile_size,
            (row + 1) * atlas_tile_size,
        ))
        texture_previews[name] = Texture(tile)

current_texture_index = textures.index("grass")
blocks = []
menu_open = False
texture_buttons = []

class Voxel(Button):
    def __init__(self, position=(0,0,0), texture_name="grass"):
        super().__init__(
            parent=scene,
            position=position,
            model='assets/models/block.obj',
            origin_y=0.5,
            texture=texture_previews[texture_name],
            color=color.white,
            scale=1
        )
        self.texture_name = texture_name
        blocks.append(self)

    def input(self, key):
        global current_texture_index

        if self.hovered and not menu_open:
            # PLACE BLOCK
            if key == 'left mouse down':
                tex = textures[current_texture_index]
                Voxel(position=self.position + mouse.normal, texture_name=tex)

            # DELETE BLOCK
            if key == 'right mouse down':
                if self in blocks:
                    blocks.remove(self)
                destroy(self)

Voxel()
blocks.pop(0)

# Editor camera
EditorCamera(rotation_speed=200, panning_speed=10)

# ======================
# TEXTURE MENU FUNCTIONS
# ======================

def open_texture_menu():
    global texture_buttons, menu_open
    menu_open = True

    for i, tex in enumerate(textures):
        btn = Button(
            parent=camera.ui,
            texture=texture_previews[tex],
            scale=0.1,
            position=(-0.4 + (i % 8)*0.12, 0.4 - (i // 8)*0.12),
            color=color.white,
            model="block.obj"
        )

        def select_texture(t=tex):
            global current_texture_index, menu_open
            current_texture_index = textures.index(t)
            print("Selected texture:", t)
            close_texture_menu()

        btn.on_click = select_texture
        texture_buttons.append(btn)

def close_texture_menu():
    global texture_buttons, menu_open
    for b in texture_buttons:
        destroy(b)
    texture_buttons.clear()
    menu_open = False

# ======================
# SAVE FUNCTION
# ======================

def save_structure(filename="worldgeneration/structures/newStructure.json"):
    data = {"blocks":[]}
    for block in blocks:
        x, y, z = block.position
        data["blocks"].append([int(x), int(y-1), int(z), block.texture_name.removesuffix('.png')])

    with open(filename, "w") as f:
        json.dump(data, f)


# ======================
# INPUT HANDLER
# ======================

def input(key):
    global current_texture_index, menu_open

    if key == 'k':
        save_structure()
        print("Saved!")

    # Open / close menu
    if key == 'f':
        if not menu_open:
            open_texture_menu()
        else:
            close_texture_menu()

    # Optional: ALT quick cycle
    if key == "left alt" and not menu_open:
        current_texture_index = (current_texture_index + 1) % len(textures)
        print("Selected texture:", textures[current_texture_index])

app.run()
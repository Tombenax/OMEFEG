from ursina import *
from ursina.prefabs.editor_camera import EditorCamera
import os

app = Ursina()

# Load textures dynamically
texture_folder = 'assets/textures'
textures = [f for f in os.listdir(texture_folder) if f.endswith(('.png', '.jpg'))]

current_texture_index = 0
blocks = []
menu_open = False
texture_buttons = []

class Voxel(Button):
    def __init__(self, position=(0,0,0), texture_name="grass.png"):
        super().__init__(
            parent=scene,
            position=position,
            model='assets/models/block.obj',
            origin_y=0.5,
            texture=f"{texture_folder}/{texture_name}",
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

# Dummy voxel (your original trick)
Voxel(texture_name="use to texture.png")
blocks.pop(0)
structure = []
with open("structure.txt", "r") as s:
    structure.extend(s.readlines())

for i in range(0, len(structure), 4):
    Voxel((int(structure[i].strip()), int(structure[i+1].strip()), int(structure[i+2].strip())), structure[i+3].strip())


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
            texture=f"{texture_folder}/{tex}",
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

def save_structure(filename="structure.txt"):
    with open(filename, "w") as f:
        for block in blocks:
            x, y, z = block.position
            f.write(f"{int(x)}\n{int(y-1)}\n{int(z)}\n{block.texture_name.removesuffix('.png')}\n")

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
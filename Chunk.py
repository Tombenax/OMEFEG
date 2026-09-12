from random import Random

from sympy import numer
from utils import generate_terrain, export_and_load_chunk
from Block import Block
from allBlocks import *
import os
import sys

# True on PC, False on Android phones. Override with OMEFEG_DESKTOP=0/1.
DESKTOP = os.environ.get("OMEFEG_DESKTOP")
if DESKTOP is None:
    DESKTOP = not hasattr(sys, "getandroidapilevel")
else:
    DESKTOP = DESKTOP == "1"

if DESKTOP:
    from Render import *
else:
    from MobileRender import *
from lists import *
from Number import Number
from typing import Callable, Any

class Chunk:
    def __init__(self, render, position:list[Number], seed:Random, heightmap:Callable, biomes_map:Callable, rules:dict[Any, Any], **kwargs):
        self.blocks = BlocksList()

        self.position = position

        self.render = render

        if not kwargs.get("empty"):
            terrain = generate_terrain(height_map=heightmap, biomes_map=biomes_map, offsett=position, rules_=rules, random_seed=seed, sin_world=True if kwargs.get("sin_world") else False, biomes=True if kwargs.get("biomes") else False)

            self.blocks.extend(terrain)

        self.model:Model = Model(self.render)
        self.model.add_model("block", vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1])

        if not kwargs.get("empty"):
            self.model.add_instances(self.blocks.positions, self.blocks.textures, "block")

            vertices, indices = export_and_load_chunk(self.blocks.positions, self.blocks.textures, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y)

            self.model.add_model("dummy", vertices = vertices, indices = indices, is_chunk_dummy=True)

            self.model.add_instances([[0, 0, 0]], [0], "dummy")

        self.is_player_in = False

        self.prev_is_player_in = False

    def _update_dummy(self):

        vertices, indices = export_and_load_chunk(self.blocks.positions, self.blocks.textures, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y)

        self.model.remove_instance(0, "dummy")

        self.model.add_model("dummy", vertices = vertices, indices = indices, is_chunk_dummy=True)

        self.model.add_instances([[0, 0, 0]], [0], "dummy")

    def render_mesh(self):
        if self.is_player_in != self.prev_is_player_in:
            self.prev_is_player_in = self.is_player_in

        if self.is_player_in and self.prev_is_player_in:
            self._update_dummy()

        if self.is_player_in: self.model.render_one("block")
        else:
            if "dummy" in self.model.instanedmodels:
                self.model.render_one("dummy")
            else:
                self._update_dummy()
                self.model.render_one("dummy")

    def _update_blocks(self):
        self.model.add_instances(self.blocks.positions, self.blocks.textures, "block")

    def get_y_at(self, x:Number, z:Number) -> Number:
        return self.get_block_pos_at(x, z)[1] + 1

    def get_block_pos_at(self, x:Number, z:Number) -> list[numer]:
        arr = np.array(self.blocks.positions)
        return list(arr[(arr[:, 0] == x) & (arr[:, 2] == z)][0])

    def get_block_at(self, position:list[Number]):
        try:
            return self.blocks.positions_blocks[tuple(position)]
        except:
            return None
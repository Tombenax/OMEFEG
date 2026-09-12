from numpy import empty

from Chunk import Chunk
from Block import Block
import os
import sys

# True on PC, False on Android phones. Override with OMEFEG_DESKTOP=0/1.
DESKTOP = os.environ.get("OMEFEG_DESKTOP")
if DESKTOP is None:
    DESKTOP = not hasattr(sys, "getandroidapilevel")
else:
    DESKTOP = DESKTOP == "1"

if DESKTOP:
    from Render import CUBE_MODEL_INFO
else:
    from MobileRender import CUBE_MODEL_INFO
from allBlocks import *
from lists import *
from Number import Number
from utils import export_and_load_chunk, square_range
if DESKTOP:
    from Render import *
else:
    from MobileRender import *

class HeightMap:
    def __init__(self, noise, width, depth, N, scale=10):
        self.noise = noise
        self.width = width
        self.depth = depth
        self.N = N
        self.scale = scale

        self._values = {}
        self._thresholds = []

        self._generate_initial()

    def _noise(self, x, z):
        """Get and cache a noise value."""
        key = (x, z)

        if key not in self._values:
            self._values[key] = self.noise(
                (x / self.scale) + 0.1,
                (z / self.scale) + 0.1
            )

        return self._values[key]

    def _generate_initial(self):
        """Generate the initial area."""
        for x in range(self.width):
            for z in range(self.depth):
                self._noise(x, z)

        self._calculate_thresholds()

    def _calculate_thresholds(self):
        """Recalculate percentile thresholds."""
        values = sorted(self._values.values())

        if not values:
            self._thresholds = []
            return

        self._thresholds = [
            values[int(len(values) * i / self.N)]
            for i in range(1, self.N)
        ]

    def _get_height(self, x, z):
        """Convert a noise value into a discrete height."""
        value = self._noise(x, z)

        height = 0

        while (
            height < len(self._thresholds)
            and value >= self._thresholds[height]
        ):
            height += 1

        return height

    def _expand(self, x, z):
        """Generate enough data to include x, z."""
        old_width = self.width
        old_depth = self.depth

        new_width = max(self.width, x + 1)
        new_depth = max(self.depth, z + 1)

        # Generate newly required values - only the new regions
        for new_x in range(old_width, new_width):
            for new_z in range(new_depth):
                self._noise(new_x, new_z)

        for new_z in range(old_depth, new_depth):
            for new_x in range(old_width):
                self._noise(new_x, new_z)

        self.width = new_width
        self.depth = new_depth
        self._calculate_thresholds()

    def __getitem__(self, position):
        """
        Get height using:

            heightmap[x, z]

        Automatically expands the heightmap if necessary.
        """
        x, z = position

        if x < 0 or z < 0:
            x = abs(x)
            z = abs(z)

        if x >= self.width or z >= self.depth:
            self._expand(x, z)

        return self._get_height(x, z)

class World:
    def __init__(self, render, seed, heightmap, rules, **kwargs):
        self.render = render
        self.seed = seed
        self.heightmap = heightmap
        self.rules = rules
        self.kwargs = kwargs
        self.biomes_map = HeightMap(heightmap, 10, 10, 3, 10)

        self.chunks:ChunksList = ChunksList()

    def generate_chunk_at(self, position:list[Number], **kwargs):
        chunk = Chunk(self.render, position, self.seed, self.heightmap, self.biomes_map, self.rules, **self.kwargs, empty=True if kwargs.get("empty") else False)
        self.chunks.add(chunk)

        
    def get_y_at(self, x:Number, z:Number) -> Number:
        chunk_pos = [x // 10 * 10, 0, z // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]
            return chunk.get_y_at(x, z)
        else:
            return None

    def get_block_pos_at(self, x:Number, z:Number) -> list[Number]:
        chunk_pos = [x // 10 * 10, 0, z // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]
            return chunk.get_block_pos_at(x, z)
        else:
            return None

    def place_block(self, block:Block):
        chunk_pos = [block.position[0] // 10 * 10, 0, block.position[2] // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]

            if not block in chunk.blocks.blocks_list:
                chunk.blocks.add(block)
                chunk.model.add_instances([block.position], [block.texture], "block")

                chunk._update_dummy()

    def destroy_block(self, block:Block):
        if block == None:
            return
        chunk_pos = [block.position[0] // 10 * 10, 0, block.position[2] // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]

            if block in chunk.blocks.blocks_list:
                chunk.blocks.remove(block)
                chunk.model.remove_instances([block.position], "block")

                chunk._update_dummy()


    def render_chunks(self, camera_chunk_position, RENDER_DISTANCE):
        for chunk in [self.get_chunk_at([x, 0, z]) for x, z in square_range(camera_chunk_position, RENDER_DISTANCE, 10)]:
            chunk.is_player_in = (camera_chunk_position == chunk.position)
            chunk.render_mesh()

    def get_chunk_at(self, chunk_pos:list[Number], **kwargs) -> Chunk:
        #chunk_pos = [chunk_pos[0] // 10 * 10, 0, chunk_pos[2] // 10 * 10]
        if self.chunks.positions_blocks.get(tuple(chunk_pos)):
            return self.chunks.positions_blocks.get(tuple(chunk_pos))
        else:
            self.generate_chunk_at(chunk_pos, **kwargs)
            return self.chunks.positions_blocks.get(tuple(chunk_pos))

    def get_block_at(self, position:list[Number]):
        chunk_pos = [position[0] // 10 * 10, 0, position[2] // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]
            return chunk.get_block_at(position)
        else:
            self.generate_chunk_at(chunk_pos)
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]
            return chunk.get_block_at(position)
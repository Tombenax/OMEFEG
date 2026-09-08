from Chunk import Chunk
from Block import Block
from Render import CUBE_MODEL_INFO
from allBlocks import *
from lists import *
from Number import Number
from utils import export_and_load_chunk, square_range
from Render import *

class World:
    def __init__(self, render, seed, heightmap, rules, **kwargs):
        self.render = render
        self.seed = seed
        self.heightmap = heightmap
        self.rules = rules
        self.kwargs = kwargs

        self.chunks:ChunksList = ChunksList()

    def generate_chunk_at(self, position:list[Number]):
        chunk = Chunk(self.render, position, self.seed, self.heightmap, self.rules, **self.kwargs)
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

                vertices, indices = export_and_load_chunk(chunk.blocks.positions, chunk.blocks.textures, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y)

                chunk.model.remove_instance(0, "dummy")

                chunk.model.add_model("dummy", vertices = vertices, indices = indices, program=chunk.render.chunk_program)

                chunk.model.add_instances([[0, 0, 0]], [0], "dummy")

    def destroy_block(self, block:Block):
        if block == None:
            return
        chunk_pos = [block.position[0] // 10 * 10, 0, block.position[2] // 10 * 10]
        if tuple(chunk_pos) in self.chunks.positions_blocks:
            chunk = self.chunks.positions_blocks[tuple(chunk_pos)]

            if block in chunk.blocks.blocks_list:
                chunk.blocks.remove(block)
                chunk.model.remove_instances([block.position], "block")

                vertices, indices = export_and_load_chunk(chunk.blocks.positions, chunk.blocks.textures, CUBE_MODEL_INFO, TEXTURES_X, TEXTURES_Y)

                chunk.model.remove_instance(0, "dummy")

                chunk.model.add_model("dummy", vertices = vertices, indices = indices, program=chunk.render.chunk_program)

                chunk.model.add_instances([[0, 0, 0]], [0], "dummy")


    def render_chunks(self, camera_chunk_position, RENDER_DISTANCE):
        for chunk in [self.get_chunk_at([x, 0, z]) for x, z in square_range(camera_chunk_position, RENDER_DISTANCE, 10)]:
            chunk.is_player_in = (camera_chunk_position == chunk.position)
            chunk.render_mesh()

    def get_chunk_at(self, chunk_pos:list[Number]) -> Chunk:
        #chunk_pos = [chunk_pos[0] // 10 * 10, 0, chunk_pos[2] // 10 * 10]
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
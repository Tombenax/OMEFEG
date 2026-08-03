from utils import generate_terrain, bake_instanced_obj
from Block import Block
from InstancedModel import InstancedModel
from random import Random

class Chunk:
    def __init__(self, position:list, heightmap, rules, use_blocks=False, blocks:list[Block]=[], isplayerin=True, ctx=None, prog=None, v=None, i=None, tex_mapping=None, seed:Random=Random(), NotRendered:InstancedModel=None):
        self.position = position
        self.is_player_in = isplayerin
        self.NotRendered = NotRendered
        if self.NotRendered:
            self.NotRendered.add_instances([[0, 0, 0]], ["texture"])
        self.is_enabled = False
        self.occupied = set()
        if ctx is not None and prog is not None and v is not None and i is not None and tex_mapping is not None:
            self.blocksinstmodel = InstancedModel(ctx, prog, v, i, tex_mapping, False)
        else:
            self.blocksinstmodel = None

        if not use_blocks:
            self.blocks = generate_terrain(10, heightmap, position, rules, random_seed=seed)
        else:
            self.blocks = blocks

        if self.blocksinstmodel:
            for block in self.blocks:
                self.blocksinstmodel.add_instances([block.position], [block.texture])
                self.occupied.add(tuple(block.position))
    
    def get_blocks(self) -> list[Block]:
        return self.blocks
    
    def render(self):
        if self.NotRendered is not None:
            if not self.is_player_in:
                self.NotRendered.render()
        if self.blocksinstmodel is not None:
            if self.is_player_in:
                self.blocksinstmodel.render()
    
    def add_block(self, block:Block):
        self.blocksinstmodel.add_instances([block.position], [block.texture])
        self.occupied.add(tuple(block.position))
    
    def remove_block(self, block:Block):
        self.blocksinstmodel.remove_instance(tuple(block.position))
        self.occupied.remove(tuple(block.position))
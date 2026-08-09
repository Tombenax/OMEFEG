from utils import generate_terrain, bake_instanced_obj
from Block import Block
from InstancedModel import InstancedModel
from random import Random

class Chunk:
    def __init__(self, position, heightmap, rules, use_blocks=False, blocks:list[Block]=[], isplayerin=True, ctx=None, prog=None, v=None, i=None, tex_mapping=None, seed:Random=Random(), NotRendered:InstancedModel=None, should_render:bool=True):
        self.position = position
        self.is_player_in = isplayerin
        self.NotRendered = NotRendered
        self.should_render = should_render
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
            positions = [tuple(block.position) for block in self.blocks]
            layers = [block.texture for block in self.blocks]
            texture_layers = []
            for tex in layers:
                if isinstance(tex, str):
                    texture_layers.append(self.blocksinstmodel.tex_mapping.get(tex.lower(), self.blocksinstmodel.tex_mapping.get(tex, 0)))
                else:
                    texture_layers.append(int(tex))

            self.blocksinstmodel.add_instances(positions, texture_layers, areInts=True)
            self.occupied.update({position for position in positions})
    
    def get_blocks(self) -> list[Block]:
        return self.blocks
    
    def render(self):
        if self.should_render:
            if self.NotRendered is not None:
                if not self.is_player_in:
                    self.NotRendered.render()
            if self.blocksinstmodel is not None:
                if self.is_player_in:
                    self.blocksinstmodel.render()
    
    def add_block(self, block:Block):
        self.blocksinstmodel.add_instances([block.position], [block.texture])
        self.occupied.add(block.position)
    
    def remove_block(self, block:Block):
        self.blocksinstmodel.remove_instance(block.position)
        self.occupied.remove(block.position)
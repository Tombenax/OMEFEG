class BlocksList:
    def __init__(self):
        self.blocks_list = []
        self.blocks_positions = {}
        self.positions_blocks = {}
        self.occupied = set()
        self.positions = []
        self.textures = []

    def add(self, block):
        self.blocks_list.append(block)
        self.blocks_positions[block] = list(block.position)
        self.positions_blocks[tuple(block.position)] = block
        self.occupied.add(tuple(block.position))
        self.positions.append(list(block.position))
        self.textures.append(block.texture)

    def extend(self, blocks):
        self.blocks_list.extend(blocks)
        self.occupied.update({tuple(block.position) for block in blocks})

        for block in blocks:
            self.blocks_positions[block] = block.position
            self.positions_blocks[tuple(block.position)] = block
            self.positions.append(block.position)
            self.textures.append(block.texture)

    def remove(self, block):
        self.blocks_list.remove(block)
        self.blocks_positions.pop(block)
        self.positions_blocks.pop(tuple(block.position))
        self.occupied.remove(tuple(block.position))
        position_index = self.positions.index(block.position)
        self.positions.pop(position_index)
        self.textures.pop(position_index)

    def clear(self):
        self.blocks_list.clear()
        self.blocks_positions.clear()
        self.positions_blocks.clear()
        self.occupied.clear()
        self.positions.clear()
        self.textures.clear()


class ChunksList:
    def __init__(self):
        self.blocks_list = []
        self.blocks_positions = {}
        self.positions_blocks = {}
        self.occupied = set()
        self.positions = []

    def add(self, block):
        self.blocks_list.append(block)
        self.blocks_positions[block] = block.position
        self.positions_blocks[tuple(block.position)] = block
        self.occupied.add(tuple(block.position))
        self.positions.append(block.position)

    def remove(self, block):
        self.blocks_list.remove(block)
        self.blocks_positions.pop(block)
        self.positions_blocks.pop(tuple(block.position))
        self.occupied.remove(tuple(block.position))

    def __getitem__(self, key):
        return self.blocks_list[key]
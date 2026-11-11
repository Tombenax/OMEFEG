from math import floor

from Vec3 import Vec3


class BlocksList:
    def __init__(self):
        self.blocks_list = []
        self.blocks_positions = {}
        self.positions_blocks = {}
        self.occupied = set()
        self.positions = []
        self.textures = []
        self.positions_by_xz = {}

    def _index_position(self, position):
        x, _, z = position
        column = (floor(x), floor(z))
        self.positions_by_xz.setdefault(column, set()).add(position)

    def add(self, block):
        if block is None: return
        if not isinstance(block.position, Vec3):
            block.position = Vec3(*block.position)
        self.blocks_list.append(block)
        self.blocks_positions[block] = block.position
        self.positions_blocks[tuple(block.position)] = block
        self.occupied.add(tuple(block.position))
        self.positions.append(block.position)
        self.textures.append(block.texture)
        self._index_position(tuple(block.position))

    def extend(self, blocks):
        # i have no clue how this works
        _blist = self.blocks_list
        _bpos = self.blocks_positions
        _pblocks = self.positions_blocks
        _occ = self.occupied
        _positions = self.positions
        _textures = self.textures
        _blist.extend(blocks)
        for block in blocks:
            try:
                _pos = block.position
                _key = (int(_pos[0]), int(_pos[1]), int(_pos[2]))
            except (TypeError, IndexError, ValueError, AttributeError):
                try:
                    _key = tuple(block.position)
                except (TypeError, AttributeError):
                    continue
                _pos = block.position
            if not isinstance(_pos, Vec3):
                _pos = Vec3(*_pos)
                block.position = _pos
            _bpos[block] = _pos
            _pblocks[_key] = block
            _occ.add(_key)
            _positions.append(_pos)
            self._index_position(_key)
            try:
                _textures.append(block.texture)
            except AttributeError:
                _textures.append(0)

    def remove(self, block):
        self.blocks_list.remove(block)
        self.blocks_positions.pop(block)
        key = tuple(block.position)
        self.positions_blocks.pop(key)
        self.occupied.remove(key)
        column = (floor(key[0]), floor(key[2]))
        column_positions = self.positions_by_xz[column]
        column_positions.discard(key)
        if not column_positions:
            del self.positions_by_xz[column]
        position_index = next(
            (i for i, position in enumerate(self.positions) if tuple(position) == key),
            None,
        )
        if position_index is None:
            raise ValueError(block.position)
        self.positions.pop(position_index)
        self.textures.pop(position_index)

    def clear(self):
        self.blocks_list.clear()
        self.blocks_positions.clear()
        self.positions_blocks.clear()
        self.occupied.clear()
        self.positions.clear()
        self.textures.clear()
        self.positions_by_xz.clear()


class ChunksList:
    def __init__(self):
        self.blocks_list = []
        self.blocks_positions = {}
        self.positions_blocks = {}
        self.occupied = set()
        self.positions = []

    def add(self, block):
        if not isinstance(block.position, Vec3):
            block.position = Vec3(*block.position)
        self.blocks_list.append(block)
        self.blocks_positions[block] = block.position
        self.positions_blocks[tuple(block.position)] = block
        self.occupied.add(tuple(block.position))
        self.positions.append(block.position)

    def remove(self, block):
        try:
            self.blocks_list.remove(block)
        except ValueError:
            pass
        self.blocks_positions.pop(block, None)
        try:
            key = tuple(block.position)
        except (TypeError, AttributeError):
            return False
        self.positions_blocks.pop(key, None)
        self.occupied.discard(key)
        # Drop the matching entry so unloaded chunks don't linger here
        # forever (old code never removed them).
        for i, position in enumerate(self.positions):
            if tuple(position) == key:
                del self.positions[i]
                break
        return True

    def __getitem__(self, key):
        return self.blocks_list[key]
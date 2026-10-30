class BlocksList:
    def __init__(self):
        self.blocks_list = []
        self.blocks_positions = {}
        self.positions_blocks = {}
        self.occupied = set()
        self.positions = []
        self.textures = []

    def add(self, block):
        if block is None: return
        self.blocks_list.append(block)
        self.blocks_positions[block] = list(block.position)
        self.positions_blocks[tuple(block.position)] = block
        self.occupied.add(tuple(block.position))
        self.positions.append(list(block.position))
        self.textures.append(block.texture)

    def extend(self, blocks):
        # Single pass (was set-comprehension alloc + second loop over the
        # same ~600 blocks). Locals avoid attribute lookups per block.
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
            _bpos[block] = _pos
            _pblocks[_key] = block
            _occ.add(_key)
            _positions.append(_pos)
            try:
                _textures.append(block.texture)
            except AttributeError:
                _textures.append(0)

    @classmethod
    def from_records(cls, records, ctors):
        """Build a populated list from save-file records in a single pass.

        `records` yields (x, y, z, texture_id) tuples (e.g. Struct.iter_unpack
        over a chunk .bin file); `ctors` maps texture id -> Block class.
        Records with unknown ids are skipped, matching load_saved_blocks.

        Fuses construct + index (the split path built Block objects in one
        loop and indexed them in a second): one pass makes the objects AND
        every index. Voxel keys reuse the unpacked ints directly (struct
        yields ints, so no per-block int() conversions), and the texture
        id doubles as the texture (ctors map id -> class by construction).
        Pure Python, worker-thread safe on a fresh instance.
        """
        self = cls()
        _blist = self.blocks_list
        _bpos = self.blocks_positions
        _pblocks = self.positions_blocks
        _occ = self.occupied
        _positions = self.positions
        _textures = self.textures
        try:
            _nctors = len(ctors)
        except TypeError:
            return self
        _app = _blist.append
        _papp = _positions.append
        _tapp = _textures.append
        for x, y, z, t in records:
            try:
                ctor = ctors[t] if t < _nctors else None
            except TypeError:
                continue
            if ctor is None:
                continue
            try:
                block = ctor([x, y, z])
            except Exception:
                continue
            _pos = block.position
            _key = (x, y, z)
            _app(block)
            _bpos[block] = _pos
            _pblocks[_key] = block
            _occ.add(_key)
            _papp(_pos)
            _tapp(t)
        return self

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
        # positions held block.position lists; drop the matching entry so
        # unloaded chunks don't linger here forever (old code never
        # removed, leaking one entry per evicted chunk).
        try:
            self.positions.remove(block.position)
        except ValueError:
            for i, p in enumerate(self.positions):
                try:
                    if tuple(p) == key:
                        del self.positions[i]
                        break
                except TypeError:
                    continue
        return True

    def __getitem__(self, key):
        return self.blocks_list[key]
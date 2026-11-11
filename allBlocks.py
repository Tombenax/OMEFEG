from collections.abc import Sequence

from Block import Block
from Vec3 import Vec3

def sum_list(list1, list2):
    return [x+y for x, y in zip(list1, list2)]


BIRCH_LEAVE = 0
BIRCH_LOG = 1
COBBLESTONE = 2
DIRT = 3
GRASS = 4
OAK_LEAVE = 5
OAK_LOG = 6
OAK_PLANKS = 7
SAND = 8
STONE = 9
WATER = 10
BACKPACK = 11
BENCH = 12
UNUSED_1 = 13
UNUSED_2 = 14
UNUSED_3 = 15
SELECTED = 16
UNBREKABLE = 18
PLAYER = 19
CAT = 20


class Grass(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("grass", position, GRASS, {"breakable":True}, True)

class Dirt(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("dirt", position, DIRT, {"breakable":True}, True)

class Stone(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("stone", position, STONE, {"breakable":True}, True)

class Birch_Leave(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("birch_leave", position, BIRCH_LEAVE, {"breakable":True}, True)

class Birch_Log(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("birch_log", position, BIRCH_LOG, {"breakable":True}, True)

class Oak_Leave(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("oak_leave", position, OAK_LEAVE, {"breakable":True}, True)

class Oak_Log(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("oak_log", position, OAK_LOG, {"breakable":True}, True)

class Oak_Planks(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("oak_planks", position, OAK_PLANKS, {"breakable":True}, True)

class Sand(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("sand", position, SAND, {"breakable":True}, True)

MAX_WATER_LENGHT = 5

class Water(Block):
    def __init__(self, position: Vec3 | Sequence[float | int], source:bool=True, lenght:int=MAX_WATER_LENGHT):
        super().__init__("water", position, WATER, {"breakable":True}, False)
        self.source = source
        self.lenght = lenght
        self.chunk_pos = Vec3(self.position[0]//10*10, 0, self.position[2]//10*10)

    def update(self, neighbours:dict[tuple, Block]):

        updated_neighbours = []

        down = Vec3(0, -1, 0)
        summed = self.position + down
        if neighbours.get(tuple(summed)) is None:
            updated_neighbours.append(Water(summed, False, self.lenght-1))

        if self.lenght == 0:
            return
        
        self.lenght -= 1
        result = self.position + down
        if isinstance(neighbours.get(tuple(result)), Water):
            return
        elif neighbours.get(tuple(result)) is None:
            return [Water(result)]
        for offset in (Vec3(1, 0, 0), Vec3(0, 0, 1), Vec3(0, 0, -1), Vec3(-1, 0, 0)):
            summed = self.position + offset
            if neighbours.get(tuple(summed)) is None:
                updated_neighbours.append(Water(summed, False, self.lenght))

                
        return updated_neighbours


class Cobblestone(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("cobblestone", position, COBBLESTONE, {"breakable":True}, True)

class Unbrekable(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("unbrekable", position, UNBREKABLE, {"breakable":False}, True)

class Bench(Block):
    def __init__(self, position: Vec3 | Sequence[float | int]):
        super().__init__("bench", position, BENCH, {"breakable":True}, True, "bench")
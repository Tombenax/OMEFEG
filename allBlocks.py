<<<<<<< HEAD
from Block import Block

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



class Grass(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("grass", position, GRASS, {0:None}, True)

class Dirt(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("dirt", position, DIRT, {0:None}, True)

class Stone(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("stone", position, STONE, {0:None}, True)

class Birch_Leave(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("birch_leave", position, BIRCH_LEAVE, {0:None}, True)

class Birch_Log(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("birch_log", position, BIRCH_LOG, {0:None}, True)

class Oak_Leave(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("oak_leave", position, OAK_LEAVE, {0:None}, True)

class Oak_Log(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("oak_log", position, OAK_LOG, {0:None}, True)

class Oak_Planks(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("oak_planks", position, OAK_PLANKS, {0:None}, True)

class Sand(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("sand", position, SAND, {0:None}, True)

MAX_WATER_LENGHT = 5

class Water(Block):
    def __init__(self, position: list[float | int], source:bool=True, lenght:int=MAX_WATER_LENGHT):
        super().__init__("water", position, WATER, {0:None}, False)
        self.source = source
        self.lenght = lenght
        self.chunk_pos = (self.position[0]//10*10, 0, self.position[2]//10*10)

    def update(self, neighbours:dict[tuple, Block]):

        updated_neighbours = []

        summed = sum_list([0, -1, 0], self.position)
        if neighbours.get(tuple(summed)) is None:
            updated_neighbours.append(Water(summed, False, self.lenght-1))

        if self.lenght == 0:
            return
        
        self.lenght -= 1
        result = sum_list([0, -1, 0], self.position)
        if isinstance(neighbours.get(tuple(result)), Water):
            return
        elif neighbours.get(tuple(result)) is None:
            return [Water(result)]
        for position in [[1, 0, 0], [0, 0, 1], [0, 0, -1], [-1, 0, 0]]:
            summed = sum_list(position, self.position)
            if neighbours.get(tuple(summed)) is None:
                updated_neighbours.append(Water(summed, False, self.lenght))

                
        return updated_neighbours


class Cobblestone(Block):
    def __init__(self, position: list[float | int]):
=======
from Block import Block

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



class Grass(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("grass", position, GRASS, {0:None}, True)

class Dirt(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("dirt", position, DIRT, {0:None}, True)

class Stone(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("stone", position, STONE, {0:None}, True)

class Birch_Leave(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("birch_leave", position, BIRCH_LEAVE, {0:None}, True)

class Birch_Log(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("birch_log", position, BIRCH_LOG, {0:None}, True)

class Oak_Leave(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("oak_leave", position, OAK_LEAVE, {0:None}, True)

class Oak_Log(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("oak_log", position, OAK_LOG, {0:None}, True)

class Oak_Planks(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("oak_planks", position, OAK_PLANKS, {0:None}, True)

class Sand(Block):
    def __init__(self, position: list[float | int]):
        super().__init__("sand", position, SAND, {0:None}, True)

MAX_WATER_LENGHT = float("inf")

class Water(Block):
    def __init__(self, position: list[float | int], source:bool=True, lenght:int=MAX_WATER_LENGHT):
        super().__init__("water", position, WATER, {0:None}, False)
        self.source = source
        self.lenght = lenght
        self.chunk_pos = (self.position[0]//10*10, 0, self.position[2]//10*10)

    def update(self, neighbours:dict[tuple, Block]):

        updated_neighbours = []

        summed = sum_list([0, -1, 0], self.position)
        if neighbours.get(tuple(summed)) is None:
            updated_neighbours.append(Water(summed, False, self.lenght-1))

        if self.lenght == 0:
            return
        
        self.lenght -= 1
        result = sum_list([0, -1, 0], self.position)
        if isinstance(neighbours.get(tuple(result)), Water):
            return
        elif neighbours.get(tuple(result)) is None:
            return [Water(result)]
        for position in [[1, 0, 0], [0, 0, 1], [0, 0, -1], [-1, 0, 0]]:
            summed = sum_list(position, self.position)
            if neighbours.get(tuple(summed)) is None:
                updated_neighbours.append(Water(summed, False, self.lenght))

                
        return updated_neighbours


class Cobblestone(Block):
    def __init__(self, position: list[float | int]):
>>>>>>> d28fd2647dd9c046033457fdeb3d5779d087a5c3
        super().__init__("cobblestone", position, COBBLESTONE, {0:None}, True)
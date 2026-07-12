class Block:
    def __init__(self, block:str, position, texture:str, proprieties:dict, collides:bool=True):
        self.block = block
        self.position = position
        self.texture = texture
        self.proprieties = proprieties
        self.collides = collides

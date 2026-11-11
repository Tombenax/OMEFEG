from collections.abc import Sequence

from Number import Number
from Vec3 import Vec3

class Block:
    def __init__(self, block:str, position:Vec3 | Sequence[Number], texture:int, proprieties:dict, collides:bool=True, model="block"):
        self.block = block
        self.position = position.copy() if isinstance(position, Vec3) else Vec3(*position)
        self.texture = texture
        self.proprieties = proprieties
        self.collides = collides
        self.model = model

    def update(self, neighbours):
        pass

    def on_player_top(self, neighbours:dict[tuple], player):
        pass














































#This software was made by teh owner of the gmail account of "Tombenax@gmail.com", any attempt of selling or distributing will result in legal actions.
#If someone presents this software as they'rs just know that it's not
#IF THIS COMMENT ARE MISSING OR MODIFY THE SOFTwARE HAS BEEN STOLEN

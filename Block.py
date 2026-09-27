from Number import Number

class Block:
    def __init__(self, block:str, position:list[Number], texture:int, proprieties:dict, collides:bool=True):
        self.block = block
        self.position = list(position)
        self.texture = texture
        self.proprieties = proprieties
        self.collides = collides

    def update(self, neighbours):
        """React to being placed. Called once by the world after the
        block lands (place_block) or when the update queue drains it.

        neighbours: dict mapping absolute voxel position (x, y, z) of
            the 6 adjacent voxels to the Block there, e.g.
            neighbours.get((x, y - 1, z)) is the block below (or None).
            Missing keys are air (or unloaded chunks, which are never
            generated for this).

        Return: None (or empty) for no further action, a single Block,
            or an iterable of Blocks. Returned blocks are NOT placed
            immediately: they enter the world's update queue, and each
            0.2s tick (UPDATE_QUEUE_INTERVAL) places + updates exactly
            one wave (the entries queued when the tick starts); their
            products wait for the following tick. Entries aimed at
            not-yet-streamed chunks wait instead of dying at the border.
            Spreads are unbounded by design; they stop when voxels fill.
            Returned blocks must have valid 3-component positions;
            anything else is ignored. Updates must be deterministic
            (same neighbours -> same blocks): every client replays them,
            so randomness desyncs multiplayer worlds.
        """
        pass

    def on_player_top(self, neighbours:dict[tuple], player):
        pass














































#This software was made by teh owner of the gmail account of "Tombenax@gmail.com", any attempt of selling or distributing will result in legal actions.
#If someone presents this software as they'rs just know that it's not
#IF THIS COMMENT ARE MISSING OR MODIFY THE SOFTwARE HAS BEEN STOLEN

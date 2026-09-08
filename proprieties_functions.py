import numpy as np
from Block import Block
import inspect
import sys
from Block import Block
from Player import Player

#put this always at the top of the file
def count_functions():
    current_module = sys.modules[__name__]
    functions = inspect.getmembers(current_module, inspect.isfunction)
    return functions[1:]


def destroy(chunk, block:Block, player:Player):
    chunk.remove_block(block)

def place(chunk, block:Block, player:Player):
    chunk.add_block(block)


#put this after all functions
functionslist = count_functions()
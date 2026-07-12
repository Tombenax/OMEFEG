import numpy as np
from Block import Block
import inspect
import sys
from InstancedModel import InstancedModel

#put this always at the top of the file
def count_functions():
    current_module = sys.modules[__name__]
    functions = inspect.getmembers(current_module, inspect.isfunction)
    return functions[1:]


def destroy(instancedmodel:InstancedModel, normal, occupied, hit, blocks, selected_block, camera_position):
    removal_index = instancedmodel.remove_instance(hit)
    occupied.discard(tuple(hit))
    blocks.pop(removal_index)

def place(instancedmodel:InstancedModel, normal, occupied, hit, blocks, selected_block, camera_position):
    new = tuple(np.array(hit) + normal)
    if new not in occupied:
        if new != tuple(np.round(camera_position).astype(int)):
            new_block = Block(selected_block, list(new), selected_block, {0:destroy, 1:place})
            blocks.append(new_block)
            occupied.add(new)
            instancedmodel.add_instances([new_block.position], [new_block.texture])


#put this after all functions
functionslist = count_functions()
from math import radians
from time import time

from pyrr import Matrix44

from Render import Model, load_obj
from Vec3 import Vec3

import numpy as np

def points_are_close(p1, p2, margin=1.0):
    return np.linalg.norm(np.array(p1) - np.array(p2)) <= margin

class Items3D:

    def __init__(self, render):
        self.model = Model(render)

        self._added = set()

        self.items = {}

        self.items_rot = {}

    def add_item(self, pos:Vec3, model_path:str, texture:int):

        identifier = texture

        if not model_path in self._added:
            self._added.add(model_path)

            v, i = load_obj(model_path)

            self.model.add_model(model_path, vertices=v, indices=i)

        self.model.add_instances([pos], [texture], model_path)

        unique_identifier = time()

        self.items_rot[unique_identifier] = 0

        if self.items.get(model_path) is None:
            self.items[model_path] = []

        self.items[model_path].append((unique_identifier, identifier))

    def update(self, dt, player):

        for model_path in self.model.instanedmodels:
            for idx, (unique_identifier, identifier) in enumerate(self.items[model_path]):

                item_mat = self.model.instanedmodels[model_path].active_instances[idx]

                pos = item_mat[3][:3].copy()

                if points_are_close(pos, player.pos.xyz): #picked up
                    if player.add_item_in_inventory(identifier): # if it fits in the inventory
                        self.model.remove_instances([pos], model_path)
                        self.items_rot.pop(unique_identifier)
                        self.items[model_path].pop(idx)

                        continue

                incr = self.items_rot[unique_identifier]

                incr += 50 * dt

                incr %= 360

                self.items_rot[unique_identifier] = incr

                item_mat[:] = (
                    Matrix44.from_y_rotation(radians(incr)) @
                    Matrix44.from_scale([0.4, 0.4, 0.4]) @
                    Matrix44.from_translation(pos) 
                )

        for a in self.model.instanedmodels.values():
            a._upload()


    def render(self):
        self.model.render()
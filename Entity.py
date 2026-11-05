"""
Entity class for blender models
"""

from Render import Model
from BlenderModel import attach_blender_model, BlenderAnimationPlayer, load_blender_model
from BehaviurScript import BehaviurScript

from Vec3 import Vec3

from time import time

class Entitys:
    def __init__(self, render):
        self.MODEL = Model(render)
        self.entities_names = []
        self.entities_names_to_evrything = {}
        self.f__k_that = False

    def add_entity(self, model_path:str, pos:Vec3, behaviur_script:BehaviurScript):

        str_time = str(time())

        name = model_path + str_time

        if not model_path in self.entities_names:
            attach_blender_model(self.MODEL, name, model_path, pos, 15)
            self.entities_names_to_evrything[name] = (behaviur_script, self.MODEL.instanedmodels[name].active_instances[-1], name)

        else:
            self.MODEL.add_instances([pos], [15], name, [None])
            model_data = load_blender_model(model_path)
            player = BlenderAnimationPlayer(
                model_data,
                self.MODEL.instanedmodels[name].set_vertices,
            )
            self.MODEL.animated_models[name] = player
            self.entities_names_to_evrything[name] = (behaviur_script, self.MODEL.instanedmodels[name].active_instances[-1], name)

        self.can_update = False

    def update(self, dt):
        for script, pos_matrix, name in self.entities_names_to_evrything.values():
            if self.can_update or self.f__k_that:
                update_status = script.update(pos_matrix, self.MODEL, name, dt)
                self.f__k_that = True
            else:
                update_status = script.init(pos_matrix, self.MODEL, name, dt)

            if update_status[0]:
                self.MODEL.instanedmodels[name]._upload()

            if update_status[1]:
                self.f__k_that = True
    
    def render_entities(self):
        self.MODEL.render()
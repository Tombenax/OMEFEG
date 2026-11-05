
from math import radians
import random
from time import time

import numpy as np
from pyrr import Matrix44

from Vec3 import Vec3

class BehaviurScript:
    def __init__(self, instructions):
        """
        instructions syntax:
        {"init": [...], "update": [...]}
        """

        self.instructions_init = instructions["init"]
        self.instructions_upate = instructions["update"]

        self.last_idx = None
        self.last_time = None
        self.start_pos = None

    def init(self, instance, animation_player, name, dt):
        return self._parse(instance, animation_player, self.instructions_init, name, dt)

    def update(self, instance, animation_player, name, dt):
        return self._parse(instance, animation_player, self.instructions_upate, name, dt)

    def _parse(self, instance, animation_player, instructions, identifier, dt):

        return_status = [False, False] #upload, can start update sequnce

        idx = -1

        for idx, inst in enumerate(instructions):

            if self.last_idx is not None:
                if idx < self.last_idx:
                    continue

                self.last_idx = None


            args = list(inst[1:])

            match inst[0]:
                case "SET_POS":
                    instance[3][:3] = np.array([args[0], args[1], args[2]], dtype=np.float64)

                    return_status[0] = True

                case "START_ANIMATION":
                    
                    animation_player.stop_animation(identifier)
                    
                    animation_player.play_animation(identifier, args[0], args[1])
                
                case "STOP_ANIMATION":
                    animation_player.stop_animation(identifier, args[0])

                case "WAIT":

                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    self.last_idx = idx
                    if self.last_time is None:
                        self.last_time = time()
                        break
                    else:
                        if time() - self.last_time >= args[0]:
                            self.last_idx = None
                            self.last_time = None
                        else:
                            break

                case "DEBUG_PRINT":
                    print(args[0])

                case "MOVE":

                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])

                    if self.start_pos is None: self.start_pos = instance[3][:3].copy()

                    time_arg = args[1]

                    if self.last_time is not None and dt + (time() - self.last_time) >= time_arg:
                        dx = (args[0].x + self.start_pos[0]) - instance[3][0]
                        dy = (args[0].y + self.start_pos[1]) - instance[3][1]
                        dz = (args[0].z + self.start_pos[2]) - instance[3][2]

                    else:
                        dx = args[0].x/time_arg * dt
                        dy = args[0].y/time_arg * dt
                        dz = args[0].z/time_arg * dt

                    instance[3][:3] = np.array([instance[3][0]+dx, instance[3][1]+dy, instance[3][2]+dz], dtype=np.float64)

                    return_status[0] = True

                    self.last_idx = idx
                    if self.last_time is None:
                        self.last_time = time()
                        break
                    else:
                        if time() - self.last_time >= time_arg:
                            self.last_idx = None
                            self.last_time = None
                            self.start_pos = None
                        else:
                            break

                case "RANDOM_NUMBER":
                    setattr(self, args[2], random.randint(args[0], args[1]))

                case "RANDOM_VECTOR":
                    setattr(self, args[3], Vec3(random.randint(args[0]*100, args[1]*100)/100 if not "x" in args[2] else 0, random.randint(args[0]*100, args[1]*100)/100 if not "y" in args[2] else 0, random.randint(args[0]*100, args[1]*100)/100 if not "z" in args[2] else 0))

                case "SET_VARIABLE":
                    setattr(self, args[0], args[1])

                case "ROTATE":
                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    instance[:] = (
                        Matrix44.from_x_rotation(radians(args[0].x))
                        @ Matrix44.from_y_rotation(radians(args[0].y))
                        @ Matrix44.from_z_rotation(radians(args[0].z))
                        @ instance
                    )

                    return_status[0] = True

                case "MULT_VEC":
                    if isinstance(args[0], str):
                        var_name = args[0]
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, var_name, args[0] * Vec3(args[1], args[2], args[3]))

                case "MULT_VEC_AND_STORE":
                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, args[4], args[0] * Vec3(args[1], args[2], args[3]))

                case "PRINT_VAR":
                    print(getattr(self, args[0]))

                case "MIN_VEC_AND_STORE":
                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, args[4], args[0] - Vec3(args[1], args[2], args[3]))

                case "MIN_VEC":
                    if isinstance(args[0], str):
                        var_name = args[0]
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, var_name, args[0] - Vec3(args[1], args[2], args[3]))

                case "ADD_VEC_AND_STORE":
                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, args[4], args[0] + Vec3(args[1], args[2], args[3]))

                case "ADD_VEC":
                    if isinstance(args[0], str):
                        var_name = args[0]
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, var_name, args[0] + Vec3(args[1], args[2], args[3]))

                case "DIV_VEC_AND_STORE":
                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, args[4], args[0] / Vec3(args[1], args[2], args[3]))

                case "DIV_VEC":
                    if isinstance(args[0], str):
                        var_name = args[0]
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])
                    if isinstance(args[2], str):
                        args[2] = getattr(self, args[2])
                    if isinstance(args[3], str):
                        args[3] = getattr(self, args[3])

                    setattr(self, var_name, args[0] / Vec3(args[1], args[2], args[3]))

                case "ROTATE_FROM_DIRECTION_VECTOR":

                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    direction_length = np.linalg.norm(args[0])
                    if direction_length > 0:
                        norm_dir = args[0] / direction_length
                        yaw_offset = radians(args[1]) if len(args) > 1 else 0
                        yaw = -np.arctan2(norm_dir[0], norm_dir[2]) + yaw_offset
                        position = instance[3, :3].copy()
                        instance[:] = (
                            Matrix44.from_y_rotation(yaw)
                            @ Matrix44.from_translation(position)
                        )
                        return_status[0] = True

                case "MUL_VEC_INT":
                    if isinstance(args[0], str):
                        var_name = args[0]
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])

                    setattr(self, var_name, args[0] * args[1])

                case "MOVE_TO":
                    if isinstance(args[0], str):
                        args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        args[1] = getattr(self, args[1])

                    if self.start_pos is None: self.start_pos = instance[3][:3].copy()

                    time_arg = args[1]

                    if self.last_time is not None and dt + (time() - self.last_time) >= time_arg:
                        dx = args[0].x - instance[3][0]
                        dy = args[0].y - instance[3][1]
                        dz = args[0].z - instance[3][2]

                    else:
                        dx = (args[0].x - self.start_pos[0])/time_arg * dt
                        dy = (args[0].y - self.start_pos[1])/time_arg * dt
                        dz = (args[0].z - self.start_pos[2])/time_arg * dt

                    instance[3][:3] = np.array([instance[3][0]+dx, instance[3][1]+dy, instance[3][2]+dz], dtype=np.float64)

                    return_status[0] = True

                    self.last_idx = idx
                    if self.last_time is None:
                        self.last_time = time()
                        break
                    else:
                        if time() - self.last_time >= time_arg:
                            self.last_idx = None
                            self.last_time = None
                            self.start_pos = None
                        else:
                            break

                case "MIN_VEC_VEC_STORE":
                    if isinstance(args[0], str):
                        if args[0] == "position":
                            args[0] = Vec3(*instance[3][:3])
                        else:
                            args[0] = getattr(self, args[0])

                    if isinstance(args[1], str):
                        if args[1] == "position":
                            args[1] = Vec3(*instance[3][:3])
                        else:
                            args[1] = getattr(self, args[1])


                    setattr(self, args[2], args[0] - args[1])

        if idx+1 == len(instructions): return_status[1] = True

        return return_status


def from_func_to_BS_func(func):

    def inner(*args):
        return func.__name__, *args

    return inner

@from_func_to_BS_func
def SET_POS(x, y, z): pass
@from_func_to_BS_func
def START_ANIMATION(name, loop): pass
@from_func_to_BS_func
def STOP_ANIMATION(reset): pass
@from_func_to_BS_func
def WAIT(time): pass
@from_func_to_BS_func
def DEBUG_PRINT(text): pass
@from_func_to_BS_func
def MOVE(vector, time): pass
@from_func_to_BS_func
def RANDOM_NUMBER(min, max, variable_name): pass
@from_func_to_BS_func
def RANDOM_VECTOR(min, max, do_not_tuch_this_axis, variable_name): pass
@from_func_to_BS_func
def SET_VARIABLE(var_name, value): pass
@from_func_to_BS_func
def ROTATE(rotate_vec): pass
@from_func_to_BS_func
def MULT_VEC(vec, x_mul, y_mul, z_mul): pass
@from_func_to_BS_func
def MULT_VEC_AND_STORE(vec, x_mul, y_mul, z_mul, new_var_name): pass
@from_func_to_BS_func
def PRINT_VAR(var_name): pass
@from_func_to_BS_func
def MIN_VEC(vec, x_min, y_min, z_min): pass
@from_func_to_BS_func
def MIN_VEC_AND_STORE(vec, x_min, y_min, z_min, new_var_name): pass
@from_func_to_BS_func
def ADD_VEC(vec, x_min, y_min, z_min): pass
@from_func_to_BS_func
def ADD_VEC_AND_STORE(vec, x_min, y_min, z_min, new_var_name): pass
@from_func_to_BS_func
def DIV_VEC(vec, x_min, y_min, z_min): pass
@from_func_to_BS_func
def DIV_VEC_AND_STORE(vec, x_min, y_min, z_min, new_var_name): pass
@from_func_to_BS_func
def ROTATE_FROM_DIRECTION_VECTOR(dir_vec, yaw_offset_degrees=0): pass
@from_func_to_BS_func
def MUL_VEC_INT(vec1, int1): pass
@from_func_to_BS_func
def MOVE_TO(pos:Vec3, time): pass
@from_func_to_BS_func
def MIN_VEC_VEC_STORE(vec1, vec2, var_nam): pass
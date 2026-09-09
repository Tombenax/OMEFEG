import numpy as np

#this are the ame variables, i use teh to set them so it's easier for me.

game_variables = None
game_variables_local = None

def get_variable(var_name:str):
    if var_name in game_variables:
        return game_variables[var_name]
    elif var_name in game_variables['__annotations__']:
        return game_variables['__annotations__'][var_name]
    elif var_name in game_variables_local:
        return game_variables_local[var_name]

def init_interfacer(global_variables, lo):
    global game_variables
    game_variables = global_variables
    global game_variables_local
    game_variables_local = lo

def set_global_variables(gv):
    global game_variables
    game_variables = gv

def set_local_variables(lo):
    global game_variables_local
    game_variables_local = lo


def move_player(x, y, z):
    get_variable("CAMERA").position = np.array([x, y, z], dtype="f4")

def place(block_name:str, x, y, z):
    get_variable("WORLD").place_block(get_variable("get_block")(block_name, [x, y, z]))

def destroy(x, y, z):
    get_variable("WORLD").destroy_block(get_variable("WORLD").get_block_at([x, y, z]))

def send_notification(title:str, message:str):
    get_variable("notification")(title, message)

def get_camera():
    return get_variable("CAMERA")

def get_world():
    return get_variable("WORLD")

def get_raycast():
    return get_variable("position"), get_variable("normal")
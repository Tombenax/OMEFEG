import numpy as np

def move_player(x, y, z):
    globals()["CAMERA"].position = np.array([x, y, z], dtype="f4")


import numpy as np
from copy import deepcopy

class Vec2:
    def __init__(self, position, dtype=np.float64):
        position = np.array(position, dtype=dtype)
        self.x = position[0]
        self.y = position[1]
        self.xy = position

    def __add__(self, other):
        return Vec2(self.xy + other.xy)

    def __mul__(self, other):
        return Vec2(self.xy * other.xy)

    def __truediv__(self, other):
        return Vec2(self.xy / other.xy)

    def __sub__(self, other):
        return Vec2(self.xy - other.xy)

    def __floordiv__(self, other):
        return Vec2(self.xy // other.xy)

    def aslist(self):
        return list(self.xy)

    def TransformIntoVec3(self, middle):
        return Vec3([self.x, middle, self.y])
    
    def convert(self, dtype):
        position = np.array(self.xy, dtype=dtype)
        self.x = position[0]
        self.y = position[1]
        self.xy = position

    def __getitem__(self, key):
        if key == 0:
            return self.x

        elif key == 1:
            return self.y

class Vec3:
    def __init__(self, position, dtype=np.float64):
        position = np.array(position, dtype=dtype)
        self.xyz = position
        self.zx = np.array([position[2], position[0]])
        self.yz = np.array([position[1], position[2]])
        self.xy = np.array([position[0], position[1]])
        self.x = position[0]
        self.y = position[1]
        self.z = position[2]


    def __add__(self, other):
        if not isinstance(other, Vec3):
            return Vec3(self.xyz + other)
        return Vec3(self.xyz + other.xyz)

    def __mul__(self, other):
        if not isinstance(other, Vec3):
            return Vec3(self.xyz * other)
        return Vec3(self.xyz * other.xyz)

    def __truediv__(self, other):
        if not isinstance(other, Vec3):
            return Vec3(self.xyz // other)
        return Vec3(self.xyz / other.xyz)

    def __sub__(self, other):
        if not isinstance(other, Vec3):
            return Vec3(self.xyz - other)
        return Vec3(self.xyz - other.xyz)

    def __floordiv__(self, other):
        if not isinstance(other, Vec3):
            return Vec3(self.xyz // other)
        return Vec3(self.xyz // other.xyz)

    def __pow__(self, other):
        if not isinstance(other, Vec3):
            return Vec3(self.xyz ** other)
        return Vec3(self.xyz ** other.xyz)

    def copy(self):
        return deepcopy(self)

    def asIterable(self, itclass):
        return itclass(self.xyz)

    def sqrt(self):
        return Vec3(np.sqrt(self.xyz))

    def aslist(self):
        return self.asIterable(list)

    def astuple(self):
        return self.asIterable(tuple)

    def TransformIntoVec2(self):
        return Vec2([self.x, self.z])

    def convert(self, dtype):
        position = np.array(self.xyz, dtype=dtype)
        self.x = position[0]
        self.y = position[1]
        self.z = position[2]
        self.xy = np.array([position[0], position[1]], dtype=dtype)
        self.yz = np.array([position[1], position[2]], dtype=dtype)
        self.zx = np.array([position[2], position[0]], dtype=dtype)
        self.xyz = position
        return self

    def __str__(self):
        return str(self.xyz)

    def __getitem__(self, key):
        if key == 0:
            return self.x

        elif key == 1:
            return self.y

        elif key == 2:
            return self.z

    def __setitem__(self, key, value):
        if key == 0:
            self.x = value

        elif key == 1:
            self.y = value

        elif key == 2:
            self.z = value

    def replace_temp(self, axis:str, value):
        temp = deepcopy(self)
        setattr(temp, axis, value)
        return temp

if __name__ == "__main__":
    new_vector = Vec3([10, 50, 30])
    a_vector = Vec2([10, 10])
    print(((new_vector.TransformIntoVec2() // a_vector) * a_vector).TransformIntoVec3(0))

#Vec3 class

import numpy as np

class Vec3:
    def __init__(self, x, y, z):
        self._xyz = np.array([x, y, z], dtype=np.float64)

    @property
    def xyz(self):
        return self._xyz

    @xyz.setter
    def xyz(self, values):
        self._xyz[:] = values

    @property
    def x(self):
        return self._xyz[0]

    @x.setter
    def x(self, value):
        self._xyz[0] = value

    @property
    def y(self):
        return self._xyz[1]

    @y.setter
    def y(self, value):
        self._xyz[1] = value

    @property
    def z(self):
        return self._xyz[2]

    @z.setter
    def z(self, value):
        self._xyz[2] = value

    def __array__(self, dtype=None, copy=None):
        if dtype is not None and dtype != self._xyz.dtype:
            return self._xyz.astype(dtype, copy=True)
        if copy:
            return self._xyz.copy()
        return self._xyz

    def __repr__(self):
        return f"Vec3({self.x!r}, {self.y!r}, {self.z!r})"

    def __len__(self):
        return 3

    def __iter__(self):
        return iter(self._xyz)

    def __getitem__(self, index):
        return self._xyz[index]

    def __setitem__(self, index, value):
        self._xyz[index] = value

    def tolist(self):
        return self._xyz.tolist()

    def _pair(self, first, second):
        return np.ndarray(
            shape=(2,),
            dtype=self._xyz.dtype,
            buffer=self._xyz,
            offset=first * self._xyz.itemsize,
            strides=((second - first) * self._xyz.itemsize,),
        )

    def __abs__(self):
        return Vec3(*np.abs(self.xyz))

    @property
    def xy(self):
        return self._pair(0, 1)

    @xy.setter
    def xy(self, values):
        self._pair(0, 1)[:] = values

    @property
    def yx(self):
        return self._pair(1, 0)

    @yx.setter
    def yx(self, values):
        self._pair(1, 0)[:] = values

    @property
    def yz(self):
        return self._pair(1, 2)

    @yz.setter
    def yz(self, values):
        self._pair(1, 2)[:] = values

    @property
    def zy(self):
        return self._pair(2, 1)

    @zy.setter
    def zy(self, values):
        self._pair(2, 1)[:] = values

    @property
    def zx(self):
        return self._pair(2, 0)

    @zx.setter
    def zx(self, values):
        self._pair(2, 0)[:] = values

    @property
    def xz(self):
        return self._pair(0, 2)

    @xz.setter
    def xz(self, values):
        self._pair(0, 2)[:] = values

    def copy(self):
        return Vec3(*self.xyz.copy())

    def sum(self):
        return self.x+self.y+self.z

    def round(self):
        return Vec3(*np.round(self.xyz))

    def __add__(self, other):
        return Vec3(*(self._xyz + (other._xyz if isinstance(other, Vec3) else other)))

    __radd__ = __add__

    def __sub__(self, other):
        return Vec3(*(self._xyz - (other._xyz if isinstance(other, Vec3) else other)))

    def __rsub__(self, other):
        return Vec3(*((other._xyz if isinstance(other, Vec3) else other) - self._xyz))

    def __mul__(self, other):
        return Vec3(*(self._xyz * (other._xyz if isinstance(other, Vec3) else other)))

    __rmul__ = __mul__

    def __truediv__(self, other):
        return Vec3(*(self._xyz / (other._xyz if isinstance(other, Vec3) else other)))

    def __floordiv__(self, other):
        return Vec3(*(self._xyz // (other._xyz if isinstance(other, Vec3) else other)))

    def __neg__(self):
        return Vec3(*(-self._xyz))

    def __iadd__(self, other):
        self._xyz += other._xyz if isinstance(other, Vec3) else other
        return self

    def __isub__(self, other):
        self._xyz -= other._xyz if isinstance(other, Vec3) else other
        return self

    def __imul__(self, other):
        self._xyz *= other._xyz if isinstance(other, Vec3) else other
        return self

    def __itruediv__(self, other):
        self._xyz /= other._xyz if isinstance(other, Vec3) else other
        return self

    def __ifloordiv__(self, other):
        self._xyz //= other._xyz if isinstance(other, Vec3) else other
        return self

    def set_xyz(self, x, y, z):
        self.xyz = [x, y, z]

    def set_xy(self, x, y):
        self.xy = [x, y]

if __name__ == "__main__":
    vec3 = Vec3(0, 1, 2)

    print(vec3.x)

    vec3.set_xyz(1, 2, 3)

    print((vec3 / 2).xyz)
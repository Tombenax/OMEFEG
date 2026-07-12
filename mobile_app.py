import math
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.uix.widget import Widget

WIDTH = 800
HEIGHT = 600

# Cube vertices
vertices = [
    (-1, -1, -1),
    (1, -1, -1),
    (1, 1, -1),
    (-1, 1, -1),
    (-1, -1, 1),
    (1, -1, 1),
    (1, 1, 1),
    (-1, 1, 1),
]

edges = [
    (0,1),(1,2),(2,3),(3,0),
    (4,5),(5,6),(6,7),(7,4),
    (0,4),(1,5),(2,6),(3,7)
]


class CubeWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.angle = 0
        Clock.schedule_interval(self.update, 1 / 60)

    def rotate_y(self, x, y, z, angle):
        c = math.cos(angle)
        s = math.sin(angle)
        return (
            x * c + z * s,
            y,
            -x * s + z * c
        )

    def rotate_x(self, x, y, z, angle):
        c = math.cos(angle)
        s = math.sin(angle)
        return (
            x,
            y * c - z * s,
            y * s + z * c
        )

    def project(self, x, y, z):
        z += 5  # Move cube away from camera
        f = 300 / z
        sx = x * f + self.width / 2
        sy = y * f + self.height / 2
        return sx, sy

    def update(self, dt):
        self.angle += dt

        self.canvas.clear()

        projected = []

        for v in vertices:
            x, y, z = v
            x, y, z = self.rotate_y(x, y, z, self.angle)
            x, y, z = self.rotate_x(x, y, z, self.angle * 0.7)
            projected.append(self.project(x, y, z))

        with self.canvas:
            Color(1, 1, 1)

            for a, b in edges:
                Line(points=[
                    projected[a][0], projected[a][1],
                    projected[b][0], projected[b][1]
                ], width=1.5)


class CubeApp(App):
    def build(self):
        return CubeWidget()


CubeApp().run()
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Color, Mesh
from kivy.clock import Clock


class TestWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # IMPORTANT: use widget size
        self.bind(size=self.redraw, pos=self.redraw)

        self.redraw()

        Clock.schedule_interval(self.update, 1/60)

    def redraw(self, *args):
        self.canvas.clear()

        with self.canvas:
            Color(0, 1, 0, 1)

            w, h = self.size
            cx, cy = self.center

            # triangle in SCREEN SPACE (not OpenGL space)
            self.mesh = Mesh(
                vertices=[
                    cx, cy + 100,   # top
                    cx - 100, cy - 100,  # bottom left
                    cx + 100, cy - 100   # bottom right
                ],
                indices=[0, 1, 2],
                mode='triangles'
            )

    def update(self, dt):
        pass


class TestApp(App):
    def build(self):
        return TestWidget()


if __name__ == "__main__":
    TestApp().run()
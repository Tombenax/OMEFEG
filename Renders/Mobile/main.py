import numpy as np

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Mesh
from kivy.core.image import Image as CoreImage
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button


def load_obj_for_moderngl(file_path):
    positions = []
    normals = []
    uvs = []

    vertices = []
    indices = []

    vertex_map = {}
    index = 0

    with open(file_path, "r") as f:
        for line in f:

            if line.startswith("v "):
                _, x, y, z = line.split()
                positions.append(
                    [float(x), float(y), float(z)]
                )

            elif line.startswith("vn "):
                _, x, y, z = line.split()
                normals.append(
                    [float(x), float(y), float(z)]
                )

            elif line.startswith("vt "):
                _, u, v = line.split()
                uvs.append(
                    [float(u), float(v)]
                )

            elif line.startswith("f "):

                face = []

                for item in line.split()[1:]:

                    values = item.split("/")

                    p = int(values[0]) - 1

                    t = (
                        int(values[1]) - 1
                        if len(values) > 1 and values[1]
                        else 0
                    )

                    n = (
                        int(values[2]) - 1
                        if len(values) > 2 and values[2]
                        else 0
                    )

                    key = (p, t, n)

                    if key not in vertex_map:

                        px, py, pz = positions[p]

                        if normals:
                            nx, ny, nz = normals[n]
                        else:
                            nx, ny, nz = 0, 1, 0

                        if uvs:
                            u, v = uvs[t]
                        else:
                            u, v = 0, 0


                        vertices.extend([
                            px, py, pz,
                            nx, ny, nz,
                            u, 1 - v
                        ])

                        vertex_map[key] = index
                        index += 1


                    face.append(vertex_map[key])


                # triangulate polygon
                for i in range(1, len(face)-1):

                    indices.extend([
                        face[0],
                        face[i+1],
                        face[i]
                    ])


    return (
        np.array(vertices, dtype="f4"),
        np.array(indices, dtype="i4")
    )



class MeshObject:

    def __init__(
        self,
        obj_path,
        texture_path,
        position=(0,0,0)
    ):

        self.vertices, self.indices = load_obj_for_moderngl(
            obj_path
        )

        self.texture = CoreImage(
            texture_path
        ).texture

        self.position = position

        self.angle = 0

occupied = set()

class Camera:
    def __init__(self, position=[0,0,0], rotation=[0,0,0]):
        self.position = position
        self.rotation = rotation
        self._up = False
        self._down = False
        self._left = False
        self._right = False
        self._jump = False
        self.width = 0.3
        self.height = 1.8
        self.speed = 5

    def up(self, b):
        self._up = b

    def down(self, b):
        self._down = b

    def left(self, b):
        self._left = b

    def right(self, b):
        self._right = b

    def jump(self, b):
        self._jump = b
    
    def _move(self, dt):
        next_pos = self.position.copy()

        if self._up:
            next_pos[2] += self.speed * dt

        if self._down:
            next_pos[2] -= self.speed * dt

        if self._left:
            next_pos[0] -= self.speed * dt

        if self._right:
            next_pos[0] += self.speed * dt
        
        if self._jump:
            next_pos[1] += self.speed * dt

        print(self.collides(next_pos))

        if not self.collides(next_pos):
            self.position = next_pos

    def update(self, dt):
        self._move(dt)

    def collides(self, pos):
        px, py, pz = pos

        # player bounds
        min_x = px - self.width
        max_x = px + self.width
        min_y = py
        max_y = py + self.height
        min_z = pz - self.width
        max_z = pz + self.width

        # For blocks centered at (x, y, z), their min/max in world coords are (x-0.5, x+0.5)
        # So we adjust only x and z, not y
        x_start = int(np.floor(min_x + 0.5))
        x_end   = int(np.floor(max_x + 0.5))
        y_start = int(np.floor(min_y+0.5))
        y_end   = int(np.floor(max_y+0.5))
        z_start = int(np.floor(min_z + 0.5))
        z_end   = int(np.floor(max_z + 0.5))

        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                for z in range(z_start, z_end + 1):
                    if (x, y, z) in occupied:
                        return True

        return False

near = 0.1

class MeshWidget(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.texture = CoreImage("assets/textures/grass.png").texture

        self.objects = []

        for j in range(10):
            for i in range(10):
                self.objects.append(MeshObject("assets/models/block.obj", "assets/textures/grass.png", position=(i, 0, j+10)))
                occupied.add(self.objects[-1].position)


        with self.canvas:
            Color(1,1,1,1)

            self.mesh = Mesh(
                vertices=[],
                indices=[],
                fmt=[
                    (b"vPosition", 2, "float"),
                    (b"vTexCoords0", 2, "float"),
                ],
                mode="triangles",
            )

            self.mesh.texture = self.texture

    def project(self, x, y, z):

        distance = 0
        scale = 250


        factor = scale / (z + distance)

        camera_z = z + distance

        if camera_z <= near:
            return (0, 0)
                    
        return (
            x * factor + self.width / 2,
            y * factor + self.height / 2
        )


    def update(self, dt, camera):

        all_vertices = []
        all_indices = []

        triangles = []

        vertex_offset = 0


        for obj in self.objects:

            obj.angle += dt


            transformed_z = []


            stride = 8


            # transform vertices
            for i in range(0, len(obj.vertices), stride):

                x = obj.vertices[i]
                y = obj.vertices[i+1]
                z = obj.vertices[i+2]

                u = obj.vertices[i+6]
                v = obj.vertices[i+7]


                # object position
                x += obj.position[0]
                y += obj.position[1]
                z += obj.position[2]

                #camera position
                x -= camera.position[0]
                y -= camera.position[1]
                z -= camera.position[2]

                #adjust for centre
                x -= 0.5
                y -= 0.5
                z -= 0.5

                transformed_z.append(z)


                sx,sy = self.project(
                    x,y,z
                )


                all_vertices.extend([
                    sx,
                    sy,
                    u,
                    v
                ])



            # collect triangles
            for i in range(0,len(obj.indices),3):

                a = obj.indices[i]
                b = obj.indices[i+1]
                c = obj.indices[i+2]


                depth = (
                    transformed_z[a] +
                    transformed_z[b] +
                    transformed_z[c]
                ) / 3


                triangles.append(
                    (
                        depth,
                        vertex_offset+a,
                        vertex_offset+b,
                        vertex_offset+c
                    )
                )


            vertex_offset += len(obj.vertices)//8



        # far -> near
        triangles.sort(reverse=True)


        for _,a,b,c in triangles:

            all_indices.extend([
                a,b,c
            ])



        self.mesh.vertices = all_vertices
        self.mesh.indices = all_indices


class RootWidget(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 3D renderer
        self.renderer = MeshWidget()
        self.add_widget(self.renderer)

        self.camera = Camera()

        # UI button on top
        self.up = Button(
            text="/\\\n |",
            size_hint=(None, None),
            size=(50, 50),
            pos=(50, 100)
        )

        self.up.bind(on_press=lambda x: self.camera.up(True), on_release=lambda x: self.camera.up(False))

        self.down = Button(
            text=" |\n\\/",
            size_hint=(None, None),
            size=(50, 50),
            pos=(50, 0)
        )

        self.down.bind(on_press=lambda x: self.camera.down(True), on_release=lambda x: self.camera.down(False))

        self.left = Button(
            text="<--",
            size_hint=(None, None),
            size=(50, 50),
            pos=(0, 50)
        )

        self.left.bind(on_press=lambda x: self.camera.left(True), on_release=lambda x: self.camera.left(False))

        self.right_ = Button(
            text="-->",
            size_hint=(None, None),
            size=(50, 50),
            pos=(100, 50)
        )

        self.right_.bind(on_press=lambda x: self.camera.right(True), on_release=lambda x: self.camera.right(False))

        self.jump = Button(
            text="Jump",
            size_hint=(None, None),
            size=(50, 50),
            pos=(50, 50)
        )

        self.jump.bind(on_press=lambda x: self.camera.jump(True), on_release=lambda x: self.camera.jump(False))

        self.add_widget(self.up)
        self.add_widget(self.down)
        self.add_widget(self.left)
        self.add_widget(self.right_)
        self.add_widget(self.jump)

        Clock.schedule_interval(
            lambda x: self.renderer.update(x, self.camera),
            1/60
        )

        Clock.schedule_interval(
            self.camera.update,
            1/60
        )

class MeshApp(App):

    def build(self):
        return RootWidget()



if __name__ == "__main__":
    MeshApp().run()
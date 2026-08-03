from pyrr import Matrix44
import numpy as np

class InstancedModel:

    def __init__(
        self,
        ctx,
        prog,
        vertices,
        indices,
        tex_mapping,
        iscnk=False
    ):

        self.ctx = ctx
        self.prog = prog

        self.iscnk = iscnk
        self.tex_mapping = tex_mapping

        # =========================================================
        # ALL INSTANCES
        # =========================================================

        self.models = np.zeros((0, 4, 4), dtype='f4')

        # texture layers
        self.layers = np.zeros((0,), dtype='i4')

        # enabled / disabled mask
        self.active = np.zeros((0,), dtype=bool)

        # =========================================================
        # VISIBLE CACHE (GPU upload only visible instances)
        # =========================================================

        self.visible_models = np.zeros((0, 4, 4), dtype='f4')
        self.visible_layers = np.zeros((0,), dtype='i4')

        self.visible_count = 0

        # if True -> rebuild GPU buffers
        self.dirty = True

        # =========================================================
        # GPU BUFFERS
        # =========================================================

        self.vbo = ctx.buffer(vertices.tobytes())
        self.ibo = ctx.buffer(indices.tobytes())

        # reserve some memory initially
        self.instance_buffer = ctx.buffer(reserve=64 * 1024)
        self.layer_buffer = ctx.buffer(reserve=4 * 1024)

        # =========================================================
        # VAO
        # =========================================================

        self.vao = ctx.vertex_array(
            prog,
            [
                (
                    self.vbo,
                    '3f 3f 2f',
                    'in_position',
                    'in_normal',
                    'in_uv'
                ),
                (
                    self.instance_buffer,
                    '16f/i',
                    'instance_model'
                ),
                (
                    self.layer_buffer,
                    '1i/i',
                    'instance_layer'
                ),
            ],
            self.ibo
        )

    # =============================================================
    # ADD INSTANCES
    # =============================================================

    def move_instance(self, index, position:list[int]):
        if not (0 <= index < len(self.models)):
            return

        model = self.models[index].copy()

        # Preserve rotation/scale, replace translation
        model[3, 0] = position[0]
        model[3, 1] = position[1]
        model[3, 2] = position[2]

        self.models[index] = model
        self.dirty = True

    
    def add_instances(
        self,
        positions,
        texture_names,
        rotations=None,
        areInts=False,
        active=True
    ):

        new_models = []

        for i, pos in enumerate(positions):

            translation = Matrix44.from_translation(
                pos,
                dtype='f4'
            )

            if rotations is not None:

                rx, ry, rz = rotations[i]

                rot_x = Matrix44.from_x_rotation(rx, dtype='f4')
                rot_y = Matrix44.from_y_rotation(ry, dtype='f4')
                rot_z = Matrix44.from_z_rotation(rz, dtype='f4')

                rotation = rot_y * rot_x * rot_z

                model = translation * rotation

            else:
                model = translation

            new_models.append(model)

        new_models = np.array(new_models, dtype='f4')

        # append matrices
        self.models = np.vstack((self.models, new_models))

        # append active flags
        if active:
            self.active = np.hstack((
                self.active,
                np.ones(len(new_models), dtype=bool)
            ))
        else:
            self.active = np.hstack((
                self.active,
                np.zeros(len(new_models), dtype=bool)
            )) 

        # ---------------------------------------------------------
        # layers
        # ---------------------------------------------------------

        if texture_names is None:
            texture_names = []

        if isinstance(texture_names, (list, tuple)) and len(texture_names) > 0:
            if len(texture_names) == 1 and isinstance(texture_names[0], (list, tuple)):
                texture_names = list(texture_names[0])
            elif all(isinstance(item, (list, tuple)) for item in texture_names):
                texture_names = [item[0] if len(item) > 0 else "" for item in texture_names]

        if not isinstance(texture_names, (list, tuple)):
            texture_names = [texture_names]

        if len(texture_names) == 1 and len(positions) > 1:
            texture_names = texture_names * len(positions)

        layers = []

        if not areInts:
            for tex in texture_names:
                if isinstance(tex, (list, tuple)):
                    tex = tex[0] if len(tex) > 0 else ""

                if hasattr(tex, 'lower'):
                    layer = self.tex_mapping.get(tex.lower())
                    if layer is None:
                        layer = self.tex_mapping.get(tex)
                else:
                    layer = self.tex_mapping.get(tex)

                if layer is None:
                    layer = 0

                layers.append(layer)
        else:
            layers = texture_names

        self.layers = np.hstack((
            self.layers,
            np.array(layers, dtype='i4')
        ))

        self.dirty = True

    # =============================================================
    # ENABLE / DISABLE
    # =============================================================

    def disable_instance(self, index):

        if 0 <= index < len(self.active):

            self.active[index] = False
            self.dirty = True

    def disable_instances(self, indices):
        try:
            self.active[indices] = False
            self.dirty = True
        except:
            pass

    def enable_instance(self, index):

        if 0 <= index < len(self.active):

            self.active[index] = True
            self.dirty = True

    def enable_instances(self, indices):
        try:
            self.active[indices] = True
            self.dirty = True
        except:
            pass

    def toggle_instance(self, index):

        if 0 <= index < len(self.active):

            self.active[index] = not self.active[index]
            self.dirty = True

    # =============================================================
    # REMOVE INSTANCE
    # =============================================================

    def remove_instance(self, position:tuple):
        index = self.find_instance_at_position(position)

        if not (0 <= index < len(self.models)):
            return

        self.models = np.delete(
            self.models,
            index,
            axis=0
        )

        self.active = np.delete(
            self.active,
            index
        )

        self.layers = np.delete(
            self.layers,
            index
        )

        self.dirty = True

        return index

    # =============================================================
    # ROTATION
    # =============================================================

    def rotate_instance(self, index, rotation):

        if not (0 <= index < len(self.models)):
            return

        rx, ry, rz = rotation

        rot_x = Matrix44.from_x_rotation(rx, dtype='f4')
        rot_y = Matrix44.from_y_rotation(ry, dtype='f4')
        rot_z = Matrix44.from_z_rotation(rz, dtype='f4')

        rotation_matrix = rot_z * rot_y * rot_x

        model = self.models[index].copy()

        translation = Matrix44.from_translation(
            model[3][:3],
            dtype='f4'
        )

        self.models[index] = translation * rotation_matrix

        self.dirty = True

    # =============================================================
    # UPDATE GPU BUFFERS
    # =============================================================

    def update_visible_buffers(self):
        # ---------------------------------------------------------
        # visible models
        # ---------------------------------------------------------

        self.visible_models = self.models

        if len(self.visible_models) > 0:

            model_bytes = self.visible_models.astype('f4').tobytes()

            self.instance_buffer.orphan(len(model_bytes))
            self.instance_buffer.write(model_bytes)

        # ---------------------------------------------------------
        # visible layers
        # ---------------------------------------------------------

        self.visible_layers = self.layers

        if len(self.visible_layers) > 0:
            layer_bytes = self.visible_layers.astype('i4').tobytes()
            self.layer_buffer.orphan(len(layer_bytes))
            self.layer_buffer.write(layer_bytes)

        self.visible_count = len(self.visible_models)

        self.dirty = False

    # =============================================================
    # RENDER
    # =============================================================

    def render(self):

        if self.dirty:
            self.update_visible_buffers()

        if self.visible_count == 0:
            return

        self.vao.render(instances=self.visible_count)

    # =============================================================
    # GET POSITION
    # =============================================================

    def get_instance_position(self, index):

        if not (0 <= index < len(self.models)):
            return None

        return tuple(self.models[index][3][:3])

    # =============================================================
    # FIND INSTANCE BY POSITION
    # =============================================================

    def find_instance_at_position(self, position):

        px, py, pz = position

        for i, model in enumerate(self.models):

            mx, my, mz = model[3][:3]

            if (
                int(mx) == int(px) and
                int(my) == int(py) and
                int(mz) == int(pz)
            ):
                return i

        return -1
    
    def reset(self):
        self.models = np.zeros((0, 4, 4), dtype='f4')
        self.layers = np.zeros((0,), dtype='i4')
        self.active = np.zeros((0,), dtype=bool)
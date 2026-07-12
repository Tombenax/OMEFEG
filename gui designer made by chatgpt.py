import glfw
import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1280
HEIGHT = 720

# -------------------------
# SHADERS (same as yours)
# -------------------------

GUI_VERTEX = """
#version 330
in vec2 in_pos;
in vec2 instance_pos;
in vec2 instance_size;
in vec3 instance_color;

out vec2 v_local;
out vec2 v_size;
out vec3 v_color;

void main() {
    vec2 pos = in_pos * instance_size + instance_pos;
    gl_Position = vec4(pos, 0.0, 1.0);

    v_local = in_pos;
    v_size = instance_size;
    v_color = instance_color;
}
"""

GUI_FRAGMENT = """
#version 330
in vec2 v_local;
in vec2 v_size;
in vec3 v_color;

out vec4 fragColor;

void main() {
    fragColor = vec4(v_color, 1.0);
}
"""

TEXT_VERTEX = """
#version 330
in vec2 in_pos;
in vec2 in_uv;

in vec2 instance_pos;
in vec2 instance_scale;
in vec4 instance_uv;
in vec3 instance_color;

out vec2 v_uv;
out vec3 v_color;

void main() {
    vec2 pos = in_pos * instance_scale + instance_pos;
    gl_Position = vec4(pos, 0.0, 1.0);

    v_uv = mix(instance_uv.xy, instance_uv.zw, in_uv);
    v_color = instance_color;
}
"""

TEXT_FRAGMENT = """
#version 330
in vec2 v_uv;
in vec3 v_color;
out vec4 fragColor;

uniform sampler2D textTexture;

void main() {
    vec4 sampled = texture(textTexture, v_uv);
    if (sampled.a < 0.1) discard;
    fragColor = vec4(v_color,1.0) * sampled;
}
"""

# -------------------------
# SIMPLE INSTANCED GUI
# -------------------------

class InstancedGui:
    def __init__(self, ctx, prog):
        self.ctx = ctx
        self.prog = prog

        vertices = np.array([
            [-0.5, -0.5],
            [ 0.5, -0.5],
            [ 0.5,  0.5],
            [-0.5,  0.5],
        ], dtype='f4')

        indices = np.array([0,1,2, 0,2,3], dtype='i4')

        self.vbo = ctx.buffer(vertices.tobytes())
        self.ibo = ctx.buffer(indices.tobytes())

        self.instance_data = np.zeros((0, 7), dtype='f4')
        self.instance_buffer = ctx.buffer(reserve=100 * 7 * 4)

        self.vao = ctx.vertex_array(
            prog,
            [
                (self.vbo, '2f', 'in_pos'),
                (self.instance_buffer, '2f 2f 3f/i',
                 'instance_pos', 'instance_size', 'instance_color')
            ],
            self.ibo
        )

    def add(self, pos, size, color):
        new = np.array([[pos[0], pos[1], size[0], size[1],
                         color[0], color[1], color[2]]], dtype='f4')

        self.instance_data = np.vstack((self.instance_data, new))
        self.upload()

    def update(self, index, pos, size):
        self.instance_data[index][:4] = [pos[0], pos[1], size[0], size[1]]
        self.upload()

    def upload(self):
        self.instance_buffer.orphan(self.instance_data.nbytes)
        if len(self.instance_data) > 0:
            self.instance_buffer.write(self.instance_data.tobytes())

    def render(self):
        if len(self.instance_data) > 0:
            self.vao.render(instances=len(self.instance_data))


# -------------------------
# TEXT SYSTEM (MINIMAL)
# -------------------------

class SimpleText:
    def __init__(self, ctx, prog):
        self.ctx = ctx
        self.prog = prog

        font = ImageFont.truetype("assets/PressStart2P-Regular.ttf", 16)

        img = Image.new("RGBA", (512, 512), (0,0,0,0))
        draw = ImageDraw.Draw(img)

        self.charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:.- "
        self.grid = 16
        cell = 32

        for i, c in enumerate(self.charset):
            x = (i % self.grid) * cell
            y = (i // self.grid) * cell
            draw.text((x+4, y+4), c, font=font, fill=(255,255,255))

        img = img.transpose(Image.FLIP_TOP_BOTTOM)

        self.tex = ctx.texture(img.size, 4, img.tobytes())
        self.tex.filter = (moderngl.NEAREST, moderngl.NEAREST)

        vertices = np.array([
            [-0.5, -0.5, 0, 0],
            [ 0.5, -0.5, 1, 0],
            [ 0.5,  0.5, 1, 1],
            [-0.5,  0.5, 0, 1],
        ], dtype='f4')

        indices = np.array([0,1,2, 0,2,3], dtype='i4')

        self.vbo = ctx.buffer(vertices.tobytes())
        self.ibo = ctx.buffer(indices.tobytes())

        self.data = []

    def draw_text(self, text, pos):
        # very simple (no instancing here for brevity)
        pass


# -------------------------
# MAIN DESIGNER
# -------------------------

def to_gl_coords(mx, my):
    x = (mx / WIDTH) * 2 - 1
    y = 1 - (my / HEIGHT) * 2
    return x, y


def point_in_rect(px, py, x, y, sx, sy):
    return (x - sx/2 <= px <= x + sx/2 and
            y - sy/2 <= py <= y + sy/2)


def detect_resize_zone(px, py, x, y, sx, sy, margin=0.03):
    left   = abs(px - (x - sx/2)) < margin
    right  = abs(px - (x + sx/2)) < margin
    top    = abs(py - (y + sy/2)) < margin
    bottom = abs(py - (y - sy/2)) < margin

    if left and top: return "top_left"
    if right and top: return "top_right"
    if left and bottom: return "bottom_left"
    if right and bottom: return "bottom_right"
    if left: return "left"
    if right: return "right"
    if top: return "top"
    if bottom: return "bottom"
    return None


def main():
    glfw.init()
    window = glfw.create_window(WIDTH, HEIGHT, "GUI Designer", None, None)
    glfw.make_context_current(window)

    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)

    gui_prog = ctx.program(vertex_shader=GUI_VERTEX, fragment_shader=GUI_FRAGMENT)
    gui = InstancedGui(ctx, gui_prog)

    selected = -1
    dragging = False
    resize_mode = None

    prev_mouse = (0, 0)

    while not glfw.window_should_close(window):
        glfw.poll_events()

        mx, my = glfw.get_cursor_pos(window)
        x, y = to_gl_coords(mx, my)

        dx = x - prev_mouse[0]
        dy = y - prev_mouse[1]
        prev_mouse = (x, y)

        mouse_pressed = glfw.get_mouse_button(window, glfw.MOUSE_BUTTON_LEFT) == glfw.PRESS

        # -------------------------
        # CLICK START
        # -------------------------
        if mouse_pressed and not dragging:
            selected = -1
            resize_mode = None

            # check existing elements
            for i in reversed(range(len(gui.instance_data))):
                px, py, sx, sy = gui.instance_data[i][:4]

                if point_in_rect(x, y, px, py, sx, sy):
                    selected = i
                    resize_mode = detect_resize_zone(x, y, px, py, sx, sy)
                    dragging = True
                    break

            # if none selected → create new
            if selected == -1:
                gui.add((x, y), (0.2, 0.1), (0.2, 0.6, 1.0))
                selected = len(gui.instance_data) - 1
                dragging = True

        # -------------------------
        # DRAG / RESIZE
        # -------------------------
        if mouse_pressed and dragging and selected != -1:
            px, py, sx, sy = gui.instance_data[selected][:4]

            if resize_mode is None:
                # MOVE
                px += dx
                py += dy

            else:
                # RESIZE
                if "left" in resize_mode:
                    sx -= dx
                    px += dx / 2
                if "right" in resize_mode:
                    sx += dx
                    px += dx / 2
                if "top" in resize_mode:
                    sy += dy
                    py += dy / 2
                if "bottom" in resize_mode:
                    sy -= dy
                    py += dy / 2

                # prevent negative size
                sx = max(0.02, sx)
                sy = max(0.02, sy)

            gui.update(selected, (px, py), (sx, sy))

        if not mouse_pressed:
            dragging = False
            resize_mode = None

        # -------------------------
        # DELETE
        # -------------------------
        if selected != -1 and glfw.get_key(window, glfw.KEY_DELETE) == glfw.PRESS:
            gui.instance_data = np.delete(gui.instance_data, selected, axis=0)
            gui.upload()
            selected = -1

        # -------------------------
        # PRINT CODE
        # -------------------------
        if glfw.get_key(window, glfw.KEY_P) == glfw.PRESS:
            print("\n--- GENERATED GUI CODE ---")
            for inst in gui.instance_data:
                px, py, sx, sy = inst[:4]
                print(f'gui.add(pos=({px:.2f}, {py:.2f}), size=({sx:.2f}, {sy:.2f}), color=(0,0,0), callback=...)')

        # -------------------------
        # COLOR FEEDBACK
        # -------------------------
        for i in range(len(gui.instance_data)):
            if i == selected:
                gui.instance_data[i][4:] = [1.0, 0.3, 0.3]  # red
            else:
                gui.instance_data[i][4:] = [0.2, 0.6, 1.0]

        gui.upload()

        # -------------------------
        # RENDER
        # -------------------------
        ctx.clear(0.08, 0.08, 0.1)
        gui.render()
        glfw.swap_buffers(window)

    glfw.terminate()


if __name__ == "__main__":
    main()
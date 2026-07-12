#version 330

in vec2 in_pos;

in vec2 instance_pos;
in vec2 instance_size;
in vec3 instance_color;

out vec2 v_size;
out vec3 v_color;
out vec2 v_local;

void main() {
    vec2 pos = in_pos * instance_size + instance_pos;
    gl_Position = vec4(pos, 0.0, 1.0);

    v_color = instance_color;
    v_local = in_pos;
    v_size = instance_size;
}

#version 330

in vec3 v_color;
in vec2 v_local;
in vec2 v_size;

out vec4 fragColor;

uniform float outline_thickness;

void main() {
    vec2 scaled = v_local * v_size;

    float edge = min(
        min(abs(scaled.x - v_size.x * 0.5), abs(scaled.x + v_size.x * 0.5)),
        min(abs(scaled.y - v_size.y * 0.5), abs(scaled.y + v_size.y * 0.5))
    );

    if (edge < outline_thickness) {
        fragColor = vec4(1.0);
    } else {
        fragColor = vec4(v_color, 1.0);
    }
}

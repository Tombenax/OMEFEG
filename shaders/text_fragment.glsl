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

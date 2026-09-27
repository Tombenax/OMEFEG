#version 330
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in mat4 instance_model;
in int instance_layer;

uniform mat4 projection;
uniform mat4 view;

out vec3 v_normal;
out vec3 v_fragPos;
out vec2 v_uv;
flat out int v_layer;

void main() {
    vec4 worldPos = instance_model * vec4(in_position, 1.0);
    gl_Position = projection * view * worldPos;

    v_fragPos = worldPos.xyz;
    // Chunk dummies use an identity instance matrix; same cheap path as
    // the blocks shader (no per-vertex inverse).
    v_normal = mat3(instance_model) * in_normal;
    v_uv = in_uv;
    v_layer = instance_layer;
}

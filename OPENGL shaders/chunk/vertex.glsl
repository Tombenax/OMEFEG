#version 410
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in dmat4 instance_model;
in int instance_layer;

uniform dmat4 projection;
uniform dmat4 view;

out vec3 v_normal;
out vec3 v_fragPos;
out vec2 v_uv;
flat out int v_layer;

uniform dvec3 viewPos;

void main() {
    dvec4 worldPos = instance_model * dvec4(dvec3(in_position), 1.0);
    gl_Position = vec4(projection * view * worldPos);

    v_fragPos = vec3(worldPos.xyz - viewPos);
    v_normal = vec3(dmat3(transpose(inverse(instance_model))) * dvec3(in_normal));
    v_uv = in_uv;
    v_layer = instance_layer;
}

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

uniform float TEXTURE_W;
uniform float TEXTURE_H;

uniform float ATLAS_W;
uniform float ATLAS_H;

void main() {
    vec4 worldPos = instance_model * vec4(in_position, 1.0);
    gl_Position = projection * view * worldPos;

    v_fragPos = worldPos.xyz;
    v_normal = mat3(transpose(inverse(instance_model))) * in_normal;

    // Number of 64x64 textures across the atlas
    int columns = int(ATLAS_W / TEXTURE_W);

    // Find which tile the index refers to
    int column = instance_layer % columns;
    int row = instance_layer / columns;

    // Size of one tile in UV coordinates
    vec2 tileSize = vec2(
        TEXTURE_W / ATLAS_W,
        TEXTURE_H / ATLAS_H
    );

    // Position of this tile in UV coordinates
    vec2 tileOffset = vec2(
        float(column) * tileSize.x,
        float(row) * tileSize.y
    );

    // Convert model UV (0..1) into the selected atlas region
    v_uv = tileOffset + in_uv * tileSize;

    // The atlas only has one array layer
    v_layer = 0;
}

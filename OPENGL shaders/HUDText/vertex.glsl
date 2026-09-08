#version 330

in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in mat4 instance_model;
in int instance_layer;

uniform vec2 screenSize;
uniform float TEXTURE_W;
uniform float TEXTURE_H;

uniform float ATLAS_W;
uniform float ATLAS_H;

out vec2 v_uv;

void main() {
	int columns = max(int(ATLAS_W / TEXTURE_W), 1);
	int column = instance_layer % columns;
	int row = instance_layer / columns;

	vec2 tileSize = vec2(
		TEXTURE_W / ATLAS_W,
		TEXTURE_H / ATLAS_H
	);

	v_uv = vec2(column, row) * tileSize + vec2(in_uv.x, 1.0 - in_uv.y) * tileSize;

	vec2 pixelPosition = vec2(
		instance_model[3].x + instance_model[3].z * TEXTURE_W + in_position.z * TEXTURE_W,
		instance_model[3].y + in_position.y * TEXTURE_H
	);

	vec2 clipPosition = vec2(
		pixelPosition.x / screenSize.x * 2.0 - 1.0,
		1.0 - pixelPosition.y / screenSize.y * 2.0
	);

	gl_Position = vec4(clipPosition, in_normal.x * 0.000001, 1.0);
}

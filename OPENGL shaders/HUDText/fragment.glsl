#version 330

in vec2 v_uv;

out vec4 fragColor;

uniform sampler2DArray atlasArray;

void main() {
	vec4 glyph = texture(atlasArray, vec3(v_uv, 0.0));

	if (glyph.a < 0.1)
		discard;

	fragColor = glyph;
}

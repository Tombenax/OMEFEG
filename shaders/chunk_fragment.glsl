#version 330

in vec3 v_normal;
in vec3 v_fragPos;
in vec2 v_uv;
flat in int v_layer;

out vec4 fragColor;

uniform sampler2DArray atlasArray;
uniform vec3 lightPos;
uniform vec3 viewPos;

void main() {
    vec4 tex = texture(atlasArray, vec3(v_uv, v_layer));

    if (tex.a < 0.1)
        discard;

    vec3 color = tex.rgb;
    vec3 norm = normalize(v_normal);

    vec3 lightDir = normalize(lightPos - v_fragPos);
    float diff = max(dot(norm, lightDir), 0.0);

    vec3 ambient = 0.4 * color;
    vec3 diffuse = diff * color;

    vec3 viewDir = normalize(viewPos - v_fragPos);
    vec3 reflectDir = reflect(-lightDir, norm);
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 16.0);

    fragColor = vec4(ambient + diffuse + spec, tex.a);
}

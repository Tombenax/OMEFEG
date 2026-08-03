#version 450

layout(location = 0) in vec3 vNormal;
layout(location = 1) in vec3 vFragPos;
layout(location = 2) in vec2 vUV;
layout(location = 3) flat in int vLayer;

layout(location = 0) out vec4 fragColor;

layout(set = 1, binding = 0) uniform sampler2DArray atlasArray;

layout(set = 1, binding = 1) uniform Lighting
{
    vec3 lightPos;
    vec3 viewPos;
} lighting;


void main()
{
    //vec4 tex = texture(atlasArray, vec3(vUV, vLayer));

    //if (tex.a < 0.1)
    //    discard;


    vec3 color = vec3(1.0, 1.0, 1.0);
    vec3 norm = normalize(vNormal);


    vec3 lightDir = normalize(lighting.lightPos - vFragPos);

    float diff = max(dot(norm, lightDir), 0.0);


    vec3 ambient = 0.4 * color;
    vec3 diffuse = diff * color;


    vec3 viewDir = normalize(lighting.viewPos - vFragPos);
    vec3 reflectDir = reflect(-lightDir, norm);

    float spec = pow(
        max(dot(viewDir, reflectDir), 0.0),
        16.0
    );


    fragColor = vec4(
        ambient + diffuse + spec,
        1.0
    );
}
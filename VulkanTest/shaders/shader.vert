#version 450

layout(location = 0) in vec3 inPosition;
layout(location = 1) in vec3 inNormal;
layout(location = 2) in vec2 inUV;

// mat4 occupies 4 consecutive locations
layout(location = 3) in mat4 instanceModel;
layout(location = 7) in int instanceLayer;

layout(set = 0, binding = 0) uniform CameraUBO
{
    mat4 projection;
    mat4 view;
} camera;


layout(location = 0) out vec3 vNormal;
layout(location = 1) out vec3 vFragPos;
layout(location = 2) out vec2 vUV;
layout(location = 3) flat out int vLayer;


void main()
{
    vec4 worldPos = instanceModel * vec4(inPosition, 1.0);

    gl_Position = camera.projection * camera.view * instanceModel * vec4(inPosition, 1.0);

    vFragPos = worldPos.xyz;
    vNormal = mat3(transpose(inverse(instanceModel))) * inNormal;
    vUV = inUV;
    vLayer = instanceLayer;
}
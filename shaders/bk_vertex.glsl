#version 330 core

uniform vec4 uColor;
out vec4 vColor;

void main()
{
    vec2 corner = vec2(
        (gl_VertexID == 0 || gl_VertexID == 2) ? -1.0 : 1.0,
        (gl_VertexID == 0 || gl_VertexID == 1) ? -1.0 : 1.0
    );

    gl_Position = vec4(corner, 0.0, 1.0);
    vColor = uColor;
}

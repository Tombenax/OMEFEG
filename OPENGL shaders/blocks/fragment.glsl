#version 330

in vec3 v_normal;
in vec3 v_fragPos;
in vec2 v_uv;
flat in int v_layer;

out vec4 fragColor;

uniform sampler2DArray atlasArray;
uniform sampler3D blockOccupancy;
uniform vec3 lightPositions[16];
uniform vec4 lightColors[16];
uniform int lightCount;
uniform vec3 worldMin;
uniform ivec3 worldSize;
uniform vec3 viewPos;
// Master shadow switch from graphics_settings["shadows"] in OMEFEG.py
// (uploaded by Render.py): 1 = shadow/sky raymarch, 0 = plain lit.
uniform int shadowsEnabled;

uniform bool enable_funky_shaders;
uniform int frame;
uniform float chance;

uint pcg(uint v)
{
    v = v * 747796405u + 2891336453u;
    v = ((v >> ((v >> 28u) + 4u)) ^ v) * 277803737u;
    return (v >> 22u) ^ v;
}

float rand(vec2 pixel, uint frame)
{
    uint seed =
        uint(pixel.x) * 1973u +
        uint(pixel.y) * 9277u +
        frame * 26699u;

    return float(pcg(seed)) / 4294967295.0;
}

float lightTransmittance(vec3 from, vec3 to)
{
    vec3 ray = to - from;
    float maxDistance = length(ray);
    if (maxDistance <= 0.001)
        return 1.0;

    vec3 direction = ray / maxDistance;
    vec3 start = from + direction * 0.001;
    // worldMin is the minimum *corner* of the occupancy volume
    // (block minimum - 0.5), because blocks are centered cubes
    // spanning [P-0.5, P+0.5]. cell = floor(start - worldMin) then maps
    // block P to texel P - minimum, matching update_block_occupancy.
    vec3 localStart = start - worldMin;
    ivec3 cell = ivec3(floor(localStart));

    bool startOutside =
        any(lessThan(cell, ivec3(0))) || any(greaterThanEqual(cell, worldSize));

    // Occupancy encoding (see update_block_occupancy): 255 = solid (full
    // shadow), 127 = light filter such as leaves/water (0.5x each, so a
    // canopy gives dappled shade instead of a black hole). Thresholds sit
    // between the exact normalized values (0.0 / 0.498 / 1.0).
    // The origin voxel itself can occlude (e.g. a hidden interior face
    // whose bias point sits inside the neighbouring block). Surface
    // origins on the outer skin of the world sit just outside the volume
    // (0.02 past the face), so only test when inside: rays starting
    // outside must be allowed to march *into* the volume below.
    float transmittance = 1.0;
    if (!startOutside) {
        float firstHit = texelFetch(blockOccupancy, cell, 0).r;
        if (firstHit > 0.75)
            return 0.0;
        else if (firstHit > 0.25)
            transmittance = 0.5;
    }

    ivec3 cellStep = ivec3(sign(direction));
    vec3 nextBoundary = vec3(cell) + step(vec3(0.0), direction);
    // Division by zero is undefined in GLSL, and axis-aligned rays
    // (light straight above) are the common case, so use a safe inverse.
    vec3 invDir = vec3(
        abs(direction.x) > 1e-8 ? 1.0 / direction.x : 1e8,
        abs(direction.y) > 1e-8 ? 1.0 / direction.y : 1e8,
        abs(direction.z) > 1e-8 ? 1.0 / direction.z : 1e8
    );
    vec3 tMax = (nextBoundary - localStart) * invDir;
    vec3 tDelta = abs(invDir);
    float travelled = 0.0;

    // 96 DDA steps cover ~96 voxels: more than the max light distance
    // in-game (render distance 3 => ~70 voxels corner to light at y=50).
    // Was 256 (2.7x the cost) with identical visuals.
    for (int stepIndex = 0; stepIndex < 96; stepIndex++) {
        if (tMax.x < tMax.y && tMax.x < tMax.z) {
            cell.x += cellStep.x;
            travelled = tMax.x;
            tMax.x += tDelta.x;
        } else if (tMax.y < tMax.z) {
            cell.y += cellStep.y;
            travelled = tMax.y;
            tMax.y += tDelta.y;
        } else {
            cell.z += cellStep.z;
            travelled = tMax.z;
            tMax.z += tDelta.z;
        }

        if (travelled >= maxDistance)
            break;
        // Do not break when outside: an outer-skin surface origin starts
        // just outside the volume and the ray may enter it on the next
        // axis step (e.g. corner voxels). Just skip the occupancy test
        // until the ray is inside; travelled/maxDistance still bounds it.
        if (any(lessThan(cell, ivec3(0))) || any(greaterThanEqual(cell, worldSize)))
            continue;
        float hit = texelFetch(blockOccupancy, cell, 0).r;
        if (hit > 0.75)
            return 0.0;
        else if (hit > 0.25)
            transmittance *= 0.5;
    }

    return transmittance;
}

float lightVisibility(vec3 surface, vec3 normal, vec3 lightPosition)
{
    // Blocks are centered cubes (block.obj spans +/-0.5), so cast from
    // just above the surface. Casting from floor(surface) + 0.5 starts
    // 0.5 deep inside the solid (over-shadowing grazing angles) and
    // mis-attributes -X/-Y/-Z faces to the neighbouring voxel.
    vec3 origin = surface + normal * 0.02;
    return lightTransmittance(origin, lightPosition);
}

float skyVisibility(vec3 surface, vec3 normal)
{
    // Sky/ambient occlusion: the constant ambient term below is what kept
    // closed boxes readable (0.35 everywhere). Cast straight up to the sky;
    // inside a closed box the ceiling blocks it -> ambient 0 -> black.
    // Outdoors with open sky above it misses -> ambient stays as before.
    // Note: downward faces always report 0 (own block sits between them
    // and the sky), which is correct for sky light; they get no sky.
    vec3 origin = surface + normal * 0.02;
    // Short range on purpose: a full march to the sky costs a second
    // 96-step DDA per fragment (this halved FPS). Cover within ~8 blocks
    // (ceilings, canopies) is what darkens ambient; distant geometry is
    // the direct light's job. travelled>=maxDistance exits after ~8 voxels.
    vec3 skyPoint = origin + vec3(0.0, 1.0, 0.0) * 8.0;
    return lightTransmittance(origin, skyPoint);
}

void main() {
    // Always sample layer 0 because the whole atlas is layer 0
    vec4 tex = texture(atlasArray, vec3(v_uv, 0));

    if (tex.a < 0.1)
        discard;

    // PCG rand every fragment even when the effect is off was pure ALU
    // waste; only roll when funky shaders are enabled.
    if (enable_funky_shaders) {
        float r = rand(gl_FragCoord.xy, uint(frame));
        if (r <= chance)
            discard;
    }

    vec3 color = tex.rgb;
    vec3 norm = normalize(v_normal);

    // Ambient is sky light, so occlude it like direct light. Without this,
    // a fully enclosed box still gets 0.35 everywhere (readable, grey).
    // Keep ~30% when occluded: pure 0 made every overhang/tree underside
    // pitch black. Tune 0.3 to taste (0.0 = black holes, 1.0 = no AO).
    float skyVis = 1.0;
    if (shadowsEnabled == 1) {
        skyVis = skyVisibility(v_fragPos, norm);
    }
    vec3 result = 0.35 * color * mix(0.3, 1.0, skyVis);
    vec3 viewDir = normalize(viewPos - v_fragPos);

    for (int i = 0; i < 16; i++) {
        if (i >= lightCount)
            break;

        vec3 lightVector = lightPositions[i] - v_fragPos;
        float distanceToLight = length(lightVector);
        vec3 lightDir = lightVector / max(distanceToLight, 0.0001);
        float diff = max(dot(norm, lightDir), 0.0);
        if (diff <= 0.0)
            continue;
        float attenuation = 1.0 / (1.0 + 0.002 * distanceToLight + 0.0001 * distanceToLight * distanceToLight);
        // Skip the 96-step shadow ray when this light contributes
        // nothing visible (far + grazing angle). No visual change.
        if (diff * attenuation < 0.003)
            continue;
        vec3 reflectDir = reflect(-lightDir, norm);
        float spec = pow(max(dot(viewDir, reflectDir), 0.0), 16.0);

        float visibility = 1.0;
        if (shadowsEnabled == 1) {
            visibility = lightVisibility(v_fragPos, norm, lightPositions[i]);
        }
        result += (diff * color + spec) * lightColors[i].rgb * attenuation * visibility;
    }

    fragColor = vec4(result, tex.a);
}

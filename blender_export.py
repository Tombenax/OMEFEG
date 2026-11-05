"""Export the current Blender scene to an OMEFEG ``.omefeg`` model archive.

Run with:
    blender --background --python blender_export.py -- --input source.blend --output output.omefeg
"""

import argparse
from array import array
import json
import os
import sys
import tempfile
import zipfile

import bpy


FORMAT = "omefeg-blender-model"
FORMAT_VERSION = 1


def _arguments():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        metavar="PATH",
        help="source .blend or .blend1 file (required)",
    )
    parser.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="destination .omefeg archive (required)",
    )
    parser.add_argument(
        "--scale", type=float, default=1.0,
        help="scale from Blender units to engine units (default: 1)",
    )
    parser.add_argument(
        "--step", type=float, default=1.0,
        help="Blender frames between samples (default: 1)",
    )
    return parser.parse_args(args)


def _mesh_objects():
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not objects:
        raise RuntimeError("The Blender scene contains no mesh objects to export")
    return objects


def _evaluated_mesh(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    if mesh is None:
        raise RuntimeError(f"Could not evaluate mesh object '{obj.name}'")
    mesh.calc_loop_triangles()
    return evaluated, mesh


def _vertex_attributes(objects, depsgraph, scale):
    positions_and_normals = []
    uvs = []
    indices = []
    mesh_sizes = []
    for obj in objects:
        evaluated, mesh = _evaluated_mesh(obj, depsgraph)
        try:
            transform = evaluated.matrix_world
            normal_transform = transform.to_3x3().inverted().transposed()
            uv_layer = mesh.uv_layers.active
            corner_normals = getattr(mesh, "corner_normals", None)
            loop_count = 0
            for triangle in mesh.loop_triangles:
                for loop_index in triangle.loops:
                    loop = mesh.loops[loop_index]
                    position = transform @ mesh.vertices[loop.vertex_index].co
                    source_normal = (
                        corner_normals[loop_index].vector
                        if corner_normals is not None
                        else loop.normal
                    )
                    normal = normal_transform @ source_normal
                    normal.normalize()
                    positions_and_normals.extend((
                        position.x * scale,
                        position.z * scale,
                        -position.y * scale,
                        normal.x,
                        normal.z,
                        -normal.y,
                    ))
                    if uv_layer is None:
                        uvs.extend((0.0, 0.0))
                    else:
                        uv = uv_layer.data[loop_index].uv
                        uvs.extend((uv.x, uv.y))
                    indices.append(len(indices))
                    loop_count += 1
            mesh_sizes.append((obj.name, loop_count))
        finally:
            evaluated.to_mesh_clear()
    return positions_and_normals, uvs, indices, mesh_sizes


def _set_action(objects, action):
    previous = []
    for obj in objects:
        animation_data = obj.animation_data
        had_animation_data = animation_data is not None
        if animation_data is None:
            animation_data = obj.animation_data_create()
        previous.append((
            obj,
            had_animation_data,
            animation_data.action,
            getattr(animation_data, "action_slot", None),
            [(track, track.mute) for track in animation_data.nla_tracks],
        ))
        animation_data.action = action
        for track in animation_data.nla_tracks:
            track.mute = True
        slots = getattr(action, "slots", None)
        if slots and hasattr(animation_data, "action_slot"):
            compatible = [
                slot for slot in slots
                if getattr(slot, "target_id_type", None) in (None, obj.id_type)
            ]
            if compatible:
                animation_data.action_slot = compatible[0]
    return previous


def _restore_actions(previous):
    for obj, had_animation_data, action, slot, tracks in previous:
        if not had_animation_data:
            obj.animation_data_clear()
            continue
        animation_data = obj.animation_data
        animation_data.action = action
        if hasattr(animation_data, "action_slot"):
            try:
                animation_data.action_slot = slot
            except (TypeError, ValueError):
                pass
        for track, muted in tracks:
            track.mute = muted


def _float_bytes(values):
    packed = array("f", values)
    if packed.itemsize != 4:
        raise RuntimeError("This platform does not provide 32-bit floats")
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def main():
    args = _arguments()
    if args.scale <= 0:
        raise ValueError("--scale must be greater than zero")
    if args.step <= 0:
        raise ValueError("--step must be greater than zero")

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Blender input file does not exist: {input_path}")
    bpy.ops.wm.open_mainfile(filepath=input_path)

    scene = bpy.context.scene
    objects = _mesh_objects()
    owners = list(scene.objects)
    for obj in objects:
        shape_keys = obj.data.shape_keys
        if shape_keys is not None and not any(owner is shape_keys for owner in owners):
            owners.append(shape_keys)
    previous_frame = scene.frame_current
    depsgraph = bpy.context.evaluated_depsgraph_get()

    scene.frame_set(previous_frame)
    bpy.context.view_layer.update()
    base_attributes, uvs, indices, mesh_sizes = _vertex_attributes(
        objects, depsgraph, args.scale
    )
    if not indices:
        raise RuntimeError("The Blender scene contains no visible mesh triangles")

    vertices = []
    for index, (x, y, z, nx, ny, nz) in enumerate(
        zip(*[iter(base_attributes)] * 6)
    ):
        uv_index = index * 2
        vertices.extend((x, y, z, nx, ny, nz, uvs[uv_index], uvs[uv_index + 1]))

    scene_fps = scene.render.fps / scene.render.fps_base
    sampled_fps = scene_fps / args.step
    clips = {}
    animations_data = bytearray()

    for action in bpy.data.actions:
        start, end = action.frame_range
        sample_frames = []
        frame = start
        while frame <= end:
            sample_frames.append(frame)
            frame += args.step
        if not sample_frames or sample_frames[-1] < end:
            sample_frames.append(end)

        clip_offset = len(animations_data)
        previous_actions = _set_action(owners, action)
        try:
            for frame in sample_frames:
                scene.frame_set(int(frame), subframe=frame - int(frame))
                bpy.context.view_layer.update()
                frame_attributes, _, _, frame_sizes = _vertex_attributes(
                    objects, depsgraph, args.scale
                )
                if frame_sizes != mesh_sizes or len(frame_attributes) != len(base_attributes):
                    raise RuntimeError(
                        f"Action '{action.name}' changes exported mesh topology"
                    )
                animations_data.extend(_float_bytes(frame_attributes))
        finally:
            _restore_actions(previous_actions)
            scene.frame_set(previous_frame)
            bpy.context.view_layer.update()

        clips[action.name] = {
            "fps": sampled_fps,
            "frame_count": len(sample_frames),
            "offset": clip_offset,
            "blender_frame_range": [start, end],
        }

    manifest = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "coordinate_system": "x-right,y-up,z-forward",
        "vertex_count": len(vertices) // 8,
        "index_count": len(indices),
        "animations": clips,
    }

    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output), exist_ok=True)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="omefeg-", suffix=".tmp", dir=os.path.dirname(output),
            delete=False,
        ) as temp:
            temp_path = temp.name
        with zipfile.ZipFile(
            temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, separators=(",", ":"), ensure_ascii=True),
            )
            archive.writestr(
                "mesh.bin",
                _float_bytes(vertices) + _uint_bytes(indices),
            )
            archive.writestr("animations.bin", animations_data)
        os.replace(temp_path, output)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        scene.frame_set(previous_frame)
        bpy.context.view_layer.update()

    print(
        f"Exported {len(indices) // 3} triangles and {len(clips)} animations "
        f"to {output}"
    )


def _uint_bytes(values):
    packed = array("I", values)
    if packed.itemsize != 4:
        raise RuntimeError("This platform does not provide 32-bit unsigned integers")
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


if __name__ == "__main__":
    main()

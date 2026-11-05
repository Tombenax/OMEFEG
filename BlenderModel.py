"""Load and play mesh animations exported by blender_export.py."""

from __future__ import annotations

import json
import time
import zipfile
from collections.abc import Sequence

import numpy as np
from Vec3 import Vec3


_FORMAT = "omefeg-blender-model"
_VERSION = 1


class BlenderModelData:
    def __init__(self, vertices, indices, animations, animation_bytes):
        self.vertices = vertices
        self.indices = indices
        self.animations = animations
        self.animation_bytes = animation_bytes


def load_blender_model(path: str) -> BlenderModelData:
    """Load a ``.omefeg`` archive created by ``blender_export.py``."""
    with zipfile.ZipFile(path, "r") as archive:
        try:
            manifest = json.loads(archive.read("manifest.json"))
            mesh_data = archive.read("mesh.bin")
            animation_bytes = archive.read("animations.bin")
        except (KeyError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid OMEFEG Blender model: {path}") from error

    if not isinstance(manifest, dict):
        raise ValueError(f"Invalid OMEFEG Blender model manifest: {path}")
    if manifest.get("format") != _FORMAT or manifest.get("version") != _VERSION:
        raise ValueError(f"Unsupported OMEFEG Blender model format: {path}")

    vertex_count = manifest.get("vertex_count")
    index_count = manifest.get("index_count")
    if (not isinstance(vertex_count, int) or vertex_count <= 0
            or not isinstance(index_count, int) or index_count <= 0):
        raise ValueError("The Blender model must contain mesh vertices and indices")

    mesh_values = np.frombuffer(mesh_data, dtype="<f4")
    expected_mesh_values = vertex_count * 8
    expected_mesh_bytes = expected_mesh_values * 4 + index_count * 4
    if len(mesh_data) != expected_mesh_bytes:
        raise ValueError("Blender model mesh data has an invalid size")

    vertices = mesh_values[:expected_mesh_values].astype("f4", copy=True)
    indices = np.frombuffer(
        mesh_data,
        dtype="<u4",
        count=index_count,
        offset=expected_mesh_values * 4,
    ).astype("i4", copy=True)
    if int(indices.max(initial=0)) >= vertex_count:
        raise ValueError("Blender model contains an out-of-range mesh index")

    animations = manifest.get("animations")
    if not isinstance(animations, dict):
        raise ValueError("Blender model animation metadata is invalid")
    animation_size = len(animation_bytes)
    for name, clip in animations.items():
        if not isinstance(name, str) or not isinstance(clip, dict):
            raise ValueError("Blender model contains invalid animation metadata")
        fps = clip.get("fps")
        frame_count = clip.get("frame_count")
        offset = clip.get("offset")
        if (not isinstance(fps, (int, float)) or fps <= 0
                or not isinstance(frame_count, int) or frame_count <= 0
                or not isinstance(offset, int) or offset < 0
                or offset + frame_count * vertex_count * 6 * 4 > animation_size):
            raise ValueError(f"Blender model animation '{name}' is invalid")
        clip["fps"] = float(fps)

    return BlenderModelData(vertices, indices, animations, animation_bytes)


class BlenderAnimationPlayer:
    """Frame-sampled playback controller for one imported model."""

    def __init__(self, model_data: BlenderModelData, set_vertices):
        self.model_data = model_data
        self._set_vertices = set_vertices
        self.animation_is_running = False
        self.current_animation = None
        self.current_frame = 0
        self.loop = True
        self._elapsed = 0.0
        self._last_update = None

    @property
    def animation_names(self):
        return tuple(self.model_data.animations)

    def play(self, name: str, loop: bool = True):
        if name not in self.model_data.animations:
            available = ", ".join(self.animation_names) or "none"
            raise KeyError(
                f"Animation '{name}' was not exported. Available animations: {available}"
            )
        self.current_animation = name
        self.current_frame = 0
        self._elapsed = 0.0
        self.loop = bool(loop)
        self.animation_is_running = True
        self._last_update = time.monotonic()
        self._apply_frame(0)

    def stop(self, reset: bool = False):
        """Stop playback, holding the current pose unless ``reset`` is true."""
        self.animation_is_running = False
        self._last_update = None
        if reset:
            self.current_animation = None
            self.current_frame = 0
            self._set_vertices(self.model_data.vertices.copy())

    def update(self):
        if not self.animation_is_running:
            return

        now = time.monotonic()
        if self._last_update is None:
            self._last_update = now
            return
        self._elapsed += max(0.0, now - self._last_update)
        self._last_update = now

        clip = self.model_data.animations[self.current_animation]
        frame_count = clip["frame_count"]
        frame_position = self._elapsed * clip["fps"]
        if frame_position >= frame_count:
            if self.loop:
                self._elapsed %= frame_count / clip["fps"]
                frame_position = self._elapsed * clip["fps"]
            else:
                frame_position = frame_count - 1
                self.animation_is_running = False
                self._last_update = None

        frame_index = min(int(frame_position), frame_count - 1)
        if frame_index != self.current_frame:
            self.current_frame = frame_index
            self._apply_frame(frame_index)

    def _apply_frame(self, frame_index: int):
        clip = self.model_data.animations[self.current_animation]
        vertex_count = len(self.model_data.vertices) // 8
        offset = clip["offset"] + frame_index * vertex_count * 6 * 4
        frame = np.frombuffer(
            self.model_data.animation_bytes,
            dtype="<f4",
            count=vertex_count * 6,
            offset=offset,
        ).reshape(vertex_count, 6)
        vertices = self.model_data.vertices.reshape(vertex_count, 8).copy()
        vertices[:, :6] = frame
        self._set_vertices(vertices.reshape(-1))


def attach_blender_model(
    model,
    identifier: str,
    path: str,
    position: Vec3 | Sequence[float] = (0, 0, 0),
    texture: int = 0,
    rotation=None,
) -> BlenderAnimationPlayer:
    """Load a Blender export into an engine ``Model`` and return its player."""
    model_data = load_blender_model(path)
    model.add_model(identifier, vertices=model_data.vertices, indices=model_data.indices)
    rotations = [] if rotation is None else [rotation]
    instance_position = position.copy() if isinstance(position, Vec3) else Vec3(*position)
    model.add_instances([instance_position], [texture], identifier, rotations)
    player = BlenderAnimationPlayer(
        model_data,
        model.instanedmodels[identifier].set_vertices,
    )
    model.animated_models[identifier] = player
    return player

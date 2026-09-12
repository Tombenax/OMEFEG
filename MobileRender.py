"""
MobileRender.py
===============

Kivy / OpenGL-ES 2.0 compatible, drop-in replacement for ``Render.py``.

How to use it
-------------
Wherever the desktop game does::

    from Render import *

the mobile build does::

    from MobileRender import *

No other game file has to change (``OMEFEG.py``, ``Chunk.py`` and
``World.py`` only rely on the public names re-exported here:
``Render``, ``Model``, ``InstancedModel``, ``Camera``, ``load_obj``,
``CUBE_MODEL_INFO``, ``CHARSET``, ``InstancedText``, ``HUDText``,
``Collectible``, ``get_key``, ``Matrix44``, ``np``, ``math``,
``random``, ``os``, ``json``, ``time``, ``Number``, ``distance`` and
the ``TEXTURES_X/Y`` / atlas constants).

Why it exists
------------
The desktop renderer is built on ``glfw`` + ``moderngl`` (desktop
OpenGL 3.3, instanced attributes, 2D texture arrays).  None of that
works on Android:

* no ``glfw`` window (Kivy owns the window / EGL context),
* no ``moderngl`` (raw GLES2 through ``kivy.graphics`` instead),
* no texture arrays in GLES2 (a single upright 2D atlas texture is
  used and the per-tile UV mapping is baked into the vertices on the
  CPU, with tile rows counted from the bottom),
* no hardware instancing in Kivy's ``Mesh`` (instances are merged into
  one CPU-side mesh per model, exactly like the desktop chunk
  "dummy" meshes already do).

So every ``InstancedModel`` keeps the exact same Python-side book
keeping as the desktop version (``instances`` as ``(N, 4, 4)``
matrices, ``tex_insta`` layers, ``add_instances`` /
``remove_instance`` / ``remove_instances`` / ``_upload``) and only the
GPU upload path is different: instances are merged into one Kivy
``Mesh`` drawn by a small GLES2 shader that reproduces the desktop
lighting (ambient + diffuse + specular, alpha cutout).

Touch controls (Android has no keyboard/mouse)
---------------------------------------------
* drag ............ look around
* tap ............. place block (left mouse button pulse)
* two-finger tap .. break block (right mouse button pulse)
* on-screen buttons: walk (arrows), JUMP, FLY (toggle), PLACE,
  BREAK, PAUSE.  They feed the very same ``get_key`` /
  ``get_mouse_button`` state the desktop game polls, so ``OMEFEG.py``
  works unchanged.

Notes for packaging (buildozer / python-for-android)
----------------------------------------------------
* requirements need at least: ``kivy, numpy, pillow, pyrr``.
* run from the game folder so ``assets/...`` resolves, same as desktop.
* ``utils.py`` (openal / desktop_notifier / requests / argon2) is NOT
  imported here on purpose; the game still needs it through
  ``Chunk.py``, so the Android recipe has to provide those (or they
  have to be trimmed from ``utils.py`` separately).
"""

import time
import json
import os
import random
import math
from typing import Any, Callable

import numpy as np
from pyrr import Matrix44
from PIL import Image

from Number import Number


def distance(first: list[Number], second: list[Number]):
    """Same helper the desktop Render.py re-exports from utils.

    Implemented locally so importing MobileRender never pulls in
    ``utils`` (which depends on desktop-only packages).
    """
    return math.hypot(
        first[0] - second[0], first[1] - second[1], first[2] - second[2]
    )


# ---------------------------------------------------------------------------
# Kivy imports (only Kivy + numpy + pillow + pyrr are required)
# ---------------------------------------------------------------------------

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.graphics import RenderContext, Mesh, BindTexture, Callback
from kivy.graphics.texture import Texture as KivyTexture
from kivy.graphics.transformation import Matrix as KivyMatrix
from kivy.graphics.opengl import (
    glEnable,
    glDisable,
    glClear,
    GL_DEPTH_TEST,
    GL_DEPTH_BUFFER_BIT,
)
from kivy.utils import platform

import logging as _logging


class _ShaderNoiseFilter(_logging.Filter):
    """Drop one benign, very noisy log record.

    Every RenderContext creation logs the Intel driver's program notes
    ("... uses varying ... but previous shader does not write to it",
    from the intermediate custom-vs/default-fs link Kivy performs when
    a shader pair is assigned).  The final custom pair links fine, so
    this text is pure spam.  Genuine compile/link errors have different
    text and still show up.
    """

    def filter(self, record):
        try:
            return (
                "previous shader does not write to it"
                not in record.getMessage()
            )
        except Exception:
            return True


try:
    _logging.getLogger("kivy").addFilter(_ShaderNoiseFilter())
except Exception:
    pass


# ---------------------------------------------------------------------------
# Input constants (same *meaning* as the glfw ones in Render.py;
# OMEFEG.py only ever compares them against get_key()/get_mouse_button()
# results, so the numeric values just have to be self-consistent and
# match what the Kivy keyboard handler reports).
# ---------------------------------------------------------------------------

PRESS = 1
RELEASE = 0

KEY_W = 119  # 'w'
KEY_A = 97   # 'a'
KEY_S = 115  # 's'
KEY_D = 100  # 'd'
KEY_F = 102  # 'f'
KEY_R = 114  # 'r'
KEY_SPACE = 32
KEY_ESCAPE = 27
KEY_LEFT_CONTROL = 1073742048  # SDL LCTRL keycode used by Kivy
KEY_LEFT_ALT = 1073742050      # SDL LALT keycode used by Kivy

CURSOR = 1
CURSOR_NORMAL = 0
CURSOR_DISABLED = 1

MOUSE_BUTTON_LEFT = 0
MOUSE_BUTTON_MIDDLE = 2
MOUSE_BUTTON_RIGHT = 1

_KEY_NAMES = {
    KEY_W: "w",
    KEY_A: "a",
    KEY_S: "s",
    KEY_D: "d",
    KEY_F: "f",
    KEY_R: "r",
    KEY_SPACE: "spacebar",
    KEY_ESCAPE: "escape",
    KEY_LEFT_CONTROL: "lctrl",
    KEY_LEFT_ALT: "lalt",
}

FOV = 60


# ---------------------------------------------------------------------------
# Atlas constants (identical computation as Render.py)
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1280, 720

ATLAS = Image.open("assets/textures/texture.png")

ATLAS_W, ATLAS_H = ATLAS.size

TEXTURE_W, TEXTURE_H = 64, 64

TEXTURES_X, TEXTURES_Y = ATLAS_W // TEXTURE_W, ATLAS_H // TEXTURE_H

TEXTURES = (ATLAS_W // TEXTURE_W) * (ATLAS_H // TEXTURE_H)

CHAR = Image.open("assets/textures/charset.png")

CHAR_W, CHAR_H = CHAR.size

CHR_W, CHR_H = 16, 16

CHRS = (CHAR_W / CHR_W) * (CHAR_H / CHR_H)

ITEMS = Image.open("assets/textures/Items.png")

ITEMS_W, ITEMS_H = ITEMS.size

ITEM_W, ITEM_H = 16, 16

ITEMS_X, ITEMS_Y = ITEMS_W // ITEM_W, ITEMS_H // ITEM_H

ITEMS_COUNT = (ITEMS_W / ITEM_W) * (ITEMS_H / ITEM_H)


# atlas description per model kind: (tile_w, tile_h, atlas_w, atlas_h)
_ATLASES = {
    "blocks": (TEXTURE_W, TEXTURE_H, ATLAS_W, ATLAS_H),
    "chars": (CHR_W, CHR_H, CHAR_W, CHAR_H),
    "items": (ITEM_W, ITEM_H, ITEMS_W, ITEMS_H),
}

_ATLAS_FILES = {
    "blocks": "assets/textures/texture.png",
    "chars": "assets/textures/charset.png",
    "items": "assets/textures/Items.png",
}


# ---------------------------------------------------------------------------
# GLES2 shaders (no #version line: Kivy adds what the backend needs).
# Same lighting as the desktop shaders: ambient 0.4 + diffuse +
# specular (16), alpha cutout at 0.1.
# ---------------------------------------------------------------------------

_WORLD_VERTEX = """
attribute vec3 a_pos;
attribute vec3 a_normal;
attribute vec2 a_uv;

uniform mat4 projection;
uniform mat4 view;

varying vec2 v_uv;
varying vec3 v_normal;
varying vec3 v_frag;

void main() {
    vec4 wp = vec4(a_pos, 1.0);
    gl_Position = projection * view * wp;
    v_frag = wp.xyz;
    v_normal = a_normal;
    v_uv = a_uv;
}
"""

_WORLD_FRAGMENT = """
#ifdef GL_ES
precision mediump float;
#endif

varying vec2 v_uv;
varying vec3 v_normal;
varying vec3 v_frag;

uniform sampler2D atlasTex;
uniform vec3 lightPos;
uniform vec3 viewPos;

void main() {
    vec4 tex = texture2D(atlasTex, v_uv);
    if (tex.a < 0.1)
        discard;
    vec3 color = tex.rgb;
    vec3 norm = normalize(v_normal);
    vec3 lightDir = normalize(lightPos - v_frag);
    float diff = max(dot(norm, lightDir), 0.0);
    vec3 ambient = 0.4 * color;
    vec3 diffuse = diff * color;
    vec3 viewDir = normalize(viewPos - v_frag);
    vec3 reflectDir = reflect(-lightDir, norm);
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 16.0);
    gl_FragColor = vec4(ambient + diffuse + spec, tex.a);
}
"""

# HUD text: positions are pre-converted to NDC on the CPU, no lighting,
# no depth test (drawn in canvas.after like the desktop version which
# disables DEPTH_TEST around HUD rendering).
_HUD_VERTEX = """
attribute vec3 a_pos;
attribute vec3 a_normal;
attribute vec2 a_uv;

varying vec2 v_uv;

void main() {
    gl_Position = vec4(a_pos, 1.0);
    v_uv = a_uv;
}
"""

_HUD_FRAGMENT = """
#ifdef GL_ES
precision mediump float;
#endif

varying vec2 v_uv;

uniform sampler2D atlasTex;

void main() {
    vec4 glyph = texture2D(atlasTex, v_uv);
    if (glyph.a < 0.1)
        discard;
    gl_FragColor = glyph;
}
"""

_MESH_FMT = [
    (b"a_pos", 3, "float"),
    (b"a_normal", 3, "float"),
    (b"a_uv", 2, "float"),
]


# ---------------------------------------------------------------------------
# Pure CPU mesh helpers (no GL, no Kivy objects -> unit testable)
# ---------------------------------------------------------------------------

def convert_dummy_uv(uv, tiles_y):
    """Convert ``utils.export_and_load_chunk`` atlas UVs to the upright
    2D layout used here.

    Export bakes ``u = (bx + u) / TX``, ``v = (by + v) / TY`` with the
    tile row counted from the TOP (for the desktop's flipped texture
    array).  U already matches; the row is mirrored so the same tile
    is addressed from the bottom.  All inputs are exact binary
    fractions, so the row recovery is exact.
    """
    uv = np.asarray(uv, dtype=np.float64)
    out = uv.copy()
    out[..., 0] = np.clip(uv[..., 0], 0.0, 1.0)
    vd = np.clip(uv[..., 1], 0.0, 1.0)
    t = vd * tiles_y
    row = np.floor(t).astype(np.int64)
    frac = t - row
    # Exact tile boundaries (v_pre = 1.0, e.g. v_d = 0.5) belong to the
    # tile below, not the one above: fold them back with frac = 1.
    on_edge = (frac < 1e-9) & (row > 0)
    row = np.where(on_edge, row - 1, row)
    frac = np.where(on_edge, 1.0, frac)
    row = np.clip(row, 0, tiles_y - 1)
    frac = np.clip(frac, 0.0, 1.0)
    out[..., 1] = (tiles_y - 1 - row + frac) / tiles_y
    return out


def merge_instances(base_vertices, base_indices, matrices, layers,
                    tile_w, tile_h, atlas_w, atlas_h,
                    pre_mapped_uv=False):
    """Merge per-instance base geometry into one world-space mesh.

    * ``base_vertices``: ``(V, 8)`` float array (pos, normal, uv).
    * ``base_indices``: ``(I,)`` int array.
    * ``matrices``: ``(N, 4, 4)`` array, row-vector convention
      (``world = [x, y, z, 1] @ M``) -- the exact convention the
      desktop ``add_instances`` builds.
    * ``layers``: texture tile index per instance.
    * when ``pre_mapped_uv`` is True (chunk dummy meshes coming from
      ``export_and_load_chunk``) UVs are already final atlas UVs and
      are passed through untouched, not re-mapped per layer.

    Tile *selection* matches the desktop shaders
    (``column = layer % columns``, ``row = layer // columns`` counted
    from the top of the atlas), but the row is stored from the BOTTOM
    because the mobile texture is the PNG as-is (upright 2D texture,
    v = 1 at the top) while the desktop samples a vertically
    strip-flipped texture array::

        uv = ((column + u) / TX, (tiles_y - 1 - row + v) / TY)

    (``block.obj`` UVs are pre-mapped atlas regions, so they plug into
    this formula directly.)

    Returns ``(vertices (M, 8) float32, indices (K,) int32)``.
    """
    base_vertices = np.asarray(base_vertices, dtype=np.float32).reshape(-1, 8)
    base_indices = np.asarray(base_indices, dtype=np.int32).reshape(-1)
    matrices = np.asarray(matrices, dtype=np.float32).reshape(-1, 4, 4)
    layers = np.asarray(layers).reshape(-1)

    count = int(matrices.shape[0])
    if count == 0 or base_vertices.shape[0] == 0:
        return np.zeros((0, 8), dtype=np.float32), np.zeros((0,), dtype=np.int32)

    v_count = base_vertices.shape[0]
    base_pos = base_vertices[:, 0:3]
    base_nor = base_vertices[:, 3:6]
    base_uv = base_vertices[:, 6:8]

    merged_pos = np.empty((count * v_count, 3), dtype=np.float32)
    merged_nor = np.empty((count * v_count, 3), dtype=np.float32)
    merged_uv = np.empty((count * v_count, 2), dtype=np.float32)

    for i in range(count):
        m = matrices[i].astype(np.float64)
        # positions: row-vector transform
        rotated = base_pos.astype(np.float64) @ m[:3, :3].T + m[3, :3]
        merged_pos[i * v_count:(i + 1) * v_count] = rotated.astype(np.float32)
        # normals: n' = n @ inv(M^T)  (row-vector form of the desktop
        # normal matrix transpose(inverse(M)))
        try:
            inv_mt = np.linalg.inv(m.T)
            n_mat = inv_mt[:3, :3]
            if not np.all(np.isfinite(n_mat)):
                raise np.linalg.LinAlgError
            tn = base_nor.astype(np.float64) @ n_mat
        except np.linalg.LinAlgError:
            tn = base_nor.astype(np.float64)
        lens = np.linalg.norm(tn, axis=1, keepdims=True)
        lens[lens == 0.0] = 1.0
        merged_nor[i * v_count:(i + 1) * v_count] = (tn / lens).astype(np.float32)
        # uvs
        if pre_mapped_uv:
            merged_uv[i * v_count:(i + 1) * v_count] = base_uv
        else:
            layer = int(layers[i]) if i < layers.shape[0] else 0
            columns = max(int(atlas_w // tile_w), 1)
            tiles_y = max(int(atlas_h // tile_h), 1)
            layer = layer % (columns * tiles_y)
            column = layer % columns
            row_bottom = tiles_y - 1 - (layer // columns)
            merged_uv[i * v_count:(i + 1) * v_count, 0] = (
                (column + base_uv[:, 0]) * tile_w / atlas_w
            )
            merged_uv[i * v_count:(i + 1) * v_count, 1] = (
                (row_bottom + base_uv[:, 1]) * tile_h / atlas_h
            )

    merged = np.concatenate([merged_pos, merged_nor, merged_uv], axis=1)
    offsets = (np.arange(count, dtype=np.int32) * v_count)[:, None]
    merged_indices = (base_indices[None, :] + offsets).reshape(-1)

    return merged.astype(np.float32), merged_indices.astype(np.int32)


# ---------------------------------------------------------------------------
# Compatibility proxies (the desktop exposes moderngl program / context
# objects; nothing in the game drives them directly, but keep the same
# attribute shapes so nothing can AttributeError).
# ---------------------------------------------------------------------------

class _UniformVar:
    def __init__(self):
        self._bytes = b""
        self._value = None

    def write(self, data):
        self._bytes = bytes(data)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, val):
        self._value = val


class _ProgramProxy:
    """Duck-typed stand-in for a moderngl program uniform interface."""

    def __init__(self):
        self._vars: dict[str, _UniformVar] = {}

    def __getitem__(self, key):
        return self._vars.setdefault(key, _UniformVar())

    def __setitem__(self, key, val):
        var = self._vars.setdefault(key, _UniformVar())
        if isinstance(val, (bytes, bytearray)):
            var.write(val)
        else:
            var.value = val


class _CtxProxy:
    """Duck-typed stand-in for the moderngl context used by OMEFEG.py.

    Only ``clear`` does something real (sets the Kivy clear color);
    everything else exists for API compatibility.
    """

    def __init__(self, render=None):
        self._render = render
        self.viewport = (0, 0, WIDTH, HEIGHT)

    def clear(self, r=0.0, g=0.0, b=0.0, a=1.0):
        try:
            Window.clearcolor = (float(r), float(g), float(b), float(a))
        except Exception:
            pass

    def enable(self, *args, **kwargs):
        return None

    def disable(self, *args, **kwargs):
        return None

    def finish(self):
        return None


def _mat4(values):
    """Wrap 16 floats in Kivy's Matrix.

    Plain Python lists silently fail as mat4 uniforms (the uniform
    keeps its default and everything gets clipped); only Kivy's
    Matrix type uploads correctly.
    """
    m = KivyMatrix()
    m.set([float(v) for v in np.asarray(values, dtype=np.float32).reshape(-1)])
    return m


def _set_shaders(rc, vs, fs):
    """Assign a custom shader pair to a RenderContext.

    Kivy links eagerly on every assignment, so assigning ``vs`` first
    always links the custom vertex shader against the *default*
    fragment shader and raises.  The source itself sticks, therefore
    assigning ``fs`` right after links the complete custom pair.
    """
    try:
        rc.shader.vs = vs
    except Exception:
        pass
    rc.shader.fs = fs


# ---------------------------------------------------------------------------
# GL state callbacks (run inside the canvas so HUD draws without depth)
# ---------------------------------------------------------------------------

def _gl_setup_frame(_instr):
    try:
        glEnable(GL_DEPTH_TEST)
        glClear(GL_DEPTH_BUFFER_BIT)
    except Exception:
        pass


def _gl_disable_depth(_instr):
    try:
        glDisable(GL_DEPTH_TEST)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# InstancedModel / Model (same public API as Render.py)
# ---------------------------------------------------------------------------

class InstancedModel:
    def __init__(self, **kwargs: dict[str, Any]):
        """
        arguments:
            render: Render instance
            indices: model's indices
            vertices: model's vertices
            !USED BY CHUNKS DUMMIES! is_chunk_dummy
            atlas: 'blocks' (default), 'chars' or 'items'
        """
        self._render = kwargs["render"]
        self._is_dummy = bool(kwargs.get("is_chunk_dummy"))
        self._atlas = kwargs.get("atlas", "blocks")
        if self._atlas not in _ATLASES:
            self._atlas = "blocks"

        self.indices = np.asarray(kwargs["indices"], dtype=np.int32).reshape(-1)
        verts = np.asarray(kwargs["vertices"], dtype=np.float32).reshape(-1, 8)
        if self._is_dummy:
            # Chunk dummy meshes arrive with desktop-style atlas UVs
            # baked by utils.export_and_load_chunk; convert once.
            tile_w, tile_h, atlas_w, atlas_h = _ATLASES[self._atlas]
            tiles_y = max(int(atlas_h // tile_h), 1)
            fixed = verts.copy()
            fixed[:, 6:8] = convert_dummy_uv(
                verts[:, 6:8], tiles_y
            ).astype(np.float32)
            verts = fixed
        self.vertices = verts

        self.instances = np.zeros((0, 4, 4), dtype="f4")
        self.tex_insta = np.zeros((0,), dtype="f4")

        self.vertices_all = np.zeros((0, 8), dtype=np.float32)
        self.indices_all = np.zeros((0,), dtype=np.int32)
        self._dirty = True
        self._visible = False

        self._rc = None
        self._mesh = None
        self._is_hud = False

        register = getattr(self._render, "_register_model", None)
        if callable(register):
            register(self)

    # -- instance bookkeeping (identical math to Render.py) -----------------

    def add_instances(self, positions: list[list[Number]],
                      textures: list[int] | np.ndarray,
                      rotations: list[list[Number]] = []):
        if not isinstance(positions, np.ndarray):
            positions = np.asarray(positions, dtype="f4")

        if positions.ndim == 1:
            positions = positions.reshape(1, 3)

        new_models = np.eye(4, dtype="f4").reshape(1, 4, 4)
        new_models = np.repeat(new_models, len(positions), axis=0)
        new_models[:, 3, 0] = positions[:, 0]
        new_models[:, 3, 1] = positions[:, 1]
        new_models[:, 3, 2] = positions[:, 2]

        for idx, rotation in enumerate(rotations):
            x, y, z = [
                Matrix44.from_x_rotation(math.radians(rotation[0])),
                Matrix44.from_y_rotation(math.radians(rotation[1])),
                Matrix44.from_z_rotation(math.radians(rotation[2])),
            ]

            new_models[idx] = x @ y @ z @ new_models[idx]

        self.instances = np.concatenate((self.instances, new_models))

        self.tex_insta = np.concatenate(
            (self.tex_insta, np.array(textures, dtype="f4"))
        )

        self._upload()

    def remove_instance(self, i):
        """Remove an instance at the given index"""
        self.instances = np.delete(self.instances, i, axis=0)
        self.tex_insta = np.delete(self.tex_insta, i, axis=0)

        self._upload()

    def remove_instances(self, positions):
        """Remove instances whose model translations match the given positions."""
        if len(positions) == 0:
            return 0

        positions = np.asarray(positions, dtype="f4")
        if positions.ndim == 1:
            positions = positions.reshape(1, 3)

        requested = {tuple(position) for position in positions}
        instance_positions = self.instances[:, 3, :3]
        remove_mask = np.array(
            [tuple(position) in requested for position in instance_positions],
            dtype=bool,
        )
        removed = int(np.count_nonzero(remove_mask))

        if removed:
            self.instances = self.instances[~remove_mask]
            self.tex_insta = self.tex_insta[~remove_mask]
            self._upload()

        return removed

    # -- CPU merge ----------------------------------------------------------

    def _rebuild(self):
        tile_w, tile_h, atlas_w, atlas_h = _ATLASES[self._atlas]
        verts, inds = merge_instances(
            self.vertices,
            self.indices,
            self.instances,
            self.tex_insta,
            tile_w,
            tile_h,
            atlas_w,
            atlas_h,
            pre_mapped_uv=self._is_dummy,
        )
        self.vertices_all = verts
        self.indices_all = inds
        self._dirty = True

    def _upload(self):
        self._rebuild()

    # -- Kivy GL objects (created lazily: init_function runs before the
    #    Kivy GL context exists, and headless tests never render) ----------

    def _ensure_gl(self):
        render = self._render
        if self._rc is not None:
            return True
        if render is None or not getattr(render, "_gl_ready", False):
            return False
        try:
            tex = render._texture(self._atlas)
            if tex is None:
                return False
            rc = RenderContext()
            _set_shaders(rc, _WORLD_VERTEX, _WORLD_FRAGMENT)
            with rc:
                BindTexture(texture=tex, index=1)
                self._mesh = Mesh(
                    fmt=_MESH_FMT,
                    mode="triangles",
                    vertices=[0.0] * 8,
                    indices=[0, 0, 0],
                )
            rc["atlasTex"] = 1
            render._attach_world_rc(rc)
            render._push_uniforms_to(self)
            self._rc = rc
            return True
        except Exception:
            if os.environ.get("MOBILE_RENDER_DEBUG"):
                import traceback

                traceback.print_exc()
            self._rc = None
            self._mesh = None
            return False

    def _sync_mesh(self):
        if self._mesh is None:
            return
        try:
            if self.vertices_all.shape[0] == 0:
                render = self._render
                if render is not None:
                    render._set_rc_visible(self._rc, False)
                self._visible = False
                return
            self._mesh.vertices = self.vertices_all.reshape(-1).tolist()
            self._mesh.indices = self.indices_all.tolist()
            render = self._render
            if render is not None:
                render._set_rc_visible(self._rc, True)
            self._visible = True
        except Exception:
            if os.environ.get("MOBILE_RENDER_DEBUG"):
                import traceback

                traceback.print_exc()
        self._dirty = False

    def push_uniforms(self, projection, view, light_pos, view_pos):
        if self._rc is None:
            return
        try:
            self._rc["projection"] = _mat4(projection)
            self._rc["view"] = _mat4(view)
            self._rc["lightPos"] = light_pos
            self._rc["viewPos"] = view_pos
        except Exception:
            if os.environ.get("MOBILE_RENDER_DEBUG"):
                import traceback

                traceback.print_exc()

    def render(self):
        if len(self.instances) == 0 and self.vertices_all.shape[0] == 0:
            if self._rc is not None and self._visible:
                try:
                    self._render._set_rc_visible(self._rc, False)
                except Exception:
                    pass
                self._visible = False
            return
        if not self._ensure_gl():
            return
        if self._dirty:
            self._sync_mesh()


class Model:
    def __init__(self, renderer):
        self.instanedmodels: dict[str, InstancedModel] = {}
        self.renderer = renderer

    def add_model(self, identifier: str, **kwargs: dict[str, Any]):
        """
        args:
            vertices: model's vertices
            indices: model's indices
            !ONlY USED BY CHUNK DUMMIES! is_chunk_dummy
            atlas: 'blocks' (default), 'chars' or 'items'
        """
        self.instanedmodels[identifier] = InstancedModel(
            render=self.renderer,
            indices=kwargs["indices"],
            vertices=kwargs["vertices"],
            is_chunk_dummy=kwargs.get("is_chunk_dummy"),
            atlas=kwargs.get("atlas", "blocks"),
        )

    def add_instances(self, positions: list[list[Number]],
                      textures: list[int], model_identifier: str,
                      rotations: list[list[Number]] = []):
        self.instanedmodels[model_identifier].add_instances(
            positions, textures, rotations
        )

    def remove_instance(self, index: Number, model_identifier: str):
        """Remove an instance at position from the specified model. Returns True if removed, False if not found."""
        if model_identifier in self.instanedmodels:
            return self.instanedmodels[model_identifier].remove_instance(index)

    def remove_instances(self, positions: list[list[Number]], model_identifier: str):
        return self.instanedmodels[model_identifier].remove_instances(positions)

    def render_one(self, identifier: str):
        self.instanedmodels[identifier].render()

    def render(self):
        for identifier in self.instanedmodels.keys():
            self.render_one(identifier)


def get_key(window, key):
    render = None
    # The game always passes render.window (which is the Render itself).
    if hasattr(window, "get_key"):
        try:
            return window.get_key(key)
        except Exception:
            pass
    if render is None:
        active = globals().get("_ACTIVE_RENDER")
        if active is not None:
            try:
                return active.get_key(key)
            except Exception:
                pass
    return RELEASE


_ACTIVE_RENDER = None


class Camera:
    def __init__(self, position, render):
        self.render = render

        self.position = np.array(position, dtype=float)

        self.start_pos = self.position.copy()

        self.yaw = 0.0
        self.pitch = 0.0

        self.eye_height = 1.8

        self.last_x = 0
        self.last_y = 0

        self.dx = 0
        self.dy = 0

        self.sensitivity = 0.1
        self.speed = 5

        self.gravity = 20

        self.fly = False

        self.do = False

        self.max_jumps = 1

        self.jump_strenght = 10

        self.jumps = 0

        self.trust_me = True

        self.front = np.array([1, 0, 0], dtype="f4")
        self.right = np.array([0, 0, -1], dtype="f4")
        self.up = np.array([0, 1, 0], dtype="f4")

        self.vel_y = 0.0
        self.on_ground = False

        self.eye_pos = self.position + np.array(
            [0, self.eye_height, 0], dtype=float
        )

        self.view = Matrix44.look_at(
            self.eye_pos, self.eye_pos + self.front, self.up
        )

    def cursor_move(self, w, x, y):
        self.dx = x - self.last_x
        self.dy = y - self.last_y

        if self.fly and self.do:
            if self.up[1] > 0:
                self.dx *= 1
            else:
                self.dx *= -1

        self.yaw += self.dx * self.sensitivity
        self.pitch -= self.dy * self.sensitivity

        self.last_x = x
        self.last_y = y

    def update(self, occupied):
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)

        # Forward direction
        front = np.array(
            [
                math.cos(yaw) * math.cos(pitch),
                math.sin(pitch),
                math.sin(yaw) * math.cos(pitch),
            ],
            dtype="f4",
        )

        front /= np.linalg.norm(front)

        # Right direction
        right = np.array(
            [math.sin(yaw), 0.0, -math.cos(yaw)], dtype="f4"
        )
        go = np.array(
            [math.cos(yaw), math.sin(pitch), math.sin(yaw)], dtype="f4"
        )

        right /= np.linalg.norm(right)
        go /= np.linalg.norm(go)

        # Up direction
        up = np.cross(right, front)
        up /= np.linalg.norm(up)

        self.front = front
        self.right = right
        self.go = go
        self.up = -up

        # --------------------
        # Movement
        # --------------------

        move = np.zeros(3, dtype=float)

        self.sprint = get_key(self.render.window, KEY_LEFT_CONTROL)
        self.fly = get_key(self.render.window, KEY_F)

        self.speed = 13 if self.sprint else 30 if self.fly else 7

        if get_key(self.render.window, KEY_R):
            self.position = self.start_pos.copy()

        if get_key(self.render.window, KEY_W):
            move += (self.go if not self.fly else self.front) * self.render.dt * self.speed

        if get_key(self.render.window, KEY_S):
            move -= (self.go if not self.fly else self.front) * self.render.dt * self.speed

        if get_key(self.render.window, KEY_A):
            move += self.right * self.render.dt * self.speed

        if get_key(self.render.window, KEY_D):
            move -= self.right * self.render.dt * self.speed

        # Don't move vertically
        if not self.fly:
            move[1] = 0

        if self.on_ground:
            self.jumps = 0
            self.trust_me = True

        self.vel_y -= self.gravity * self.render.dt

        if (
            get_key(self.render.window, KEY_SPACE)
            and (self.on_ground or self.jumps < self.max_jumps)
            and self.trust_me
        ):
            self.vel_y = self.jump_strenght
            self.jumps += 1
            self.trust_me = False

        if get_key(self.render.window, KEY_SPACE) != PRESS:
            self.trust_me = True

        dy = self.vel_y * self.render.dt

        if self.fly:
            dy = 0
            self.vel_y = 0

        move[1] += dy

        # collision
        self.try_move(move, occupied)

        # --------------------
        # View matrix
        # --------------------

        self.eye_pos = self.position + np.array(
            [0, self.eye_height, 0], dtype=float
        )

        self.view = Matrix44.look_at(
            self.eye_pos, self.eye_pos + self.front, self.up
        )

    def collides(self, new_pos, occupied):
        thing = np.round(new_pos)
        return tuple(thing) in occupied

    def collides_h(self, new_pos, occupied, height=2):
        a_pos = new_pos.copy()
        for h in range(height):
            if self.collides(a_pos, occupied):
                return True
            a_pos[1] += 1

        return False

    def try_move(self, new_position, occupied):
        self.position[0] += new_position[0]
        if self.collides_h(self.position, occupied):
            # print("colliding x")
            self.position[0] -= new_position[0]

        self.position[2] += new_position[2]
        if self.collides_h(self.position, occupied):
            # print("colliding z")
            self.position[2] -= new_position[2]

        self.position[1] += new_position[1]
        if self.collides_h(self.position, occupied):
            # print("colliding y")
            self.position[1] -= new_position[1]
            self.vel_y = 0.0
            self.on_ground = True
        else:
            self.on_ground = False


def load_obj(file_path: str):
    positions = []
    normals = []
    uvs = []
    vertices = []
    indices = []
    vertex_map = {}
    idx = 0

    with open(file_path) as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()
                positions.append([float(x), float(y), float(z)])
            elif line.startswith("vn "):
                _, x, y, z = line.split()
                normals.append([float(x), float(y), float(z)])
            elif line.startswith("vt "):
                _, u, v = line.split()
                uvs.append([float(u), float(v)])
            elif line.startswith("f "):
                face = []
                for part in line.split()[1:]:
                    vals = part.split("/")

                    p = int(vals[0]) - 1

                    t = int(vals[1]) - 1 if len(vals) > 1 and vals[1] else 0

                    n = int(vals[2]) - 1 if len(vals) > 2 and vals[2] else 0
                    key = (p, t, n)
                    if key not in vertex_map:
                        px, py, pz = positions[p]
                        if len(normals) > 0:
                            nx, ny, nz = normals[n]
                        else:
                            nx, ny, nz = (0.0, 1.0, 0.0)
                        u, v = uvs[t]
                        v = 1 - v
                        vertices.extend([px, py, pz, nx, ny, nz, u, 1 - v])
                        vertex_map[key] = idx
                        idx += 1
                    face.append(vertex_map[key])
                for i in range(1, len(face) - 1):
                    indices.extend([face[0], face[i], face[i + 1]])

    return [np.array(vertices, dtype="f4"), np.array(indices, dtype="i4")]


CUBE_MODEL_INFO = load_obj("assets/models/block.obj")

CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890:!? "

# quad facing X- (same base geometry as Render.py text/collectibles)
_QUAD_VERTICES = np.array(
    [
        # position              # normal          # uv
        0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0,
        0.0, 1.0, 1.0, -1.0, 0.0, 0.0, 1.0, 1.0,
        0.0, 1.0, 1.0, -1.0, 0.0, 0.0, 1.0, 1.0,
        0.0, 0.0, 1.0, -1.0, 0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0,
    ],
    dtype="f4",
)

_QUAD_INDICES = np.array([0, 1, 2, 3, 4, 5], dtype="i4")


class InstancedText(InstancedModel):
    def __init__(self, **kwargs):
        """
        args:
            render: Render instance
            charset: charset
            !ONLY USED BY HUDText! is_hud_text
        """
        self._charset = kwargs["charset"]
        self.charset_lookup = {}
        for idx, key in enumerate(self._charset):
            self.charset_lookup[key] = idx

        # Bypass InstancedModel.__init__ signature on purpose and call it
        # with quad geometry on the chars atlas.
        super().__init__(
            render=kwargs["render"],
            indices=_QUAD_INDICES,
            vertices=_QUAD_VERTICES,
            atlas="chars",
        )

        self.texts = {}
        self._text_entries = []

    def _upload_text_instances(self):
        # Desktop writes GPU buffers here; we rebuild the merged mesh.
        self._upload()

    def _rebuild_text_instances(self):
        instances = []
        textures = []

        for entry in self._text_entries:
            text, position = entry["text"], entry["position"]
            for character_index, character in enumerate(text.upper()):
                model = np.eye(4, dtype="f4")
                model[3, 0] = position[0]
                model[3, 1] = position[1]
                model[3, 2] = position[2] + character_index
                instances.append(model)
                textures.append(self.charset_lookup[character])

        self.instances = np.asarray(instances, dtype="f4").reshape((-1, 4, 4))
        self.tex_insta = np.asarray(textures, dtype="f4")
        self._upload_text_instances()

    def add_texts(self, texts, positions, identifiers=None):
        if len(texts) != len(positions):
            raise ValueError("texts and positions must have the same length")

        if identifiers is None:
            identifiers = [None] * len(texts)
        elif len(identifiers) != len(texts):
            raise ValueError("identifiers must match the number of texts")

        for text, position, identifier in zip(texts, positions, identifiers):
            if len(position) != 3:
                raise ValueError("text positions must be [x, y, z]")
            if identifier is not None and identifier in self.texts:
                raise ValueError(f"text identifier already exists: {identifier}")

            entry = {
                "text": text,
                "position": list(position),
                "identifier": identifier,
            }
            self._text_entries.append(entry)
            if identifier is not None:
                self.texts[identifier] = entry

        self._rebuild_text_instances()

    def update_text(self, identifier: str, text=None, position=None):
        if identifier not in self.texts:
            raise KeyError(f"unknown text identifier: {identifier}")

        entry = self.texts[identifier]
        if text is not None:
            entry["text"] = text
        if position is not None:
            if len(position) != 3:
                raise ValueError("text positions must be [x, y, z]")
            entry["position"] = list(position)

        self._rebuild_text_instances()

    def remove_text(self, identifier: str):
        if identifier not in self.texts:
            return False

        entry = self.texts.pop(identifier)
        self._text_entries.remove(entry)
        self._rebuild_text_instances()
        return True


class Collectible(InstancedModel):
    def __init__(self, render):
        """
        args:
            render: Render instance
        """
        self.render_ = render
        super().__init__(
            render=render,
            indices=_QUAD_INDICES,
            vertices=_QUAD_VERTICES,
            atlas="items",
        )
        self.callbacks: list[callable] = []

    def add_collectibles(
        self,
        positions: list[list[Number]],
        textures: list[int],
        on_collect: list[callable],
    ):
        self.callbacks.extend(on_collect)

        if not isinstance(positions, np.ndarray):
            positions = np.asarray(positions, dtype="f4")

        if positions.ndim == 1:
            positions = positions.reshape(1, 3)

        new_models = np.eye(4, dtype="f4").reshape(1, 4, 4)
        new_models = np.repeat(new_models, len(positions), axis=0)
        new_models[:, 3, 0] = positions[:, 0]
        new_models[:, 3, 1] = positions[:, 1]
        new_models[:, 3, 2] = positions[:, 2]

        self.instances = np.concatenate((self.instances, new_models))

        self.tex_insta = np.concatenate(
            (self.tex_insta, np.array(textures, dtype="f4"))
        )

        self._upload()

    def update(self, player_position: list[Number]):
        for i, instance in enumerate(self.instances):
            a = list(instance[3][:3])

            if distance(a, player_position) < 3:
                self.instances = np.delete(self.instances, i, axis=0)
                self.tex_insta = np.delete(self.tex_insta, i, axis=0)
                self.callbacks[i](self.render_)
                continue

            x = Matrix44.from_x_rotation(self.render_.dt)
            y = Matrix44.from_y_rotation(self.render_.dt)
            z = Matrix44.from_z_rotation(self.render_.dt)

            self.instances[i] = (x @ y @ z @ instance).astype("f4")

        self._upload()


class HUDText(InstancedText):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._is_hud = True
        self._hud_built_for = None
        # same public attributes the desktop HUDText sets
        self.screen_size = kwargs.get("screen_size", (WIDTH, HEIGHT))

    def _screen_size(self):
        render = self._render
        if render is not None and hasattr(render, "_win_w"):
            try:
                return (int(render._win_w), int(render._win_h))
            except Exception:
                pass
        return (WIDTH, HEIGHT)

    def _rebuild_hud(self):
        """Build NDC quads directly (desktop does this in-shader)."""
        sw, sh = self._screen_size()
        if sh == 0:
            sh = 1
        if sw == 0:
            sw = 1
        tile_w, tile_h, atlas_w, atlas_h = _ATLASES["chars"]
        columns = max(int(atlas_w // tile_w), 1)

        # 6 corners of the base quad: (x_px_offset, y_px_offset, u, v)
        corners = (
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 1.0),
            (1.0, 1.0, 1.0, 1.0),
            (1.0, 1.0, 1.0, 1.0),
            (1.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 0.0),
        )

        verts = []
        inds = []
        tiles_y = max(int(atlas_h // tile_h), 1)
        for entry in self._text_entries:
            text, position = entry["text"], entry["position"]
            for character_index, character in enumerate(text.upper()):
                # upright 2D mapping: tile row counted from the bottom.
                layer = int(self.charset_lookup[character])
                column = layer % columns
                row_bottom = tiles_y - 1 - (layer // columns)
                base = len(verts) // 8
                for qx, qy, qu, qv in corners:
                    # x grows with the character index, y is the entry
                    # position (both in pixels, origin top-left).
                    x_px = (
                        position[0]
                        + character_index * tile_w
                        + qx * tile_w
                    )
                    y_px = position[1] + qy * tile_h
                    nx = x_px / sw * 2.0 - 1.0
                    ny = 1.0 - y_px / sh * 2.0
                    uu = (column + qu) * tile_w / atlas_w
                    # pixel-space +y runs DOWN the screen, so the top of
                    # a glyph (qy = 0) samples the top of its tile.
                    vv = (row_bottom + (1.0 - qv)) * tile_h / atlas_h
                    verts.extend(
                        [nx, ny, 0.0, 0.0, 0.0, 1.0, uu, vv]
                    )
                inds.extend(
                    [base, base + 1, base + 2, base + 3, base + 4, base + 5]
                )

        if verts:
            self.vertices_all = np.asarray(verts, dtype=np.float32).reshape(-1, 8)
            self.indices_all = np.asarray(inds, dtype=np.int32).reshape(-1)
        else:
            self.vertices_all = np.zeros((0, 8), dtype=np.float32)
            self.indices_all = np.zeros((0,), dtype=np.int32)
        self._hud_built_for = (sw, sh)
        self._dirty = True

    def _upload_text_instances(self):
        self._rebuild_hud()

    def add_texts(self, texts, positions, identifiers=None):
        hud_positions = []
        for position in positions:
            if len(position) != 2:
                raise ValueError(
                    "HUD text positions must be [x, y] pixel coordinates"
                )
            hud_positions.append([position[0], position[1], 0])

        super().add_texts(texts, hud_positions, identifiers)

    def update_text(self, identifier: str, text=None, position=None):
        hud_position = None
        if position is not None:
            if len(position) != 2:
                raise ValueError(
                    "HUD text positions must be [x, y] pixel coordinates"
                )
            hud_position = [position[0], position[1], 0]

        super().update_text(identifier, text, hud_position)

    def render(self):
        if self._hud_built_for != self._screen_size():
            self._rebuild_hud()
        if self.vertices_all.shape[0] == 0:
            if self._rc is not None and self._visible:
                try:
                    self._render._set_rc_visible(self._rc, False)
                except Exception:
                    pass
                self._visible = False
            return
        if not self._ensure_hud_gl():
            return
        if self._dirty:
            self._sync_mesh()

    def _ensure_hud_gl(self):
        render = self._render
        if self._rc is not None:
            return True
        if render is None or not getattr(render, "_gl_ready", False):
            return False
        try:
            tex = render._texture("chars")
            if tex is None:
                return False
            rc = RenderContext()
            _set_shaders(rc, _HUD_VERTEX, _HUD_FRAGMENT)
            with rc:
                BindTexture(texture=tex, index=1)
                self._mesh = Mesh(
                    fmt=_MESH_FMT,
                    mode="triangles",
                    vertices=[0.0] * 8,
                    indices=[0, 0, 0],
                )
            rc["atlasTex"] = 1
            render._attach_hud_rc(rc)
            self._rc = rc
            return True
        except Exception:
            self._rc = None
            self._mesh = None
            return False

    def push_uniforms(self, projection, view, light_pos, view_pos):
        # HUD is screen-space: no per-frame uniforms needed.
        return None


# ---------------------------------------------------------------------------
# Kivy widgets / app
# ---------------------------------------------------------------------------

class _GameWidget(Widget):
    def __init__(self, render, **kwargs):
        super().__init__(**kwargs)
        self._render = render
        # depth setup runs before everything in this canvas
        with self.canvas.before:
            Callback(_gl_setup_frame)
        # HUD renders without depth test, always on top.
        # Depth stays DISABLED afterwards on purpose: Kivy widgets
        # (e.g. button labels) share their background's depth, so with
        # depth testing on the label fails against its own background
        # and text disappears. The next frame re-enables depth in
        # canvas.before before any 3D drawing.
        with self.canvas.after:
            Callback(_gl_disable_depth)
            # (HUD RenderContexts are inserted here)

    def on_touch_down(self, touch):
        render = self._render
        if self.collide_point(touch.x, touch.y):
            if getattr(touch, "button", "left") == "right":
                render._mouse_held.add(MOUSE_BUTTON_RIGHT)
                return True
            if getattr(touch, "button", "left") == "middle":
                return True
            # tap start, kept immutable so tap distance is measured
            # from the real touch-down point
            render._touches[touch.uid] = (touch.x, touch.y, time.time())
            render._max_simultaneous = max(
                render._max_simultaneous, len(render._touches)
            )
            if render._look_uid is None:
                # first finger steers the camera; seed the last
                # position so the first move has no delta snap
                render._look_uid = touch.uid
                try:
                    render.CAMERA.last_x = touch.x
                    render.CAMERA.last_y = render._touch_look_y(touch.y)
                except Exception:
                    pass
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        render = self._render
        if touch.uid == render._look_uid:
            # direct 1:1 drag-look: the view turns exactly as far as
            # the finger moves (same deltas as a desktop mouse drag)
            look_y = render._touch_look_y(touch.y)
            try:
                render.CAMERA.cursor_move(None, touch.x, look_y)
                if render._cursor_cb is not None:
                    render._cursor_cb(None, touch.x, look_y)
            except Exception:
                pass
            return True
        if touch.uid in render._touches:
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        render = self._render
        if getattr(touch, "button", None) == "right":
            render._mouse_held.discard(MOUSE_BUTTON_RIGHT)
            return True
        if touch.uid in render._touches:
            x0, y0, t0 = render._touches.pop(touch.uid)
            dt = time.time() - t0
            moved = math.hypot(touch.x - x0, touch.y - y0)
            # short tap without drag = place / break pulse
            if dt < 0.3 and moved < 25:
                if render._max_simultaneous >= 2:
                    render._pulse_mouse(MOUSE_BUTTON_RIGHT)
                else:
                    render._pulse_mouse(MOUSE_BUTTON_LEFT)
            if render._look_uid == touch.uid:
                # hand the camera to another finger already down
                # (re-seeded, so no snap), else wait for next touch
                render._look_uid = None
                for other_uid, (ox, oy, _t) in render._touches.items():
                    render._look_uid = other_uid
                    try:
                        render.CAMERA.last_x = ox
                        render.CAMERA.last_y = render._touch_look_y(oy)
                    except Exception:
                        pass
                    break
            if not render._touches:
                render._max_simultaneous = 0
                render._look_uid = None
            return True
        return super().on_touch_up(touch)


class _HoldButton(Button):
    """Button that holds a key / mouse button while pressed."""

    def __init__(self, render, binding, text="", toggle=False, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self._render = render
        self._binding = binding  # ("key", KEY_x) or ("mouse", BTN) or ("esc",)
        self._toggle = toggle
        self._toggled = False
        self.opacity = 0.55
        self.bind(on_press=self._on_press, on_release=self._on_release)

    def _apply(self, down):
        kind = self._binding[0]
        if kind == "key":
            if down:
                self._render._keys.add(self._binding[1])
            else:
                self._render._keys.discard(self._binding[1])
        elif kind == "mouse":
            if down:
                self._render._mouse_held.add(self._binding[1])
            else:
                self._render._mouse_held.discard(self._binding[1])
        elif kind == "esc":
            # momentary press like a keyboard tap: release MUST remove
            # the key again, otherwise ESC stays held and the pause
            # toggle in OMEFEG.py fires every 0.2 s forever.
            if down:
                self._render._keys.add(KEY_ESCAPE)
            else:
                self._render._keys.discard(KEY_ESCAPE)

    def _on_press(self, _instance):
        if self._toggle:
            self._toggled = not self._toggled
            self.opacity = 1.0 if self._toggled else 0.55
            self._apply(self._toggled)
        else:
            self._apply(True)

    def _on_release(self, _instance):
        if not self._toggle:
            self._apply(False)


class _GameApp(App):
    def __init__(self, render, **kwargs):
        super().__init__(**kwargs)
        self._render = render

    def build(self):
        render = self._render
        root = FloatLayout()
        game = _GameWidget(render)
        game.size_hint = (1, 1)
        game.pos_hint = {"x": 0, "y": 0}
        root.add_widget(game)
        render._game_widget = game

        # -- on-screen controls (only what the game polls via
        #    get_key / get_mouse_button, so OMEFEG.py is untouched) --
        def _btn(text, binding, x, y, w=0.12, h=0.09, toggle=False):
            b = _HoldButton(
                render,
                binding,
                text=text,
                toggle=toggle,
                size_hint=(w, h),
                pos_hint={"x": x, "y": y},
            )
            # readable on small phone screens
            b.font_size = "18sp"
            root.add_widget(b)
            return b

        # movement block (bottom-left)
        _btn("FWD", ("key", KEY_W), 0.13, 0.19)
        _btn("LEFT", ("key", KEY_A), 0.01, 0.10)
        _btn("BACK", ("key", KEY_S), 0.13, 0.10)
        _btn("RIGHT", ("key", KEY_D), 0.25, 0.10)
        # actions (bottom-right)
        _btn("JUMP", ("key", KEY_SPACE), 0.87, 0.10)
        _btn("FLY", ("key", KEY_F), 0.75, 0.10, toggle=True)
        _btn("PLACE", ("mouse", MOUSE_BUTTON_LEFT), 0.87, 0.20)
        _btn("BREAK", ("mouse", MOUSE_BUTTON_RIGHT), 0.75, 0.20)
        # cycles the selected block (same as ALT on desktop); each tap
        # advances one block and the HUD "SELECTED BLOCK" line updates
        _btn("BLOCK", ("key", KEY_LEFT_ALT), 0.87, 0.30)
        # pause (top-right)
        _btn("PAUSE", ("esc",), 0.86, 0.88, w=0.12, h=0.07)

        if platform in ("win", "linux", "macosx"):
            try:
                Window.size = (WIDTH, HEIGHT)
            except Exception:
                pass
        Window.bind(on_resize=render._on_resize)

        if platform not in ("android", "ios"):
            try:
                # target must be a Widget (Kivy calls to_window on it)
                self._keyboard = Window.request_keyboard(
                    render._keyboard_closed, game
                )
                if self._keyboard is not None:
                    self._keyboard.bind(
                        on_key_down=render._on_key_down,
                        on_key_up=render._on_key_up,
                    )
            except Exception:
                self._keyboard = None
        else:
            self._keyboard = None

        Clock.schedule_interval(render._frame, 0)
        return root

    def on_start(self):
        render = self._render
        render._gl_ready = True
        try:
            render._load_textures()
        except Exception:
            pass
        # push initial uniforms once GL exists
        try:
            render.update_programs()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Render (same public API as Render.py)
# ---------------------------------------------------------------------------

class Render:
    PRESS = PRESS
    RELEASE = RELEASE

    KEY_W = KEY_W
    KEY_S = KEY_S
    KEY_A = KEY_A
    KEY_D = KEY_D

    KEY_LEFT_CONTROL = KEY_LEFT_CONTROL

    KEY_F = KEY_F
    KEY_R = KEY_R
    KEY_SPACE = KEY_SPACE

    KEY_ESCAPE = KEY_ESCAPE

    CURSOR = CURSOR
    CURSOR_NORMAL = CURSOR_NORMAL
    CURSOR_DISABLED = CURSOR_DISABLED

    MOUSE_BUTTON_RIGHT = MOUSE_BUTTON_RIGHT

    MOUSE_BUTTON_LEFT = MOUSE_BUTTON_LEFT

    KEY_LEFT_ALT = KEY_LEFT_ALT

    FOV = FOV

    PROJECTION = np.array(
        Matrix44.perspective_projection(FOV, WIDTH / HEIGHT, 0.1, 1000),
        dtype="f4",
    )

    def __init__(self, init_function: Callable, update_function: Callable):
        global _ACTIVE_RENDER
        self.init_function = init_function
        self.update_function = update_function

        # render.window is passed to get_key() by Camera; keep it self.
        self.window = self

        self.ctx = _CtxProxy(self)
        self.ctx.clear(0, 0, 0, 1)

        self.dt = 1.0 / 60.0

        self._keys: set[int] = set()
        self._key_names: set[str] = set()
        self._mouse_held: set[int] = set()
        self._mouse_pulse: dict[int, float] = {}
        self._touches: dict = {}
        self._max_simultaneous = 0
        # uid of the single finger currently steering the camera
        # (extra fingers only count for tap detection)
        self._look_uid = None

        self._cursor_cb = None
        self._size_callbacks: list[Callable] = []
        self._input_mode = {}

        self._win_w, self._win_h = WIDTH, HEIGHT
        self.PROJECTION = np.array(
            Matrix44.perspective_projection(
                self.FOV, WIDTH / HEIGHT, 0.1, 1000
            ),
            dtype="f4",
        )

        self._models: list = []
        self._gl_ready = False
        self._textures: dict[str, Any] = {}
        self._game_widget = None
        self._should_close = False

        self._create_programs()

        self.CAMERA = Camera([0, 2, 0], self)

        self.set_cursor_pos_callback(self.CAMERA.cursor_move)

        self.init_programs()

        _ACTIVE_RENDER = self

        self.init_function(self)

        self._app = _GameApp(self)
        self._app.run()

    # -- programs (uniform proxies, same names as desktop) ------------------

    def _create_programs(self):
        self.blocks_program = _ProgramProxy()
        self.text_program = _ProgramProxy()
        self.item_program = _ProgramProxy()
        self.chunk_program = _ProgramProxy()
        self.HUDText_program = _ProgramProxy()

    def init_programs(self):
        self.blocks_program["atlasArray"] = 0
        self.blocks_program["projection"].write(self.PROJECTION)
        self.blocks_program["frame"] = 0
        self.blocks_program["chance"] = -1
        self.blocks_program["TEXTURE_W"] = TEXTURE_W
        self.blocks_program["TEXTURE_H"] = TEXTURE_H
        self.blocks_program["ATLAS_W"] = ATLAS_W
        self.blocks_program["ATLAS_H"] = ATLAS_H

        self.text_program["atlasArray"] = 1
        self.text_program["projection"].write(self.PROJECTION)
        self.text_program["frame"] = 0
        self.text_program["chance"] = -1
        self.text_program["TEXTURE_W"] = CHR_W
        self.text_program["TEXTURE_H"] = CHR_H
        self.text_program["ATLAS_W"] = CHAR_W
        self.text_program["ATLAS_H"] = CHAR_H

        self.item_program["atlasArray"] = 2
        self.item_program["projection"].write(self.PROJECTION)
        self.item_program["frame"] = 0
        self.item_program["chance"] = -1
        self.item_program["TEXTURE_W"] = ITEM_W
        self.item_program["TEXTURE_H"] = ITEM_H
        self.item_program["ATLAS_W"] = ITEMS_W
        self.item_program["ATLAS_H"] = ITEMS_H

        self.chunk_program["atlasArray"] = 0
        self.chunk_program["projection"].write(self.PROJECTION)

        self.HUDText_program["atlasArray"] = 1
        self.HUDText_program["screenSize"].value = (WIDTH, HEIGHT)
        self.HUDText_program["TEXTURE_W"] = CHR_W
        self.HUDText_program["TEXTURE_H"] = CHR_H
        self.HUDText_program["ATLAS_W"] = CHAR_W
        self.HUDText_program["ATLAS_H"] = CHAR_H

    def update_programs(self):
        try:
            view = self.CAMERA.view.astype("f4")
            campos = self.CAMERA.position.astype("f4")
        except Exception:
            return
        view_bytes = view.tobytes()
        campos_bytes = campos.tobytes()

        for prog in (
            self.blocks_program,
            self.text_program,
            self.chunk_program,
            self.item_program,
        ):
            prog["view"].write(view_bytes)
            prog["lightPos"].value = (9, 50, 9)
            prog["viewPos"].write(campos_bytes)

        proj = list(np.asarray(self.PROJECTION, dtype=np.float32).reshape(-1))
        view_l = list(np.asarray(view, dtype=np.float32).reshape(-1))
        campos_l = [float(campos[0]), float(campos[1]), float(campos[2])]
        for model in list(self._models):
            try:
                model.push_uniforms(proj, view_l, (9, 50, 9), campos_l)
            except Exception:
                pass

    # -- model registry / GL helpers ----------------------------------------

    def _register_model(self, model):
        if model not in self._models:
            self._models.append(model)

    def _texture(self, kind):
        tex = self._textures.get(kind)
        if tex is None:
            self._load_textures()
            tex = self._textures.get(kind)
        return tex

    def _load_textures(self):
        # Preload attempt (GL context exists in on_start).  The authoritative
        # path is lazy creation in _texture() during actual draws.
        for kind in _ATLAS_FILES:
            self._texture(kind)

    def _texture(self, kind):
        tex = self._textures.get(kind)
        if tex is None and getattr(self, "_gl_ready", False):
            tex = self._make_texture(kind)
            if tex is not None:
                self._textures[kind] = tex
        return tex

    @staticmethod
    def _make_texture(kind):
        """Build the atlas texture with an explicit upload.

        Created lazily during draws (GL context guaranteed current):
        ``CoreImage(...).texture`` outside a live context segfaults on
        some drivers.  The PNG is uploaded as-is (upright); tile rows
        are counted from the bottom in every UV mapping in this file.
        """
        path = _ATLAS_FILES[kind]
        try:
            with Image.open(path) as src:
                img = src.convert("RGBA")
            # blit_buffer takes bottom-row-first bytes (GL convention);
            # PIL gives top-row-first, so flip once here.
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            w, h = img.size
            tex = KivyTexture.create(size=(w, h), colorfmt="rgba")
            tex.blit_buffer(
                img.tobytes(), colorfmt="rgba", bufferfmt="ubyte"
            )
            tex.mag_filter = "nearest"
            tex.min_filter = "nearest"
            return tex
        except Exception:
            if os.environ.get("MOBILE_RENDER_DEBUG"):
                import traceback

                traceback.print_exc()
            return None

    def _attach_world_rc(self, rc):
        try:
            if self._game_widget is not None:
                self._game_widget.canvas.add(rc)
        except Exception:
            pass

    def _attach_hud_rc(self, rc):
        # HUD lives in canvas.after (depth already disabled there) so it
        # always draws last and without depth testing.
        try:
            widget = self._game_widget
            if widget is None:
                return
            after = widget.canvas.after
            children = list(after.children)
            if children:
                idx = len(children) - 1
                after.insert(idx, rc)
            else:
                after.add(rc)
        except Exception:
            try:
                self._game_widget.canvas.after.add(rc)
            except Exception:
                pass

    def _set_rc_visible(self, rc, visible):
        try:
            parent = rc.parent
        except Exception:
            return
        try:
            if visible and parent is None:
                # re-attach world contexts to the main canvas
                if self._game_widget is not None:
                    self._game_widget.canvas.add(rc)
            elif not visible and parent is not None:
                parent.remove(rc)
        except Exception:
            pass

    def _push_uniforms_to(self, model):
        try:
            view = self.CAMERA.view.astype("f4")
            campos = self.CAMERA.position.astype("f4")
        except Exception:
            return
        try:
            model.push_uniforms(
                list(np.asarray(self.PROJECTION, dtype=np.float32).reshape(-1)),
                list(np.asarray(view, dtype=np.float32).reshape(-1)),
                (9, 50, 9),
                [float(campos[0]), float(campos[1]), float(campos[2])],
            )
        except Exception:
            pass

    # -- frame ---------------------------------------------------------------

    def _frame(self, dt):
        if self._should_close:
            try:
                self._app.stop()
            except Exception:
                pass
            return
        self.dt = min(float(dt) if dt else 1.0 / 60.0, 0.05)

        self.update_programs()

        try:
            self.update_function(self)
        except Exception:
            # Never kill the whole app from here; the game logs itself.
            raise

    # -- input API (same as Render.py) ---------------------------------------

    def get_key(self, key: int):
        if key in self._keys:
            return PRESS
        name = _KEY_NAMES.get(key)
        if name is not None and name in self._key_names:
            return PRESS
        return RELEASE

    def _touch_look_y(self, y):
        """Kivy touch Y runs bottom-up, desktop mouse Y (which
        Camera.cursor_move expects) runs top-down. Flip so swipe up
        looks up and swipe down looks down, like a desktop drag."""
        try:
            h = Window.height or self._win_h
        except Exception:
            h = self._win_h
        return h - y

    def _on_key_down(self, _keyboard, keycode, _text, _modifiers):
        try:
            code, name = keycode
        except Exception:
            return
        if isinstance(code, int):
            self._keys.add(code)
        if isinstance(name, str):
            self._key_names.add(name)

    def _on_key_up(self, _keyboard, keycode):
        try:
            code, name = keycode
        except Exception:
            return
        self._keys.discard(code)
        if isinstance(name, str):
            self._key_names.discard(name)

    def _keyboard_closed(self):
        self._keys.clear()
        self._key_names.clear()

    def _pulse_mouse(self, button, duration=0.18):
        self._mouse_pulse[button] = time.time() + duration

    def get_mouse_button(self, button: int):
        if button in self._mouse_held:
            return PRESS
        if time.time() < self._mouse_pulse.get(button, 0):
            return PRESS
        return RELEASE

    def set_cursor_pos_callback(self, callback: Callable):
        self._cursor_cb = callback

    def set_window_size_callback(self, callback: Callable):
        self._size_callbacks.append(callback)

    def set_window_should_close(self, value):
        self._should_close = bool(value)

    def set_input_mode(self, input_mode, value):
        self._input_mode[input_mode] = value

    def set_window_pos(self, x, y):
        # no-op on mobile; kept for API compatibility
        return None

    def get_window_pos(self):
        return (0, 0)

    def _on_resize(self, window, width, height):
        try:
            self._win_w, self._win_h = int(width), int(height)
        except Exception:
            return
        try:
            self.resized(int(width), int(height))
        except Exception:
            pass
        for cb in list(self._size_callbacks):
            try:
                cb(window, width, height)
            except Exception:
                pass

    def resized(self, *args):
        """Robust against the desktop call shape
        ``render.resized(render, w, h)`` used by OMEFEG.py."""
        nums = [a for a in args if isinstance(a, (int, float))]
        if len(nums) >= 2:
            width, height = int(nums[-2]), int(nums[-1])
        else:
            try:
                width, height = int(Window.width), int(Window.height)
            except Exception:
                width, height = self._win_w, self._win_h
        if height == 0:
            height = 1
        if width == 0:
            width = 1
        self._win_w, self._win_h = width, height
        try:
            self.ctx.viewport = (0, 0, width, height)
        except Exception:
            pass
        self.PROJECTION = np.array(
            Matrix44.perspective_projection(
                self.FOV, width / height, 0.1, 1000
            ),
            dtype="f4",
        )
        try:
            self.blocks_program["projection"].write(self.PROJECTION)
            self.text_program["projection"].write(self.PROJECTION)
            self.chunk_program["projection"].write(self.PROJECTION)
            self.item_program["projection"].write(self.PROJECTION)
            self.HUDText_program["screenSize"].value = (width, height)
        except Exception:
            pass


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser()
    _parser.add_argument(
        "--stay", action="store_true", help="do not auto-close the demo"
    )
    _args = _parser.parse_args()

    def _demo_init(render):
        model = Model(render)
        model.add_model(
            "block", vertices=CUBE_MODEL_INFO[0], indices=CUBE_MODEL_INFO[1]
        )
        model.add_instances([[0, 0, 0], [2, 0, 0], [0, 0, 2]], [4, 9, 3], "block")
        text = InstancedText(render=render, charset=CHARSET)
        text.add_texts(["HELLO"], [[0, 3, 0]])
        hud = HUDText(render=render, charset=CHARSET)
        hud.add_texts(["FPS: 60"], [[10, 10]], ["FPS"])
        coll = Collectible(render)
        coll.add_collectibles([[1, 2, 1]], [0], [lambda _r: None])
        render._demo = (model, text, hud, coll)
        render.CAMERA.position = np.array([6.0, 5.0, 6.0])
        render.CAMERA.yaw = 225.0
        render.CAMERA.pitch = -20.0
        # solid floor so gravity settles the camera instead of
        # dropping it through the world before the screenshot
        render._demo_floor = {
            (x, 0, z) for x in range(-8, 9) for z in range(-8, 9)
        }
        if not _args.stay:
            import os as _os

            _shot = _os.environ.get("MOBILE_RENDER_SHOT")
            if _shot:
                Clock.schedule_once(
                    lambda _dt: Window.screenshot(name=_shot), 4
                )
            Clock.schedule_once(lambda _dt: render.set_window_should_close(True), 8)

    def _demo_update(render):
        render.ctx.clear(0.05, 0.07, 0.1, 1)
        render.CAMERA.update(render._demo_floor)
        model, text, hud, coll = render._demo
        coll.update(render.CAMERA.position.tolist())
        coll.render()
        model.render()
        text.render()
        hud.render()

    render = Render(_demo_init, _demo_update)

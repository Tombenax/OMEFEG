# buildozer.spec — OMEFEG Android build (buildozer >= 1.5.0)
# Copy next to main.py and run:  buildozer android debug
# Release (needs signing keys):  buildozer android release

[app]

title = OMEFEG

package.name = omefeg

# App id becomes org.omefeg.omefeg — keep it: main.py hardcodes this
# private dir (/data/.../org.omefeg.omefeg/files/...) as a fallback.
package.domain = org.omefeg

source.dir = .

source.include_exts = py,png,jpg,atlas,json,txt,wav,mp3,ttf,obj

# Keep the APK lean: dev server, logs, test saves, caches, Windows-only
# and VCS junk. OPENGL shaders stay (harmless, tiny).
source.exclude_patterns = logs/*,saves/*,server/*,*__pycache__*,*.pyc,*.dll,.git/*,.vscode/*

version = 0.1

# Runtime deps of the mobile path (main.py -> OMEFEG.py -> MobileRender.py):
#   kivy          UI + GLES2 renderer
#   numpy         mesh math (also a pyrr dependency)
#   pillow        texture loading (imported as PIL)
#   pyrr          matrix math (needs multipledispatch below — p4a does not
#                 reliably pull transitive deps, missing it crashes at import)
#   perlin-noise  terrain (imported as perlin_noise in perlineNoise.py).
#                 Pinned to 1.13: 1.14+ requires-python <3.13, incompatible
#                 with the p4a hostpython 3.14 used here (resolver backtracks
#                 otherwise). 1.13 is pure-Python and installs clean.
#   colorama      log colours in utils.py (unguarded import)
#   requests      account login in utils.py (guarded import, but needed for
#                 login to work; p4a auto-pulls its pure-Python deps like
#                 certifi/urllib3/idna/chardet — do NOT list those manually)
#   android       p4a android module (jnius bridge)
# Desktop-only deps (glfw, moderngl, openal, desktop_notifier, argon2,
# cryptography, ...) are either never imported on Android (Render.py is
# skipped via OMEFEG_DESKTOP) or wrapped in try/except in utils.py,
# so they stay out on purpose.
requirements = python3,kivy,numpy,pillow,pyrr,multipledispatch,perlin-noise==1.13,colorama,requests,android

# 1280x720 landscape game.
orientation = landscape

fullscreen = 1

# Multiplayer (network.py, UDP sockets) + account login (utils.py, requests).
android.permissions = INTERNET

# Launcher icon. For a splash screen, add e.g. assets/presplash.png and set:
# presplash.filename = %(source.dir)s/assets/presplash.png
icon.filename = %(source.dir)s/assets/icon.png

# One build for modern phones + emulators. android.api / minapi / ndk are
# intentionally left at buildozer defaults (last working setup).
android.archs = arm64-v8a, x86_64

[buildozer]

log_level = 2

warn_on_root = 1

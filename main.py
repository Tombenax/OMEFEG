"""Android entry point.

python-for-android only starts an app through main.py, while the game
lives in OMEFEG.py, so this just hands over to it. The game loads
everything (assets, shaders, structures, mods) through relative paths,
so run it from this folder.
"""
import os
import sys

def _prep_path(path):
    try:
        if path and os.path.isdir(path):
            os.chdir(path)
            if path not in sys.path:
                sys.path.insert(0, path)
            return True
    except Exception:
        pass
    return False


# 1. Normal case: __file__ points at the on-device app dir
#    (.../files/app). Works for both .py and compiled .pyc builds.
try:
    _prep_path(os.path.dirname(os.path.abspath(__file__)))
except Exception:
    pass

# 2. Fallback: pyc builds bake the host compile path
#    (/home/.../.buildozer/...) into tracebacks, so don't trust
#    __file__ blindly. Try the known private dirs + cwd.
for _p in (
    "/data/user/0/org.omefeg.omefeg/files/app",
    "/data/data/org.omefeg.omefeg/files/app",
    os.getcwd(),
):
    try:
        if os.path.isfile(os.path.join(_p, "OMEFEG.py")) or os.path.isfile(
            os.path.join(_p, "OMEFEG.pyc")
        ):
            _prep_path(_p)
            break
    except Exception:
        continue

# Import (not runpy.run_path("OMEFEG.py")) so both OMEFEG.py
# and compiled-only OMEFEG.pyc builds work.
import OMEFEG  # noqa: F401,E402

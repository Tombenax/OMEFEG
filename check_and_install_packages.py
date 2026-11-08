
from pathlib import Path
import ast
import subprocess
import sys
import importlib.util

script_dir = Path(__file__).parent.resolve()

# Python standard library modules that should not be installed
stdlib = sys.stdlib_module_names

# Map import names to their pip package names
PACKAGE_MAP = {
    "sdl2": "PySDL2",
    "colorama": "colorama",
    "desktop_notifier": "desktop_notifier",
    "glfw": "glfw",
    "kivy": "kivy",
    "moderngl": "moderngl",
    "numpy": "numpy",
    "openal": "PyOpenAL",
    "perlin_noise": "perlin-noise",
    "PIL": "pillow",
    "psutil": "psutil",
    "pyrr": "pyrr",
    "requests": "requests",
    "ursina": "ursina",
}

# Modules that are local or require special installation
IGNORE = {
    "OMEFEG",
    "check_and_install_packages",
    "bpy",
    "DesktopRender"
}

# Find local Python modules and packages
local_modules = {
    file.stem
    for file in script_dir.glob("*.py")
}

local_packages = {
    folder.name
    for folder in script_dir.iterdir()
    if folder.is_dir() and (
        (folder / "__init__.py").exists()
        or any(folder.glob("*.py"))
    )
}

LOCAL_MODULES = local_modules | local_packages

packages = set()

for file in script_dir.glob("*.py"):

    if file.name == "check_and_install_packages.py":
        continue

    try:
        source = file.read_text(encoding="utf-8")
        tree = ast.parse(source)

    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"Skipping {file.name}: {e}")
        continue

    for node in ast.walk(tree):

        modules = []

        if isinstance(node, ast.Import):
            modules = [
                alias.name.split(".")[0]
                for alias in node.names
            ]

        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module.split(".")[0]]

        for module in modules:

            if (
                module not in stdlib
                and module not in IGNORE
                and module not in LOCAL_MODULES
                and importlib.util.find_spec(module) is None
            ):
                packages.add(
                    PACKAGE_MAP.get(module, module)
                )

print("Found external packages:")
for package in sorted(packages):
    print(" -", package)

if not packages:
    print("No external packages found.")

else:
    answer = input("\nDo you want to install packages? (y/n): ")

    if answer.lower() == "y":
        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            *sorted(packages)
        ])

        print("\nPackages installed successfully!")
    else:
        print("Installation cancelled.")

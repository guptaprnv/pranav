"""
py2app setup — packages the menu bar app into a macOS .app bundle.

Usage:
  pip install py2app
  python setup.py py2app

Output: dist/Distributed Training.app
Then use dmgbuild to wrap it into a .dmg for distribution.
"""
from setuptools import setup

APP = ["menu_bar.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,           # hide from Dock — menu bar only
        "CFBundleName": "Distributed Training",
        "CFBundleDisplayName": "Distributed Training",
        "CFBundleIdentifier": "ai.dtrain.node",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHumanReadableCopyright": "© 2026 DTrain",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    },
    "packages": [
        "rumps",
        "node_agent",
        "p2p",
        "ledger",
        "orchestrator",
        "cloud",
        "src",
    ],
    "iconfile": "assets/icon.icns",   # place your icon here
    "semi_standalone": False,
    "site_packages": True,
}

setup(
    app=APP,
    name="Distributed Training",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

"""
dmgbuild settings — creates a distributable macOS .dmg installer.

Usage:
  pip install dmgbuild
  dmgbuild -s dmgbuild_settings.py "Distributed Training" dist/DTrain.dmg

The resulting .dmg shows the classic "drag app to Applications" window.
"""
import os

# Basic info
application = defines.get("app", "dist/Distributed Training.app")
appname = os.path.basename(application)

# .dmg volume
volume_name = "Distributed Training"
format = "UDZO"           # compressed
size = None               # auto-calculate

# Window layout
background = "builtin-arrow"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False

window_rect = ((200, 120), (540, 380))
default_view = "icon-view"
icon_size = 128
text_size = 14

# Files in the .dmg
files = [application]
symlinks = {"Applications": "/Applications"}

# Icon positions
icon_locations = {
    appname:        (160, 180),
    "Applications": (380, 180),
}

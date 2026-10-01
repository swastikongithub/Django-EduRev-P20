"""
The official LPU brand slot.

The official LPU seal (static/img/lpu_logo.png) was supplied by the project owner; the files in
static/img/brand/ are resized renditions of it (scripts/brand_renditions.py), never redrawn.
Every slot whose file is absent falls back to the neutral LPU Reserve placeholder
(docs/branding.md).
"""

from functools import cache

from django.contrib.staticfiles import finders

BRAND_DIR = "img/brand"
BRAND_FILES = {
    # Derived from the official seal static/img/lpu_logo.png by scripts/brand_renditions.py.
    "mark": "mark.png",  # the seal: rail, top bar, sign-in, MFA, error pages, door sign
    "favicon_ico": "favicon.ico",  # browser tab: 16, 32 and 48 px
    "favicon_png": "favicon-32.png",  # browser tab, PNG
    "apple_touch_icon": "apple-touch-icon.png",  # 180x180 on white, iOS home screen
    "icon_192": "icon-192.png",  # web app manifest
    "icon_512": "icon-512.png",  # web app manifest, splash
    # Optional, not supplied: a horizontal lockup for the sign-in hero, and an SVG favicon.
    "logo": "logo.svg",
    "favicon": "favicon.svg",
}


@cache
def brand_assets() -> dict[str, str]:
    """Static paths of the official files that are present (looked up once per process)."""
    found = {}
    for slot, filename in BRAND_FILES.items():
        path = f"{BRAND_DIR}/{filename}"
        if finders.find(path):
            found[slot] = path
    return found

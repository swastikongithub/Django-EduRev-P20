"""
The official LPU seal (static/img/lpu_logo.png) and its renditions in static/img/brand/
(scripts/brand_renditions.py): where they render, the favicon set, the manifest, and the
absence of any icon reference when no artwork is present (docs/branding.md).
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import override_settings
from PIL import Image

from apps.core.branding import BRAND_DIR, brand_assets

STATIC = Path(settings.BASE_DIR) / "static" / "img"
RENDITIONS = {
    "mark.png": 128,
    "icon-192.png": 192,
    "icon-512.png": 512,
    "apple-touch-icon.png": 180,
    "favicon-32.png": 32,
}


@pytest.fixture(autouse=True)
def clear_brand_cache():
    brand_assets.cache_clear()
    yield
    brand_assets.cache_clear()


def test_master_and_renditions_are_square_and_sized():
    master = Image.open(STATIC / "lpu_logo.png")
    assert master.width == master.height
    for name, size in RENDITIONS.items():
        assert Image.open(STATIC / "brand" / name).size == (size, size), name
    ico = Image.open(STATIC / "brand" / "favicon.ico")
    assert {(16, 16), (32, 32), (48, 48)} <= set(ico.info["sizes"])
    # iOS shows transparency as black: the touch icon must be opaque.
    assert Image.open(STATIC / "brand" / "apple-touch-icon.png").mode == "RGB"


def test_slots_found():
    assets = brand_assets()
    for slot in ("mark", "favicon_ico", "favicon_png", "apple_touch_icon", "icon_192", "icon_512"):
        assert slot in assets, slot
    assert "logo" not in assets  # no horizontal lockup was supplied; the seal is used instead


@pytest.mark.django_db
def test_sign_in_page_shows_the_seal_and_official_favicons(client):
    html = client.get("/login/").content.decode()
    assert f"{BRAND_DIR}/mark" in html  # sign-in hero
    assert f"{BRAND_DIR}/favicon" in html
    assert f"{BRAND_DIR}/apple-touch-icon" in html
    assert "img/favicon.svg" not in html  # the placeholder favicon is gone
    assert 'rel="manifest"' in html


@pytest.mark.django_db
def test_navigation_seal_is_decorative_inside_its_labelled_link(client, student):
    client.force_login(student)
    html = client.get("/home/").content.decode()
    rail_link = html.split('class="rail__brand"', 1)[1].split("</a>", 1)[0]
    assert 'aria-label="LPU Reserve home"' in rail_link
    assert f"{BRAND_DIR}/mark" in rail_link
    assert 'alt=""' in rail_link


@pytest.mark.django_db
def test_standalone_seal_has_alt_text(client):
    html = client.get("/no-such-page/").content.decode()  # branded error page
    assert f"{BRAND_DIR}/mark" in html
    assert 'alt="Lovely Professional University"' in html


@pytest.mark.django_db
def test_manifest_lists_the_official_icons(client):
    resp = client.get("/site.webmanifest")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/manifest+json"
    icons = resp.json()["icons"]
    assert [i["sizes"] for i in icons] == ["192x192", "512x512"]
    assert all(BRAND_DIR in i["src"] for i in icons)


@pytest.mark.django_db
def test_every_icon_reference_points_at_a_real_static_file(client):
    html = client.get("/login/").content.decode()
    hrefs = re.findall(r'<link rel="(?:icon|apple-touch-icon)" href="([^"]+)"', html)
    hrefs += [i["src"] for i in client.get("/site.webmanifest").json()["icons"]]
    assert len(hrefs) >= 5  # .ico, PNG favicon, touch icon, two manifest icons
    for href in hrefs:
        assert href.startswith(settings.STATIC_URL) and finders.find(href.removeprefix(settings.STATIC_URL)), href


@pytest.mark.django_db
def test_without_artwork_no_icon_is_referenced(client, tmp_path):
    # The old placeholder favicon was removed; nothing may point at it or at any missing file.
    with override_settings(STATICFILES_DIRS=[tmp_path]):
        brand_assets.cache_clear()
        html = client.get("/login/").content.decode()
        assert 'rel="icon"' not in html and 'rel="apple-touch-icon"' not in html
        assert "favicon.svg" not in html
        assert f"{BRAND_DIR}/" not in html
        assert client.get("/site.webmanifest").json()["icons"] == []

"""
Derive the brand renditions in static/img/brand/ from the official LPU seal.

    python scripts/brand_renditions.py

The master is static/img/lpu_logo.png, supplied by the project owner as the official asset
(docs/branding.md). This script only resizes it (Lanczos) and, for the iOS icon, places it on an
opaque white square because iOS renders transparency as black. It never redraws, crops or
recolours the logo. Re-run it whenever the master is replaced, and commit the results.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "static" / "img" / "lpu_logo.png"
OUT = ROOT / "static" / "img" / "brand"


def resized(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main():
    master = Image.open(MASTER).convert("RGBA")
    if master.width != master.height:
        raise SystemExit(f"{MASTER.name} is {master.size}; the seal renditions expect a square master")
    OUT.mkdir(parents=True, exist_ok=True)

    # The seal in the UI: shown at 22-64 CSS px, so 128 px covers 2x screens everywhere.
    resized(master, 128).save(OUT / "mark.png", optimize=True)
    # Web app manifest / Android.
    resized(master, 192).save(OUT / "icon-192.png", optimize=True)
    resized(master, 512).save(OUT / "icon-512.png", optimize=True)
    # iOS home screen: opaque background, 180x180.
    tile = Image.new("RGBA", (180, 180), (255, 255, 255, 255))
    seal = resized(master, 164)
    tile.alpha_composite(seal, (8, 8))
    tile.convert("RGB").save(OUT / "apple-touch-icon.png", optimize=True)
    # Browser tab: the seal is square, so it is used whole; ICO carries 16, 32 and 48 px.
    resized(master, 256).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    resized(master, 32).save(OUT / "favicon-32.png", optimize=True)

    for path in sorted(OUT.iterdir()):
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()

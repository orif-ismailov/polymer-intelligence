#!/usr/bin/env python3
"""Crop marketplace.jpeg into named section references for pixel-matching.

Run with the backend venv (system python has no Pillow):

    backend/.venv/bin/python docs/new-design/crop_sections.py

The boxes below were measured off the source with a brightness/edge scan, not
eyeballed — see the geometry table in the redesign plan.

The source is 1199 px wide, but the portal's desktop layout only engages at
Tailwind `xl` (1280) — at 1200 the page is still on the tablet layout (hamburger
nav, 3-across directory strip, rail wrapped below). The mockup plainly shows the
desktop layout, so it is treated as a 1440-wide design exported small: every
crop is emitted twice, raw and upscaled by TARGET/1199. Compare the browser at
**1440** against the `sections1440/` set — those are 1:1.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "marketplace.jpeg"
OUT = ROOT / "sections"
OUT_1440 = ROOT / "sections1440"
OUT.mkdir(exist_ok=True)
OUT_1440.mkdir(exist_ok=True)

TARGET = 1440

im = Image.open(SRC)
w, h = im.size
SCALE = TARGET / w
print(f"source: {w}x{h}  scale->{TARGET}: {SCALE:.4f}")

im1440 = im.resize((TARGET, round(h * SCALE)), Image.LANCZOS)
im1440.save(ROOT / "marketplace@1440.jpeg", quality=95)
print(f"saved marketplace@1440.jpeg {im1440.size}")

# Coarse bands (kept — they are the "read the whole page" views).
CROPS = {
    "01-nav": (0, 0, w, 58),
    "02-hero": (0, 55, w, 365),
    "03-categories": (0, 325, w, 480),
    "04-main": (0, 480, w, 1125),
    "05-footer": (0, 1125, w, h),
    "02a-hero-copy": (0, 55, w, 230),
    "02b-hero-search": (0, 230, w, 325),
    "04a-products": (0, 480, w, 820),
    "04b-producers-rail": (0, 820, w, 1125),
}

# Per-section references, one per redesign step. Boxes are absolute pixels in
# the source; the small pad around each keeps the panel's own border visible so
# radii and hairlines can be compared, not just the fill.
CROPS.update(
    {
        # Step 2 — hero panel is a contained card: 20,64 -> 1178,359.
        "s2a-hero-copy": (14, 58, 700, 200),
        "s2b-hero-stats": (14, 195, 700, 250),
        # Step 3 — search shell 212,262 -> 985,310; chips 224,328 -> 851,346.
        "s3a-hero-search": (200, 252, 1000, 320),
        "s3b-popular-chips": (200, 320, 900, 356),
        # Step 4 — six directory cards.
        "s4-directory-strip": (14, 364, w - 14, 476),
        # Step 5 — sidebar column (categories card, then filters card).
        "s5a-sidebar-categories": (14, 484, 218, 720),
        "s5b-sidebar-filters": (14, 720, 218, 1020),
        # Step 6 — four featured product cards + their section header.
        "s6-featured-products": (218, 484, 942, 820),
        # Step 7 — verified manufacturers rail.
        "s7-manufacturers-rail": (218, 826, 942, 1040),
        # Step 8 — right rail, one card per crop.
        "s8a-rail-prices": (900, 484, w - 14, 706),
        "s8b-rail-news": (900, 712, w - 14, 940),
        "s8c-rail-services": (900, 946, w - 14, 1096),
        # Step 9 — trust band + stats bar.
        "s9a-why-join": (14, 1112, w - 14, 1232),
        "s9b-stats-bar": (14, 1236, w - 14, h - 4),
    }
)

for name, box in sorted(CROPS.items()):
    crop = im.crop(box)
    crop.save(OUT / f"{name}.jpeg", quality=95)

    scaled_box = tuple(round(v * SCALE) for v in box)
    crop1440 = im1440.crop(scaled_box)
    crop1440.save(OUT_1440 / f"{name}.jpeg", quality=95)

    print(f"saved {name:26s} {crop.size} -> @1440 {crop1440.size} at {scaled_box}")

#!/usr/bin/env python3
"""Stack a mockup crop above the matching live capture for one-image comparison.

    backend/.venv/bin/python .planning/tmp/redesign/compare.py <section> <live.png> [out.png]

<section> is a name from docs/new-design/sections1440/ (e.g. s4-directory-strip).
The mockup crop goes on top, the live capture below, both left-aligned on a
magenta background so any width/offset mismatch is loud. A ruler strip every
50px sits between them so horizontal drift is readable without a pixel probe.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
REF = ROOT / "docs/new-design/sections1440"

section, live_path = sys.argv[1], Path(sys.argv[2])
out = Path(sys.argv[3]) if len(sys.argv) > 3 else live_path.with_name(f"cmp-{section}.png")

ref = Image.open(REF / f"{section}.jpeg").convert("RGB")
live = Image.open(live_path).convert("RGB")

RULER = 22
w = max(ref.width, live.width)
canvas = Image.new("RGB", (w, ref.height + RULER + live.height), (255, 0, 255))
canvas.paste(ref, (0, 0))
canvas.paste(live, (0, ref.height + RULER))

d = ImageDraw.Draw(canvas)
y = ref.height
d.rectangle([0, y, w, y + RULER], fill=(20, 20, 20))
for x in range(0, w, 50):
    tall = x % 100 == 0
    d.line([x, y, x, y + (RULER if tall else RULER // 2)], fill=(255, 255, 255), width=1)
    if tall:
        d.text((x + 2, y + 6), str(x), fill=(200, 200, 200))

canvas.save(out)
print(f"{section}: ref {ref.size} / live {live.size} -> {out}")

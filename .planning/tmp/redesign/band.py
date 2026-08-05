#!/usr/bin/env python3
"""Stack the same y-band of the mockup and the newest live capture.

    backend/.venv/bin/python .planning/tmp/redesign/band.py <y0> <y1> [live.png]

Both are 1440-wide, so the band is a direct overlay: the mockup on top, a ruler,
then the live page. Defaults to the newest *.png at the repo root, which is where
the Playwright MCP screenshots land, and moves it into this scratch dir.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REF = ROOT / "docs/new-design/marketplace@1440.jpeg"

y0, y1 = int(sys.argv[1]), int(sys.argv[2])

if len(sys.argv) > 3:
    live_path = Path(sys.argv[3])
else:
    shots = sorted(ROOT.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not shots:
        raise SystemExit("no *.png at repo root — take a screenshot first")
    live_path = HERE / "live.png"
    shots[0].replace(live_path)
    print(f"picked up {shots[0].name}")

ref = Image.open(REF).convert("RGB")
live = Image.open(live_path).convert("RGB")
h = y1 - y0
ref_band = ref.crop((0, min(y0, ref.height), 1440, min(y1, ref.height)))
live_band = live.crop((0, min(y0, live.height), 1440, min(y1, live.height)))

RULER = 22
c = Image.new("RGB", (1440, ref_band.height + RULER + live_band.height), (255, 0, 255))
c.paste(ref_band, (0, 0))
c.paste(live_band, (0, ref_band.height + RULER))

d = ImageDraw.Draw(c)
y = ref_band.height
d.rectangle([0, y, 1440, y + RULER], fill=(20, 20, 20))
for x in range(0, 1440, 50):
    tall = x % 100 == 0
    d.line([x, y, x, y + (RULER if tall else RULER // 2)], fill=(255, 255, 255))
    if tall:
        d.text((x + 2, y + 6), str(x), fill=(200, 200, 200))

out = HERE / f"cmp-{y0}-{y1}.png"
c.save(out)
print(f"band {y0}..{y1} (h={h}) -> {out}")

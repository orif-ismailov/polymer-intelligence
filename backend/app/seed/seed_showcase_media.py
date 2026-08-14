"""
Showcase media — renders and uploads the imagery the showcase dataset refers to.

Two kinds of asset, both generated rather than sourced: freely-licensed stock
photography of polymer product does not exist in usable quality (searches return
beach-litter "nurdle" shots and clip art), and an inaccurate photo is worse than
no photo. Everything here is drawn from the product's real physical appearance.

  * product photos — a macro bed of pellets per resin (translucent PP, milky HDPE,
    clear PET, white PVC powder, warm ABS), cropped differently per offer so no two
    listings show the same frame.
  * company logos — a monogram tile keyed off the company name.

Uploads go through `storage_service`, so object keys, MIME sniffing and the
`seller_offer_files` / `companies.logo_storage_path` rows match what the real
upload endpoints produce.

    docker exec <api> python -m app.seed.seed_showcase_media

Idempotent: an offer that already has a photo, and a company that already has a
logo, are skipped. Safe to re-run.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import math
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.storage import ensure_bucket
from app.domains.companies.models import Company
from app.domains.marketplace.models import SellerOffer
from app.models.enums import OfferFileKind
from app.services import storage_service

MASTER = (2000, 1500)
CARD = (1400, 1050)

# ── Physical appearance per resin ─────────────────────────────────────────────
RESINS: dict[str, dict] = {
    "PP":    {"base": (238, 236, 230), "hi": (255, 255, 252), "alpha": 232,
              "shape": "lens", "bg": (150, 146, 138), "size": (63, 48)},
    "HDPE":  {"base": (246, 245, 241), "hi": (255, 255, 255), "alpha": 248,
              "shape": "cyl", "bg": (158, 156, 150), "size": (61, 53)},
    "LDPE":  {"base": (232, 236, 234), "hi": (255, 255, 255), "alpha": 220,
              "shape": "lens", "bg": (146, 152, 150), "size": (65, 51)},
    "LLDPE": {"base": (235, 238, 238), "hi": (255, 255, 255), "alpha": 214,
              "shape": "cyl", "bg": (148, 154, 154), "size": (58, 53)},
    "PVC":   {"base": (250, 250, 248), "hi": (255, 255, 255), "alpha": 255,
              "shape": "powder", "bg": (196, 195, 190), "size": (10, 10)},
    "PET":   {"base": (226, 234, 238), "hi": (255, 255, 255), "alpha": 196,
              "shape": "cyl", "bg": (140, 150, 156), "size": (56, 48)},
    "PS":    {"base": (240, 239, 233), "hi": (255, 255, 255), "alpha": 200,
              "shape": "lens", "bg": (152, 150, 143), "size": (61, 48)},
    "ABS":   {"base": (238, 230, 214), "hi": (252, 248, 240), "alpha": 252,
              "shape": "cyl", "bg": (154, 146, 130), "size": (61, 53)},
}

# ── Per-grade appearance ──────────────────────────────────────────────────────
# A resin is not one colour. Pipe and cable compounds are carbon-black filled,
# bottle PET is a blue-tinted chip, film grades are more translucent than
# injection grades, and GPPS is glassy where HIPS is opaque. Rendering every
# listing from the resin alone produced a catalogue of near-identical grey beds
# — accurate for nothing and useless for telling two cards apart.
#
# Keys are `grade_text`; the value overrides fields of the resin spec above.
GRADE_APPEARANCE: dict[str, dict] = {
    # PE100 pressure-pipe resin — supplied black (carbon black is the UV package).
    "F7000":    {"base": (38, 38, 40), "hi": (150, 152, 156), "alpha": 255,
                 "bg": (24, 24, 26)},
    # Cable compound — black for the same reason.
    "SG-3":     {"base": (44, 44, 46), "hi": (158, 160, 164), "alpha": 255,
                 "shape": "cyl", "bg": (26, 26, 28), "size": (58, 50)},
    # Blow-moulding HDPE: opaque milky white.
    "B5823":    {"base": (250, 250, 247), "alpha": 255, "bg": (168, 167, 162)},
    # Injection HDPE: natural, slightly warmer.
    "HD50200S": {"base": (243, 240, 232), "alpha": 250, "bg": (160, 156, 147)},
    # Bottle PET — clear chips with the classic blue tint.
    "BG-780":   {"base": (214, 230, 240), "hi": (255, 255, 255), "alpha": 178,
                 "bg": (120, 138, 150)},
    "BG-841":   {"base": (206, 226, 240), "hi": (255, 255, 255), "alpha": 170,
                 "bg": (112, 132, 148)},
    # GPPS is glassy; HIPS is opaque ivory.
    "GPPS-525": {"base": (236, 240, 243), "hi": (255, 255, 255), "alpha": 158,
                 "bg": (134, 140, 146)},
    "HIPS-486": {"base": (245, 243, 236), "alpha": 255, "bg": (156, 153, 145)},
    # ABS: one natural, one the darker heat-resistant compound.
    "ABS-757":  {"base": (242, 234, 218), "alpha": 253, "bg": (158, 150, 134)},
    "ABS-121H": {"base": (206, 196, 178), "alpha": 255, "bg": (128, 121, 108)},
    # PP film grade — more translucent than the raffia/injection grades.
    "PPH-FN04": {"base": (236, 238, 236), "alpha": 208, "bg": (146, 149, 146)},
    # PP block copolymer for automotive — greyer natural.
    "EP548R":   {"base": (230, 230, 227), "alpha": 240, "bg": (144, 143, 139)},
    # Agricultural LDPE carries a UV masterbatch: faint blue-grey cast.
    "153-02K":  {"base": (222, 230, 232), "alpha": 226, "bg": (136, 146, 150)},
    # Suspension PVC for rigid profile stays the white powder of the resin spec.
}


def _pellet(spec: dict, rng: random.Random, scale: float) -> Image.Image:
    w = max(4, int(spec["size"][0] * scale))
    h = max(4, int(spec["size"][1] * scale))
    ss = 3
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    jitter = rng.randint(-10, 8)
    body = tuple(max(0, min(255, c + jitter)) for c in spec["base"])

    if spec["shape"] == "cyl":
        d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1],
                            radius=int(w * ss * 0.34), fill=(*body, spec["alpha"]))
    else:
        d.ellipse([0, 0, w * ss - 1, h * ss - 1], fill=(*body, spec["alpha"]))

    mask = img.split()[3]
    empty = Image.new("RGBA", img.size, (0, 0, 0, 0))

    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).ellipse(
        [w * ss * 0.18, h * ss * 0.24, w * ss * 1.12, h * ss * 1.16], fill=(0, 0, 0, 70))
    img = Image.alpha_composite(
        img, Image.composite(shade.filter(ImageFilter.GaussianBlur(w * ss * 0.10)), empty, mask))

    glint = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glint).ellipse(
        [w * ss * 0.20, h * ss * 0.14, w * ss * 0.52, h * ss * 0.42], fill=(*spec["hi"], 205))
    img = Image.alpha_composite(
        img, Image.composite(glint.filter(ImageFilter.GaussianBlur(w * ss * 0.055)), empty, mask))

    return img.resize((w, h), Image.LANCZOS).rotate(
        rng.uniform(0, 360), expand=True, resample=Image.BICUBIC)


def render_master(code: str, seed: int, appearance: dict | None = None) -> Image.Image:
    """A large pellet bed, later cropped per offer so listings differ.

    `appearance` overrides fields of the resin spec for a specific grade (a black
    pipe compound, a blue-tinted PET chip) — see GRADE_APPEARANCE.
    """
    spec = {**RESINS[code], **(appearance or {})}
    rng = random.Random(seed)
    w, h = MASTER
    canvas = Image.new("RGB", (w, h), spec["bg"])

    mottle = Image.new("L", (w // 8, h // 8))
    md = ImageDraw.Draw(mottle)
    for _ in range(600):
        x, y = rng.randrange(mottle.width), rng.randrange(mottle.height)
        md.ellipse([x, y, x + rng.randint(4, 22), y + rng.randint(4, 22)],
                   fill=rng.randint(70, 190))
    mottle = mottle.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(9))
    canvas = Image.composite(
        canvas, Image.new("RGB", (w, h), tuple(int(c * 0.72) for c in spec["bg"])), mottle)

    if spec["shape"] == "powder":
        grain = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grain)
        for _ in range(170_000):
            x, y = rng.randrange(w), rng.randrange(h)
            r = rng.choice([1, 1, 1, 2, 2, 3])
            v = rng.randint(214, 255)
            gd.ellipse([x, y, x + r, y + r],
                       fill=(v, v, v - rng.randint(0, 6), rng.randint(150, 255)))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), grain).convert("RGB")
        canvas = canvas.filter(ImageFilter.GaussianBlur(0.6))
        shade = Image.new("L", (w, h), 0)
        sd = ImageDraw.Draw(shade)
        for i in range(11):
            sd.ellipse([-400 + i * 240, h * 0.30 + math.sin(i) * 150, 320 + i * 240, h * 1.25],
                       fill=26)
        canvas = Image.composite(
            canvas, Image.new("RGB", (w, h), (176, 175, 170)),
            shade.filter(ImageFilter.GaussianBlur(70)).point(lambda v: 255 - v))
    else:
        for scale, blur, dim, count in (
            (0.86, 3.4, 0.62, 1250), (1.00, 1.4, 0.82, 1000), (1.16, 0.0, 1.0, 760)
        ):
            plane = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            for _ in range(count):
                sprite = _pellet(spec, rng, scale)
                x, y = rng.randint(-40, w - 10), rng.randint(-40, h - 10)
                sh = Image.new("RGBA", sprite.size, (0, 0, 0, 0))
                ImageDraw.Draw(sh).ellipse(
                    [sprite.width * 0.10, sprite.height * 0.16,
                     sprite.width * 0.96, sprite.height * 1.0], fill=(0, 0, 0, 115))
                plane.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)), (x + 5, y + 7))
                plane.alpha_composite(sprite, (x, y))
            if blur:
                plane = plane.filter(ImageFilter.GaussianBlur(blur))
            if dim < 1.0:
                r, g, b, a = plane.split()
                plane = Image.merge("RGBA", (
                    r.point(lambda v, d=dim: int(v * d)),
                    g.point(lambda v, d=dim: int(v * d)),
                    b.point(lambda v, d=dim: int(v * d)), a))
            canvas = Image.alpha_composite(canvas.convert("RGBA"), plane).convert("RGB")

    light = Image.new("L", (w, h), 0)
    ImageDraw.Draw(light).ellipse([-w * 0.35, -h * 0.55, w * 0.95, h * 1.05], fill=255)
    canvas = Image.composite(
        canvas.point(lambda v: min(255, int(v * 1.13))), canvas,
        light.filter(ImageFilter.GaussianBlur(230)))
    return canvas


def crop_variant(master: Image.Image, seed: int) -> bytes:
    """A distinct framing of the master: crop, flip, slight tone shift, vignette."""
    rng = random.Random(seed)
    mw, mh = master.size
    cw = rng.randint(int(mw * 0.62), int(mw * 0.86))
    ch = int(cw * CARD[1] / CARD[0])
    ch = min(ch, mh)
    x = rng.randint(0, mw - cw)
    y = rng.randint(0, mh - ch)
    im = master.crop((x, y, x + cw, y + ch)).resize(CARD, Image.LANCZOS)
    if rng.random() < 0.5:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)

    tone = rng.uniform(0.95, 1.06)
    im = im.point(lambda v, t=tone: max(0, min(255, int(v * t))))

    vig = Image.new("L", CARD, 0)
    ImageDraw.Draw(vig).ellipse(
        [-CARD[0] * 0.14, -CARD[1] * 0.14, CARD[0] * 1.14, CARD[1] * 1.14], fill=255)
    im = Image.composite(im, im.point(lambda v: int(v * 0.63)),
                         vig.filter(ImageFilter.GaussianBlur(190)))
    im = im.filter(ImageFilter.UnsharpMask(radius=2.4, percent=76, threshold=3))

    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, subsampling=1, optimize=True)
    return buf.getvalue()


# ── Company logos ─────────────────────────────────────────────────────────────

#: Deep, saturated marks — readable at 40 px in the members list and at 128 px on
#: the profile header. Paired light/dark so the monogram always has contrast.
_LOGO_PALETTE = [
    ((16, 84, 62), (52, 211, 153)), ((14, 63, 105), (96, 165, 250)),
    ((72, 33, 96), (192, 132, 252)), ((104, 46, 18), (251, 146, 60)),
    ((94, 20, 40), (251, 113, 133)), ((22, 68, 74), (45, 212, 191)),
    ((60, 62, 16), (190, 214, 60)), ((30, 34, 88), (129, 140, 248)),
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _initials(name: str) -> str:
    cleaned = name.replace("ООО", "").replace("АО", "").replace("СП", "")
    for ch in "«»\"'":
        cleaned = cleaned.replace(ch, " ")
    words = [w for w in cleaned.split() if len(w) > 1 and w[0].isalpha()]
    if not words:
        return "PI"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def render_logo(name: str, seed: int) -> bytes:
    """A monogram tile: hexagon motif (polymer chain) behind two initials."""
    size = 512
    rng = random.Random(seed)
    dark, light = _LOGO_PALETTE[seed % len(_LOGO_PALETTE)]

    img = Image.new("RGB", (size, size), dark)
    d = ImageDraw.Draw(img, "RGBA")

    # Diagonal wash so the tile is not flat.
    wash = Image.new("L", (size, size))
    wd = ImageDraw.Draw(wash)
    for i in range(size):
        wd.line([(i, 0), (0, i)], fill=int(150 * i / size))
    img = Image.composite(
        Image.new("RGB", (size, size), tuple(min(255, int(c * 1.7)) for c in dark)), img, wash)
    d = ImageDraw.Draw(img, "RGBA")

    # Hexagonal lattice — the polymer-chain motif, low contrast.
    r = size * 0.13
    for row in range(-1, 6):
        for col in range(-1, 6):
            cx = col * r * 1.75 + (r * 0.87 if row % 2 else 0)
            cy = row * r * 1.5
            pts = [(cx + r * math.cos(math.pi / 6 + k * math.pi / 3),
                    cy + r * math.sin(math.pi / 6 + k * math.pi / 3)) for k in range(6)]
            d.polygon(pts, outline=(*light, 34))

    initials = _initials(name)
    font = _font(int(size * 0.40))
    box = d.textbbox((0, 0), initials, font=font)
    d.text(((size - (box[2] - box[0])) / 2 - box[0],
            (size - (box[3] - box[1])) / 2 - box[1] - size * 0.02),
           initials, font=font, fill=(*light, 255))

    # Accent underline, aligned with the design system's neon rule.
    d.rounded_rectangle([size * 0.34, size * 0.775, size * 0.66, size * 0.795],
                        radius=size * 0.01, fill=(*light, 220))

    del rng
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True)
    return buf.getvalue()


# ── Upload ────────────────────────────────────────────────────────────────────


def seed_media(db: Session, *, force: bool = False) -> None:
    ensure_bucket()

    # ── logos ────────────────────────────────────────────────────────────────
    companies = db.query(Company).order_by(Company.id).all()
    logos = 0
    for company in companies:
        if company.logo_storage_path and not force:
            continue
        name = company.short_name or company.legal_name or f"Company {company.id}"
        seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
        storage_service.upload_company_logo(db, company, render_logo(name, seed), "logo.jpg")
        logos += 1
    db.commit()
    print(f"logos: {logos} uploaded")

    # ── product photos ───────────────────────────────────────────────────────
    offers = (
        db.query(SellerOffer)
        .filter(SellerOffer.status.in_(("approved", "pending_moderation", "draft", "archived")))
        .order_by(SellerOffer.id)
        .all()
    )
    masters: dict[str, Image.Image] = {}
    photos = 0
    for offer in offers:
        existing = [f for f in offer.files if f.kind == OfferFileKind.image]
        if existing and not force:
            continue
        # --force REPLACES: without this the old frames stay attached and the
        # gallery just grows, so a re-render of the same offer would show both
        # the previous look and the new one side by side.
        for stale in existing:
            db.delete(stale)
        if existing:
            db.flush()
        code = (offer.polymer_type or "PP").upper()
        if code not in RESINS:
            code = "PP"
        # A master per (resin, grade appearance) — grades that override nothing
        # share the resin's master, so this stays a handful of renders.
        grade = (offer.grade_text or "").strip()
        key = f"{code}:{grade}" if grade in GRADE_APPEARANCE else code
        if key not in masters:
            masters[key] = render_master(code, seed=abs(hash(key)) % 10_000,
                                         appearance=GRADE_APPEARANCE.get(grade))
            print(f"  rendered master {key}")
        master = masters[key]

        for n in range(2 if offer.id % 3 else 3):
            data = crop_variant(master, seed=offer.id * 17 + n)
            storage_service.upload_offer_file(
                db, offer.id, data,
                f"{code.lower()}-{offer.grade_text or 'grade'}-{n + 1}.jpg",
                kind=OfferFileKind.image,
            )
            photos += 1
        db.commit()

    print(f"photos: {photos} uploaded across {len(offers)} offers")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render and upload showcase media.")
    parser.add_argument("--force", action="store_true",
                        help="re-render even where media already exists")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        seed_media(db, force=args.force)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

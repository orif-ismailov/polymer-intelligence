"""
Showcase product photography — real photos, mapped per grade.

Replaces the procedurally rendered pellet beds from `seed_showcase_media` with
actual photographs. The renders were accurate and cohesive but they were drawings;
this seeder attaches real images sourced from Pexels (free licence, commercial use
permitted, no attribution required).

The source files are NOT in the repository — they are third-party photographs, and
committing 3 MB of them would put a licence question into source control for no
benefit. They are staged on the host instead:

    scp curated/*.jpg <host>:/tmp/product_photos/
    docker cp /tmp/product_photos <api>:/tmp/product_photos
    docker exec <api> python -m app.seed.seed_showcase_photos --dir /tmp/product_photos

Mapping is physical, not decorative: a grade gets the photo that looks like how
that material is actually supplied. PE100 pipe resin and PVC cable compound are
black; suspension PVC is a powder; bottle PET and GPPS are clear; the rest are
natural. A pink pellet stock shot would be a prettier card and a wrong one.

Each offer gets 2-3 DIFFERENT crops of its source photo, so a catalogue with more
grades than source images still reads as many listings rather than one repeated
frame. Idempotent: an offer that already has a photo is skipped unless --force.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import random
import sys

from PIL import Image, ImageEnhance
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.domains.marketplace.models import SellerOffer
from app.models.enums import OfferFileKind
from app.services import storage_service

RNG = random.Random(20260803)
CARD = (1400, 1050)

#: grade_text → source photo stem. Grades absent here fall back to POLYMER_FALLBACK.
GRADE_PHOTO: dict[str, str] = {
    # ── black compounds ───────────────────────────────────────────────────────
    "F7000": "black_a",       # PE100 pressure pipe — carbon black is the UV package
    # black_b is the same material on a pink studio backdrop — right pellets,
    # wrong register for an industrial catalogue.
    "SG-3": "black_c",        # PVC cable compound
    # ── powder ────────────────────────────────────────────────────────────────
    "SG-5": "powder",         # suspension PVC for rigid profile
    # ── clear / glassy ────────────────────────────────────────────────────────
    "BG-780": "clear_a",      # bottle PET
    "BG-841": "clear_b",
    "GPPS-525": "clear_a",    # general-purpose polystyrene
    "PPH-FN04": "clear_b",    # BOPP film grade — low gel, high clarity
    "2420D": "clear_b",       # LDPE film
    # ── natural ───────────────────────────────────────────────────────────────
    "T30S": "natural_a",
    "030SG": "natural_b",
    "H030 SG": "natural_a",
    "EP548R": "natural_b",    # block copolymer, automotive
    "B5823": "natural_a",     # blow moulding HDPE
    "HD50200S": "natural_b",  # injection HDPE
    "153-02K": "natural_b",   # agricultural LDPE
    "LL0209AA": "natural_a",
    "HIPS-486": "natural_a",  # opaque ivory
    "ABS-757": "natural_b",
    "ABS-121H": "natural_b",
}

#: Used when a grade is not listed above (a seller's own free-text grade).
POLYMER_FALLBACK: dict[str, str] = {
    "PP": "natural_a", "HDPE": "natural_a", "LDPE": "clear_b", "LLDPE": "natural_a",
    "PVC": "powder", "PET": "clear_a", "PS": "clear_a", "ABS": "natural_b",
}


def _load(directory: pathlib.Path) -> dict[str, Image.Image]:
    photos: dict[str, Image.Image] = {}
    for path in sorted(directory.glob("*.jpg")):
        photos[path.stem] = Image.open(path).convert("RGB")
    return photos


def crop_variant(source: Image.Image, seed: int) -> bytes:
    """One framing of a source photo: crop, flip, mild tone shift.

    A crop rather than a resize — the point is that two listings sharing a source
    image do not show the same frame. The window is kept large enough that the
    subject survives; a tight crop of a pellet bed stops looking like product.
    """
    rng = random.Random(seed)
    w, h = source.size
    target_ratio = CARD[0] / CARD[1]

    # Largest window of the card's aspect that fits, then pulled in a little.
    if w / h > target_ratio:
        box_h = int(h * rng.uniform(0.80, 0.97))
        box_w = int(box_h * target_ratio)
    else:
        box_w = int(w * rng.uniform(0.80, 0.97))
        box_h = int(box_w / target_ratio)
    box_w, box_h = min(box_w, w), min(box_h, h)

    x = rng.randint(0, max(0, w - box_w))
    y = rng.randint(0, max(0, h - box_h))
    im = source.crop((x, y, x + box_w, y + box_h)).resize(CARD, Image.LANCZOS)

    if rng.random() < 0.5:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.96, 1.05))
    im = ImageEnhance.Color(im).enhance(rng.uniform(0.94, 1.06))

    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, subsampling=1, optimize=True)
    return buf.getvalue()


def seed_photos(db: Session, directory: pathlib.Path, *, force: bool = False) -> None:
    photos = _load(directory)
    if not photos:
        print(f"no .jpg files in {directory}")
        return
    print(f"source photos: {', '.join(sorted(photos))}")

    offers = (
        db.query(SellerOffer)
        .filter(SellerOffer.status.in_(("approved", "pending_moderation", "draft", "archived")))
        .order_by(SellerOffer.id)
        .all()
    )
    uploaded = skipped = 0
    for offer in offers:
        existing = [f for f in offer.files if f.kind == OfferFileKind.image]
        if existing and not force:
            skipped += 1
            continue
        # --force REPLACES; otherwise the rendered frames would stay attached and
        # the gallery would show a drawing next to a photograph.
        for stale in existing:
            db.delete(stale)
        if existing:
            db.flush()

        grade = (offer.grade_text or "").strip()
        code = (offer.polymer_type or "PP").upper()
        stem = GRADE_PHOTO.get(grade) or POLYMER_FALLBACK.get(code, "natural_a")
        source = photos.get(stem) or next(iter(photos.values()))

        for n in range(2 if offer.id % 3 else 3):
            data = crop_variant(source, seed=offer.id * 31 + n)
            storage_service.upload_offer_file(
                db, offer.id, data,
                f"{code.lower()}-{grade or 'grade'}-{n + 1}.jpg",
                kind=OfferFileKind.image,
            )
            uploaded += 1
        db.commit()

    print(f"photos: {uploaded} uploaded, {skipped} offers left alone")


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach real product photography to offers.")
    parser.add_argument("--dir", default="/tmp/product_photos", help="source photo directory")
    parser.add_argument("--force", action="store_true", help="replace existing images")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        seed_photos(db, pathlib.Path(args.dir), force=args.force)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

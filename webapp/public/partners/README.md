# Partner logos

The landing "НАШИ ПАРТНЁРЫ" section renders logos from this folder. Drop each
company's official, licensed logo here using the **exact filenames** below. Until a
file exists, that tile falls back to a styled brand name automatically — nothing
breaks if a logo is missing.

Served at `${BASE_URL}partners/<file>` (i.e. `/partners/…` in dev, `/webapp/partners/…`
in production). Referenced from `src/pages/Landing.tsx` → `PARTNERS`.

## Expected files

| Company                | Filename            |
|------------------------|---------------------|
| LUKOIL                 | `lukoil.svg`        |
| SINOPEC                | `sinopec.svg`       |
| China Energy           | `china-energy.svg`  |
| KunLun                 | `kunlun.svg`        |
| SIBUR                  | `sibur.svg`         |
| Turkmennebit           | `turkmennebit.svg`  |
| KazMunayGas            | `kazmunaygas.svg`   |
| NIOC                   | `nioc.svg`          |
| Uzbekneftegaz          | `uzbekneftegaz.svg` |

`.svg` is preferred (crisp at any size); `.png` works too — if you use PNG, update the
extension in the `PARTNERS` list in `src/pages/Landing.tsx`. Aim for transparent
background; the tiles render on a dark surface, so light/white or full-color marks
read best. Rendered height is capped at ~34px.

## Sourcing & licensing — IMPORTANT

These are third-party trademarks. Only add a logo if:

1. **You have the right to display it** — i.e. there is a genuine partnership/relationship,
   or you are otherwise permitted to reference the brand.
2. **You use the official asset** from the company's own brand / press / media kit
   (search "<company> brand assets" or "<company> media kit"), and follow their usage
   guidelines (clear space, do-not-alter, color variants).

Do not scrape or recolor logos, and do not imply a partnership that does not exist —
that is trademark misuse and can be misleading. If you are unsure about a specific
logo, leave the file out and the styled text fallback will be shown instead.

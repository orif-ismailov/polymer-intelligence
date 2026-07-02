# Final-CTA image

The "Готовы начать выгодные сделки?" section renders an image from here.

- **Add a file:** drop your photo as `deal.jpg` (or `.png`/`.webp`) in this folder.
  It appears automatically. Recommended ~1000×700px, landscape; it's cropped to the
  panel with `object-fit: cover` (max height ~240px).
- **Or use a URL:** paste a full `https://…` image URL into `CTA_IMAGE` in
  `src/pages/Landing.tsx` (if you use a different local filename, set it there too).
- **Fallback:** until a file/URL is present, the CSS "barrels" illustration is shown —
  nothing breaks.

## Free, commercial-use sources (no attribution required)

Pick something on-brand (polymer granules / pellets, refinery, industrial):

- Unsplash — https://unsplash.com/s/photos/plastic-pellets  ·  https://unsplash.com/s/photos/plastic-granules
- Pexels — https://www.pexels.com/search/petrochemical/  ·  https://www.pexels.com/search/chemical%20plant/
- Pixabay — https://pixabay.com/images/search/petrochemical/

Only use images whose license permits your use (the sources above are free for
commercial use). Save the file here as `deal.jpg` and you're done.

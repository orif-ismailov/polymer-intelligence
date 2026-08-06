/**
 * Composited-pixel contrast probe for the storefront hero.
 *
 * `docs/design-system.md`: "No contrast assertion can see text on a photograph.
 * Token maths compares two flat colours; the storefront hero paints over a JPEG,
 * where the backdrop varies per pixel and per breakpoint. Measure it by hand:
 * hide the text runs, screenshot, then sample the composited pixels inside each
 * run's box and take the *worst* ratio, not the average. Re-run it at 390 AND
 * desktop, in both themes, whenever the scrim, the crop or the copy's position
 * changes."
 *
 * This is that procedure, automated. It screenshots with the text hidden, loads
 * the shot back into the same page as a data URL, and reads the pixels off a
 * canvas — so there is no PNG decoder dependency.
 *
 * Usage: node scripts/hero-contrast.mjs [baseURL]
 */
import { chromium } from "playwright-core";

const BASE = process.argv[2] ?? "http://localhost:5173";

const MATRIX = [
  { theme: "dark", width: 1440, height: 900 },
  { theme: "dark", width: 390, height: 844 },
  { theme: "light", width: 1440, height: 900 },
  { theme: "light", width: 390, height: 844 },
];

/** The three runs the design-system note names, by role rather than by class. */
const RUNS = `() => {
  const section = document.querySelector('section[aria-labelledby="hero-heading"]');
  const h1 = section.querySelector('#hero-heading');
  const subtitle = h1.nextElementSibling;
  const popular = [...section.querySelectorAll('span,p,div')].find((el) =>
    el.children.length === 0 && /Popular queries|Популярные|Ommabop/i.test(el.textContent || ''));
  return [
    ['h1', h1],
    ['subtitle', subtitle],
    ['popular-query label', popular],
  ].filter(([, el]) => el);
}`;

function luminance([r, g, b]) {
  const f = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const browser = await chromium.launch();
const rows = [];

for (const { theme, width, height } of MATRIX) {
  const page = await browser.newPage({ viewport: { width, height } });
  await page.addInitScript((t) => localStorage.setItem("portal.theme", t), theme);
  await page.goto(BASE, { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForSelector("#hero-heading");
  // The hero image is the LCP element; sampling before it decodes measures the
  // scrim over nothing and always passes.
  await page.waitForFunction(() => {
    const img = document.querySelector('section[aria-labelledby="hero-heading"] img');
    return img && img.complete && img.naturalWidth > 0;
  });
  await page.waitForTimeout(400); // hero-rise / hero-drift settle

  const runs = await page.evaluate(`(${RUNS})().map(([name, el]) => {
    const r = el.getBoundingClientRect();
    const c = getComputedStyle(el).color;
    return { name, color: c, box: { x: r.x, y: r.y, w: r.width, h: r.height } };
  })`);

  // Hide every run at once, so no run's glyphs land inside another's box.
  await page.evaluate(`(${RUNS})().forEach(([, el]) => { el.style.visibility = 'hidden'; })`);
  const shot = (await page.screenshot({ type: "png" })).toString("base64");

  const sampled = await page.evaluate(
    async ({ b64, runs }) => {
      const img = new Image();
      img.src = `data:image/png;base64,${b64}`;
      await img.decode();
      const cv = document.createElement("canvas");
      cv.width = img.width;
      cv.height = img.height;
      cv.getContext("2d").drawImage(img, 0, 0);
      // The shot is in device pixels; the boxes are in CSS pixels.
      const s = img.width / window.innerWidth;
      return runs.map(({ name, color, box }) => {
        const x = Math.max(0, Math.round(box.x * s));
        const y = Math.max(0, Math.round(box.y * s));
        const w = Math.min(cv.width - x, Math.round(box.w * s));
        const h = Math.min(cv.height - y, Math.round(box.h * s));
        if (w <= 0 || h <= 0) return { name, color, pixels: [] };
        const d = cv.getContext("2d").getImageData(x, y, w, h).data;
        const pixels = [];
        for (let i = 0; i < d.length; i += 4) {
          const px = i / 4;
          pixels.push([d[i], d[i + 1], d[i + 2], (px % w) / w, Math.floor(px / w) / h]);
        }
        return { name, color, box, pixels };
      });
    },
    { b64: shot, runs },
  );

  for (const { name, color, box, pixels } of sampled) {
    const fg = color.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number);
    let worst = Infinity;
    let worstPx = null;
    for (const px of pixels) {
      const r = ratio(fg, px);
      if (r < worst) {
        worst = r;
        worstPx = px;
      }
    }
    rows.push({
      cell: `${theme} ${width}`,
      run: name,
      worstBackdrop: worstPx ? `rgb(${worstPx.slice(0, 3).join(",")})` : "-",
      // Where inside the run's own box the worst pixel sits, and where that is
      // on the page — which knob to reach for depends entirely on this.
      atInBox: worstPx ? `${Math.round(worstPx[3] * 100)}%,${Math.round(worstPx[4] * 100)}%` : "-",
      atVw: worstPx ? `${Math.round(((box.x + worstPx[3] * box.w) / width) * 100)}%vw` : "-",
      worstRatio: Number.isFinite(worst) ? worst.toFixed(2) : "-",
      AA: worst >= 4.5 ? "pass" : "FAIL",
    });
  }
  await page.close();
}

await browser.close();
console.table(rows);
const failed = rows.filter((r) => r.AA === "FAIL");
console.log(failed.length ? `\n${failed.length} run(s) under AA 4.5:1` : "\nAll runs >= 4.5:1");

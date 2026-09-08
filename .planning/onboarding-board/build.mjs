#!/usr/bin/env node
/**
 * Собирает онбординг-карту из board-model.json в два носителя:
 *
 *   dist/onboarding-board.excalidraw  — сцена для excalidraw.com (перетащить на холст)
 *   dist/onboarding-board.html        — одностраничная читаемая карта
 *
 * Оба выводятся из ОДНОГО описания, поэтому разойтись не могут.
 *
 *   node .planning/onboarding-board/build.mjs
 */
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const model = JSON.parse(readFileSync(join(here, "board-model.json"), "utf8"));
const outDir = join(here, "dist");
mkdirSync(outDir, { recursive: true });

/* ── кадры ──────────────────────────────────────────────────────────────────
 * Снимки лежат вне git (.tmp-onboarding/), а носители собираются в dist/,
 * который тоже вне git. Поэтому кадры КОПИРУЮТСЯ в dist/shots — HTML остаётся
 * самодостаточным и переносится одной папкой.
 *
 * Для сцены Excalidraw из каждого кадра делается уменьшенный JPEG: сцена хранит
 * картинки как dataURL внутри самого файла, и полноразмерные PNG раздули бы его
 * до десятков мегабайт. Уменьшение — системным sips, без зависимостей.
 */
const shotsSrc = join(here, "..", "..", ".tmp-onboarding", "shots");
const shotsOut = join(outDir, "shots");
const thumbsDir = join(outDir, ".thumbs");
mkdirSync(shotsOut, { recursive: true });
mkdirSync(thumbsDir, { recursive: true });

const frames = (model.frames ?? []).filter((f) => {
  const ok = existsSync(join(shotsSrc, f.file));
  if (!ok) console.warn(`! кадр ${f.n}: файла нет — ${f.file}`);
  return ok;
});

const THUMB_W = 1500;
const shotMeta = new Map(); // file → {w, h, dataURL}

for (const f of frames) {
  const src = join(shotsSrc, f.file);
  copyFileSync(src, join(shotsOut, f.file));

  const jpg = join(thumbsDir, f.file.replace(/\.png$/i, ".jpg"));
  execFileSync("sips", ["-Z", String(THUMB_W), "-s", "format", "jpeg", "-s", "formatOptions", "62", src, "--out", jpg], {
    stdio: "ignore",
  });
  const dims = execFileSync("sips", ["-g", "pixelWidth", "-g", "pixelHeight", jpg], { encoding: "utf8" });
  const w = Number(/pixelWidth:\s*(\d+)/.exec(dims)?.[1] ?? THUMB_W);
  const h = Number(/pixelHeight:\s*(\d+)/.exec(dims)?.[1] ?? Math.round(THUMB_W * 0.6));
  shotMeta.set(f.file, { w, h, dataURL: `data:image/jpeg;base64,${readFileSync(jpg).toString("base64")}` });
}
rmSync(thumbsDir, { recursive: true, force: true });

const byPart = (key) => frames.filter((f) => f.part === key);

/* ── общий визуальный язык ──────────────────────────────────────────────── */

const COLOR = Object.fromEntries(model.legend.colors.map((c) => [c.key, c.hex]));
const BG = {
  user: "#e7f4ff",
  system: "#ede4ff",
  rule: "#fff5d6",
  success: "#e4f8e8",
  error: "#ffe6e0",
  state: "#f0f0f0",
  rail: "#fff0e0",
};
const BADGE = Object.fromEntries(model.legend.badges.map((b) => [b.key, b.glyph]));

/* ── Excalidraw ─────────────────────────────────────────────────────────── */
// Формат сцены документирован; каждый элемент — плоский объект со своей геометрией.
// seed/versionNonce влияют только на слияние правок, поэтому детерминированы.

let seq = 0;
const nid = (p) => `${p}-${(seq++).toString(36)}`;
const els = [];

const baseEl = (o) => ({
  id: o.id,
  type: o.type,
  x: o.x,
  y: o.y,
  width: o.width,
  height: o.height,
  angle: 0,
  strokeColor: o.strokeColor ?? "#1e1e1e",
  backgroundColor: o.backgroundColor ?? "transparent",
  fillStyle: "solid",
  strokeWidth: o.strokeWidth ?? 2,
  strokeStyle: "solid",
  roughness: 0,
  opacity: 100,
  groupIds: o.groupIds ?? [],
  frameId: o.frameId ?? null,
  roundness: o.roundness ?? null,
  seed: 1000 + seq,
  version: 1,
  versionNonce: 2000 + seq,
  isDeleted: false,
  boundElements: o.boundElements ?? null,
  updated: 1,
  link: null,
  locked: false,
});

const CHAR_W = 0.62; // приблизительная ширина символа Excalidraw при заданном кегле

function wrap(text, fontSize, maxWidth) {
  const perLine = Math.max(8, Math.floor(maxWidth / (fontSize * CHAR_W)));
  const out = [];
  for (const para of String(text).split("\n")) {
    let line = "";
    for (const word of para.split(/\s+/)) {
      if (!line.length) line = word;
      else if ((line + " " + word).length <= perLine) line += " " + word;
      else {
        out.push(line);
        line = word;
      }
    }
    out.push(line);
  }
  return out;
}

function text(str, x, y, { size = 16, color = "#1e1e1e", maxWidth = 400, bold = false, frameId = null } = {}) {
  const lines = wrap(str, size, maxWidth);
  const lineHeight = 1.25;
  const el = {
    ...baseEl({
      id: nid("t"),
      type: "text",
      x,
      y,
      width: maxWidth,
      height: Math.ceil(lines.length * size * lineHeight),
      strokeColor: color,
      frameId,
    }),
    text: lines.join("\n"),
    originalText: str,
    fontSize: size,
    fontFamily: 2, // Helvetica — читаемее рукописного для плотного текста
    textAlign: "left",
    verticalAlign: "top",
    containerId: null,
    lineHeight,
    autoResize: false,
    baseline: size,
  };
  if (bold) el.strokeColor = color;
  els.push(el);
  return el;
}

function box(x, y, w, h, { fill = "#ffffff", stroke = "#1e1e1e", frameId = null, radius = true } = {}) {
  const el = baseEl({
    id: nid("r"),
    type: "rectangle",
    x,
    y,
    width: w,
    height: h,
    backgroundColor: fill,
    strokeColor: stroke,
    frameId,
    roundness: radius ? { type: 3 } : null,
  });
  els.push(el);
  return el;
}

function diamond(x, y, w, h, { fill, stroke, frameId = null } = {}) {
  const el = baseEl({ id: nid("d"), type: "diamond", x, y, width: w, height: h, backgroundColor: fill, strokeColor: stroke, frameId });
  els.push(el);
  return el;
}

function arrow(x1, y1, x2, y2, { stroke = "#5e5e5e", frameId = null } = {}) {
  const el = {
    ...baseEl({
      id: nid("a"),
      type: "arrow",
      x: x1,
      y: y1,
      width: x2 - x1,
      height: y2 - y1,
      strokeColor: stroke,
      frameId,
    }),
    points: [
      [0, 0],
      [x2 - x1, y2 - y1],
    ],
    lastCommittedPoint: null,
    startBinding: null,
    endBinding: null,
    startArrowhead: null,
    endArrowhead: "arrow",
    elbowed: false,
  };
  els.push(el);
  return el;
}

function frame(x, y, w, h, name) {
  const el = { ...baseEl({ id: nid("f"), type: "frame", x, y, width: w, height: h, strokeColor: "#bbb", backgroundColor: "transparent" }), name };
  els.push(el);
  return el;
}

const sceneFiles = {};

function image(fileKey, x, y, w, h, { frameId = null } = {}) {
  const meta = shotMeta.get(fileKey);
  if (!meta) return null;
  const fileId = `sh${fileKey.replace(/[^a-z0-9]/gi, "")}`.slice(0, 40);
  sceneFiles[fileId] = { mimeType: "image/jpeg", id: fileId, dataURL: meta.dataURL, created: 1, lastRetrieved: 1 };
  const el = {
    ...baseEl({ id: nid("i"), type: "image", x, y, width: w, height: h, frameId, strokeColor: "transparent" }),
    fileId,
    status: "saved",
    scale: [1, 1],
    crop: null,
  };
  els.push(el);
  return el;
}

/* ── раскладка ──────────────────────────────────────────────────────────── */

const PAD = 40;
const COL = 460; // ширина колонки шага
const GAP = 70;
let cursorY = 0;

// Заголовок
text(model.title, PAD, cursorY, { size: 48, maxWidth: 1600 });
cursorY += 70;
text(model.subtitle, PAD, cursorY, { size: 22, color: "#595959", maxWidth: 1500 });
cursorY += 60;
text(model.note, PAD, cursorY, { size: 16, color: "#595959", maxWidth: 1500 });
cursorY += 80;

// Легенда
{
  const f = frame(PAD, cursorY, 1560, 340, "0 · Легенда");
  text("ЛЕГЕНДА", PAD + 24, cursorY + 24, { size: 24, maxWidth: 400, frameId: f.id });
  let ly = cursorY + 70;
  model.legend.colors.forEach((c) => {
    box(PAD + 24, ly, 28, 28, { fill: c.hex, stroke: c.hex, frameId: f.id });
    text(c.label, PAD + 66, ly + 4, { size: 16, maxWidth: 520, frameId: f.id });
    ly += 38;
  });
  let by = cursorY + 70;
  model.legend.badges.forEach((b) => {
    text(`${b.glyph}  ${b.label}`, PAD + 640, by, { size: 16, maxWidth: 880, frameId: f.id });
    by += 46;
  });
  cursorY += 340 + GAP;
}

// Карта продукта
{
  const h = 120 + model.product.surfaces.length * 96;
  const f = frame(PAD, cursorY, 1560, h, "1 · Карта продукта");
  text("ЧТО ЭТО ЗА ПРОДУКТ", PAD + 24, cursorY + 24, { size: 24, maxWidth: 600, frameId: f.id });
  text(model.product.what, PAD + 24, cursorY + 62, { size: 16, color: "#595959", maxWidth: 1480, frameId: f.id });
  let sy = cursorY + 130;
  model.product.surfaces.forEach((s) => {
    box(PAD + 24, sy, 1500, 82, { fill: BG.state, stroke: "#b3b3b3", frameId: f.id });
    text(`${s.name}  ·  ${s.url}`, PAD + 44, sy + 12, { size: 18, maxWidth: 700, frameId: f.id });
    text(`Кто: ${s.who}. ${s.what}`, PAD + 44, sy + 42, { size: 15, color: "#595959", maxWidth: 1440, frameId: f.id });
    sy += 96;
  });
  cursorY += h + GAP;
}

// Ролевая модель
{
  const rows = model.roleModel.features;
  const h = 210 + rows.length * 40 + model.roleModel.notes.length * 46;
  const f = frame(PAD, cursorY, 1560, h, "2 · Ролевая модель");
  text("РОЛЕВАЯ МОДЕЛЬ", PAD + 24, cursorY + 24, { size: 24, maxWidth: 600, frameId: f.id });
  text(model.roleModel.idea, PAD + 24, cursorY + 62, { size: 16, color: "#595959", maxWidth: 1480, frameId: f.id });

  let cx = PAD + 24;
  model.roleModel.identityChain.forEach((step, i) => {
    const w = 340;
    box(cx, cursorY + 120, w, 52, { fill: BG.user, stroke: COLOR.user, frameId: f.id });
    text(step, cx + 14, cursorY + 136, { size: 15, maxWidth: w - 28, frameId: f.id });
    if (i < model.roleModel.identityChain.length - 1) arrow(cx + w + 6, cursorY + 146, cx + w + 34, cursorY + 146, { frameId: f.id });
    cx += w + 40;
  });

  let ry = cursorY + 200;
  text("Фича → каким ролям компании она открыта", PAD + 24, ry - 32, { size: 17, maxWidth: 900, frameId: f.id });
  rows.forEach((r) => {
    text(r.label, PAD + 24, ry, { size: 15, maxWidth: 420, frameId: f.id });
    text(r.roles.join(" · "), PAD + 470, ry, { size: 15, color: "#595959", maxWidth: 1040, frameId: f.id });
    ry += 40;
  });
  ry += 16;
  model.roleModel.notes.forEach((n) => {
    text("▸ " + n, PAD + 24, ry, { size: 15, color: "#b86114", maxWidth: 1480, frameId: f.id });
    ry += 46;
  });
  cursorY += h + GAP;
}

// Кадры — пошаговый разбор живого продукта
(model.parts ?? []).forEach((part, pi) => {
  const list = byPart(part.key);
  if (!list.length) return;

  // Кадры раскладываются в три колонки: в одну колонку часть B вытягивалась
  // на 12 000 пикселей, и доска переставала читаться как доска. Следующий кадр
  // всегда уходит в самую короткую колонку — снимки разной высоты, и так они
  // не расползаются лесенкой.
  const COLS = 3;
  const IMG_W = 1000;
  const CGAP = 56;
  const CAP = 104; // подпись над кадром
  const HEAD = 150; // заголовок части
  const gridW = COLS * IMG_W + (COLS - 1) * CGAP;
  const colY = new Array(COLS).fill(0);
  const placedFrames = list.map((fr) => {
    const m = shotMeta.get(fr.file);
    const ih = Math.round((IMG_W * m.h) / m.w);
    const c = colY.indexOf(Math.min(...colY));
    const spot = { fr, ih, x: PAD + 24 + c * (IMG_W + CGAP), y: colY[c] };
    colY[c] += CAP + ih + 54;
    return spot;
  });
  const bodyH = Math.max(...colY);
  const f = frame(PAD, cursorY, gridW + 48, HEAD + bodyH, `3.${pi + 1} · Часть ${part.key} — ${part.title}`);

  text(`ЧАСТЬ ${part.key} · ${part.title.toUpperCase()}`, PAD + 24, cursorY + 24, { size: 26, maxWidth: 1400, frameId: f.id });
  text(part.about, PAD + 24, cursorY + 64, { size: 16, color: "#595959", maxWidth: gridW - 40, frameId: f.id });

  placedFrames.forEach(({ fr, ih, x, y }) => {
    const top = cursorY + HEAD + y;
    text(`${String(fr.n).padStart(2, "0")} · ${fr.title}`, x, top, { size: 20, maxWidth: IMG_W, frameId: f.id });
    text(fr.what, x, top + 30, { size: 14, color: "#595959", maxWidth: IMG_W, frameId: f.id });
    if (fr.findings?.length)
      text(fr.findings.join(" · "), x, top + 80, { size: 13, color: "#b02a1f", maxWidth: IMG_W, frameId: f.id });
    image(fr.file, x, top + CAP, IMG_W, ih, { frameId: f.id });
  });

  cursorY += HEAD + bodyH + GAP;
});

// Потоки — swimlane
const FLOW_BASE = 3 + (model.parts ?? []).filter((p) => byPart(p.key).length).length;
model.flows.forEach((flow, fi) => {
  const lanes = flow.lanes;
  const laneH = 200;
  const headerH = 150;
  const bodyH = lanes.length * laneH;
  const rulesH = 60 + flow.rules.length * 46;
  const w = Math.max(1560, 260 + flow.steps.length * (COL + 40));
  const f = frame(PAD, cursorY, w, headerH + bodyH + rulesH, `${FLOW_BASE + fi} · ${flow.title}`);

  text(flow.title.toUpperCase(), PAD + 24, cursorY + 24, { size: 26, maxWidth: 1000, frameId: f.id });
  text("Цель: " + flow.goal, PAD + 24, cursorY + 64, { size: 16, color: "#595959", maxWidth: 1400, frameId: f.id });

  const laneX = PAD + 24;
  const laneLabelW = 210;
  lanes.forEach((lane, li) => {
    const ly = cursorY + headerH + li * laneH;
    box(laneX, ly, w - 48, laneH - 16, { fill: li % 2 ? "#fbfbfb" : "#f5f5f5", stroke: "#e0e0e0", frameId: f.id, radius: false });
    text(lane, laneX + 16, ly + 16, { size: 17, maxWidth: laneLabelW - 24, frameId: f.id });
  });

  flow.steps.forEach((s, si) => {
    const li = lanes.indexOf(s.lane);
    const x = laneX + laneLabelW + si * (COL + 40);
    const y = cursorY + headerH + li * laneH + 24;
    const stroke = COLOR[s.kind] ?? "#1e1e1e";
    const fill = BG[s.kind] ?? "#ffffff";
    const isDecision = /\?$/.test(s.text);
    if (isDecision) diamond(x, y, COL, 130, { fill, stroke, frameId: f.id });
    else box(x, y, COL, 130, { fill, stroke, frameId: f.id });
    text(`${BADGE[s.badge] ?? ""} ${s.text}`, x + 16, y + 14, { size: 16, maxWidth: COL - 32, frameId: f.id });
    if (s.detail) text(s.detail, x + 16, y + 58, { size: 13, color: "#595959", maxWidth: COL - 32, frameId: f.id });

    const next = flow.steps[si + 1];
    if (next) {
      const nli = lanes.indexOf(next.lane);
      const nx = laneX + laneLabelW + (si + 1) * (COL + 40);
      const ny = cursorY + headerH + nli * laneH + 24;
      arrow(x + COL + 4, y + 65, nx - 6, ny + 65, { frameId: f.id });
    }
  });

  let ry = cursorY + headerH + bodyH + 20;
  flow.rules.forEach((r) => {
    box(laneX, ry, w - 48, 40, { fill: BG.rule, stroke: COLOR.rule, frameId: f.id });
    text("ПРАВИЛО · " + r, laneX + 14, ry + 11, { size: 15, maxWidth: w - 80, frameId: f.id });
    ry += 46;
  });

  cursorY += headerH + bodyH + rulesH + GAP;
});

// Что не исследовано
{
  const h = 110 + model.notExplored.length * 52;
  const f = frame(PAD, cursorY, 1560, h, "Что ещё не исследовано");
  text("ЧТО ЕЩЁ НЕ ИССЛЕДОВАНО", PAD + 24, cursorY + 24, { size: 24, maxWidth: 800, frameId: f.id });
  let y = cursorY + 80;
  model.notExplored.forEach((n) => {
    box(PAD + 24, y, 1500, 44, { fill: BG.state, stroke: "#b3b3b3", frameId: f.id });
    text(`${n.what}  —  ${n.why}`, PAD + 40, y + 13, { size: 15, maxWidth: 1460, frameId: f.id });
    y += 52;
  });
  cursorY += h;
}

const scene = {
  type: "excalidraw",
  version: 2,
  source: "polymer-intelligence/.planning/onboarding-board/build.mjs",
  elements: els,
  appState: { gridSize: null, viewBackgroundColor: "#ffffff" },
  files: sceneFiles,
};
writeFileSync(join(outDir, "onboarding-board.excalidraw"), JSON.stringify(scene, null, 1));

/* ── HTML ───────────────────────────────────────────────────────────────── */

const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const partsWithFrames = (model.parts ?? []).filter((p) => byPart(p.key).length);

const partHtml = (part, pi) => `
<section id="part-${part.key}">
  <h2><span class="num">3.${pi + 1}</span>Часть ${esc(part.key)} · ${esc(part.title)}</h2>
  <p class="goal">${esc(part.about)}</p>
  ${byPart(part.key)
    .map(
      (f) => `
  <figure class="shot" id="frame-${f.n}">
    <figcaption>
      <span class="fnum">${String(f.n).padStart(2, "0")}</span>
      <span class="ftitle">${esc(f.title)}</span>
      ${(f.findings ?? []).map((x) => `<a class="fchip" href="#" title="см. findings.md">${esc(x)}</a>`).join("")}
    </figcaption>
    <p class="fwhat">${esc(f.what)}</p>
    <a href="shots/${encodeURIComponent(f.file)}" target="_blank" rel="noreferrer">
      <img src="shots/${encodeURIComponent(f.file)}" alt="${esc(f.title)}" loading="lazy">
    </a>
  </figure>`,
    )
    .join("")}
</section>`;

const flowHtml = (flow, i) => `
<section class="flow" id="flow-${flow.id}">
  <h2><span class="num">${FLOW_BASE + i}</span>${esc(flow.title)}</h2>
  <p class="goal">${esc(flow.goal)}</p>
  <div class="lanes">
    ${flow.lanes
      .map(
        (lane) => `
    <div class="lane">
      <div class="lane-name">${esc(lane)}</div>
      <div class="lane-steps">
        ${flow.steps
          .map((s, si) =>
            s.lane !== lane
              ? `<div class="step ghost" style="--i:${si}"></div>`
              : `<div class="step k-${s.kind}" style="--i:${si}">
                   <div class="step-head"><span class="badge b-${s.badge}">${BADGE[s.badge] ?? ""}</span>${esc(s.text)}</div>
                   ${s.detail ? `<div class="step-detail">${esc(s.detail)}</div>` : ""}
                 </div>`,
          )
          .join("")}
      </div>
    </div>`,
      )
      .join("")}
  </div>
  <div class="rules">
    ${flow.rules.map((r) => `<div class="rule">${esc(r)}</div>`).join("")}
  </div>
</section>`;

const html = `<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(model.title)}</title>
<style>
  :root{
    --user:${COLOR.user}; --system:${COLOR.system}; --rule:${COLOR.rule};
    --success:${COLOR.success}; --error:${COLOR.error}; --state:${COLOR.state}; --rail:${COLOR.rail};
    --ink:#1e1e1e; --mut:#595959; --line:#e4e4e4; --bg:#fbfbfc;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
  header{padding:56px 40px 28px;border-bottom:1px solid var(--line);background:#fff;position:relative}
  h1{margin:0 0 10px;font-size:40px;letter-spacing:-.5px}
  .sub{margin:0 0 8px;font-size:19px;color:var(--mut);max-width:900px}
  .note{margin:0;font-size:14px;color:var(--mut);max-width:900px}
  nav{position:sticky;top:0;z-index:9;display:flex;gap:6px;flex-wrap:wrap;
      padding:12px 40px;background:#fff;border-bottom:1px solid var(--line)}
  nav a{font-size:14px;text-decoration:none;color:var(--mut);padding:5px 11px;border-radius:99px;border:1px solid var(--line)}
  nav a:hover{color:var(--ink);border-color:#bbb;background:#f5f5f5}
  main{padding:32px 40px 90px;max-width:1700px}
  section{background:#fff;border:1px solid var(--line);border-radius:14px;padding:26px 28px;margin:0 0 26px}
  h2{margin:0 0 6px;font-size:24px;display:flex;align-items:center;gap:12px}
  .num{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:8px;
       background:#f0f0f0;font-size:15px;color:var(--mut)}
  .goal{margin:0 0 20px;color:var(--mut)}
  .legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px 26px}
  .lg{display:flex;align-items:center;gap:10px;font-size:15px}
  .sw{width:22px;height:22px;border-radius:6px;flex:none}
  .chain{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:14px 0 22px}
  .chain b{background:#e7f4ff;border:1px solid var(--user);border-radius:9px;padding:8px 13px;font-weight:500;font-size:14px}
  .chain i{color:var(--mut);font-style:normal}
  table{border-collapse:collapse;width:100%;font-size:14px}
  th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
  th{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}
  code{background:#f2f2f2;border-radius:4px;padding:1px 5px;font-size:13px}
  .lanes{overflow-x:auto;padding-bottom:8px}
  .lane{display:flex;align-items:stretch;border-top:1px solid var(--line)}
  .lane:last-child{border-bottom:1px solid var(--line)}
  .lane-name{flex:none;width:150px;padding:14px 12px;font-size:13px;font-weight:600;
             letter-spacing:.04em;color:var(--mut);background:#fafafa;border-right:1px solid var(--line)}
  .lane-steps{display:flex;gap:12px;padding:12px}
  .step{flex:none;width:290px;border-radius:11px;padding:11px 13px;border:1.5px solid #ddd;background:#fff}
  .step.ghost{background:transparent;border:none;pointer-events:none}
  .step-head{font-size:14px;font-weight:600;display:flex;gap:7px;align-items:flex-start}
  .step-detail{margin-top:6px;font-size:12.5px;color:var(--mut);line-height:1.45}
  .badge{flex:none;width:18px;height:18px;border-radius:99px;display:grid;place-items:center;
         font-size:11px;color:#fff;margin-top:1px}
  .b-ok{background:#1f804d}.b-code{background:#3866bf}.b-q{background:#b86114}
  .k-user{border-color:var(--user);background:#f2f9ff}
  .k-system{border-color:var(--system);background:#f7f3ff}
  .k-success{border-color:var(--success);background:#f1fbf4}
  .k-error{border-color:var(--error);background:#fff3ef}
  .k-state{border-color:var(--state);background:#f7f7f7}
  .k-rail{border-color:var(--rail);background:#fff6ec}
  .k-rule{border-color:var(--rule);background:#fffaeb}
  .rules{margin-top:18px;display:grid;gap:8px}
  .rule{background:#fffaeb;border:1px solid var(--rule);border-left-width:5px;border-radius:9px;
        padding:10px 14px;font-size:14px}
  .rule::before{content:"ПРАВИЛО · ";font-weight:700;font-size:11px;letter-spacing:.06em;color:#8a6300}
  .surf{border:1px solid var(--line);border-radius:10px;padding:12px 15px;margin-bottom:9px;background:#fafafa}
  .surf b{font-size:15px}.surf span{color:var(--mut);font-size:14px}
  .notes li{margin-bottom:7px;font-size:14.5px}
  .gap{background:#f7f7f7;border:1px solid var(--line);border-radius:9px;padding:10px 14px;
       margin-bottom:8px;font-size:14px}
  .gap b{font-weight:600}
  footer{padding:26px 40px;color:var(--mut);font-size:13px;border-top:1px solid var(--line);background:#fff}
  .shot{margin:0 0 34px;padding:0}
  .shot figcaption{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}
  .fnum{display:inline-grid;place-items:center;min-width:34px;height:26px;border-radius:7px;
        background:var(--ink);color:#fff;font-size:13px;font-weight:700;padding:0 7px}
  .ftitle{font-size:17px;font-weight:650}
  .fchip{font-size:11.5px;font-weight:700;letter-spacing:.04em;color:#b02a1f;text-decoration:none;
         border:1px solid #f0c4bf;background:#fff3ef;border-radius:99px;padding:2px 9px}
  .fwhat{margin:0 0 10px;font-size:14.5px;color:var(--mut);max-width:1100px}
  .shot img{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:10px;
            background:#fff}
  .shot a{display:block}
</style>

<header>
  <h1>${esc(model.title)}</h1>
  <p class="sub">${esc(model.subtitle)}</p>
  <p class="note">${esc(model.note)}</p>
</header>

<nav>
  <a href="#legend">0 · Легенда</a>
  <a href="#product">1 · Карта продукта</a>
  <a href="#roles">2 · Ролевая модель</a>
  ${partsWithFrames.map((p, i) => `<a href="#part-${p.key}">3.${i + 1} · ${esc(p.title)}</a>`).join("")}
  ${model.flows.map((f, i) => `<a href="#flow-${f.id}">${FLOW_BASE + i} · ${esc(f.title)}</a>`).join("")}
  <a href="#gaps">Не исследовано</a>
</nav>

<main>
  <section id="legend">
    <h2><span class="num">0</span>Легенда</h2>
    <p class="goal">Цвет отвечает на «кто действует», бейдж — на «откуда мы это знаем».</p>
    <div class="legend">
      ${model.legend.colors
        .map((c) => `<div class="lg"><span class="sw" style="background:${c.hex}"></span>${esc(c.label)}</div>`)
        .join("")}
    </div>
    <div class="legend" style="margin-top:16px">
      ${model.legend.badges
        .map((b) => `<div class="lg"><span class="badge b-${b.key}">${b.glyph}</span>${esc(b.label)}</div>`)
        .join("")}
    </div>
  </section>

  <section id="product">
    <h2><span class="num">1</span>Карта продукта</h2>
    <p class="goal">${esc(model.product.what)}</p>
    ${model.product.surfaces
      .map(
        (s) =>
          `<div class="surf"><b>${esc(s.name)}</b> <code>${esc(s.url)}</code><br><span>Кто: ${esc(s.who)}. ${esc(s.what)}</span></div>`,
      )
      .join("")}
  </section>

  <section id="roles">
    <h2><span class="num">2</span>Ролевая модель</h2>
    <p class="goal">${esc(model.roleModel.idea)}</p>
    <div class="chain">
      ${model.roleModel.identityChain.map((c, i, a) => `<b>${esc(c)}</b>${i < a.length - 1 ? "<i>→</i>" : ""}`).join("")}
    </div>
    <table>
      <thead><tr><th>Фича</th><th>Каким ролям компании открыта</th></tr></thead>
      <tbody>
        ${model.roleModel.features
          .map((f) => `<tr><td>${esc(f.label)} <code>${esc(f.feature)}</code></td><td>${f.roles.map((r) => `<code>${esc(r)}</code>`).join(" ")}</td></tr>`)
          .join("")}
      </tbody>
    </table>
    <ul class="notes" style="margin-top:18px">
      ${model.roleModel.notes.map((n) => `<li>${esc(n)}</li>`).join("")}
    </ul>
  </section>

  ${partsWithFrames.map(partHtml).join("")}

  ${model.flows.map(flowHtml).join("")}

  <section id="gaps">
    <h2>Что ещё не исследовано</h2>
    <p class="goal">Честный список того, чего на карте нет и почему. Ничего не додумано.</p>
    ${model.notExplored.map((n) => `<div class="gap"><b>${esc(n.what)}</b> — ${esc(n.why)}</div>`).join("")}
  </section>
</main>

<footer>
  Собрано из <code>.planning/onboarding-board/board-model.json</code> командой
  <code>node .planning/onboarding-board/build.mjs</code>.
  Находки и дефекты — в <code>findings.md</code>.
</footer>
</html>`;

writeFileSync(join(outDir, "onboarding-board.html"), html);

console.log(`excalidraw: ${els.length} элементов → dist/onboarding-board.excalidraw`);
console.log(`html:                              → dist/onboarding-board.html`);

/**
 * Аннотатор скриншотов. Вставляется в страницу перед снимком.
 *
 * Смысл: разметка привязывается к РЕАЛЬНОМУ прямоугольнику элемента
 * (getBoundingClientRect + скролл документа), а не к прикидке на глаз.
 * Если селектор ничего не находит — mark() возвращает ошибку и ничего
 * не рисует, поэтому стрелка физически не может указать в пустоту.
 *
 * Использование из evaluate_script:
 *   __ann.reset()
 *   __ann.mark('button.primary', 1, 'Нажать «Далее»')
 *   __ann.inset('Ответ сервера', ['POST /api/... → 204', 'тело пустое'])
 *   __ann.done()   // → отчёт: что размечено и по каким координатам
 */
(() => {
  const ID = "__ann_layer";
  const C = {
    accent: "#e5484d",
    accentSoft: "rgba(229,72,77,.12)",
    ink: "#101010",
    panel: "rgba(255,255,255,.97)",
    mut: "#5b5b5b",
  };

  const layer = () => {
    let el = document.getElementById(ID);
    if (!el) {
      el = document.createElement("div");
      el.id = ID;
      el.style.cssText =
        "position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:2147483600";
      document.body.appendChild(el);
    }
    return el;
  };

  const marks = [];
  const placed = []; // занятые подписями прямоугольники — чтобы разводить их

  const rectOf = (sel) => {
    const el = typeof sel === "string" ? document.querySelector(sel) : sel;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (!r.width && !r.height) return null;
    return {
      el,
      x: r.left + window.scrollX,
      y: r.top + window.scrollY,
      w: r.width,
      h: r.height,
    };
  };

  const add = (html, css) => {
    const d = document.createElement("div");
    d.style.cssText = css;
    d.innerHTML = html;
    layer().appendChild(d);
    return d;
  };

  const api = {
    /** Убрать разметку и начать заново. */
    reset() {
      const el = document.getElementById(ID);
      if (el) el.remove();
      marks.length = 0;
      placed.length = 0;
      return { cleared: true };
    },

    /**
     * Прогрев: прокрутить страницу до низа и обратно, чтобы дорисовались
     * ленивые секции. Без этого полностраничный снимок ловит пустоты.
     */
    async settle(ms = 260) {
      const h = document.documentElement.scrollHeight;
      for (let y = 0; y < h; y += window.innerHeight * 0.8) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 60));
      }
      window.scrollTo(0, 0);
      await new Promise((r) => setTimeout(r, ms));
      return { scrolledTo: h, finalHeight: document.documentElement.scrollHeight };
    },

    /**
     * Обвести элемент и поставить номер с подписью.
     *
     * opts.expect — обязательная страховка от промаха: если текст элемента
     * не содержит эту подстроку, метка НЕ рисуется и возвращается ошибка.
     * opts.maxArea — доля площади документа, выше которой элемент считается
     * «не тем» (эвристики любят ловить огромные обёртки вместо контрола).
     *
     * @returns {ok:false,error} — тогда ничего не рисуется.
     */
    mark(sel, n, text, opts = {}) {
      const r = rectOf(sel);
      if (!r) return { ok: false, error: `не найден элемент: ${sel}` };

      if (opts.expect) {
        const got = (r.el.innerText || r.el.value || "").replace(/\s+/g, " ").trim();
        if (!got.toLowerCase().includes(String(opts.expect).toLowerCase()))
          return { ok: false, error: `элемент не содержит «${opts.expect}»`, got: got.slice(0, 120) };
      }
      const docArea = document.documentElement.scrollWidth * document.documentElement.scrollHeight;
      const frac = (r.w * r.h) / docArea;
      if (frac > (opts.maxArea ?? 0.5))
        return { ok: false, error: `элемент занимает ${Math.round(frac * 100)}% документа — похоже, это обёртка, а не контрол` };
      if (r.w < 4 || r.h < 4) return { ok: false, error: "элемент схлопнут в точку" };

      // Экран может прокручиваться ВНУТРЕННИМ контейнером (в дашборде это <main>),
      // а не документом. Тогда window.scrollY всегда 0, полностраничный снимок
      // берёт только видимую часть, и метка на элементе за краем окна уйдёт в никуда.
      // Если же прокручивается сам документ — снимок захватит всё, и запрет не нужен.
      const docScrolls = document.documentElement.scrollHeight > window.innerHeight + 4;
      const vr = r.el.getBoundingClientRect();
      if (!opts.offscreenOk && !docScrolls && (vr.bottom < 0 || vr.top > window.innerHeight))
        return {
          ok: false,
          error: `элемент вне окна (top=${Math.round(vr.top)}, окно ${window.innerHeight}) — доскролль контейнер и снимай видимую часть`,
        };

      // Слой разметки — absolute в документе, поэтому sticky/fixed предок делает
      // координаты бессмысленными: на полностраничном снимке элемент нарисован в
      // одном месте, а его rect посчитан для текущей прокрутки. Метка уйдёт в пустоту.
      // opts.stickyOk снимает запрет — но только осознанно: при scrollY === 0 залипающая
      // шапка стоит на своём естественном месте, и метка ляжет верно.
      for (let p = r.el; p && p !== document.body && !opts.stickyOk; p = p.parentElement) {
        const pos = getComputedStyle(p).position;
        if (pos === "sticky" || pos === "fixed")
          return {
            ok: false,
            error: `элемент внутри ${pos}-контейнера (${p.tagName.toLowerCase()}) — координаты уедут при прокрутке; вынеси факт во врезку`,
          };
      }

      const pad = opts.pad ?? 4;

      add(
        "",
        `position:absolute;left:${r.x - pad}px;top:${r.y - pad}px;
         width:${r.w + pad * 2}px;height:${r.h + pad * 2}px;
         border:3px solid ${C.accent};border-radius:8px;
         background:${C.accentSoft};box-sizing:border-box`,
      );

      // Номер: слева, если есть место, иначе справа. opts.side принудительно задаёт
      // сторону — на экранах с боковым меню левое поле занято навигацией, и подписи
      // по умолчанию садятся ровно на неё.
      const left = opts.side ? opts.side === "left" : r.x > 74;
      const bx = left ? r.x - 62 : r.x + r.w + 16;
      const by = r.y + r.h / 2 - 20;
      add(
        String(n),
        `position:absolute;left:${bx}px;top:${by}px;width:40px;height:40px;
         border-radius:50%;background:${C.accent};color:#fff;
         font:700 20px/40px -apple-system,Segoe UI,Roboto,sans-serif;
         text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.28)`,
      );
      add(
        "",
        `position:absolute;left:${left ? bx + 40 : r.x + r.w + pad}px;top:${by + 19}px;
         width:${left ? r.x - pad - (bx + 40) : bx - (r.x + r.w + pad)}px;height:3px;
         background:${C.accent}`,
      );

      if (text) {
        const cw = opts.at?.width ?? 320;
        const est = 34 + Math.ceil(text.length / (cw / 8.4)) * 20; // высота подписи по длине текста
        let cx = opts.at
          ? opts.at.x
          : left
            ? Math.max(8, bx - cw - 14)
            : Math.min(document.documentElement.scrollWidth - cw - 8, bx + 54);
        let cy = opts.at ? opts.at.y : by - 2;
        // Развести подписи: сдвигать вниз, пока пересекается с уже нарисованной.
        // При явном opts.at позиция считается осознанной и не двигается.
        for (let guard = 0; guard < (opts.at ? 0 : 40); guard++) {
          const hit = placed.find(
            (p) => Math.abs(p.x - cx) < cw - 20 && cy < p.y + p.h + 10 && cy + est > p.y - 10,
          );
          if (!hit) break;
          cy = hit.y + hit.h + 12;
        }
        placed.push({ x: cx, y: cy, h: est });
        add(
          `<b style="color:${C.accent}">${n}</b> &nbsp;${text}`,
          `position:absolute;left:${cx}px;top:${cy}px;width:${cw}px;
           background:${C.panel};border:2px solid ${C.accent};border-radius:10px;
           padding:9px 12px;color:${C.ink};
           font:500 14px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;
           box-shadow:0 3px 12px rgba(0,0,0,.16)`,
        );
      }

      marks.push({ n, sel: String(sel), rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.w), h: Math.round(r.h) }, text });
      return { ok: true, n, rect: marks[marks.length - 1].rect };
    },

    /** Врезка с фактическими данными — ответ сервера, строка из Postgres, лог. */
    inset(title, lines, opts = {}) {
      const w = opts.width ?? 470;
      let x = opts.x ?? Math.max(8, document.documentElement.scrollWidth - w - 24);
      let y = opts.y ?? window.scrollY + 24;
      // Врезка тоже участвует в разведении: иначе она садится поверх подписей.
      const est = 46 + lines.length * 20;
      for (let guard = 0; guard < 40; guard++) {
        const hit = placed.find(
          (p) => Math.abs(p.x - x) < w - 20 && y < p.y + p.h + 10 && y + est > p.y - 10,
        );
        if (!hit) break;
        y = hit.y + hit.h + 14;
      }
      placed.push({ x, y, h: est });
      add(
        `<div style="font:700 12px/1 -apple-system,Segoe UI,sans-serif;
                     letter-spacing:.08em;text-transform:uppercase;color:${C.accent};
                     margin-bottom:8px">${title}</div>` +
          lines
            .map((l) =>
              l === ""
                ? `<div style="height:9px"></div>` // пустая строка — распорка, иначе схлопнется
                : `<div style="font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
                             color:${C.ink};white-space:pre-wrap;word-break:break-word">${l}</div>`,
            )
            .join(""),
        `position:absolute;left:${x}px;top:${y}px;width:${w}px;
         background:${C.panel};border:2px solid ${C.accent};border-radius:12px;
         padding:14px 16px;box-shadow:0 4px 18px rgba(0,0,0,.18)`,
      );
      return { ok: true, title, at: { x, y } };
    },

    /**
     * Заголовок кадра — что именно на нём показано.
     *
     * Ширина по умолчанию подгоняется под ЛЕВОЕ ПОЛЕ страницы: иначе плашка
     * наезжает на верх контента (в кадре 07 она закрыла ленту шагов).
     * Поле меряется по самому левому непустому элементу в верхней полосе.
     */
    caption(text, sub, opts = {}) {
      let w = opts.width;
      if (!w) {
        let leftmost = document.documentElement.scrollWidth;
        for (const el of document.body.querySelectorAll("*")) {
          if (el.closest(`#${ID}`)) continue;
          const r = el.getBoundingClientRect();
          if (r.width < 40 || r.height < 12) continue;
          if (r.top + window.scrollY > window.scrollY + 240) continue; // только верхняя полоса
          if (!(el.innerText || "").trim() && el.tagName !== "IMG") continue;
          leftmost = Math.min(leftmost, r.left + window.scrollX);
        }
        w = Math.max(300, Math.min(640, leftmost - 24 - 20));
      }
      const y = opts.y ?? window.scrollY + 24;
      const x = opts.x ?? 24;
      add(
        `<div style="font:700 17px/1.3 -apple-system,Segoe UI,sans-serif;color:#fff">${text}</div>` +
          (sub
            ? `<div style="font:13px/1.4 -apple-system,Segoe UI,sans-serif;color:rgba(255,255,255,.82);margin-top:3px">${sub}</div>`
            : ""),
        `position:absolute;left:${x}px;top:${y}px;width:${w}px;box-sizing:border-box;
         background:${C.ink};border-radius:11px;padding:12px 16px;
         box-shadow:0 4px 16px rgba(0,0,0,.3)`,
      );
      // Подписи не должны садиться на заголовок.
      placed.push({ x, y, h: 46 + (sub ? 22 : 0) + Math.ceil(text.length / (w / 9)) * 22 });
      return { ok: true, width: w };
    },

    /** Отчёт: что размечено. Кладётся рядом с PNG, чтобы кадр можно было пересобрать. */
    done() {
      return { url: location.href, title: document.title, marks };
    },
  };

  window.__ann = api;
  return { installed: true };
})();

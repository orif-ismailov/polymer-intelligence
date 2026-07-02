/**
 * Thin @telegram-apps/sdk v2 wrapper.
 *
 * Provides:
 *   - initTelegram()    — init SDK, expand viewport
 *   - getInitData()     — raw initData string for the X-Telegram-Init-Data header
 *   - mainButton        — setText/show/hide/enable/disable/onClick helpers
 *   - backButton        — show/hide/onClick helpers
 *   - haptics           — impactLight(), notifySuccess(), notifyError(), notifyWarning()
 *
 * The SDK v2 uses SafeWrapped functions with `.isAvailable()` (Computed<boolean>)
 * guards. All calls are wrapped in try/catch so they degrade gracefully in
 * browser/dev context outside Telegram.
 */

import {
  init,
  isTMA,
  retrieveLaunchParams,
  // mainButton scoped functions
  mountMainButton,
  setMainButtonParams,
  onMainButtonClick,
  offMainButtonClick,
  // backButton scoped functions
  mountBackButton,
  showBackButton,
  hideBackButton,
  onBackButtonClick,
  offBackButtonClick,
  // haptic feedback
  hapticFeedbackImpactOccurred,
  hapticFeedbackNotificationOccurred,
  // viewport
  mountViewport,
  expandViewport,
} from "@telegram-apps/sdk";

import type { EventListener } from "@telegram-apps/sdk";

// ── SDK Initialisation ─────────────────────────────────────────────────────────

let _initialized = false;

// initData captured from the launch hash before HashRouter clears it (see below).
let _capturedInitData = "";

/**
 * Telegram opens the Mini App at `<url>#tgWebAppData=...&tgWebAppVersion=...`.
 * Because the app routes with HashRouter, that launch hash would be interpreted as
 * a route — matching nothing and rendering a BLANK page. So we capture initData
 * from the hash up front, let the SDK read the hash during init(), then strip the
 * tg params back to `#/` so HashRouter starts at the home route. getInitData()
 * returns the captured value. Order matters: capture → init() → clean.
 */
function _captureLaunchInitData(): void {
  try {
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash.includes("tgWebApp")) return;
    const raw = new URLSearchParams(hash).get("tgWebAppData");
    if (raw) _capturedInitData = raw;
  } catch {
    /* ignore — dev/browser without a launch hash */
  }
}

function _cleanLaunchHash(): void {
  try {
    if (!window.location.hash.includes("tgWebApp")) return;
    const { pathname, search } = window.location;
    window.history.replaceState(null, "", `${pathname}${search}#/`);
  } catch {
    /* ignore */
  }
}

export function initTelegram(): void {
  if (_initialized) return;
  // 1. Capture initData from the launch hash before anything touches it.
  _captureLaunchInitData();
  try {
    if (isTMA('simple')) {
      // 2. The SDK reads the launch params from the hash here.
      init();
      _initialized = true;

      // Mount main button (needed before setParams/show/hide work)
      try { mountMainButton(); } catch {/* not supported */}

      // Mount back button
      try { mountBackButton(); } catch {/* not supported */}

      // Expand the Web App to full height
      try {
        mountViewport().then(() => {
          try { expandViewport(); } catch {/* not supported */}
        }).catch(() => {/* ignore */});
      } catch {/* not supported */}
    }
  } catch {
    // Outside Telegram — silently ignore (dev/browser testing)
  } finally {
    // 3. Strip the tg params so HashRouter routes to "/" instead of blanking.
    _cleanLaunchHash();
  }
}

/**
 * True when running inside the Telegram Mini App (identity available via initData),
 * false in a plain browser. Drives the dual auth model: Mini App = no login gate;
 * browser = Telegram Login Widget + client_session cookie.
 */
export function isMiniApp(): boolean {
  try {
    return isTMA("simple");
  } catch {
    return false;
  }
}

// ── initData string ────────────────────────────────────────────────────────────

export function getInitData(): string {
  // Prefer the value captured from the launch hash before it was stripped for the
  // router — retrieveLaunchParams() / the legacy WebApp.initData may be empty now.
  if (_capturedInitData) return _capturedInitData;
  // @telegram-apps/sdk v2: retrieveLaunchParams().initDataRaw
  try {
    if (isTMA('simple')) {
      const params = retrieveLaunchParams();
      return params.initDataRaw ?? "";
    }
  } catch {
    // fall through
  }
  // Fallback: Telegram.WebApp.initData (legacy SDK injected by index.html script)
  return (
    (
      window as unknown as {
        Telegram?: { WebApp?: { initData?: string } };
      }
    ).Telegram?.WebApp?.initData ?? ""
  );
}

// ── Main Button helpers ────────────────────────────────────────────────────────

type MainButtonClickListener = EventListener<"main_button_pressed">;
type CleanupFn = () => void;

export const mainButton = {
  setText(text: string): void {
    try { setMainButtonParams({ text }); } catch {/* dev env */}
  },

  show(): void {
    try { setMainButtonParams({ isVisible: true }); } catch {/* dev env */}
  },

  hide(): void {
    try { setMainButtonParams({ isVisible: false }); } catch {/* dev env */}
  },

  enable(): void {
    try { setMainButtonParams({ isEnabled: true }); } catch {/* dev env */}
  },

  disable(): void {
    try { setMainButtonParams({ isEnabled: false }); } catch {/* dev env */}
  },

  /** Registers a click handler. Returns a cleanup function. */
  onClick(handler: MainButtonClickListener): CleanupFn {
    try {
      const avail = onMainButtonClick.isAvailable as unknown as () => boolean;
      if (avail()) {
        return onMainButtonClick(handler);
      }
    } catch {/* dev env */}
    return () => {/* noop */};
  },

  offClick(handler: MainButtonClickListener): void {
    try {
      offMainButtonClick(handler);
    } catch {/* dev env */}
  },
};

// ── Back Button helpers ────────────────────────────────────────────────────────

type BackButtonClickListener = EventListener<"back_button_pressed">;

export const backButton = {
  show(): void {
    try {
      if (showBackButton.isAvailable()) {
        showBackButton();
      }
    } catch {/* dev env */}
  },

  hide(): void {
    try {
      if (hideBackButton.isAvailable()) {
        hideBackButton();
      }
    } catch {/* dev env */}
  },

  /** Registers a click handler. Returns a cleanup function. */
  onClick(handler: BackButtonClickListener): CleanupFn {
    try {
      const avail = onBackButtonClick.isAvailable as unknown as () => boolean;
      if (avail()) {
        return onBackButtonClick(handler);
      }
    } catch {/* dev env */}
    return () => {/* noop */};
  },

  offClick(handler: BackButtonClickListener): void {
    try {
      if (offBackButtonClick.isAvailable()) {
        offBackButtonClick(handler);
      }
    } catch {/* dev env */}
  },
};

// ── Haptic feedback helpers ────────────────────────────────────────────────────

export function impactLight(): void {
  try {
    if (hapticFeedbackImpactOccurred.isAvailable()) {
      hapticFeedbackImpactOccurred("light");
    }
  } catch {/* dev env */}
}

export function notifySuccess(): void {
  try {
    if (hapticFeedbackNotificationOccurred.isAvailable()) {
      hapticFeedbackNotificationOccurred("success");
    }
  } catch {/* dev env */}
}

export function notifyError(): void {
  try {
    if (hapticFeedbackNotificationOccurred.isAvailable()) {
      hapticFeedbackNotificationOccurred("error");
    }
  } catch {/* dev env */}
}

export function notifyWarning(): void {
  try {
    if (hapticFeedbackNotificationOccurred.isAvailable()) {
      hapticFeedbackNotificationOccurred("warning");
    }
  } catch {/* dev env */}
}

// ── Color scheme (theme) ─────────────────────────────────────────────────────
// Detection uses the legacy window.Telegram.WebApp global (injected by the
// telegram-web-app.js script in index.html) for colorScheme + the themeChanged
// event — the most reliable signal inside the Mini App — and falls back to the
// browser's prefers-color-scheme outside Telegram (dev / dashboard parity).

type ColorScheme = "light" | "dark";

interface LegacyWebApp {
  colorScheme?: ColorScheme;
  onEvent?: (event: string, handler: () => void) => void;
  offEvent?: (event: string, handler: () => void) => void;
}

function _legacyWebApp(): LegacyWebApp | undefined {
  return (window as unknown as { Telegram?: { WebApp?: LegacyWebApp } }).Telegram?.WebApp;
}

/** Current platform color scheme. Telegram first, then prefers-color-scheme, then dark. */
export function getColorScheme(): ColorScheme {
  try {
    const cs = _legacyWebApp()?.colorScheme;
    if (cs === "light" || cs === "dark") return cs;
  } catch {/* ignore */}
  try {
    if (window.matchMedia?.("(prefers-color-scheme: light)").matches) return "light";
  } catch {/* ignore */}
  return "dark";
}

/** Subscribe to platform color-scheme changes. Returns a cleanup function. */
export function onColorSchemeChange(cb: (scheme: ColorScheme) => void): () => void {
  const handler = () => cb(getColorScheme());
  const cleanups: Array<() => void> = [];

  try {
    const wa = _legacyWebApp();
    if (wa?.onEvent && wa?.offEvent) {
      wa.onEvent("themeChanged", handler);
      cleanups.push(() => wa.offEvent?.("themeChanged", handler));
    }
  } catch {/* ignore */}

  try {
    const mq = window.matchMedia?.("(prefers-color-scheme: light)");
    if (mq?.addEventListener) {
      mq.addEventListener("change", handler);
      cleanups.push(() => mq.removeEventListener("change", handler));
    }
  } catch {/* ignore */}

  return () => cleanups.forEach((c) => c());
}

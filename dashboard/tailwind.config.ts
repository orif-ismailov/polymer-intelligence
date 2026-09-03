import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // ── shadcn primitive tokens ──────────────────────────────────────────
        //
        // The shadcn components in components/ui/ style themselves with these
        // names (`bg-popover`, `text-muted-foreground`, `border-input`, …), and
        // `app/globals.css` defines the matching CSS variables. That was not
        // enough: Tailwind only EMITS a utility for a colour that appears here,
        // so `bg-popover` was never generated and every dialog, dropdown and
        // select rendered with NO BACKGROUND — a transparent panel over a
        // transparent overlay. Nothing failed; the class simply did not exist,
        // which is the same silent hole `text-muted` and `border-line` left.
        //
        // `<alpha-value>` is required for the opacity variants the primitives
        // use (`bg-muted/50` in DialogFooter, `bg-destructive/10` in Button).
        //
        // DELIBERATELY ABSENT: `accent`. Ours is emerald and 44 files depend on
        // it; shadcn's `--accent` is slate-700 hover fill. Mapping it here would
        // repaint every accent in the product to grey.
        popover: "hsl(var(--popover) / <alpha-value>)",
        "popover-foreground": "hsl(var(--popover-foreground) / <alpha-value>)",
        card: "hsl(var(--card) / <alpha-value>)",
        "card-foreground": "hsl(var(--card-foreground) / <alpha-value>)",
        muted: "hsl(var(--muted) / <alpha-value>)",
        "muted-foreground": "hsl(var(--muted-foreground) / <alpha-value>)",
        primary: "hsl(var(--primary) / <alpha-value>)",
        "primary-foreground": "hsl(var(--primary-foreground) / <alpha-value>)",
        secondary: "hsl(var(--secondary) / <alpha-value>)",
        "secondary-foreground": "hsl(var(--secondary-foreground) / <alpha-value>)",
        destructive: "hsl(var(--destructive) / <alpha-value>)",
        "destructive-foreground": "hsl(var(--destructive-foreground) / <alpha-value>)",
        "accent-foreground": "hsl(var(--accent-foreground) / <alpha-value>)",
        input: "hsl(var(--input) / <alpha-value>)",
        ring: "hsl(var(--ring) / <alpha-value>)",

        // Dark theme base
        background: {
          DEFAULT: "#0f172a", // slate-900
          secondary: "#1e293b", // slate-800
          tertiary: "#334155", // slate-700
        },
        foreground: {
          DEFAULT: "#f8fafc", // slate-50
          muted: "#94a3b8", // slate-400
          subtle: "#64748b", // slate-500
        },
        // Emerald accent
        accent: {
          DEFAULT: "#10b981", // emerald-500
          light: "#34d399", // emerald-400
          dark: "#059669", // emerald-600
          subtle: "#064e3b", // emerald-950
        },
        // Border
        border: {
          DEFAULT: "#334155", // slate-700
          subtle: "#1e293b", // slate-800
        },
        // Status / urgency color tokens
        status: {
          new: "#3b82f6", // blue-500
          viewed: "#94a3b8", // slate-400
          "in-progress": "#f59e0b", // amber-500
          "offer-sent": "#8b5cf6", // violet-500
          matched: "#10b981", // emerald-500
          closed: "#64748b", // slate-500
          cancelled: "#ef4444", // red-500
        },
        urgency: {
          high: "#ef4444", // red-500
          medium: "#f59e0b", // amber-500
          low: "#94a3b8", // slate-400
        },
        // Signal kind colors
        kind: {
          "buy-request": "#3b82f6", // blue-500
          "sell-offer": "#10b981", // emerald-500
          deal: "#8b5cf6", // violet-500
          "price-quote": "#f59e0b", // amber-500
          news: "#64748b", // slate-500
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;

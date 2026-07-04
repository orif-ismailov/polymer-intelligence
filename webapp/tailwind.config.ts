import type { Config } from "tailwindcss";

/*
 * Tailwind for the webapp. Colors are wired to the shared design tokens in
 * src/styles/tokens.css (CSS custom properties) so utilities like `bg-bg`,
 * `bg-surface`, `text-text-muted`, and `bg-green` automatically follow the
 * dark/light theme (ThemeProvider flips <html data-theme>). Never hardcode hex
 * in components — reference these token-backed color names instead.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // Theme flips via <html data-theme="light|dark"> (see tokens.css). Colors below
  // read CSS vars, so no `dark:` variants are needed — kept here for completeness.
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      screens: {
        // Faithful to the original landing breakpoints (was @media max-560 / min-980).
        phone: { max: "560px" },
        desk: "980px",
      },
      colors: {
        bg: "var(--bg)",
        surface: {
          DEFAULT: "var(--surface)",
          2: "var(--surface-2)",
        },
        border: "var(--border)",
        text: {
          DEFAULT: "var(--text)",
          muted: "var(--text-muted)",
        },
        green: {
          DEFAULT: "var(--green)",
          on: "var(--green-on)",
          // Translucent variants derived from the token green so they track the theme.
          soft: "color-mix(in srgb, var(--green) 14%, transparent)",
          line: "color-mix(in srgb, var(--green) 35%, transparent)",
        },
        blue: "var(--blue)",
        orange: "var(--orange)",
        purple: "var(--purple)",
        danger: "var(--danger)",
      },
      borderColor: {
        DEFAULT: "var(--border)",
      },
      keyframes: {
        "pulse-glow": {
          "0%,100%": {
            transform: "translate(-50%,-50%) scale(1)",
            boxShadow: "0 0 40px color-mix(in srgb, var(--green) 45%, transparent)",
          },
          "50%": {
            transform: "translate(-50%,-50%) scale(1.05)",
            boxShadow: "0 0 64px color-mix(in srgb, var(--green) 72%, transparent)",
          },
        },
      },
      animation: {
        "pulse-glow": "pulse-glow 3.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;

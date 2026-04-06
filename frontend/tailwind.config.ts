import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: [
          "ui-monospace",
          "JetBrains Mono",
          "Fira Code",
          "Cascadia Code",
          "monospace",
        ],
      },
      colors: {
        // GLIOTRACK design tokens — mirrors lib/constants.ts COLOURS
        gliotrack: {
          bg:              "#0d1117",
          surface:         "#161b22",
          elevated:        "#21262d",
          border:          "#30363d",
          blue:            "#2f81f7",
          green:           "#3fb950",
          amber:           "#d29922",
          red:             "#f85149",
          "text-primary":  "#e6edf3",
          "text-muted":    "#8b949e",
          "text-faint":    "#484f58",
        },
      },
      borderRadius: {
        card:   "12px",
        button: "8px",
        badge:  "4px",
      },
      boxShadow: {
        "blue-glow":   "0 0 20px rgba(47, 129, 247, 0.35)",
        "green-glow":  "0 0 16px rgba(63, 185, 80, 0.25)",
        "red-glow":    "0 0 16px rgba(248, 81, 73, 0.25)",
      },
      keyframes: {
        // Subtle fade-in for page transitions
        "fade-up": {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.25s ease-out forwards",
      },
    },
  },
  plugins: [],
};

export default config;

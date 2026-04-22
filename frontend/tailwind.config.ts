import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#081a34",
        paper2: "#0c2548",
        ink: "#e3edff",
        "ink-dim": "rgba(227,237,255,0.55)",
        cyan: "#7ac9ff",
        "cyan-dim": "rgba(122,201,255,0.4)",
      },
      fontFamily: {
        serif: ["var(--font-fraunces)", "ui-serif", "serif"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;

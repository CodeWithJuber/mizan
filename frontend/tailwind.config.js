/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        mizan: {
          gold: "#D4AF37",
          "gold-light": "#F3E5AB",
          "gold-dim": "#AA8529",
          "gold-text": "#996515",
          dark: "#0B0C10",
          "dark-surface": "#1F2833",
          "bg-primary": "#020617",
          "bg-secondary": "#0F172A",
          "bg-surface": "#1E293B",
          "bg-elevated": "#334155",
        },
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body: [
          "DM Sans",
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
        arabic: ["Amiri", "serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        micro: "12px",
        "2xs": "13px",
        xxs: "14px",
      },
      zIndex: {
        dropdown: "10",
        sticky: "20",
        overlay: "30",
        modal: "40",
        toast: "50",
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "fade-in-up": "fadeInUp 0.4s ease-out forwards",
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        float: "float 3s ease-in-out infinite",
        shimmer: "shimmer 1.5s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-5px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};

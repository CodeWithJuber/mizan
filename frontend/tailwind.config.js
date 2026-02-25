/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        mizan: {
          gold: '#c9a227',
          'gold-light': '#e8c84a',
          dark: '#0a0a0f',
          'dark-card': '#111118',
          'dark-border': '#1e1e2e',
          'dark-hover': '#16161f',
          accent: '#2563eb',
        },
      },
      fontFamily: {
        arabic: ['Amiri', 'serif'],
      },
    },
  },
  plugins: [],
}

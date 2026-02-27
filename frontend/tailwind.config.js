/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        mizan: {
          gold: '#c9a227',
          'gold-light': '#e8c84a',
          'gold-dim': '#8a6e1a',
        },
      },
      fontFamily: {
        arabic: ['Amiri', 'serif'],
        display: ['Cinzel', 'serif'],
        body: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        'micro': '9px',
        '2xs': '10px',
        'xxs': '11px',
      },
    },
  },
  plugins: [],
}

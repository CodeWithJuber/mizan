import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Where /api and /ws go in dev and preview: the local backend, or the mock
// API of the browser tests (MIZAN_API_TARGET).
const target = process.env.MIZAN_API_TARGET || 'http://localhost:8000'
const proxy = {
  '/api': target,
  '/ws': { target: target.replace(/^http/, 'ws'), ws: true },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // The entry has its own name so the size budget (.size-limit.json) finds it.
  build: { rolldownOptions: { output: { entryFileNames: 'assets/app-[hash].js' } } },
  server: { port: 3000, proxy },
  preview: { proxy },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the UI runs on :5173 and forwards /api to the FastAPI server on :8000.
// For the demo and Render, `npm run build` writes ../backend/static, which FastAPI serves itself.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { outDir: '../backend/static', emptyOutDir: true },
})

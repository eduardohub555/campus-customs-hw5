import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite takes the first free port from 5173 upward. This machine already has
// other course projects on 5173 and 5174, so the board may land on 5175 — the
// backend accepts any localhost origin, so whichever it picks works.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: false, open: true },
})

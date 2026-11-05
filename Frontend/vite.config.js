import { defineConfig } from 'vite'

// Serves on http://localhost:5173, which matches the CORS origin
// allowed by the backend (FastAPI api.py).
export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
  },
})

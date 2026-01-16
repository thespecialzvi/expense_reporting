import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Todo lo que empiece con /api se lo manda a Django
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      }
    }
  }
})

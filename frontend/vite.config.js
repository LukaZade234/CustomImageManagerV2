import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // Every Flask path the browser can reach must be listed here, not just the
    // ones that appear in frontend source. /thumbs is served by Flask but its
    // URL arrives inside an API response, so nothing in src/ mentions it and it
    // was missed -- every thumbnail 404'd in dev while working in production.
    proxy: {
      // changeOrigin stays off so Flask sees the origin the browser is actually
      // on. Sign-in picks its OAuth callback from that host (a laptop on
      // localhost, a phone on the Tailscale address), and Discord only accepts a
      // callback registered verbatim; rewriting the Host would collapse both to
      // localhost:5000 and send every flow to one of them.
      '/api': { target: 'http://localhost:5000', changeOrigin: false },
      '/thumbs': 'http://localhost:5000',
      '/characters': 'http://localhost:5000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})

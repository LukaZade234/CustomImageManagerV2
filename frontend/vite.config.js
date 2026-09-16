import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

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
        // React, the router and react-query change far less often than the app
        // does, so everything from node_modules gets its own chunk and stays
        // cached across deploys. (Rolldown, which Vite 8 uses, wants a function
        // here rather than the object form.)
        manualChunks(id) {
          if (id.includes('node_modules')) return 'vendor'
        },
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})

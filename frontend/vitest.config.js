import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
      include: ['src/**/*.{test,spec}.{js,jsx,ts,tsx}'],
      coverage: {
        provider: 'v8',
        include: ['src/**'],
        exclude: ['src/test/**', 'src/**/*.{test,spec}.*'],
      },
    },
  }),
)

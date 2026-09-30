import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import legacy from '@vitejs/plugin-legacy'

export default defineConfig({
  // PLAN-066: keep the new workbench assets isolated from the legacy Vue/Gradio surface.
  base: '/app-assets/',
  plugins: [
    vue({
      template: {
        transformAssetUrls: {
          // Don't transform absolute URLs starting with /static/
          includeAbsolute: false
        }
      }
    }),
    legacy({
      targets: ['Chrome >= 60', 'Safari >= 11', 'Firefox >= 60', 'Edge >= 79'],
      additionalLegacyPolyfills: ['regenerator-runtime/runtime']
    })
  ],
  build: {
    outDir: '../qyunslation/static/app',
    // The isolated app directory contains only generated Vue artifacts.
    emptyOutDir: true,
    cssMinify: false
  }
})

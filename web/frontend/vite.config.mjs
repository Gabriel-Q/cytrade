import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

const backendPort = process.env.VITE_BACKEND_PORT || '8080'
const backendHttpTarget = `http://127.0.0.1:${backendPort}`
const backendWsTarget = `ws://127.0.0.1:${backendPort}`

export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: ['vue'],
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver({ importStyle: 'css' })],
    }),
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('element-plus')) return 'element-plus'
          if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) return 'vue-vendor'
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: backendHttpTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: backendWsTarget,
        ws: true,
      }
    }
  }
})

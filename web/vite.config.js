import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { quasar, transformAssetUrls } from "@quasar/vite-plugin"

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue({
      template: { transformAssetUrls },
    }),
    quasar(),
  ],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
})

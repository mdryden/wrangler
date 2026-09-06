import { defineStore } from "pinia"
import { ref } from "vue"

export const useAppStore = defineStore("app", () => {
  const appName = ref("Wrangler")
  const initialized = ref(true)

  return {
    appName,
    initialized,
  }
})

import { defineStore } from "pinia"
import { ref } from "vue"

export const useAppStore = defineStore("app", () => {
  const appName = ref<string>("Wrangler")
  const initialized = ref<boolean>(true)

  return {
    appName,
    initialized,
  }
})

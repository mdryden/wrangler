import { defineStore } from "pinia"
import { ref } from "vue"

export const STORAGE_KEY_SIDEBAR_COLLAPSED = "wrangler_sidebar_collapsed"

export const useAppStore = defineStore("app", () => {
  const appName = ref<string>("Wrangler")
  const initialized = ref<boolean>(true)

  const storedCollapsed = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY_SIDEBAR_COLLAPSED) === "true" : false
  const sidebarCollapsed = ref<boolean>(storedCollapsed)

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY_SIDEBAR_COLLAPSED, String(sidebarCollapsed.value))
    }
  }

  function setSidebarCollapsed(collapsed: boolean): void {
    sidebarCollapsed.value = collapsed
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY_SIDEBAR_COLLAPSED, String(collapsed))
    }
  }

  return {
    appName,
    initialized,
    sidebarCollapsed,
    toggleSidebar,
    setSidebarCollapsed,
  }
})

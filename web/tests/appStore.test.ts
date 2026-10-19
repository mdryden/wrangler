import { describe, it, expect, beforeEach } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useAppStore, STORAGE_KEY_SIDEBAR_COLLAPSED } from "../src/stores/app"

// In-memory mock storage
const mockStorage = new Map<string, string>()
const mockLocalStorage = {
  getItem: (key: string): string | null => mockStorage.get(key) || null,
  setItem: (key: string, val: string): void => {
    mockStorage.set(key, String(val))
  },
  removeItem: (key: string): void => {
    mockStorage.delete(key)
  },
  clear: (): void => mockStorage.clear(),
  length: 0,
  key: () => null,
}

Object.defineProperty(globalThis, "localStorage", {
  value: mockLocalStorage,
  writable: true,
})

Object.defineProperty(globalThis, "window", {
  value: globalThis,
  writable: true,
})

describe("useAppStore", () => {
  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
  })

  it("exports STORAGE_KEY_SIDEBAR_COLLAPSED as wrangler_sidebar_collapsed", () => {
    expect(STORAGE_KEY_SIDEBAR_COLLAPSED).toBe("wrangler_sidebar_collapsed")
  })

  it("initializes with sidebarCollapsed = false when localStorage has no record", () => {
    const app = useAppStore()
    expect(app.sidebarCollapsed).toBe(false)
    expect(app.appName).toBe("Wrangler")
    expect(app.initialized).toBe(true)
  })

  it("initializes with sidebarCollapsed = true when localStorage contains 'true'", () => {
    globalThis.localStorage.setItem(STORAGE_KEY_SIDEBAR_COLLAPSED, "true")

    const app = useAppStore()
    expect(app.sidebarCollapsed).toBe(true)
  })

  it("initializes with sidebarCollapsed = false when localStorage contains 'false' or invalid value", () => {
    globalThis.localStorage.setItem(STORAGE_KEY_SIDEBAR_COLLAPSED, "false")

    const app = useAppStore()
    expect(app.sidebarCollapsed).toBe(false)
  })

  it("toggleSidebar flips state from false to true and writes 'true' to localStorage", () => {
    const app = useAppStore()
    expect(app.sidebarCollapsed).toBe(false)

    app.toggleSidebar()
    expect(app.sidebarCollapsed).toBe(true)
    expect(globalThis.localStorage.getItem(STORAGE_KEY_SIDEBAR_COLLAPSED)).toBe("true")

    app.toggleSidebar()
    expect(app.sidebarCollapsed).toBe(false)
    expect(globalThis.localStorage.getItem(STORAGE_KEY_SIDEBAR_COLLAPSED)).toBe("false")
  })

  it("setSidebarCollapsed directly updates sidebarCollapsed and synchronizes with localStorage", () => {
    const app = useAppStore()

    app.setSidebarCollapsed(true)
    expect(app.sidebarCollapsed).toBe(true)
    expect(globalThis.localStorage.getItem(STORAGE_KEY_SIDEBAR_COLLAPSED)).toBe("true")

    app.setSidebarCollapsed(false)
    expect(app.sidebarCollapsed).toBe(false)
    expect(globalThis.localStorage.getItem(STORAGE_KEY_SIDEBAR_COLLAPSED)).toBe("false")
  })
})

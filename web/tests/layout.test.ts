import fs from "fs"
import path from "path"
import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { navItems, handleSidebarKeydown } from "../src/layouts/nav"
import { useAppStore } from "../src/stores/app"

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

function createMockKeyEvent(options: {
  key: string
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
  target?: Partial<HTMLElement> | null
}): KeyboardEvent {
  const event = {
    key: options.key,
    ctrlKey: options.ctrlKey ?? false,
    metaKey: options.metaKey ?? false,
    altKey: options.altKey ?? false,
    shiftKey: options.shiftKey ?? false,
    target: options.target ?? null,
    defaultPrevented: false,
    preventDefault: vi.fn(),
  } as unknown as KeyboardEvent
  return event
}

describe("MainLayout Navigation Drawer & Rail Configuration", () => {
  it("defines the primary persistent navigation items including import", () => {
    expect(navItems).toHaveLength(6)
    const itemNames = navItems.map(item => item.name)
    expect(itemNames).toEqual(["ledger", "import", "manual-entry", "export-manager", "checklist", "settings"])
  })

  it("configures each navigation item with label, icon, and route path", () => {
    const ledger = navItems.find(item => item.name === "ledger")
    expect(ledger).toEqual({
      name: "ledger",
      label: "Ledger",
      icon: "receipt_long",
      path: "/ledger",
    })

    const importItem = navItems.find(item => item.name === "import")
    expect(importItem).toEqual({
      name: "import",
      label: "Import",
      icon: "cloud_upload",
      path: "/import",
    })

    const manualEntry = navItems.find(item => item.name === "manual-entry")
    expect(manualEntry).toEqual({
      name: "manual-entry",
      label: "Manual Entry",
      icon: "post_add",
      path: "/manual-entry",
    })

    const exportManager = navItems.find(item => item.name === "export-manager")
    expect(exportManager).toEqual({
      name: "export-manager",
      label: "Export Manager",
      icon: "file_download",
      path: "/export-manager",
    })

    const checklist = navItems.find(item => item.name === "checklist")
    expect(checklist).toEqual({
      name: "checklist",
      label: "Checklist",
      icon: "fact_check",
      path: "/checklist",
    })

    const settings = navItems.find(item => item.name === "settings")
    expect(settings).toEqual({
      name: "settings",
      label: "Settings",
      icon: "settings",
      path: "/settings",
    })
  })
})

describe("Keyboard Shortcut Hotkey & Input Guarding (Ctrl+B / Cmd+B)", () => {
  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
  })

  it("triggers toggleSidebar and prevents default on Ctrl+B keydown", () => {
    const appStore = useAppStore()
    expect(appStore.sidebarCollapsed).toBe(false)

    const event = createMockKeyEvent({ key: "b", ctrlKey: true })
    const handled = handleSidebarKeydown(event, () => appStore.toggleSidebar())

    expect(handled).toBe(true)
    expect(event.preventDefault).toHaveBeenCalledTimes(1)
    expect(appStore.sidebarCollapsed).toBe(true)
  })

  it("triggers toggleSidebar and prevents default on Cmd+B (metaKey) keydown", () => {
    const appStore = useAppStore()
    expect(appStore.sidebarCollapsed).toBe(false)

    const event = createMockKeyEvent({ key: "b", metaKey: true })
    const handled = handleSidebarKeydown(event, () => appStore.toggleSidebar())

    expect(handled).toBe(true)
    expect(event.preventDefault).toHaveBeenCalledTimes(1)
    expect(appStore.sidebarCollapsed).toBe(true)
  })

  it("handles case-insensitive 'B' with modifier keys", () => {
    const appStore = useAppStore()
    expect(appStore.sidebarCollapsed).toBe(false)

    const event = createMockKeyEvent({ key: "B", ctrlKey: true })
    const handled = handleSidebarKeydown(event, () => appStore.toggleSidebar())

    expect(handled).toBe(true)
    expect(event.preventDefault).toHaveBeenCalledTimes(1)
    expect(appStore.sidebarCollapsed).toBe(true)
  })

  it("ignores hotkey when typing inside an <input> element", () => {
    const appStore = useAppStore()
    expect(appStore.sidebarCollapsed).toBe(false)

    const inputTarget = { tagName: "INPUT", isContentEditable: false } as HTMLElement
    const event = createMockKeyEvent({ key: "b", ctrlKey: true, target: inputTarget })
    const handled = handleSidebarKeydown(event, () => appStore.toggleSidebar())

    expect(handled).toBe(false)
    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(appStore.sidebarCollapsed).toBe(false)
  })

  it("ignores hotkey when typing inside a <textarea> element", () => {
    const appStore = useAppStore()
    expect(appStore.sidebarCollapsed).toBe(false)

    const textareaTarget = { tagName: "TEXTAREA", isContentEditable: false } as HTMLElement
    const event = createMockKeyEvent({ key: "b", ctrlKey: true, target: textareaTarget })
    const handled = handleSidebarKeydown(event, () => appStore.toggleSidebar())

    expect(handled).toBe(false)
    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(appStore.sidebarCollapsed).toBe(false)
  })

  it("ignores hotkey when typing inside a contenteditable element", () => {
    const appStore = useAppStore()
    expect(appStore.sidebarCollapsed).toBe(false)

    const editableTarget = { tagName: "DIV", isContentEditable: true } as HTMLElement
    const event = createMockKeyEvent({ key: "b", ctrlKey: true, target: editableTarget })
    const handled = handleSidebarKeydown(event, () => appStore.toggleSidebar())

    expect(handled).toBe(false)
    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(appStore.sidebarCollapsed).toBe(false)
  })

  it("ignores non-matching key combinations", () => {
    const appStore = useAppStore()
    expect(appStore.sidebarCollapsed).toBe(false)

    // Plain "b" without modifier
    const plainB = createMockKeyEvent({ key: "b" })
    expect(handleSidebarKeydown(plainB, () => appStore.toggleSidebar())).toBe(false)
    expect(plainB.preventDefault).not.toHaveBeenCalled()
    expect(appStore.sidebarCollapsed).toBe(false)

    // Ctrl+A
    const ctrlA = createMockKeyEvent({ key: "a", ctrlKey: true })
    expect(handleSidebarKeydown(ctrlA, () => appStore.toggleSidebar())).toBe(false)
    expect(ctrlA.preventDefault).not.toHaveBeenCalled()
    expect(appStore.sidebarCollapsed).toBe(false)

    // Alt+B
    const altB = createMockKeyEvent({ key: "b", altKey: true })
    expect(handleSidebarKeydown(altB, () => appStore.toggleSidebar())).toBe(false)
    expect(altB.preventDefault).not.toHaveBeenCalled()
    expect(appStore.sidebarCollapsed).toBe(false)

    // Shift+B
    const shiftB = createMockKeyEvent({ key: "B", shiftKey: true })
    expect(handleSidebarKeydown(shiftB, () => appStore.toggleSidebar())).toBe(false)
    expect(shiftB.preventDefault).not.toHaveBeenCalled()
    expect(appStore.sidebarCollapsed).toBe(false)
  })
})

describe("MainLayout Template & Structural Contract Specification", () => {
  const layoutFilePath = path.resolve(__dirname, "../src/layouts/MainLayout.vue")
  const templateContent = fs.readFileSync(layoutFilePath, "utf-8")

  it("configures full-height left drawer layout view ('lHh Lpr lFf')", () => {
    expect(templateContent).toContain('view="lHh Lpr lFf"')
  })

  it("configures docked drawer attributes for mini icon rail mode", () => {
    expect(templateContent).toContain(':mini="appStore.sidebarCollapsed"')
    expect(templateContent).toContain(':mini-width="60"')
    expect(templateContent).toContain(':width="240"')
    expect(templateContent).toContain(':breakpoint="0"')
    expect(templateContent).toContain('side="left"')
    expect(templateContent).toContain("show-if-above")
    expect(templateContent).toContain("bordered")
  })

  it("renders dedicated external sidebar trigger button with panel-left SVG icon", () => {
    expect(templateContent).toContain('aria-label="Toggle sidebar"')
    expect(templateContent).toContain('@click="appStore.toggleSidebar"')
    // Lucide panel-left icon markup
    expect(templateContent).toContain('<rect width="18" height="18" x="3" y="3" rx="2" />')
    expect(templateContent).toContain('<path d="M9 3v18" />')
  })

  it("provides dynamic hotkey tooltip on trigger button", () => {
    expect(templateContent).toMatch(
      /appStore\.sidebarCollapsed\s*\?\s*['"]Expand sidebar \(Ctrl\+B\)['"]\s*:\s*['"]Collapse sidebar \(Ctrl\+B\)['"]/,
    )
  })

  it("relocates application branding into full-height drawer top", () => {
    expect(templateContent).toContain('name="account_balance_wallet"')
    expect(templateContent).toContain("Wrangler")
    expect(templateContent).toContain('v-show="!appStore.sidebarCollapsed"')
  })

  it("provides contextual tooltips on navigation items for mini rail mode", () => {
    expect(templateContent).toContain('v-if="appStore.sidebarCollapsed"')
    expect(templateContent).toContain('anchor="center right"')
    expect(templateContent).toContain('self="center left"')
    expect(templateContent).toContain(':offset="[14, 14]"')
    expect(templateContent).toContain("{{ item.label }}")
  })

  it("centers navigation rail icons in collapsed mini mode", () => {
    expect(templateContent).toContain("sidebar-mini-item")
    expect(templateContent).toContain("sidebar-mini-avatar")
    expect(templateContent).toContain(".sidebar-mini-item {")
    expect(templateContent).toContain(".sidebar-mini-avatar {")
  })
})

describe("Application Favicon Contract", () => {
  const indexHtmlPath = path.resolve(__dirname, "../index.html")
  const faviconSvgPath = path.resolve(__dirname, "../public/favicon.svg")

  it("links to the SVG favicon in index.html", () => {
    const htmlContent = fs.readFileSync(indexHtmlPath, "utf-8")
    expect(htmlContent).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg" />')
  })

  it("provides the account_balance_wallet icon SVG asset in public/favicon.svg", () => {
    expect(fs.existsSync(faviconSvgPath)).toBe(true)
    const svgContent = fs.readFileSync(faviconSvgPath, "utf-8")
    expect(svgContent).toContain('viewBox="0 0 24 24"')
    expect(svgContent).toContain("M21 18v1c0 1.1-.9 2-2 2H5")
    expect(svgContent).toContain("#1976D2")
  })
})

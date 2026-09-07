import { describe, it, expect } from "vitest"
import { navItems } from "../src/layouts/nav"

describe("MainLayout Navigation Drawer", () => {
  it("defines the 4 primary persistent navigation items", () => {
    expect(navItems).toHaveLength(4)
    const itemNames = navItems.map(item => item.name)
    expect(itemNames).toEqual(["ledger", "manual-entry", "export-manager", "settings"])
  })

  it("configures each navigation item with label, icon, and route path", () => {
    const ledger = navItems.find(item => item.name === "ledger")
    expect(ledger).toEqual({
      name: "ledger",
      label: "Ledger",
      icon: "receipt_long",
      path: "/ledger",
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

    const settings = navItems.find(item => item.name === "settings")
    expect(settings).toEqual({
      name: "settings",
      label: "Settings",
      icon: "settings",
      path: "/settings",
    })
  })
})

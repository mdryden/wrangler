import { describe, it, expect } from "vitest"
import { navItems } from "../src/layouts/nav"

describe("MainLayout Navigation Drawer", () => {
  it("defines the 4 primary persistent navigation items", () => {
    expect(navItems).toHaveLength(4)
    const itemNames = navItems.map(item => item.name)
    expect(itemNames).toEqual(["ledger", "manual-entry", "sync-manager", "settings"])
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

    const syncManager = navItems.find(item => item.name === "sync-manager")
    expect(syncManager).toEqual({
      name: "sync-manager",
      label: "Sync Manager",
      icon: "sync",
      path: "/sync-manager",
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

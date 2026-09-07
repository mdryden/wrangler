export interface NavItem {
  name: string
  label: string
  icon: string
  path: string
}

export const navItems: NavItem[] = [
  { name: "ledger", label: "Ledger", icon: "receipt_long", path: "/ledger" },
  { name: "manual-entry", label: "Manual Entry", icon: "post_add", path: "/manual-entry" },
  { name: "export-manager", label: "Export Manager", icon: "file_download", path: "/export-manager" },
  { name: "settings", label: "Settings", icon: "settings", path: "/settings" },
]

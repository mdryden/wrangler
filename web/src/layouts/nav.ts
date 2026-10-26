export interface NavItem {
  name: string
  label: string
  icon: string
  path: string
}

export const navItems: NavItem[] = [
  { name: "ledger", label: "Ledger", icon: "receipt_long", path: "/ledger" },
  { name: "import", label: "Import", icon: "cloud_upload", path: "/import" },
  { name: "manual-entry", label: "Manual Entry", icon: "post_add", path: "/manual-entry" },
  { name: "export-manager", label: "Export Manager", icon: "file_download", path: "/export-manager" },
  { name: "checklist", label: "Checklist", icon: "fact_check", path: "/checklist" },
  { name: "settings", label: "Settings", icon: "settings", path: "/settings" },
]

export function handleSidebarKeydown(event: KeyboardEvent, toggleSidebar: () => void): boolean {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
      return false
    }
    event.preventDefault()
    toggleSidebar()
    return true
  }
  return false
}

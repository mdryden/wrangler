import type { QTableColumn } from "quasar"
import type { Company } from "../types/company"
import type { StagedTransaction } from "../types/staging"
import { formatCurrency } from "./ledger"

/**
 * Formats a staged amount or string into standard CAD currency format ($X,XXX.XX or -$X,XXX.XX).
 */
export function formatStagedAmount(amount: string | number | null | undefined): string {
  return formatCurrency(amount)
}

export const stagingTableColumns: QTableColumn[] = [
  {
    name: "select",
    label: "",
    align: "center",
    field: (row: StagedTransaction) => row.id,
    sortable: false,
    style: "width: 48px",
    headerStyle: "width: 48px",
  },
  {
    name: "url",
    label: "",
    align: "center",
    field: (row: StagedTransaction) => row.url ?? "",
    sortable: false,
    style: "width: 44px",
    headerStyle: "width: 44px",
  },
  {
    name: "actions",
    label: "Actions",
    align: "left",
    field: () => "",
    sortable: false,
    style: "width: 80px",
    headerStyle: "width: 80px",
  },
  {
    name: "allocations",
    label: "Allocation",
    align: "left",
    field: (row: StagedTransaction) => row.id,
    sortable: false,
    style: "width: 150px",
    headerStyle: "width: 150px",
  },
  {
    name: "date",
    required: true,
    label: "Date",
    align: "left",
    field: (row: StagedTransaction) => row.date,
    sortable: false,
    style: "width: 95px",
    headerStyle: "width: 95px",
  },
  {
    name: "description",
    required: true,
    label: "Description",
    align: "left",
    field: (row: StagedTransaction) => row.description,
    sortable: false,
    style: "min-width: 240px",
    headerStyle: "min-width: 240px",
  },
  {
    name: "total_amount",
    required: true,
    label: "Amount",
    align: "right",
    field: (row: StagedTransaction) => row.total_amount,
    sortable: false,
    style: "width: 95px",
    headerStyle: "width: 95px",
  },
  {
    name: "receipt",
    label: "Receipt",
    align: "center",
    field: (row: StagedTransaction) => (row.receipt_file_path ? "Yes" : "No"),
    sortable: false,
    style: "width: 80px",
    headerStyle: "width: 80px",
  },
]

/**
 * Checks whether a staged transaction is strictly allocated as 100% Personal.
 */
export function isRowPersonal(row: StagedTransaction): boolean {
  return Boolean(row.allocations && row.allocations.length === 1 && row.allocations[0].is_personal && !row.allocations[0].company_id)
}

/**
 * Determines whether the importer summary notification should be a warning
 * (when files failed or duplicates were skipped) or positive success.
 */
export function getImportNotificationType(result: { failed_files?: string[]; skipped_duplicates: number }): "warning" | "positive" {
  if ((result.failed_files && result.failed_files.length > 0) || result.skipped_duplicates > 0) {
    return "warning"
  }
  return "positive"
}

/**
 * Checks whether all visible STAGED rows are currently selected.
 */
export function isMasterHeaderChecked(visibleStagedRowIds: string[], selectedRowIds: string[]): boolean {
  if (visibleStagedRowIds.length === 0) return false
  return visibleStagedRowIds.every(id => selectedRowIds.includes(id))
}

/**
 * Checks whether some (but not all) visible STAGED rows are currently selected.
 */
export function isMasterHeaderIndeterminate(visibleStagedRowIds: string[], selectedRowIds: string[]): boolean {
  if (visibleStagedRowIds.length === 0) return false
  const selectedCount = visibleStagedRowIds.filter(id => selectedRowIds.includes(id)).length
  return selectedCount > 0 && selectedCount < visibleStagedRowIds.length
}

/**
 * Toggles selection of all visible STAGED rows.
 * If all or some are selected, deselects all visible STAGED rows.
 * Otherwise, selects all visible STAGED rows.
 */
export function toggleVisibleStagedRows(visibleStagedRowIds: string[], currentSelectedRowIds: string[]): string[] {
  const isAllOrSomeSelected = visibleStagedRowIds.some(id => currentSelectedRowIds.includes(id))
  if (isAllOrSomeSelected) {
    return currentSelectedRowIds.filter(id => !visibleStagedRowIds.includes(id))
  }
  const toAdd = visibleStagedRowIds.filter(id => !currentSelectedRowIds.includes(id))
  return [...currentSelectedRowIds, ...toAdd]
}

/**
 * Returns the count of selected transactions that are ready to accept into the ledger.
 */
export function getSelectedReadyCount(selectedRowIds: string[], stagedTransactions: StagedTransaction[]): number {
  return stagedTransactions.filter(tx => selectedRowIds.includes(tx.id) && tx.is_ready).length
}

/**
 * Returns the IDs of selected transactions that are ready to accept into the ledger.
 */
export function getSelectedReadyIds(selectedRowIds: string[], stagedTransactions: StagedTransaction[]): string[] {
  return stagedTransactions.filter(tx => selectedRowIds.includes(tx.id) && tx.is_ready).map(tx => tx.id)
}

export const SOURCE_FRIENDLY_NAMES: Record<string, string> = {
  amazon_csv: "Amazon",
  receipt_parser: "Receipt",
  ai_receipt: "Receipt",
  mcp: "AI Assistant",
  manual: "Manual",
  wrangler_csv: "Wrangler",
  google_groups: "Google Groups",
}

export function getSourceFriendlyName(source: string): string {
  return SOURCE_FRIENDLY_NAMES[source] || source.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
}

export interface StagingShortcutContext {
  activeActionRowId: string | null
  stagedTransactions: StagedTransaction[]
  companies: Company[]
  isDialogOpen: boolean
  onPersonal: (row: StagedTransaction) => void
  onCompanyEdit: (row: StagedTransaction, defaultCompanyId?: string | null) => void
  onDismissStrip: () => void
}

/**
 * Evaluates keyboard shortcuts when an active staging action strip is open.
 * Returns true if a shortcut was handled and default event behavior should be prevented.
 */
export function handleStagingKeyboardShortcut(event: KeyboardEvent, context: StagingShortcutContext): boolean {
  if (!context.activeActionRowId || context.isDialogOpen) {
    return false
  }

  // Guard: Ignore modifier key combinations (Ctrl, Meta, Alt) to preserve browser/system shortcuts (e.g. Ctrl+C)
  if (event.ctrlKey || event.metaKey || event.altKey) {
    return false
  }

  // Guard: Do not intercept typing inside form inputs, textareas, selects, or editable elements
  const target = event.target as HTMLElement | null
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)) {
    return false
  }

  const activeRow = context.stagedTransactions.find(r => r.id === context.activeActionRowId)
  if (!activeRow || activeRow.status !== "STAGED") {
    return false
  }

  const key = event.key.toLowerCase()

  if (key === "x") {
    event.preventDefault()
    context.onPersonal(activeRow)
    return true
  }

  if (key === "c") {
    event.preventDefault()
    context.onCompanyEdit(activeRow, null)
    return true
  }

  if (/^[1-9]$/.test(event.key)) {
    const companyIndex = Number(event.key) - 1
    if (companyIndex >= 0 && companyIndex < context.companies.length) {
      event.preventDefault()
      const targetCompany = context.companies[companyIndex]
      context.onCompanyEdit(activeRow, targetCompany.id)
      return true
    }
  }

  if (key === "escape") {
    event.preventDefault()
    context.onDismissStrip()
    return true
  }

  return false
}

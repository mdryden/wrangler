import type { Company, CompanyExportOptions } from "../types/company"
import type { Transaction } from "../types/transaction"
import { formatCurrency } from "./ledger"

export { formatCurrency }

export const DEFAULT_EXPORT_PAGE_SIZE = 50

export interface ExportControlsState {
  company_id: string | null
  include_locked: boolean
  start_date: string
  end_date: string
}

export interface ExportAllocationRow {
  id: string
  transaction_id: string
  date: string
  description: string
  amount: string | number
  is_locked: boolean
  company_id: string | null
  receipt_file_path: string | null
  wave_category_id: string | null
  wave_transaction_id: string | null
}

export interface CompanyExportSummary {
  id: string
  name: string
  unlockedCount: number
  unlockedTotalFormatted: string
  lockedCount: number
  totalBusinessCount: number
}

/**
 * Creates the default state for Export Manager controls (company starts empty).
 */
export function createInitialExportControlsState(): ExportControlsState {
  return {
    company_id: null,
    include_locked: false,
    start_date: "",
    end_date: "",
  }
}

/**
 * Resets Export Manager controls back to their defaults.
 */
export function resetExportControlsState(state: ExportControlsState): void {
  state.company_id = null
  state.include_locked = false
  state.start_date = ""
  state.end_date = ""
}

/**
 * Builds query options for `exportTransactionsCsv` from the current UI controls state.
 */
export function buildCompanyExportOptions(state: ExportControlsState): CompanyExportOptions {
  return {
    include_locked: Boolean(state.include_locked),
    start_date: state.start_date.trim() || undefined,
    end_date: state.end_date.trim() || undefined,
  }
}

/**
 * Extracts flattened business allocation rows for the selected company and lock filter from a list of transactions.
 */
export function extractCompanyAllocationRows(
  transactions: Transaction[] | undefined | null,
  companyId: string | null | undefined,
  includeLocked = false,
): ExportAllocationRow[] {
  if (!companyId || !Array.isArray(transactions)) {
    return []
  }

  const rows: ExportAllocationRow[] = []
  for (const tx of transactions) {
    for (const alloc of tx.allocations ?? []) {
      if (alloc.is_personal || alloc.company_id !== companyId) {
        continue
      }
      if (!includeLocked && alloc.is_locked) {
        continue
      }
      rows.push({
        id: alloc.id,
        transaction_id: tx.id,
        date: tx.date,
        description: tx.description,
        amount: alloc.amount,
        is_locked: Boolean(alloc.is_locked),
        company_id: alloc.company_id,
        receipt_file_path: tx.receipt_file_path,
        wave_category_id: alloc.wave_category_id ?? null,
        wave_transaction_id: alloc.wave_transaction_id ?? null,
      })
    }
  }
  return rows
}

/**
 * Determines whether a row was previously pushed to Wave but was subsequently unlocked in Wrangler.
 * Legacy check retained for backwards compatibility with tests.
 * Since unlocked rows have wave_transaction_id reset to null, this returns false.
 */
export function isWaveAlreadySynced(row: ExportAllocationRow): boolean {
  return Boolean(!row.is_locked && row.wave_transaction_id)
}

/**
 * Determines whether a row is eligible to be selected and synced to Wave.
 * A row is eligible if it is unlocked and has an assigned Wave category.
 */
export function canSyncRowToWave(row: ExportAllocationRow): boolean {
  return Boolean(!row.is_locked && row.wave_category_id)
}

/**
 * Builds the URL to open a parent transaction in the Ledger view.
 */
export function getLedgerTransactionUrl(transactionId: string): string {
  return `/ledger?transaction_id=${encodeURIComponent(transactionId)}`
}

/**
 * Opens a parent transaction in the Ledger view in a new browser tab.
 */
export function openTransactionInLedgerNewTab(transactionId: string): string {
  const url = getLedgerTransactionUrl(transactionId)
  if (typeof window !== "undefined" && typeof window.open === "function") {
    window.open(url, "_blank", "noopener,noreferrer")
  } else if (typeof globalThis.open === "function") {
    globalThis.open(url, "_blank", "noopener,noreferrer")
  }
  return url
}

/**
 * Computes formatted summary metrics for a company in the Export Manager.
 */
export function getCompanyExportSummary(company: Company): CompanyExportSummary {
  const unlockedCount = Number(company.unlocked_allocation_count ?? 0)
  const lockedCount = Number(company.locked_allocation_count ?? 0)
  return {
    id: company.id,
    name: company.name,
    unlockedCount,
    unlockedTotalFormatted: formatCurrency(company.unlocked_amount_total ?? 0),
    lockedCount,
    totalBusinessCount: unlockedCount + lockedCount,
  }
}

/**
 * Determines whether a company has exportable business allocations given the current `include_locked` setting.
 */
export function canExportCompany(company: Company | null | undefined, includeLocked = false): boolean {
  if (!company) return false
  const unlockedCount = Number(company.unlocked_allocation_count ?? 0)
  const lockedCount = Number(company.locked_allocation_count ?? 0)
  if (includeLocked) {
    return unlockedCount + lockedCount > 0
  }
  return unlockedCount > 0
}

/**
 * Determines whether the master header checkbox should be fully checked.
 * True when visibleRowIds is non-empty and every visible ID is selected.
 */
export function isMasterHeaderChecked(visibleRowIds: string[], selectedRowIds: string[]): boolean {
  if (visibleRowIds.length === 0) return false
  const selectedSet = new Set(selectedRowIds)
  return visibleRowIds.every(id => selectedSet.has(id))
}

/**
 * Determines whether the master header checkbox should be in an indeterminate state.
 * True when some, but not all, visible IDs are selected.
 */
export function isMasterHeaderIndeterminate(visibleRowIds: string[], selectedRowIds: string[]): boolean {
  if (visibleRowIds.length === 0) return false
  const selectedSet = new Set(selectedRowIds)
  const count = visibleRowIds.filter(id => selectedSet.has(id)).length
  return count > 0 && count < visibleRowIds.length
}

/**
 * Counts how many rows in selectedRows have an existing assigned wave_category_id.
 */
export function countOverwrittenCategories(selectedRows: ExportAllocationRow[]): number {
  if (!Array.isArray(selectedRows)) return 0
  return selectedRows.filter(row => Boolean(row.wave_category_id)).length
}

/**
 * Determines whether all selected rows are eligible to sync to Wave.
 * True if selectedRows is non-empty and every selected row is unlocked and has a wave_category_id.
 */
export function canSyncSelectedToWave(selectedRows: ExportAllocationRow[]): boolean {
  if (!Array.isArray(selectedRows) || selectedRows.length === 0) return false
  return selectedRows.every(row => !row.is_locked && Boolean(row.wave_category_id))
}

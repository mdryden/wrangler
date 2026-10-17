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
  currency_code: string
  is_locked: boolean
  company_id: string | null
  receipt_file_path: string | null
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
        currency_code: tx.currency_code || "CAD",
        is_locked: Boolean(alloc.is_locked),
        company_id: alloc.company_id,
        receipt_file_path: tx.receipt_file_path,
      })
    }
  }
  return rows
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

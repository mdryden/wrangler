import type { Company, CompanyExportOptions } from "../types/company"
import { formatCurrency } from "./ledger"

export { formatCurrency }

export interface ExportControlsState {
  include_locked: boolean
  start_date: string
  end_date: string
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
 * Creates the default state for Export Manager controls.
 */
export function createInitialExportControlsState(): ExportControlsState {
  return {
    include_locked: false,
    start_date: "",
    end_date: "",
  }
}

/**
 * Resets Export Manager controls back to their defaults.
 */
export function resetExportControlsState(state: ExportControlsState): void {
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
 * Computes formatted summary metrics for a company row in the Export Manager.
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
export function canExportCompany(company: Company, includeLocked = false): boolean {
  const unlockedCount = Number(company.unlocked_allocation_count ?? 0)
  const lockedCount = Number(company.locked_allocation_count ?? 0)
  if (includeLocked) {
    return unlockedCount + lockedCount > 0
  }
  return unlockedCount > 0
}

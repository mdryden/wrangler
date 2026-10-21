import type { Allocation, Transaction } from "../types/transaction"
import type { Company } from "../types/company"
import { DELETE_LOCKED_TOOLTIP, UNLOCK_WARNING_MESSAGE } from "../components/transactionEdit"

export { DELETE_LOCKED_TOOLTIP, UNLOCK_WARNING_MESSAGE }

export type TransactionLockStatus = "unlocked" | "partially_locked" | "fully_locked"

/**
 * Formats a numeric amount or string into standard CAD currency format ($X,XXX.XX or -$X,XXX.XX).
 */
export function formatCurrency(amount: string | number | null | undefined): string {
  if (amount === null || amount === undefined || amount === "") {
    return "$0.00"
  }
  const num = typeof amount === "string" ? parseFloat(amount) : amount
  if (Number.isNaN(num)) return "$0.00"

  const isNegative = num < 0
  const absFormatted = Math.abs(num).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return `${isNegative ? "-" : ""}$${absFormatted}`
}

/**
 * Resolves allocation display text for a transaction.
 * Returns "Personal", the company name (e.g. "Company X"), or "X splits".
 */
export function getAllocationLabel(
  target: Transaction | Allocation[] | undefined | null,
  companies: Company[] | Map<string, string> = [],
): string {
  const allocations: Allocation[] = Array.isArray(target) ? target : (target?.allocations ?? [])

  if (allocations.length === 1) {
    const alloc = allocations[0]
    if (alloc.is_personal) {
      return "Personal"
    }

    if (alloc.company_id) {
      const companyName = companies instanceof Map ? companies.get(alloc.company_id) : companies.find(c => c.id === alloc.company_id)?.name

      if (companyName) {
        return companyName
      }
    }
  }

  return `${allocations.length} splits`
}

/**
 * Resolves the display name for a single allocation item (e.g. for per-split lock menus).
 */
export function getAllocationItemLabel(alloc: Allocation | undefined | null, companies: Company[] | Map<string, string> = []): string {
  if (!alloc) return "Unassigned"
  if (alloc.is_personal) return "Personal"
  if (alloc.company_id) {
    const companyName = companies instanceof Map ? companies.get(alloc.company_id) : companies.find(c => c.id === alloc.company_id)?.name
    if (companyName) return companyName
  }
  return "Business Split"
}

/**
 * Alias returning the allocation text ("Personal", "Company X", or "X splits").
 */
export const getAllocationBadgeInfo = getAllocationLabel

/**
 * Convenience helper returning the company name if the transaction is single-allocated
 * to a recognized company, or null otherwise.
 */
export function getSingleAllocationCompany(
  target: Transaction | Allocation[] | undefined | null,
  companies: Company[] | Map<string, string> = [],
): string | null {
  const allocations: Allocation[] = Array.isArray(target) ? target : (target?.allocations ?? [])
  if (allocations.length === 1) {
    const alloc = allocations[0]
    if (!alloc.is_personal && alloc.company_id) {
      return companies instanceof Map
        ? (companies.get(alloc.company_id) ?? null)
        : (companies.find(c => c.id === alloc.company_id)?.name ?? null)
    }
  }
  return null
}

/**
 * Computes the overall lock status of a transaction ("unlocked", "partially_locked", or "fully_locked").
 */
export function getTransactionLockStatus(target: Transaction | Allocation[] | undefined | null): TransactionLockStatus {
  const allocations: Allocation[] = Array.isArray(target) ? target : (target?.allocations ?? [])
  if (allocations.length === 0) {
    return "unlocked"
  }
  const lockedCount = allocations.filter(a => a.is_locked).length
  if (lockedCount === 0) {
    return "unlocked"
  }
  if (lockedCount === allocations.length) {
    return "fully_locked"
  }
  return "partially_locked"
}

/**
 * Returns true when all allocations on the transaction are locked (and at least one allocation exists).
 */
export function isTransactionFullyLocked(target: Transaction | Allocation[] | undefined | null): boolean {
  return getTransactionLockStatus(target) === "fully_locked"
}

/**
 * Returns true when some, but not all, allocations on the transaction are locked.
 */
export function isTransactionPartiallyLocked(target: Transaction | Allocation[] | undefined | null): boolean {
  return getTransactionLockStatus(target) === "partially_locked"
}

/**
 * Returns true if any allocation on the transaction has is_locked == true.
 */
export function hasLockedAllocations(target: Transaction | Allocation[] | undefined | null): boolean {
  return getTransactionLockStatus(target) !== "unlocked"
}

/**
 * Returns true if the transaction can be deleted (no locked allocations).
 */
export function canDeleteTransaction(target: Transaction | Allocation[] | undefined | null): boolean {
  return !hasLockedAllocations(target)
}

/**
 * Returns badge display metadata for a transaction's lock state.
 */
export function getTransactionLockBadge(target: Transaction | Allocation[] | undefined | null): {
  status: TransactionLockStatus
  label: string
  icon: string
  color: string
} {
  const status = getTransactionLockStatus(target)
  if (status === "fully_locked") {
    return {
      status,
      label: "Locked",
      icon: "lock",
      color: "amber-9",
    }
  }
  if (status === "partially_locked") {
    return {
      status,
      label: "Partially Locked",
      icon: "lock_open",
      color: "orange-7",
    }
  }
  return {
    status,
    label: "Unlocked",
    icon: "lock_open",
    color: "grey-6",
  }
}

/**
 * Resolves font weight CSS class for transaction ledger columns.
 * Returns "text-weight-regular" when locked, and "text-weight-bold" when unlocked.
 */
export function getTextWeightClass(target: Transaction | Allocation[] | undefined | null): string {
  return isTransactionFullyLocked(target) ? "text-weight-regular" : "text-weight-bold"
}

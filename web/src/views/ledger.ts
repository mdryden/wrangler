import type { Allocation, Transaction } from "../types/transaction"
import type { Company } from "../types/company"

/**
 * Formats a numeric amount or string into localized currency format.
 */
export function formatCurrency(amount: string | number, currencyCode = "USD"): string {
  const num = typeof amount === "string" ? parseFloat(amount) : amount
  if (Number.isNaN(num)) return "$0.00"
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currencyCode || "USD",
  }).format(num)
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

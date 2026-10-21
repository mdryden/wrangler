import type { StagedBulkAllocateRequest, StagedTransaction } from "../types/staging"

export type BulkAllocateTargetType = "personal" | "company" | "clear"

export function countOverwrittenTransactions(transactions: StagedTransaction[]): number {
  return transactions.filter(tx => tx.allocations && tx.allocations.length > 0).length
}

export function buildBulkAllocatePayload(
  transactions: StagedTransaction[],
  targetType: BulkAllocateTargetType,
  companyId: string | null = null,
): StagedBulkAllocateRequest {
  const ids = transactions.map(tx => tx.id)
  if (targetType === "clear") {
    return {
      staged_transaction_ids: ids,
      clear: true,
      is_personal: false,
      company_id: null,
    }
  }
  if (targetType === "personal") {
    return {
      staged_transaction_ids: ids,
      clear: false,
      is_personal: true,
      company_id: null,
    }
  }
  return {
    staged_transaction_ids: ids,
    clear: false,
    is_personal: false,
    company_id: companyId,
  }
}

import { defineStore } from "pinia"
import { ref } from "vue"
import { apiClient } from "../api/client"
import type {
  Allocation,
  PaginatedTransactionsResponse,
  Transaction,
  TransactionCreatePayload,
  TransactionQueryParams,
  TransactionUpdatePayload,
} from "../types/transaction"

export const useTransactionStore = defineStore("transactions", () => {
  const transactions = ref<Transaction[]>([])
  const total = ref<number>(0)
  const page = ref<number>(1)
  const pageSize = ref<number>(20)
  const totalPages = ref<number>(0)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)

  function replaceTransactionInList(updated: Transaction): void {
    const idx = transactions.value.findIndex(t => t.id === updated.id)
    if (idx !== -1) {
      transactions.value[idx] = updated
    }
  }

  /**
   * Fetch paginated and filtered transactions from GET /api/transactions.
   */
  async function fetchTransactions(params: TransactionQueryParams = {}): Promise<PaginatedTransactionsResponse> {
    loading.value = true
    error.value = null

    // Clean params to omit empty strings, null, and undefined
    const cleanParams: Record<string, unknown> = {}
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null && val !== "") {
        cleanParams[key] = val
      }
    }

    try {
      const data = await apiClient.get<PaginatedTransactionsResponse>("/api/transactions", {
        params: cleanParams,
      })
      transactions.value = data.items
      total.value = data.total
      page.value = data.page
      pageSize.value = data.page_size
      totalPages.value = data.total_pages
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load transactions"
      error.value = msg
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Create a new transaction (manual entry).
   */
  async function createTransaction(payload: TransactionCreatePayload | FormData): Promise<Transaction> {
    error.value = null
    try {
      const created = await apiClient.post<Transaction>("/api/transactions", payload)
      return created
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to create transaction"
      error.value = msg
      throw err
    }
  }

  /**
   * Unified update for transaction metadata, split allocations, and optional receipt replacement/removal.
   */
  async function updateTransaction(id: string, payload: TransactionUpdatePayload | FormData): Promise<Transaction> {
    error.value = null
    try {
      const updated = await apiClient.put<Transaction>(`/api/transactions/${id}`, payload)
      replaceTransactionInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update transaction"
      error.value = msg
      throw err
    }
  }

  /**
   * Delete a transaction (only permitted when no allocations are locked).
   */
  async function deleteTransaction(id: string): Promise<void> {
    error.value = null
    try {
      await apiClient.delete(`/api/transactions/${id}`)
      const idx = transactions.value.findIndex(t => t.id === id)
      if (idx !== -1) {
        transactions.value.splice(idx, 1)
        if (total.value > 0) {
          total.value -= 1
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to delete transaction"
      error.value = msg
      throw err
    }
  }

  /**
   * Lock or unlock all allocations belonging to a transaction.
   */
  async function lockTransaction(id: string, isLocked: boolean): Promise<Transaction> {
    error.value = null
    try {
      const updated = await apiClient.put<Transaction>(`/api/transactions/${id}/lock`, {
        is_locked: isLocked,
      })
      replaceTransactionInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update transaction lock status"
      error.value = msg
      throw err
    }
  }

  /**
   * Lock or unlock a single allocation.
   */
  async function lockAllocation(id: string, isLocked: boolean): Promise<Allocation> {
    error.value = null
    try {
      const updatedAlloc = await apiClient.put<Allocation>(`/api/allocations/${id}/lock`, {
        is_locked: isLocked,
      })
      for (const tx of transactions.value) {
        const allocIdx = tx.allocations.findIndex(a => a.id === id)
        if (allocIdx !== -1) {
          tx.allocations[allocIdx] = updatedAlloc
          break
        }
      }
      return updatedAlloc
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update allocation lock status"
      error.value = msg
      throw err
    }
  }

  /**
   * Upload or replace a receipt file on a transaction.
   */
  async function uploadReceipt(id: string, file: File): Promise<Transaction> {
    error.value = null
    try {
      const fd = new FormData()
      fd.append("file", file)
      const updated = await apiClient.post<Transaction>(`/api/transactions/${id}/receipt`, fd)
      replaceTransactionInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to upload receipt"
      error.value = msg
      throw err
    }
  }

  /**
   * Remove an attached receipt from a transaction.
   */
  async function deleteReceipt(id: string): Promise<Transaction> {
    error.value = null
    try {
      const updated = await apiClient.delete<Transaction>(`/api/transactions/${id}/receipt`)
      replaceTransactionInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to delete receipt"
      error.value = msg
      throw err
    }
  }

  /**
   * Fetch receipt blob via authenticated API client, create object URL, and open in a new tab.
   */
  async function openReceiptInNewTab(receiptPath: string): Promise<string> {
    error.value = null
    try {
      const cleanPath = receiptPath.replace(/^\/+/, "")
      const endpoint = cleanPath.startsWith("api/receipts/") ? `/${cleanPath}` : `/api/receipts/${cleanPath}`
      const blob = await apiClient.getBlob(endpoint)
      const blobUrl = URL.createObjectURL(blob)
      if (typeof window !== "undefined" && typeof window.open === "function") {
        window.open(blobUrl, "_blank")
      } else if (typeof globalThis.open === "function") {
        globalThis.open(blobUrl, "_blank")
      }
      return blobUrl
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to open receipt"
      error.value = msg
      throw err
    }
  }

  return {
    transactions,
    total,
    page,
    pageSize,
    totalPages,
    loading,
    error,
    fetchTransactions,
    createTransaction,
    updateTransaction,
    deleteTransaction,
    lockTransaction,
    lockAllocation,
    uploadReceipt,
    deleteReceipt,
    openReceiptInNewTab,
  }
})

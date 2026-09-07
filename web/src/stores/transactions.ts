import { defineStore } from "pinia"
import { ref } from "vue"
import { apiClient } from "../api/client"
import type { PaginatedTransactionsResponse, Transaction, TransactionQueryParams } from "../types/transaction"

export const useTransactionStore = defineStore("transactions", () => {
  const transactions = ref<Transaction[]>([])
  const total = ref<number>(0)
  const page = ref<number>(1)
  const pageSize = ref<number>(20)
  const totalPages = ref<number>(0)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)

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

  return {
    transactions,
    total,
    page,
    pageSize,
    totalPages,
    loading,
    error,
    fetchTransactions,
  }
})

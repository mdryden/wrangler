import { defineStore } from "pinia"
import { ref } from "vue"
import { apiClient } from "../api/client"
import type { Company } from "../types/company"
import type {
  ImporterMetadata,
  ImporterRunResponse,
  PaginatedStagedTransactions,
  StagedStatus,
  StagedTransaction,
  StagedTransactionUpdatePayload,
  StagingAcceptResponse,
  StagingQueryParams,
} from "../types/staging"

export const MARK_IMPORTED_CAPABILITY_LABEL = "Automatically marks items as imported in source upon acceptance"
export const PERSONAL_QUICK_ASSIGN_VALUE = "__personal__"

export const SOURCE_FILTER_OPTIONS: { label: string; value: string }[] = [
  { label: "All Sources", value: "" },
  { label: "Manual", value: "manual" },
  { label: "Wrangler CSV", value: "wrangler_csv" },
  { label: "Amazon CSV", value: "amazon_csv" },
  { label: "Receipt Scanner", value: "receipt_parser" },
  { label: "Google Groups", value: "google_groups" },
  { label: "MCP", value: "mcp" },
]

export function formatImporterSummaryToast(result: ImporterRunResponse): string {
  let msg = `Imported ${result.staged_count} new transactions into staging (${result.skipped_duplicates} duplicates skipped)`
  if (result.failed_files && result.failed_files.length > 0) {
    msg += ` (${result.failed_files.length} failed: ${result.failed_files.join(", ")})`
  }
  return msg
}

export function canRunImporter(importer: ImporterMetadata | null, file: File | File[] | null): boolean {
  if (!importer) {
    return false
  }
  if (importer.input_type === "file") {
    if (Array.isArray(file)) {
      return file.length > 0
    }
    return Boolean(file)
  }
  return true
}

export function getAcceptedFileTypesAttr(importer: ImporterMetadata | null): string {
  if (!importer || importer.input_type !== "file" || !importer.accepted_file_types?.length) {
    return ""
  }
  return importer.accepted_file_types.join(",")
}

export function getStagedAllocationSummary(
  row: StagedTransaction,
  companies: Company[] | Map<string, string> = [],
): {
  label: string
  isReady: boolean
  color: string
  textColor: string
} {
  if (!row.allocations || row.allocations.length === 0) {
    return {
      label: "Unallocated",
      isReady: false,
      color: "orange-2",
      textColor: "orange-10",
    }
  }

  if (!row.is_ready) {
    return {
      label: "Unallocated",
      isReady: false,
      color: "orange-2",
      textColor: "orange-10",
    }
  }

  if (row.allocations.length === 1) {
    const alloc = row.allocations[0]
    if (alloc.is_personal) {
      return {
        label: "Personal",
        isReady: true,
        color: "green-1",
        textColor: "positive",
      }
    }
    const companyName = alloc.company_id
      ? companies instanceof Map
        ? companies.get(alloc.company_id)
        : companies.find(c => c.id === alloc.company_id)?.name
      : null
    return {
      label: companyName || "1 splits",
      isReady: true,
      color: "green-1",
      textColor: "positive",
    }
  }

  const names = row.allocations
    .map(alloc => {
      if (alloc.is_personal) return "Personal"
      if (!alloc.company_id) return null
      return companies instanceof Map
        ? (companies.get(alloc.company_id) ?? null)
        : (companies.find(c => c.id === alloc.company_id)?.name ?? null)
    })
    .filter((n): n is string => Boolean(n))

  const uniqueNames = Array.from(new Set(names))
  return {
    label: uniqueNames.length > 0 ? uniqueNames.join(", ") : `${row.allocations.length} splits`,
    isReady: true,
    color: "green-1",
    textColor: "positive",
  }
}

export function getQuickAssignValue(row: StagedTransaction): string | null {
  if (!row.allocations || row.allocations.length !== 1) {
    return null
  }
  const alloc = row.allocations[0]
  if (alloc.is_personal) {
    return PERSONAL_QUICK_ASSIGN_VALUE
  }
  return alloc.company_id ?? null
}

export function buildQuickAssignPayload(row: StagedTransaction, value: string | null): StagedTransactionUpdatePayload {
  if (!value) {
    return { allocations: [] }
  }
  if (value === PERSONAL_QUICK_ASSIGN_VALUE) {
    return {
      allocations: [
        {
          amount: row.total_amount,
          is_personal: true,
          company_id: null,
        },
      ],
    }
  }
  return {
    allocations: [
      {
        amount: row.total_amount,
        is_personal: false,
        company_id: value,
      },
    ],
  }
}

export function getReadyToAcceptTransactions(rows: StagedTransaction[], selectedIds: string[] = []): StagedTransaction[] {
  const readyStaged = rows.filter(r => r.status === "STAGED" && r.is_ready)
  if (selectedIds.length > 0) {
    const selectedSet = new Set(selectedIds)
    return readyStaged.filter(r => selectedSet.has(r.id))
  }
  return readyStaged
}

export const useStagingStore = defineStore("staging", () => {
  const importers = ref<ImporterMetadata[]>([])
  const loadingImporters = ref<boolean>(false)

  const stagedTransactions = ref<StagedTransaction[]>([])
  const total = ref<number>(0)
  const page = ref<number>(1)
  const pageSize = ref<number>(50)
  const totalPages = ref<number>(0)
  const statusFilter = ref<StagedStatus>("STAGED")
  const sourceFilter = ref<string | null>(null)
  const loadingStaging = ref<boolean>(false)
  const error = ref<string | null>(null)

  function replaceStagedInList(updated: StagedTransaction): void {
    const idx = stagedTransactions.value.findIndex(item => item.id === updated.id)
    if (idx !== -1) {
      if (updated.status !== statusFilter.value) {
        stagedTransactions.value.splice(idx, 1)
        if (total.value > 0) {
          total.value -= 1
        }
      } else {
        stagedTransactions.value[idx] = updated
      }
    }
  }

  async function fetchImporters(): Promise<ImporterMetadata[]> {
    loadingImporters.value = true
    error.value = null
    try {
      const data = await apiClient.get<ImporterMetadata[]>("/api/importers")
      importers.value = data
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load importers"
      error.value = msg
      throw err
    } finally {
      loadingImporters.value = false
    }
  }

  async function runImporter(importerId: string, file?: File | File[] | null): Promise<ImporterRunResponse> {
    error.value = null
    try {
      let body: FormData | Record<string, never> = {}
      if (file) {
        const fd = new FormData()
        if (Array.isArray(file)) {
          for (const f of file) {
            fd.append("files", f)
          }
        } else {
          fd.append("files", file)
        }
        body = fd
      }
      const res = await apiClient.post<ImporterRunResponse>(`/api/importers/${importerId}/run`, body)
      return res
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to run importer"
      error.value = msg
      throw err
    }
  }

  async function fetchStagedTransactions(params: StagingQueryParams = {}): Promise<PaginatedStagedTransactions> {
    loadingStaging.value = true
    error.value = null

    const effectiveStatus = params.status ?? statusFilter.value
    const effectiveSource = params.source !== undefined ? params.source : sourceFilter.value
    const effectivePage = params.page ?? page.value
    const effectivePageSize = params.page_size ?? pageSize.value

    statusFilter.value = effectiveStatus
    sourceFilter.value = effectiveSource || null

    const cleanParams: Record<string, string | number> = {
      status: effectiveStatus,
      page: effectivePage,
      page_size: effectivePageSize,
    }
    if (effectiveSource && effectiveSource.trim()) {
      cleanParams.source = effectiveSource.trim()
    }

    try {
      const data = await apiClient.get<PaginatedStagedTransactions>("/api/staging", {
        params: cleanParams,
      })
      stagedTransactions.value = data.items
      total.value = data.total
      page.value = data.page
      pageSize.value = data.page_size
      totalPages.value = data.total_pages
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load staged transactions"
      error.value = msg
      throw err
    } finally {
      loadingStaging.value = false
    }
  }

  async function updateStagedTransaction(
    stagedId: string,
    payload: StagedTransactionUpdatePayload,
    receiptFile?: File | null,
  ): Promise<StagedTransaction> {
    error.value = null
    try {
      let requestBody: StagedTransactionUpdatePayload | FormData = payload
      if (receiptFile) {
        const fd = new FormData()
        if (payload.date !== undefined) {
          fd.append("date", payload.date)
        }
        if (payload.description !== undefined) {
          fd.append("description", payload.description)
        }
        if (payload.total_amount !== undefined) {
          fd.append("total_amount", String(payload.total_amount))
        }
        if (payload.allocations !== undefined) {
          fd.append("allocations", JSON.stringify(payload.allocations))
        }
        if (payload.remove_receipt !== undefined) {
          fd.append("remove_receipt", String(payload.remove_receipt))
        }
        fd.append("file", receiptFile)
        requestBody = fd
      }

      const updated = await apiClient.put<StagedTransaction>(`/api/staging/${stagedId}`, requestBody)
      replaceStagedInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update staged transaction"
      error.value = msg
      throw err
    }
  }

  async function uploadStagedReceipt(stagedId: string, file: File): Promise<StagedTransaction> {
    error.value = null
    try {
      const fd = new FormData()
      fd.append("file", file)
      const updated = await apiClient.post<StagedTransaction>(`/api/staging/${stagedId}/receipt`, fd)
      replaceStagedInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to upload receipt"
      error.value = msg
      throw err
    }
  }

  async function deleteStagedReceipt(stagedId: string): Promise<StagedTransaction> {
    error.value = null
    try {
      const updated = await apiClient.delete<StagedTransaction>(`/api/staging/${stagedId}/receipt`)
      replaceStagedInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to delete receipt"
      error.value = msg
      throw err
    }
  }

  async function dismissStagedTransaction(stagedId: string): Promise<StagedTransaction> {
    error.value = null
    try {
      const updated = await apiClient.post<StagedTransaction>(`/api/staging/${stagedId}/dismiss`)
      replaceStagedInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to dismiss staged transaction"
      error.value = msg
      throw err
    }
  }

  async function restoreStagedTransaction(stagedId: string): Promise<StagedTransaction> {
    error.value = null
    try {
      const updated = await apiClient.post<StagedTransaction>(`/api/staging/${stagedId}/restore`)
      replaceStagedInList(updated)
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to restore staged transaction"
      error.value = msg
      throw err
    }
  }

  async function acceptStagedTransactions(stagedTransactionIds?: string[] | null): Promise<StagingAcceptResponse> {
    error.value = null
    try {
      const payload =
        stagedTransactionIds && stagedTransactionIds.length > 0
          ? { staged_transaction_ids: stagedTransactionIds }
          : { staged_transaction_ids: null }
      const res = await apiClient.post<StagingAcceptResponse>("/api/staging/accept", payload)
      return res
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to accept staged transactions"
      error.value = msg
      throw err
    }
  }

  return {
    importers,
    loadingImporters,
    stagedTransactions,
    total,
    page,
    pageSize,
    totalPages,
    statusFilter,
    sourceFilter,
    loadingStaging,
    error,
    fetchImporters,
    runImporter,
    fetchStagedTransactions,
    updateStagedTransaction,
    uploadStagedReceipt,
    deleteStagedReceipt,
    dismissStagedTransaction,
    restoreStagedTransaction,
    acceptStagedTransactions,
  }
})

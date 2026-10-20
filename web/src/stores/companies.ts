import { defineStore } from "pinia"
import { ref } from "vue"
import { apiClient } from "../api/client"
import type { Company, CompanyCreatePayload, CompanyExportOptions, CompanyUpdatePayload } from "../types/company"
import type { Allocation } from "../types/transaction"
import type { WaveBusiness, WaveBusinessAccountsResponse, WaveCategory, WaveConnectPayload, WaveSyncResponse } from "../types/wave"

export function extractFilenameFromContentDisposition(header: string | null | undefined, fallbackFilename: string): string {
  if (!header) return fallbackFilename
  const match = /filename\*?=(?:UTF-8''|")?([^";\r\n]+)"?/i.exec(header)
  if (match && match[1]) {
    return match[1].trim()
  }
  return fallbackFilename
}

export function triggerBrowserDownload(blob: Blob, filename: string): void {
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
    return
  }
  const blobUrl = URL.createObjectURL(blob)
  try {
    if (typeof document !== "undefined" && typeof document.createElement === "function") {
      const link = document.createElement("a")
      link.href = blobUrl
      link.download = filename
      if (document.body && typeof document.body.appendChild === "function") {
        document.body.appendChild(link)
      }
      if (typeof link.click === "function") {
        link.click()
      }
      if (link.parentNode && typeof link.parentNode.removeChild === "function") {
        link.parentNode.removeChild(link)
      }
    }
  } finally {
    if (typeof URL.revokeObjectURL === "function") {
      URL.revokeObjectURL(blobUrl)
    }
  }
}

export const useCompanyStore = defineStore("companies", () => {
  const companies = ref<Company[]>([])
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)

  /**
   * Fetch all companies from the backend.
   */
  async function fetchCompanies(): Promise<Company[]> {
    loading.value = true
    error.value = null
    try {
      const data = await apiClient.get<Company[]>("/api/companies")
      companies.value = data
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load companies"
      error.value = msg
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Create a new company record.
   */
  async function createCompany(payload: CompanyCreatePayload): Promise<Company> {
    error.value = null
    try {
      const created = await apiClient.post<Company>("/api/companies", payload)
      companies.value.push(created)
      // Keep sorted by name
      companies.value.sort((a, b) => a.name.localeCompare(b.name))
      return created
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to create company"
      error.value = msg
      throw err
    }
  }

  /**
   * Update an existing company record.
   */
  async function updateCompany(id: string, payload: CompanyUpdatePayload): Promise<Company> {
    error.value = null
    try {
      const updated = await apiClient.put<Company>(`/api/companies/${id}`, payload)
      const index = companies.value.findIndex(c => c.id === id)
      if (index !== -1) {
        companies.value[index] = updated
        companies.value.sort((a, b) => a.name.localeCompare(b.name))
      }
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update company"
      error.value = msg
      throw err
    }
  }

  /**
   * Delete a company record.
   */
  async function deleteCompany(id: string): Promise<void> {
    error.value = null
    try {
      await apiClient.delete(`/api/companies/${id}`)
      companies.value = companies.value.filter(c => c.id !== id)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to delete company"
      error.value = msg
      throw err
    }
  }

  /**
   * Export business allocations for a company as a Wave-compatible CSV file,
   * trigger a browser file download, and refresh company summary counts.
   */
  async function exportTransactionsCsv(companyId: string, options: CompanyExportOptions = {}): Promise<Blob> {
    error.value = null
    const cleanParams: Record<string, unknown> = {}
    if (options.include_locked !== undefined && options.include_locked !== null) {
      cleanParams.include_locked = options.include_locked
    }
    if (options.start_date !== undefined && options.start_date !== null && options.start_date !== "") {
      cleanParams.start_date = options.start_date
    }
    if (options.end_date !== undefined && options.end_date !== null && options.end_date !== "") {
      cleanParams.end_date = options.end_date
    }

    try {
      const response = await apiClient.get<Response>(`/api/companies/${companyId}/export-transactions`, {
        params: cleanParams,
        responseType: "raw",
      })

      let blob: Blob
      if (response && typeof response.blob === "function") {
        blob = await response.blob()
      } else if (response && typeof response.text === "function") {
        const text = await response.text()
        blob = new Blob([text], { type: "text/csv;charset=utf-8;" })
      } else if (typeof Blob !== "undefined" && response instanceof Blob) {
        blob = response
      } else {
        blob = new Blob([String(response ?? "")], { type: "text/csv;charset=utf-8;" })
      }

      const company = companies.value.find(c => c.id === companyId)
      const safeName = company
        ? company.name
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9-_]/g, "_")
        : companyId
      const fallbackFilename = `${safeName}_transactions.csv`
      const contentDisposition = response?.headers?.get?.("content-disposition") ?? null
      const filename = extractFilenameFromContentDisposition(contentDisposition, fallbackFilename)

      triggerBrowserDownload(blob, filename)

      try {
        await fetchCompanies()
      } catch {
        error.value = null
      }

      return blob
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to export company transactions"
      error.value = msg
      throw err
    }
  }

  /**
   * Lock business allocations for a company (optionally filtered by allocation_ids).
   */
  async function lockCompanyAllocations(companyId: string, allocationIds?: string[]): Promise<Allocation[]> {
    error.value = null
    try {
      const body = allocationIds !== undefined ? { allocation_ids: allocationIds } : undefined
      const locked = await apiClient.post<Allocation[]>(`/api/companies/${companyId}/lock-allocations`, body)
      return locked
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to lock company allocations"
      error.value = msg
      throw err
    }
  }

  /**
   * Unlock business allocations for a company (optionally filtered by allocation_ids).
   */
  async function unlockCompanyAllocations(companyId: string, allocationIds?: string[]): Promise<Allocation[]> {
    error.value = null
    try {
      const body = allocationIds !== undefined ? { allocation_ids: allocationIds } : undefined
      const unlocked = await apiClient.post<Allocation[]>(`/api/companies/${companyId}/unlock-allocations`, body)
      return unlocked
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to unlock company allocations"
      error.value = msg
      throw err
    }
  }

  /**
   * Verify Full Access Token against Wave and return accessible businesses.
   */
  async function testWaveToken(token: string): Promise<WaveBusiness[]> {
    error.value = null
    try {
      const data = await apiClient.post<WaveBusiness[]>("/api/companies/wave/test-token", { token })
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to test Wave token"
      error.value = msg
      throw err
    }
  }

  /**
   * Fetch Chart of Accounts candidate anchors and expense categories for a Wave business.
   */
  async function fetchBusinessAccounts(token: string, businessId: string): Promise<WaveBusinessAccountsResponse> {
    error.value = null
    try {
      const data = await apiClient.post<WaveBusinessAccountsResponse>("/api/companies/wave/business-accounts", {
        token,
        business_id: businessId,
      })
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to fetch Wave business accounts"
      error.value = msg
      throw err
    }
  }

  /**
   * Connect a company to Wave with credentials and anchor account.
   */
  async function connectWave(companyId: string, payload: WaveConnectPayload): Promise<Company> {
    error.value = null
    try {
      const updated = await apiClient.post<Company>(`/api/companies/${companyId}/wave/connect`, payload)
      const index = companies.value.findIndex(c => c.id === companyId)
      if (index !== -1) {
        companies.value[index] = updated
      }
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to connect Wave"
      error.value = msg
      throw err
    }
  }

  /**
   * Disconnect Wave credentials from a company.
   */
  async function disconnectWave(companyId: string): Promise<Company> {
    error.value = null
    try {
      const updated = await apiClient.delete<Company>(`/api/companies/${companyId}/wave`)
      const index = companies.value.findIndex(c => c.id === companyId)
      if (index !== -1) {
        companies.value[index] = updated
      }
      return updated
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to disconnect Wave"
      error.value = msg
      throw err
    }
  }

  /**
   * Fetch cached Wave expense categories for a company.
   */
  async function fetchWaveCategories(companyId: string): Promise<WaveCategory[]> {
    error.value = null
    try {
      const data = await apiClient.get<WaveCategory[]>(`/api/companies/${companyId}/wave/categories`)
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to fetch Wave categories"
      error.value = msg
      throw err
    }
  }

  /**
   * Refresh and sync cached Wave expense categories from Wave.
   */
  async function syncWaveCategories(companyId: string): Promise<WaveCategory[]> {
    error.value = null
    try {
      const data = await apiClient.post<WaveCategory[]>(`/api/companies/${companyId}/wave/sync-categories`)
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to sync Wave categories"
      error.value = msg
      throw err
    }
  }

  /**
   * Direct batch synchronize categorized allocations to Wave.
   */
  async function syncCompanyToWave(companyId: string, allocationIds?: string[]): Promise<WaveSyncResponse> {
    error.value = null
    try {
      const body = allocationIds !== undefined ? { allocation_ids: allocationIds } : undefined
      const data = await apiClient.post<WaveSyncResponse>(`/api/companies/${companyId}/sync-wave`, body)
      return data
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to sync to Wave"
      error.value = msg
      throw err
    }
  }

  return {
    companies,
    loading,
    error,
    fetchCompanies,
    createCompany,
    updateCompany,
    deleteCompany,
    exportTransactionsCsv,
    lockCompanyAllocations,
    unlockCompanyAllocations,
    testWaveToken,
    fetchBusinessAccounts,
    connectWave,
    disconnectWave,
    fetchWaveCategories,
    syncWaveCategories,
    syncCompanyToWave,
  }
})

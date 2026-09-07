import { defineStore } from "pinia"
import { ref } from "vue"
import { apiClient } from "../api/client"
import type { Company, CompanyCreatePayload, CompanyUpdatePayload, WaveAuthorizeResponse, WaveCategory } from "../types/company"

export const useCompanyStore = defineStore("companies", () => {
  const companies = ref<Company[]>([])
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const syncingCategories = ref<Record<string, boolean>>({})
  const connectingOAuth = ref<Record<string, boolean>>({})

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
   * Fetch the Wave OAuth authorization URL for a specific company.
   */
  async function getWaveAuthorizeUrl(companyId: string): Promise<WaveAuthorizeResponse> {
    return await apiClient.get<WaveAuthorizeResponse>(`/api/wave/oauth/authorize?company_id=${encodeURIComponent(companyId)}`)
  }

  /**
   * Initiate Wave OAuth authorization by fetching authorization URL and redirecting the browser.
   */
  async function connectToWave(companyId: string): Promise<string> {
    connectingOAuth.value[companyId] = true
    try {
      const response = await getWaveAuthorizeUrl(companyId)
      const targetUrl = response.authorization_url || response.redirect_url
      if (targetUrl && typeof window !== "undefined") {
        window.location.href = targetUrl
      }
      return targetUrl
    } finally {
      connectingOAuth.value[companyId] = false
    }
  }

  /**
   * Trigger synchronization of Wave categories (Chart of Accounts) for a company.
   */
  async function syncCategories(companyId: string): Promise<WaveCategory[]> {
    syncingCategories.value[companyId] = true
    try {
      const result = await apiClient.post<WaveCategory[]>(`/api/companies/${companyId}/sync-categories`)
      return result
    } finally {
      syncingCategories.value[companyId] = false
    }
  }

  /**
   * Retrieve cached categories for a company.
   */
  async function fetchCategories(companyId: string): Promise<WaveCategory[]> {
    return await apiClient.get<WaveCategory[]>(`/api/companies/${companyId}/categories`)
  }

  return {
    companies,
    loading,
    error,
    syncingCategories,
    connectingOAuth,
    fetchCompanies,
    createCompany,
    updateCompany,
    deleteCompany,
    getWaveAuthorizeUrl,
    connectToWave,
    syncCategories,
    fetchCategories,
  }
})

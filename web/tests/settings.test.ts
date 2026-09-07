import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useCompanyStore } from "../src/stores/companies"
import { getCompanyTokenStatus, getTokenStatusInfo, type Company } from "../src/types/company"

const mockStorage = new Map<string, string>()
const mockLocalStorage = {
  getItem: (key: string): string | null => mockStorage.get(key) || null,
  setItem: (key: string, val: string): void => {
    mockStorage.set(key, String(val))
  },
  removeItem: (key: string): void => {
    mockStorage.delete(key)
  },
  clear: (): void => mockStorage.clear(),
  length: 0,
  key: () => null,
}

Object.defineProperty(globalThis, "localStorage", {
  value: mockLocalStorage,
  writable: true,
})

describe("Settings & Company Management View Integration", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  it("handles the complete company lifecycle (create, list, update, delete)", async () => {
    const store = useCompanyStore()

    // 1. Initially empty
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => [],
    })
    await store.fetchCompanies()
    expect(store.companies).toEqual([])

    // 2. Create Company
    const createdCompany: Company = {
      id: "comp-uuid-1",
      name: "Family Holdings LLC",
      wave_equity_account_id: "wave-eq-12345",
      wave_business_id: "biz-wave-99",
      wave_access_token: null,
      wave_refresh_token: null,
      wave_token_expires_at: null,
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => createdCompany,
    })

    const newComp = await store.createCompany({
      name: "Family Holdings LLC",
      wave_equity_account_id: "wave-eq-12345",
      wave_business_id: "biz-wave-99",
    })

    expect(newComp.id).toBe("comp-uuid-1")
    expect(store.companies).toContainEqual(createdCompany)
    expect(getCompanyTokenStatus(newComp)).toBe("disconnected")

    // 3. Update Company
    const updatedCompany: Company = {
      ...createdCompany,
      name: "Family Holdings International LLC",
      wave_equity_account_id: "wave-eq-99999",
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updatedCompany,
    })

    const updated = await store.updateCompany(createdCompany.id, {
      name: "Family Holdings International LLC",
      wave_equity_account_id: "wave-eq-99999",
    })

    expect(updated.name).toBe("Family Holdings International LLC")
    expect(store.companies.find(c => c.id === "comp-uuid-1")?.wave_equity_account_id).toBe("wave-eq-99999")

    // 4. Delete Company
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: new Headers(),
    })

    await store.deleteCompany(createdCompany.id)
    expect(store.companies.find(c => c.id === "comp-uuid-1")).toBeUndefined()
  })

  it("initiates OAuth connection and handles token status changes", async () => {
    const store = useCompanyStore()
    const targetUrl = "https://api.waveapps.com/oauth2/authorize?client_id=client_1&state=jwt_token"

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ authorization_url: targetUrl, redirect_url: targetUrl }),
    })

    const authResp = await store.getWaveAuthorizeUrl("comp-1")
    expect(authResp.authorization_url).toBe(targetUrl)

    // Token status before connection
    const companyBeforeOAuth: Company = {
      id: "comp-1",
      name: "Test Corp",
      wave_equity_account_id: "eq-1",
      wave_access_token: null,
    }
    expect(getCompanyTokenStatus(companyBeforeOAuth)).toBe("disconnected")
    expect(getTokenStatusInfo("disconnected").label).toBe("Disconnected")

    // Token status after OAuth connection (active)
    const companyConnected: Company = {
      ...companyBeforeOAuth,
      wave_access_token: "wave-access-token-123",
      wave_token_expires_at: new Date(Date.now() + 86400000).toISOString(),
    }
    expect(getCompanyTokenStatus(companyConnected)).toBe("connected")
    expect(getTokenStatusInfo("connected").label).toBe("Connected")

    // Token status after expiration
    const companyExpired: Company = {
      ...companyConnected,
      wave_token_expires_at: new Date(Date.now() - 10000).toISOString(),
    }
    expect(getCompanyTokenStatus(companyExpired)).toBe("expired")
    expect(getTokenStatusInfo("expired").label).toBe("Expired")
  })

  it("syncs Chart of Accounts categories and handles errors", async () => {
    const store = useCompanyStore()
    const mockCategories = [
      { id: "cat-1", company_id: "comp-1", wave_account_id: "acc-101", name: "Advertising & Promotion" },
      { id: "cat-2", company_id: "comp-1", wave_account_id: "acc-102", name: "Computer Hardware" },
      { id: "cat-3", company_id: "comp-1", wave_account_id: "acc-103", name: "Professional Services" },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockCategories,
    })

    const categories = await store.syncCategories("comp-1")
    expect(categories).toHaveLength(3)
    expect(categories[0].name).toBe("Advertising & Promotion")
    expect(store.syncingCategories["comp-1"]).toBe(false)

    // Error scenario: Wave not connected or token expired
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Company is not connected to Wave" }),
    })

    await expect(store.syncCategories("comp-2")).rejects.toThrow("Company is not connected to Wave")
    expect(store.syncingCategories["comp-2"]).toBe(false)
  })
})

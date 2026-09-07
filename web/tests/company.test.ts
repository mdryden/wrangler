import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useCompanyStore } from "../src/stores/companies"
import { getCompanyTokenStatus, getTokenStatusInfo, type Company } from "../src/types/company"

// In-memory mock storage
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

describe("getCompanyTokenStatus", () => {
  it("returns 'disconnected' when company has no wave_access_token", () => {
    const comp: Company = {
      id: "1",
      name: "Acme Inc",
      wave_equity_account_id: "eq_123",
      wave_access_token: null,
    }
    expect(getCompanyTokenStatus(comp)).toBe("disconnected")
    expect(getCompanyTokenStatus(null)).toBe("disconnected")
    expect(getCompanyTokenStatus(undefined)).toBe("disconnected")
  })

  it("returns 'connected' when company has wave_access_token and no expiration", () => {
    const comp: Company = {
      id: "1",
      name: "Acme Inc",
      wave_equity_account_id: "eq_123",
      wave_access_token: "token_abc",
      wave_token_expires_at: null,
    }
    expect(getCompanyTokenStatus(comp)).toBe("connected")
  })

  it("returns 'connected' when company has wave_access_token and future expiration", () => {
    const futureDate = new Date(Date.now() + 3600 * 1000).toISOString()
    const comp: Company = {
      id: "1",
      name: "Acme Inc",
      wave_equity_account_id: "eq_123",
      wave_access_token: "token_abc",
      wave_token_expires_at: futureDate,
    }
    expect(getCompanyTokenStatus(comp)).toBe("connected")
  })

  it("returns 'expired' when company has wave_access_token and past expiration", () => {
    const pastDate = new Date(Date.now() - 3600 * 1000).toISOString()
    const comp: Company = {
      id: "1",
      name: "Acme Inc",
      wave_equity_account_id: "eq_123",
      wave_access_token: "token_abc",
      wave_token_expires_at: pastDate,
    }
    expect(getCompanyTokenStatus(comp)).toBe("expired")
  })
})

describe("getTokenStatusInfo", () => {
  it("returns correct labels and colors for statuses", () => {
    const connected = getTokenStatusInfo("connected")
    expect(connected.label).toBe("Connected")
    expect(connected.color).toBe("positive")
    expect(connected.icon).toBe("check_circle")

    const expired = getTokenStatusInfo("expired")
    expect(expired.label).toBe("Expired")
    expect(expired.color).toBe("warning")
    expect(expired.icon).toBe("warning")

    const disconnected = getTokenStatusInfo("disconnected")
    expect(disconnected.label).toBe("Disconnected")
    expect(disconnected.color).toBe("grey-6")
    expect(disconnected.icon).toBe("cloud_off")
  })
})

describe("useCompanyStore", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  it("initializes with empty companies array and default flags", () => {
    const store = useCompanyStore()
    expect(store.companies).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it("fetchCompanies successfully fetches and sets sorted companies", async () => {
    const mockCompanies: Company[] = [
      { id: "2", name: "Zebra LLC", wave_equity_account_id: "eq_2" },
      { id: "1", name: "Alpha Corp", wave_equity_account_id: "eq_1" },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockCompanies,
    })

    const store = useCompanyStore()
    const result = await store.fetchCompanies()

    expect(mockFetch).toHaveBeenCalledWith("/api/companies", expect.anything())
    expect(result).toEqual(mockCompanies)
    expect(store.companies).toEqual(mockCompanies)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it("fetchCompanies records error message on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Database locked" }),
    })

    const store = useCompanyStore()
    await expect(store.fetchCompanies()).rejects.toThrow("Database locked")
    expect(store.loading).toBe(false)
    expect(store.error).toBe("Database locked")
  })

  it("createCompany sends POST request and adds to store sorted", async () => {
    const existing: Company = { id: "1", name: "Beta LLC", wave_equity_account_id: "eq_1" }
    const newCompany: Company = { id: "2", name: "Alpha Inc", wave_equity_account_id: "eq_2" }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => newCompany,
    })

    const store = useCompanyStore()
    store.companies = [existing]

    const result = await store.createCompany({
      name: "Alpha Inc",
      wave_equity_account_id: "eq_2",
    })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "Alpha Inc", wave_equity_account_id: "eq_2" }),
      }),
    )
    expect(result).toEqual(newCompany)
    expect(store.companies).toHaveLength(2)
    // Alpha Inc should sort before Beta LLC
    expect(store.companies[0].name).toBe("Alpha Inc")
    expect(store.companies[1].name).toBe("Beta LLC")
  })

  it("updateCompany sends PUT request and updates item in store", async () => {
    const existing1: Company = { id: "1", name: "Alpha Inc", wave_equity_account_id: "eq_1" }
    const existing2: Company = { id: "2", name: "Beta LLC", wave_equity_account_id: "eq_2" }

    const updated1: Company = {
      id: "1",
      name: "Alpha Updated Corp",
      wave_equity_account_id: "eq_new",
      wave_business_id: "biz_123",
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updated1,
    })

    const store = useCompanyStore()
    store.companies = [existing1, existing2]

    const result = await store.updateCompany("1", {
      name: "Alpha Updated Corp",
      wave_equity_account_id: "eq_new",
      wave_business_id: "biz_123",
    })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/1",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          name: "Alpha Updated Corp",
          wave_equity_account_id: "eq_new",
          wave_business_id: "biz_123",
        }),
      }),
    )
    expect(result).toEqual(updated1)
    expect(store.companies.find(c => c.id === "1")?.name).toBe("Alpha Updated Corp")
  })

  it("deleteCompany sends DELETE request and removes company from store", async () => {
    const existing1: Company = { id: "1", name: "Alpha Inc", wave_equity_account_id: "eq_1" }
    const existing2: Company = { id: "2", name: "Beta LLC", wave_equity_account_id: "eq_2" }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: new Headers(),
    })

    const store = useCompanyStore()
    store.companies = [existing1, existing2]

    await store.deleteCompany("1")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/1",
      expect.objectContaining({
        method: "DELETE",
      }),
    )
    expect(store.companies).toHaveLength(1)
    expect(store.companies[0].id).toBe("2")
  })

  it("getWaveAuthorizeUrl calls the backend authorize endpoint", async () => {
    const authUrl = "https://api.waveapps.com/oauth2/authorize?client_id=123"
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ authorization_url: authUrl, redirect_url: authUrl }),
    })

    const store = useCompanyStore()
    const res = await store.getWaveAuthorizeUrl("comp-1")

    expect(mockFetch).toHaveBeenCalledWith("/api/wave/oauth/authorize?company_id=comp-1", expect.anything())
    expect(res.authorization_url).toBe(authUrl)
  })

  it("connectToWave invokes authorize endpoint and returns the URL", async () => {
    const authUrl = "https://api.waveapps.com/oauth2/authorize?client_id=abc"
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ authorization_url: authUrl, redirect_url: authUrl }),
    })

    const store = useCompanyStore()
    const url = await store.connectToWave("comp-2")

    expect(url).toBe(authUrl)
    expect(store.connectingOAuth["comp-2"]).toBe(false)
  })

  it("syncCategories calls POST sync-categories endpoint and manages loading state", async () => {
    const mockCategories = [
      { id: "c1", company_id: "comp-1", wave_account_id: "acc_1", name: "Meals & Entertainment" },
      { id: "c2", company_id: "comp-1", wave_account_id: "acc_2", name: "Office Supplies" },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockCategories,
    })

    const store = useCompanyStore()
    const result = await store.syncCategories("comp-1")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/comp-1/sync-categories",
      expect.objectContaining({
        method: "POST",
      }),
    )
    expect(result).toEqual(mockCategories)
    expect(store.syncingCategories["comp-1"]).toBe(false)
  })

  it("fetchCategories calls GET categories endpoint", async () => {
    const mockCategories = [{ id: "c1", company_id: "comp-1", wave_account_id: "acc_1", name: "Travel" }]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockCategories,
    })

    const store = useCompanyStore()
    const result = await store.fetchCategories("comp-1")

    expect(mockFetch).toHaveBeenCalledWith("/api/companies/comp-1/categories", expect.anything())
    expect(result).toEqual(mockCategories)
  })
})

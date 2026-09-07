import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useCompanyStore } from "../src/stores/companies"
import type { Company } from "../src/types/company"

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

  it("fetchCompanies successfully fetches and sets sorted companies with transaction counts", async () => {
    const mockCompanies: Company[] = [
      { id: "2", name: "Zebra LLC", transaction_count: 5 },
      { id: "1", name: "Alpha Corp", transaction_count: 12 },
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
    const existing: Company = { id: "1", name: "Beta LLC", transaction_count: 0 }
    const newCompany: Company = { id: "2", name: "Alpha Inc", transaction_count: 0 }

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
    })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "Alpha Inc" }),
      }),
    )
    expect(result).toEqual(newCompany)
    expect(store.companies).toHaveLength(2)
    // Alpha Inc should sort before Beta LLC
    expect(store.companies[0].name).toBe("Alpha Inc")
    expect(store.companies[1].name).toBe("Beta LLC")
  })

  it("updateCompany sends PUT request and updates item in store", async () => {
    const existing1: Company = { id: "1", name: "Alpha Inc", transaction_count: 3 }
    const existing2: Company = { id: "2", name: "Beta LLC", transaction_count: 7 }

    const updated1: Company = {
      id: "1",
      name: "Alpha Updated Corp",
      transaction_count: 3,
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
    })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/1",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          name: "Alpha Updated Corp",
        }),
      }),
    )
    expect(result).toEqual(updated1)
    expect(store.companies.find(c => c.id === "1")?.name).toBe("Alpha Updated Corp")
  })

  it("deleteCompany sends DELETE request and removes company from store", async () => {
    const existing1: Company = { id: "1", name: "Alpha Inc" }
    const existing2: Company = { id: "2", name: "Beta LLC" }

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
})

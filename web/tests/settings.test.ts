import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useCompanyStore } from "../src/stores/companies"
import type { Company } from "../src/types/company"

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
      transaction_count: 0,
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => createdCompany,
    })

    const newComp = await store.createCompany({
      name: "Family Holdings LLC",
    })

    expect(newComp.id).toBe("comp-uuid-1")
    expect(store.companies).toContainEqual(createdCompany)

    // 3. Update Company
    const updatedCompany: Company = {
      ...createdCompany,
      name: "Family Holdings International LLC",
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updatedCompany,
    })

    const updated = await store.updateCompany(createdCompany.id, {
      name: "Family Holdings International LLC",
    })

    expect(updated.name).toBe("Family Holdings International LLC")
    expect(store.companies.find(c => c.id === "comp-uuid-1")?.name).toBe("Family Holdings International LLC")

    // 4. Delete Company
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: new Headers(),
    })

    await store.deleteCompany(createdCompany.id)
    expect(store.companies.find(c => c.id === "comp-uuid-1")).toBeUndefined()
  })

  it("loads companies with transaction counts for display", async () => {
    const store = useCompanyStore()
    const mockCompanies: Company[] = [
      { id: "c1", name: "Alpha Consulting", transaction_count: 8 },
      { id: "c2", name: "Beta Properties", transaction_count: 0 },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockCompanies,
    })

    await store.fetchCompanies()
    expect(store.companies).toHaveLength(2)
    expect(store.companies[0].transaction_count).toBe(8)
    expect(store.companies[1].transaction_count).toBe(0)
  })
})

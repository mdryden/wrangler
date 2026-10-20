import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useCompanyStore } from "../src/stores/companies"
import { useTransactionStore } from "../src/stores/transactions"
import type { Company } from "../src/types/company"
import type { WaveBusiness, WaveBusinessAccountsResponse, WaveCategory, WaveSyncResponse } from "../src/types/wave"
import type { Transaction } from "../src/types/transaction"

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

describe("Wave Store Integration", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  it("testWaveToken sends POST /api/companies/wave/test-token and returns business list", async () => {
    const mockBusinesses: WaveBusiness[] = [
      { id: "biz_1", name: "Alpha Biz", is_personal: false },
      { id: "biz_2", name: "Personal Books", is_personal: true },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockBusinesses,
    })

    const store = useCompanyStore()
    const result = await store.testWaveToken("valid-token")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/wave/test-token",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ token: "valid-token" }),
      }),
    )
    expect(result).toEqual(mockBusinesses)
  })

  it("fetchBusinessAccounts sends POST /api/companies/wave/business-accounts and returns accounts", async () => {
    const mockAccounts: WaveBusinessAccountsResponse = {
      anchor_accounts: [{ id: "a1", name: "Owner's Equity", type: "EQUITY", subtype: "OWNERS_EQUITY" }],
      expense_categories: [{ id: "c1", name: "Office Supplies", type: "EXPENSE", subtype: null, is_uncategorized: false }],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockAccounts,
    })

    const store = useCompanyStore()
    const result = await store.fetchBusinessAccounts("valid-token", "biz_1")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/wave/business-accounts",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ token: "valid-token", business_id: "biz_1" }),
      }),
    )
    expect(result).toEqual(mockAccounts)
  })

  it("connectWave updates target company in store with is_wave_connected: true", async () => {
    const store = useCompanyStore()
    store.companies = [
      { id: "comp_1", name: "Acme Corp", is_wave_connected: false },
      { id: "comp_2", name: "Beta LLC", is_wave_connected: false },
    ]

    const updatedCompany: Company = {
      id: "comp_1",
      name: "Acme Corp",
      wave_business_id: "biz_1",
      wave_business_name: "Acme Wave",
      wave_equity_account_id: "a1",
      is_wave_connected: true,
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updatedCompany,
    })

    const payload = {
      token: "tok_123",
      business_id: "biz_1",
      business_name: "Acme Wave",
      equity_account_id: "a1",
    }
    const result = await store.connectWave("comp_1", payload)

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/comp_1/wave/connect",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      }),
    )
    expect(result.is_wave_connected).toBe(true)
    expect(store.companies.find(c => c.id === "comp_1")?.is_wave_connected).toBe(true)
  })

  it("disconnectWave clears credentials and resets is_wave_connected to false", async () => {
    const store = useCompanyStore()
    store.companies = [
      {
        id: "comp_1",
        name: "Acme Corp",
        wave_business_id: "biz_1",
        wave_equity_account_id: "a1",
        is_wave_connected: true,
      },
    ]

    const disconnectedCompany: Company = {
      id: "comp_1",
      name: "Acme Corp",
      wave_business_id: null,
      wave_equity_account_id: null,
      is_wave_connected: false,
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => disconnectedCompany,
    })

    const result = await store.disconnectWave("comp_1")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/comp_1/wave",
      expect.objectContaining({
        method: "DELETE",
      }),
    )
    expect(result.is_wave_connected).toBe(false)
    expect(store.companies.find(c => c.id === "comp_1")?.is_wave_connected).toBe(false)
  })

  it("fetchWaveCategories and syncWaveCategories fetch and refresh cached categories", async () => {
    const store = useCompanyStore()
    const mockCategories: WaveCategory[] = [
      {
        id: "cat_1",
        company_id: "comp_1",
        wave_account_id: "wa_1",
        name: "Advertising",
        account_type: "EXPENSE",
        is_uncategorized: false,
      },
      {
        id: "cat_2",
        company_id: "comp_1",
        wave_account_id: "wa_2",
        name: "Uncategorized Expense",
        account_type: "EXPENSE",
        is_uncategorized: true,
      },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockCategories,
    })

    const fetched = await store.fetchWaveCategories("comp_1")
    expect(mockFetch).toHaveBeenCalledWith("/api/companies/comp_1/wave/categories", expect.anything())
    expect(fetched).toEqual(mockCategories)

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockCategories,
    })

    const synced = await store.syncWaveCategories("comp_1")
    expect(mockFetch).toHaveBeenCalledWith("/api/companies/comp_1/wave/sync-categories", expect.anything())
    expect(synced).toEqual(mockCategories)
  })

  it("syncCompanyToWave dispatches sync request and returns WaveSyncResponse", async () => {
    const store = useCompanyStore()
    const mockSyncResponse: WaveSyncResponse = {
      total_processed: 3,
      synced_count: 3,
      failed_count: 0,
      errors: [],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockSyncResponse,
    })

    const result = await store.syncCompanyToWave("comp_1", ["alloc_1", "alloc_2", "alloc_3"])

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/comp_1/sync-wave",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ allocation_ids: ["alloc_1", "alloc_2", "alloc_3"] }),
      }),
    )
    expect(result).toEqual(mockSyncResponse)
  })

  it("updateAllocationCategory updates allocation category and locally syncs transaction store state", async () => {
    const txStore = useTransactionStore()
    const initialTx: Transaction = {
      id: "tx_1",
      source: "MANUAL",
      external_id: null,
      date: "2026-10-20",
      description: "Supplies",
      total_amount: "75.00",
      receipt_file_path: null,
      allocations: [
        {
          id: "alloc_1",
          transaction_id: "tx_1",
          amount: "75.00",
          is_personal: false,
          company_id: "comp_1",
          is_locked: false,
          wave_category_id: null,
          wave_transaction_id: null,
        },
      ],
    }
    txStore.transactions = [initialTx]

    const updatedAlloc = {
      ...initialTx.allocations[0],
      wave_category_id: "cat_999",
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updatedAlloc,
    })

    const result = await txStore.updateAllocationCategory("alloc_1", "cat_999")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/allocations/alloc_1/category",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ wave_category_id: "cat_999" }),
      }),
    )
    expect(result.wave_category_id).toBe("cat_999")
    expect(txStore.transactions[0].allocations[0].wave_category_id).toBe("cat_999")
  })
})

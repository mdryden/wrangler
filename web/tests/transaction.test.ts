import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import { useTransactionStore } from "../src/stores/transactions"
import type { PaginatedTransactionsResponse, Transaction } from "../src/types/transaction"

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

describe("useTransactionStore & Ledger Integration", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  const sampleTransactions: Transaction[] = [
    {
      id: "tx-1",
      source: "manual",
      external_id: "EXT-001",
      date: "2026-09-01",
      description: "Office Supplies",
      total_amount: "45.99",
      currency_code: "USD",
      receipt_file_path: "receipts/tx-1.pdf",
      is_approved: true,
      allocations: [
        {
          id: "alloc-1",
          transaction_id: "tx-1",
          amount: "45.99",
          is_personal: false,
          company_id: "comp-1",
          sync_status: "PENDING",
        },
      ],
    },
    {
      id: "tx-2",
      source: "amazon",
      external_id: "AMZ-999",
      date: "2026-09-03",
      description: "Cloud Hosting",
      total_amount: "120.00",
      currency_code: "USD",
      receipt_file_path: null,
      is_approved: false,
      allocations: [],
    },
  ]

  const samplePaginatedResponse: PaginatedTransactionsResponse = {
    items: sampleTransactions,
    total: 2,
    page: 1,
    page_size: 20,
    total_pages: 1,
  }

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  it("initializes with default empty state", () => {
    const store = useTransactionStore()
    expect(store.transactions).toEqual([])
    expect(store.total).toBe(0)
    expect(store.page).toBe(1)
    expect(store.pageSize).toBe(20)
    expect(store.totalPages).toBe(0)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it("fetches transactions and updates state on success", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => samplePaginatedResponse,
    })

    const store = useTransactionStore()
    const result = await store.fetchTransactions()

    expect(mockFetch).toHaveBeenCalledWith("/api/transactions", expect.anything())
    expect(result).toEqual(samplePaginatedResponse)
    expect(store.transactions).toEqual(sampleTransactions)
    expect(store.total).toBe(2)
    expect(store.page).toBe(1)
    expect(store.pageSize).toBe(20)
    expect(store.totalPages).toBe(1)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it("passes server-side pagination and sorting parameters", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        items: [sampleTransactions[1]],
        total: 2,
        page: 2,
        page_size: 1,
        total_pages: 2,
      }),
    })

    const store = useTransactionStore()
    await store.fetchTransactions({
      page: 2,
      rowsPerPage: 10,
      sortBy: "total_amount",
      descending: false,
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("page=2")
    expect(calledUrl).toContain("rowsPerPage=10")
    expect(calledUrl).toContain("sortBy=total_amount")
    expect(calledUrl).toContain("descending=false")
  })

  it("passes filter parameters (source, is_approved, start_date, end_date)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => samplePaginatedResponse,
    })

    const store = useTransactionStore()
    await store.fetchTransactions({
      source: "amazon",
      is_approved: true,
      start_date: "2026-09-01",
      end_date: "2026-09-07",
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("source=amazon")
    expect(calledUrl).toContain("is_approved=true")
    expect(calledUrl).toContain("start_date=2026-09-01")
    expect(calledUrl).toContain("end_date=2026-09-07")
  })

  it("cleans empty string and null parameters from request query string", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => samplePaginatedResponse,
    })

    const store = useTransactionStore()
    await store.fetchTransactions({
      page: 1,
      rowsPerPage: 20,
      source: "",
      is_approved: null,
      start_date: "",
      end_date: "",
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("page=1")
    expect(calledUrl).toContain("rowsPerPage=20")
    expect(calledUrl).not.toContain("source=")
    expect(calledUrl).not.toContain("is_approved=")
    expect(calledUrl).not.toContain("start_date=")
    expect(calledUrl).not.toContain("end_date=")
  })

  it("handles fetch errors and stores error message", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Database connection failed" }),
    })

    const store = useTransactionStore()
    await expect(store.fetchTransactions()).rejects.toThrow("Database connection failed")
    expect(store.loading).toBe(false)
    expect(store.error).toBe("Database connection failed")
  })

  it("supports boolean false for unapproved transactions filter", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        items: [sampleTransactions[1]],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      }),
    })

    const store = useTransactionStore()
    await store.fetchTransactions({
      is_approved: false,
    })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("is_approved=false")
    expect(store.transactions).toHaveLength(1)
    expect(store.transactions[0].is_approved).toBe(false)
  })

  it("passes company_id filter parameter when provided", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({
        items: [sampleTransactions[0]],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      }),
    })

    const store = useTransactionStore()
    await store.fetchTransactions({
      company_id: "comp-1",
    })

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("company_id=comp-1")
    expect(store.transactions).toHaveLength(1)
    expect(store.transactions[0].id).toBe("tx-1")
  })
})

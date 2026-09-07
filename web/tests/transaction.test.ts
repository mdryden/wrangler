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

describe("ManualEntryView Form Controls & Validation", () => {
  it("initializes form state with empty date, description, amount, receipt, and default is_approved true", async () => {
    const { createInitialManualEntryState } = await import("../src/views/manualEntry")
    const state = createInitialManualEntryState()

    expect(state.date).toBe("")
    expect(state.company_id).toBe("")
    expect(state.description).toBe("")
    expect(state.total_amount).toBe("")
    expect(state.receipt_file).toBeNull()
    expect(state.is_approved).toBe(true)
  })

  it("validates date rules: required and YYYY-MM-DD format", async () => {
    const { dateRules } = await import("../src/views/manualEntry")

    // Empty date
    expect(dateRules[0]("")).toBe("Date is required")
    expect(dateRules[0]("   ")).toBe("Date is required")
    expect(dateRules[0]("2026-09-06")).toBe(true)

    // Format validation
    expect(dateRules[1]("09-06-2026")).toBe("Date must be in YYYY-MM-DD format")
    expect(dateRules[1]("2026/09/06")).toBe("Date must be in YYYY-MM-DD format")
    expect(dateRules[1]("invalid-date")).toBe("Date must be in YYYY-MM-DD format")
    expect(dateRules[1]("2026-09-06")).toBe(true)
  })

  it("validates company rules: required", async () => {
    const { companyRules } = await import("../src/views/manualEntry")

    expect(companyRules[0]("")).toBe("Company is required")
    expect(companyRules[0]("   ")).toBe("Company is required")
    expect(companyRules[0]("company-uuid-123")).toBe(true)
  })

  it("validates description rules: non-empty required", async () => {
    const { descriptionRules } = await import("../src/views/manualEntry")

    expect(descriptionRules[0]("")).toBe("Description / Payee is required")
    expect(descriptionRules[0]("   ")).toBe("Description / Payee is required")
    expect(descriptionRules[0]("Office Supplies")).toBe(true)
  })

  it("validates total amount rules: required, numeric, and strictly non-zero", async () => {
    const { amountRules } = await import("../src/views/manualEntry")

    // Required
    expect(amountRules[0]("")).toBe("Total amount is required")

    // Numeric
    expect(amountRules[1]("abc")).toBe("Must be a valid number")
    expect(amountRules[1]("12.50")).toBe(true)

    // Strictly non-zero
    expect(amountRules[2]("0")).toBe("Amount must be strictly non-zero")
    expect(amountRules[2]("0.00")).toBe("Amount must be strictly non-zero")
    expect(amountRules[2](0 as unknown as string)).toBe("Amount must be strictly non-zero")

    // Valid positive and negative (refund) amounts
    expect(amountRules[2]("45.99")).toBe(true)
    expect(amountRules[2]("-25.50")).toBe(true)
  })

  it("formats amount on blur to two decimal places", async () => {
    const { formatAmount } = await import("../src/views/manualEntry")

    expect(formatAmount("125")).toBe("125.00")
    expect(formatAmount("125.5")).toBe("125.50")
    expect(formatAmount("125.556")).toBe("125.56")
    expect(formatAmount("-50")).toBe("-50.00")
    expect(formatAmount("0")).toBe("0")
    expect(formatAmount("")).toBe("")
  })
})

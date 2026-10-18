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
      currency_code: "CAD",
      receipt_file_path: "receipts/tx-1.pdf",
      allocations: [
        {
          id: "alloc-1",
          transaction_id: "tx-1",
          amount: "45.99",
          is_personal: false,
          company_id: "comp-1",
          is_locked: false,
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
      currency_code: "CAD",
      receipt_file_path: null,
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

  it("passes filter parameters (source, start_date, end_date)", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => samplePaginatedResponse,
    })

    const store = useTransactionStore()
    await store.fetchTransactions({
      source: "amazon",
      start_date: "2026-09-01",
      end_date: "2026-09-07",
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("source=amazon")
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
      start_date: "",
      end_date: "",
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toContain("page=1")
    expect(calledUrl).toContain("rowsPerPage=20")
    expect(calledUrl).not.toContain("source=")
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

  it("creates a transaction via JSON payload and returns created transaction", async () => {
    const createdTx: Transaction = {
      id: "tx-new-1",
      source: "manual",
      external_id: null,
      date: "2026-09-07",
      description: "Team Lunch",
      total_amount: "50.00",
      currency_code: "CAD",
      receipt_file_path: null,
      allocations: [
        {
          id: "alloc-new-1",
          transaction_id: "tx-new-1",
          amount: "50.00",
          is_personal: false,
          company_id: "comp-1",
          is_locked: false,
        },
      ],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => createdTx,
    })

    const store = useTransactionStore()
    const result = await store.createTransaction({
      date: "2026-09-07",
      description: "Team Lunch",
      total_amount: "50.00",
      allocations: [
        {
          company_id: "comp-1",
          amount: "50.00",
        },
      ],
    })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/transactions",
      expect.objectContaining({
        method: "POST",
      }),
    )
    expect(result).toEqual(createdTx)
    expect(store.error).toBeNull()
  })

  it("handles createTransaction failure and stores error message", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Sum of split allocations does not equal transaction total amount" }),
    })

    const store = useTransactionStore()
    await expect(
      store.createTransaction({
        date: "2026-09-07",
        description: "Unbalanced",
        total_amount: "100.00",
        allocations: [
          {
            company_id: "comp-1",
            amount: "100.00",
          },
        ],
      }),
    ).rejects.toThrow("Sum of split allocations does not equal transaction total amount")
    expect(store.error).toBe("Sum of split allocations does not equal transaction total amount")
  })

  it("updates a transaction via PUT /api/transactions/{id} and replaces item in state", async () => {
    const store = useTransactionStore()
    store.transactions = [...sampleTransactions]

    const updatedTx: Transaction = {
      ...sampleTransactions[0],
      description: "Updated Office Supplies",
      total_amount: "60.00",
      allocations: [
        {
          id: "alloc-1",
          transaction_id: "tx-1",
          amount: "60.00",
          is_personal: false,
          company_id: "comp-1",
          is_locked: false,
        },
      ],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updatedTx,
    })

    const res = await store.updateTransaction("tx-1", {
      description: "Updated Office Supplies",
      total_amount: "60.00",
      allocations: [
        {
          id: "alloc-1",
          amount: "60.00",
          is_personal: false,
          company_id: "comp-1",
          is_locked: false,
        },
      ],
    })

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/transactions/tx-1",
      expect.objectContaining({
        method: "PUT",
      }),
    )
    expect(res).toEqual(updatedTx)
    expect(store.transactions[0].description).toBe("Updated Office Supplies")
  })

  it("deletes a transaction via DELETE /api/transactions/{id} and removes item from state", async () => {
    const store = useTransactionStore()
    store.transactions = [...sampleTransactions]
    store.total = 2

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: new Headers(),
    })

    await store.deleteTransaction("tx-1")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/transactions/tx-1",
      expect.objectContaining({
        method: "DELETE",
      }),
    )
    expect(store.transactions).toHaveLength(1)
    expect(store.transactions[0].id).toBe("tx-2")
    expect(store.total).toBe(1)
  })

  it("locks and unlocks all allocations on a transaction via PUT /api/transactions/{id}/lock", async () => {
    const store = useTransactionStore()
    store.transactions = [...sampleTransactions]

    const lockedTx: Transaction = {
      ...sampleTransactions[0],
      allocations: [
        {
          ...sampleTransactions[0].allocations[0],
          is_locked: true,
        },
      ],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => lockedTx,
    })

    const res = await store.lockTransaction("tx-1", true)

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/transactions/tx-1/lock",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ is_locked: true }),
      }),
    )
    expect(res.allocations[0].is_locked).toBe(true)
    expect(store.transactions[0].allocations[0].is_locked).toBe(true)
  })

  it("locks or unlocks a single allocation via PUT /api/allocations/{id}/lock", async () => {
    const store = useTransactionStore()
    store.transactions = JSON.parse(JSON.stringify(sampleTransactions))

    const updatedAlloc = {
      ...sampleTransactions[0].allocations[0],
      is_locked: true,
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => updatedAlloc,
    })

    const res = await store.lockAllocation("alloc-1", true)

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/allocations/alloc-1/lock",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ is_locked: true }),
      }),
    )
    expect(res.is_locked).toBe(true)
    expect(store.transactions[0].allocations[0].is_locked).toBe(true)
  })

  it("uploads and deletes a receipt via uploadReceipt and deleteReceipt", async () => {
    const store = useTransactionStore()
    store.transactions = JSON.parse(JSON.stringify(sampleTransactions))

    const txWithReceipt: Transaction = {
      ...sampleTransactions[1],
      receipt_file_path: "tx-2_invoice.pdf",
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => txWithReceipt,
    })

    const file = new File(["pdf bytes"], "invoice.pdf", { type: "application/pdf" })
    const uploaded = await store.uploadReceipt("tx-2", file)
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/transactions/tx-2/receipt",
      expect.objectContaining({
        method: "POST",
      }),
    )
    expect(uploaded.receipt_file_path).toBe("tx-2_invoice.pdf")
    expect(store.transactions[1].receipt_file_path).toBe("tx-2_invoice.pdf")

    const txWithoutReceipt: Transaction = {
      ...sampleTransactions[1],
      receipt_file_path: null,
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => txWithoutReceipt,
    })

    const deleted = await store.deleteReceipt("tx-2")
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/transactions/tx-2/receipt",
      expect.objectContaining({
        method: "DELETE",
      }),
    )
    expect(deleted.receipt_file_path).toBeNull()
    expect(store.transactions[1].receipt_file_path).toBeNull()
  })

  it("fetches receipt blob and opens object URL in new tab via openReceiptInNewTab", async () => {
    const store = useTransactionStore()
    const mockBlob = new Blob(["pdf content"], { type: "application/pdf" })

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/pdf" }),
      blob: async () => mockBlob,
    })

    const createObjectUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:http://localhost/receipt-123")
    const openSpy = vi.fn()
    Object.defineProperty(globalThis, "open", {
      value: openSpy,
      writable: true,
    })

    const blobUrl = await store.openReceiptInNewTab("receipts/tx-1.pdf")

    expect(mockFetch).toHaveBeenCalledWith("/api/receipts/receipts/tx-1.pdf", expect.anything())
    expect(createObjectUrlSpy).toHaveBeenCalledWith(mockBlob)
    expect(openSpy).toHaveBeenCalledWith("blob:http://localhost/receipt-123", "_blank")
    expect(blobUrl).toBe("blob:http://localhost/receipt-123")
  })
})

describe("ManualEntryView Form Controls & Validation", () => {
  it("initializes form state with empty date, description, amount, receipt, and default split", async () => {
    const { createInitialManualEntryState } = await import("../src/views/manualEntry")
    const state = createInitialManualEntryState()

    expect(state.date).toBe("")
    expect((state as unknown as { company_id?: unknown }).company_id).toBeUndefined()
    expect(state.description).toBe("")
    expect(state.total_amount).toBe("")
    expect(state.receipt_file).toBeNull()
    expect(state.splits).toEqual([{ company_id: "", amount: "" }])
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

describe("ManualEntryView Inline Allocation Splitter (Task 13.3)", () => {
  it("initializes form state with default single split matching company attribution", async () => {
    const { createInitialManualEntryState } = await import("../src/views/manualEntry")
    const state = createInitialManualEntryState("comp-abc-123")

    expect((state as unknown as { company_id?: unknown }).company_id).toBeUndefined()
    expect(state.splits).toHaveLength(1)
    expect(state.splits[0].company_id).toBe("comp-abc-123")
    expect(state.splits[0].amount).toBe("")
  })

  it("converts amount strings to integer cents handling float precision", async () => {
    const { toCents } = await import("../src/views/manualEntry")

    expect(toCents("100")).toBe(10000)
    expect(toCents("45.99")).toBe(4599)
    expect(toCents("1.15")).toBe(115) // Floating point edge case (1.15 * 100 = 114.99999999999999)
    expect(toCents("-25.50")).toBe(-2550)
    expect(toCents("0")).toBe(0)
    expect(toCents("")).toBeNull()
    expect(toCents("invalid")).toBeNull()
  })

  it("calculates split remainder: single split 100% balanced", async () => {
    const { calculateSplitRemainder } = await import("../src/views/manualEntry")

    const res = calculateSplitRemainder("100.00", [{ amount: "100.00" }])
    expect(res.remainderCents).toBe(0)
    expect(res.remainderFormatted).toBe("0.00")
    expect(res.isBalanced).toBe(true)
  })

  it("calculates split remainder: multiple splits balanced across companies", async () => {
    const { calculateSplitRemainder } = await import("../src/views/manualEntry")

    const res = calculateSplitRemainder("150.75", [{ amount: "100.50" }, { amount: "50.25" }])
    expect(res.remainderCents).toBe(0)
    expect(res.remainderFormatted).toBe("0.00")
    expect(res.isBalanced).toBe(true)
  })

  it("calculates split remainder: unallocated remainder (sum < total)", async () => {
    const { calculateSplitRemainder } = await import("../src/views/manualEntry")

    const res = calculateSplitRemainder("100.00", [{ amount: "60.00" }])
    expect(res.remainderCents).toBe(4000)
    expect(res.remainderFormatted).toBe("40.00")
    expect(res.isBalanced).toBe(false)
  })

  it("calculates split remainder: overallocated remainder (sum > total)", async () => {
    const { calculateSplitRemainder } = await import("../src/views/manualEntry")

    const res = calculateSplitRemainder("100.00", [{ amount: "80.00" }, { amount: "40.00" }])
    expect(res.remainderCents).toBe(-2000)
    expect(res.remainderFormatted).toBe("-20.00")
    expect(res.isBalanced).toBe(false)
  })

  it("calculates split remainder: refund/negative transactions", async () => {
    const { calculateSplitRemainder } = await import("../src/views/manualEntry")

    // Balanced refund
    const balancedRefund = calculateSplitRemainder("-50.00", [{ amount: "-30.00" }, { amount: "-20.00" }])
    expect(balancedRefund.remainderCents).toBe(0)
    expect(balancedRefund.remainderFormatted).toBe("0.00")
    expect(balancedRefund.isBalanced).toBe(true)

    // Unbalanced refund
    const unbalancedRefund = calculateSplitRemainder("-50.00", [{ amount: "-30.00" }])
    expect(unbalancedRefund.remainderCents).toBe(-2000)
    expect(unbalancedRefund.isBalanced).toBe(false)
  })

  it("marks unbalanced when total amount or splits are missing or 0", async () => {
    const { calculateSplitRemainder } = await import("../src/views/manualEntry")

    expect(calculateSplitRemainder("", [{ amount: "10.00" }]).isBalanced).toBe(false)
    expect(calculateSplitRemainder("0", [{ amount: "0" }]).isBalanced).toBe(false)
    expect(calculateSplitRemainder("50.00", []).isBalanced).toBe(false)
    expect(calculateSplitRemainder("50.00", [{ amount: "" }]).isBalanced).toBe(false)
    expect(calculateSplitRemainder("50.00", [{ amount: "0" }]).isBalanced).toBe(false)
  })

  it("validates split company rules: required", async () => {
    const { splitCompanyRules } = await import("../src/views/manualEntry")

    expect(splitCompanyRules[0]("")).toBe("Split company is required")
    expect(splitCompanyRules[0]("   ")).toBe("Split company is required")
    expect(splitCompanyRules[0]("company-uuid-1")).toBe(true)
  })

  it("validates split amount rules: required, numeric, and non-zero", async () => {
    const { splitAmountRules } = await import("../src/views/manualEntry")

    expect(splitAmountRules[0]("")).toBe("Split amount is required")
    expect(splitAmountRules[1]("not-a-number")).toBe("Must be a valid number")
    expect(splitAmountRules[2]("0")).toBe("Split amount must be strictly non-zero")
    expect(splitAmountRules[2]("0.00")).toBe("Split amount must be strictly non-zero")
    expect(splitAmountRules[2]("25.50")).toBe(true)
    expect(splitAmountRules[2]("-25.50")).toBe(true)
  })
})

describe("ManualEntryView Keyboard Shortcuts, Continuous Entry & Submission (Task 13.4)", () => {
  it("returns today's date formatted as YYYY-MM-DD", async () => {
    const { getTodayDateString } = await import("../src/views/manualEntry")

    const fixedDate = new Date(2026, 8, 7) // Sept 7, 2026
    expect(getTodayDateString(fixedDate)).toBe("2026-09-07")

    // Default current date format check
    const today = getTodayDateString()
    expect(today).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it("prepares JSON payload without file attachment and sets allocations as business splits", async () => {
    const { prepareTransactionPayload } = await import("../src/views/manualEntry")

    const formState = {
      date: "2026-09-07",
      description: "Hardware Store",
      total_amount: "150.00",
      receipt_file: null,
      splits: [
        { company_id: "comp-1", amount: "100.00" },
        { company_id: "comp-2", amount: "50.00" },
      ],
    }

    const { isMultipart, payload } = prepareTransactionPayload(formState)
    expect(isMultipart).toBe(false)
    const json = payload as import("../src/types/transaction").TransactionCreatePayload
    expect((json as unknown as { company_id?: unknown }).company_id).toBeUndefined()
    expect(json.source).toBe("manual")
    expect(json.date).toBe("2026-09-07")
    expect(json.description).toBe("Hardware Store")
    expect(json.total_amount).toBe("150.00")
    expect(json.allocations).toEqual([
      { company_id: "comp-1", amount: "100.00", is_personal: false, is_locked: false },
      { company_id: "comp-2", amount: "50.00", is_personal: false, is_locked: false },
    ])
  })

  it("prepares FormData payload with file attachment and stringified allocations", async () => {
    const { prepareTransactionPayload } = await import("../src/views/manualEntry")

    const fakeFile = new File(["dummy content"], "receipt.pdf", { type: "application/pdf" })
    const formState = {
      date: "2026-09-07",
      description: "Lumber Supplies",
      total_amount: "85.20",
      receipt_file: fakeFile,
      splits: [{ company_id: "comp-1", amount: "85.20" }],
    }

    const { isMultipart, payload } = prepareTransactionPayload(formState)
    expect(isMultipart).toBe(true)
    expect(payload).toBeInstanceOf(FormData)

    const fd = payload as FormData
    expect(fd.get("company_id")).toBeNull()
    expect(fd.get("source")).toBe("manual")
    expect(fd.get("date")).toBe("2026-09-07")
    expect(fd.get("description")).toBe("Lumber Supplies")
    expect(fd.get("total_amount")).toBe("85.20")
    expect(fd.get("receipt")).toBe(fakeFile)

    const parsedAllocations = JSON.parse(fd.get("allocations") as string)
    expect(parsedAllocations).toEqual([{ company_id: "comp-1", amount: "85.20", is_personal: false, is_locked: false }])
  })

  it("handles date keydown: sets today's date when Ctrl+; is pressed", async () => {
    const { getTodayDateString } = await import("../src/views/manualEntry")
    let currentDate = ""
    let defaultPrevented = false

    const handleDateKeydown = (e: {
      ctrlKey: boolean
      metaKey: boolean
      key: string
      code: string
      preventDefault: () => void
      stopPropagation: () => void
    }) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === ";" || e.code === "Semicolon")) {
        e.preventDefault()
        e.stopPropagation()
        currentDate = getTodayDateString()
      }
    }

    // Press Ctrl + ;
    handleDateKeydown({
      ctrlKey: true,
      metaKey: false,
      key: ";",
      code: "Semicolon",
      preventDefault: () => {
        defaultPrevented = true
      },
      stopPropagation: () => {},
    })

    expect(defaultPrevented).toBe(true)
    expect(currentDate).toBe(getTodayDateString())

    // Press regular key without ctrl
    defaultPrevented = false
    currentDate = ""
    handleDateKeydown({
      ctrlKey: false,
      metaKey: false,
      key: ";",
      code: "Semicolon",
      preventDefault: () => {
        defaultPrevented = true
      },
      stopPropagation: () => {},
    })

    expect(defaultPrevented).toBe(false)
    expect(currentDate).toBe("")
  })

  it("handles form keydown: triggers submit on Ctrl+Enter", async () => {
    let submitCalled = false
    let defaultPrevented = false

    const handleFormKeydown = (
      e: { ctrlKey: boolean; metaKey: boolean; key: string; preventDefault: () => void },
      submitFn: () => void,
    ) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault()
        submitFn()
      }
    }

    // Press Ctrl + Enter
    handleFormKeydown(
      {
        ctrlKey: true,
        metaKey: false,
        key: "Enter",
        preventDefault: () => {
          defaultPrevented = true
        },
      },
      () => {
        submitCalled = true
      },
    )

    expect(defaultPrevented).toBe(true)
    expect(submitCalled).toBe(true)

    // Press Enter alone without Ctrl
    submitCalled = false
    defaultPrevented = false
    handleFormKeydown(
      {
        ctrlKey: false,
        metaKey: false,
        key: "Enter",
        preventDefault: () => {
          defaultPrevented = true
        },
      },
      () => {
        submitCalled = true
      },
    )

    expect(defaultPrevented).toBe(false)
    expect(submitCalled).toBe(false)
  })

  it("resets form after successful submission preserving company attribution in split 0", async () => {
    const { createInitialManualEntryState } = await import("../src/views/manualEntry")

    // Current state before submission
    const state = {
      date: "2026-09-07",
      description: "Coffee meeting",
      total_amount: "15.00",
      receipt_file: new File(["data"], "coffee.png", { type: "image/png" }),
      splits: [{ company_id: "comp-retained-123", amount: "15.00" }],
    }

    // Reset preserving company in split 0
    const resetState = createInitialManualEntryState(state.splits[0].company_id)
    expect((resetState as unknown as { company_id?: unknown }).company_id).toBeUndefined()
    expect(resetState.date).toBe("")
    expect(resetState.description).toBe("")
    expect(resetState.total_amount).toBe("")
    expect(resetState.receipt_file).toBeNull()
    expect(resetState.splits).toEqual([{ company_id: "comp-retained-123", amount: "" }])
  })

  it("calculates remaining unallocated balance when one split has an amount and another is empty", async () => {
    const { calculateSplitRemainder } = await import("../src/views/manualEntry")

    const res = calculateSplitRemainder("100.00", [{ amount: "60.00" }, { amount: "" }])
    expect(res.remainderCents).toBe(4000)
    expect(res.remainderFormatted).toBe("40.00")
    expect(res.isBalanced).toBe(false)
  })

  it("prepares transaction payload with allocations directly without top-level company_id", async () => {
    const { prepareTransactionPayload } = await import("../src/views/manualEntry")

    const formState = {
      date: "2026-09-07",
      description: "Hosting Services",
      total_amount: "79.99",
      receipt_file: null,
      splits: [{ company_id: "comp-only-in-split", amount: "79.99" }],
    }

    const { isMultipart, payload } = prepareTransactionPayload(formState)
    expect(isMultipart).toBe(false)
    const json = payload as import("../src/types/transaction").TransactionCreatePayload
    expect((json as unknown as { company_id?: unknown }).company_id).toBeUndefined()
    expect(json.total_amount).toBe("79.99")
    expect(json.allocations).toEqual([{ company_id: "comp-only-in-split", amount: "79.99", is_personal: false, is_locked: false }])
  })

  it("demonstrates allocation readonly logic: readonly when 1 split, writable when multiple splits", () => {
    // Single allocation state: splits.length === 1
    const singleSplitForm = {
      total_amount: "150.00",
      splits: [{ company_id: "comp-1", amount: "150.00" }],
    }
    const isSingleReadonly = singleSplitForm.splits.length === 1
    expect(isSingleReadonly).toBe(true)

    // Multiple allocation state: splits.length > 1
    const multiSplitForm = {
      total_amount: "150.00",
      splits: [
        { company_id: "comp-1", amount: "100.00" },
        { company_id: "comp-2", amount: "50.00" },
      ],
    }
    const isMultiReadonly = multiSplitForm.splits.length === 1
    expect(isMultiReadonly).toBe(false)

    // Reduced back to single allocation
    multiSplitForm.splits.pop()
    expect(multiSplitForm.splits).toHaveLength(1)
    const isRevertedReadonly = multiSplitForm.splits.length === 1
    expect(isRevertedReadonly).toBe(true)
  })
})

describe("Unified Transaction & Allocation Editor Dialog Logic (transactionEdit.ts)", () => {
  const sampleUnlockedTx: Transaction = {
    id: "tx-edit-1",
    source: "manual",
    external_id: null,
    date: "2026-09-10",
    description: "Office Desk",
    total_amount: "200.00",
    currency_code: "CAD",
    receipt_file_path: "tx-edit-1_desk.pdf",
    allocations: [
      {
        id: "alloc-edit-1",
        transaction_id: "tx-edit-1",
        amount: "200.00",
        is_personal: false,
        company_id: "comp-1",
        is_locked: false,
      },
    ],
  }

  const samplePartialLockTx: Transaction = {
    id: "tx-edit-2",
    source: "manual",
    external_id: null,
    date: "2026-09-12",
    description: "Shared Server",
    total_amount: "150.00",
    currency_code: "CAD",
    receipt_file_path: null,
    allocations: [
      {
        id: "alloc-locked",
        transaction_id: "tx-edit-2",
        amount: "100.00",
        is_personal: false,
        company_id: "comp-1",
        is_locked: true,
      },
      {
        id: "alloc-unlocked",
        transaction_id: "tx-edit-2",
        amount: "50.00",
        is_personal: false,
        company_id: "comp-2",
        is_locked: false,
      },
    ],
  }

  const sampleFullyLockedTx: Transaction = {
    id: "tx-edit-3",
    source: "manual",
    external_id: null,
    date: "2026-09-15",
    description: "Locked Expense",
    total_amount: "90.00",
    currency_code: "CAD",
    receipt_file_path: "tx-edit-3_receipt.png",
    allocations: [
      {
        id: "alloc-full-1",
        transaction_id: "tx-edit-3",
        amount: "90.00",
        is_personal: false,
        company_id: "comp-1",
        is_locked: true,
      },
    ],
  }

  it("initializes edit state from unlocked, partially locked, and unallocated transactions", async () => {
    const { createTransactionEditState, getEditLockState } = await import("../src/components/transactionEdit")

    const unlockedState = createTransactionEditState(sampleUnlockedTx)
    expect(unlockedState.date).toBe("2026-09-10")
    expect(unlockedState.description).toBe("Office Desk")
    expect(unlockedState.total_amount).toBe("200.00")
    expect(unlockedState.is_personal).toBe(false)
    expect(unlockedState.existing_receipt_path).toBe("tx-edit-1_desk.pdf")
    expect(unlockedState.splits).toHaveLength(1)

    const unlockedLock = getEditLockState(unlockedState)
    expect(unlockedLock.isFullyLocked).toBe(false)
    expect(unlockedLock.isPartiallyLocked).toBe(false)
    expect(unlockedLock.isDateDisabled).toBe(false)
    expect(unlockedLock.isDescriptionDisabled).toBe(false)
    expect(unlockedLock.isTotalAmountDisabled).toBe(false)

    const partialState = createTransactionEditState(samplePartialLockTx)
    const partialLock = getEditLockState(partialState)
    expect(partialLock.isFullyLocked).toBe(false)
    expect(partialLock.isPartiallyLocked).toBe(true)
    expect(partialLock.isDateDisabled).toBe(true)
    expect(partialLock.isDescriptionDisabled).toBe(true)
    expect(partialLock.isTotalAmountDisabled).toBe(false)
    expect(partialLock.isPersonalToggleDisabled).toBe(true)
    expect(partialLock.isAddSplitDisabled).toBe(false)

    const fullState = createTransactionEditState(sampleFullyLockedTx)
    const fullLock = getEditLockState(fullState)
    expect(fullLock.isFullyLocked).toBe(true)
    expect(fullLock.isPartiallyLocked).toBe(false)
    expect(fullLock.isDateDisabled).toBe(true)
    expect(fullLock.isDescriptionDisabled).toBe(true)
    expect(fullLock.isTotalAmountDisabled).toBe(true)
    expect(fullLock.isPersonalToggleDisabled).toBe(true)
    expect(fullLock.isAddSplitDisabled).toBe(true)
  })

  it("enforces personal expense toggle rules (disabled when splits.length > 1 or locked)", async () => {
    const {
      createTransactionEditState,
      togglePersonalExpense,
      addEditSplit,
      canSaveTransactionEdit,
      prepareTransactionEditPayload,
      PERSONAL_SPLIT_TOOLTIP,
    } = await import("../src/components/transactionEdit")

    expect(PERSONAL_SPLIT_TOOLTIP).toBe("Remove extra splits before marking this transaction as personal.")

    const state = createTransactionEditState(sampleUnlockedTx)
    // Toggle personal = true on single unlocked split
    const toggled = togglePersonalExpense(state, true)
    expect(toggled).toBe(true)
    expect(state.is_personal).toBe(true)
    expect(state.splits[0].is_personal).toBe(true)
    expect(state.splits[0].company_id).toBeNull()
    expect(state.splits[0].amount).toBe("200.00")

    // Cannot add split while personal is true
    expect(addEditSplit(state)).toBe(false)
    expect(canSaveTransactionEdit(state)).toBe(true)

    const { payload } = prepareTransactionEditPayload(state)
    const jsonPayload = payload as import("../src/types/transaction").TransactionUpdatePayload
    expect(jsonPayload.allocations).toEqual([
      {
        id: "alloc-edit-1",
        amount: "200.00",
        is_personal: true,
        company_id: null,
        is_locked: false,
      },
    ])

    // Toggle back to business
    expect(togglePersonalExpense(state, false, "comp-1")).toBe(true)
    expect(state.is_personal).toBe(false)
    expect(state.splits[0].company_id).toBe("comp-1")

    // Add a second split -> personal toggle must now fail
    state.splits[0].amount = "120.00"
    expect(addEditSplit(state, "comp-2")).toBe(true)
    expect(state.splits).toHaveLength(2)
    expect(state.splits[1].amount).toBe("80.00")
    expect(togglePersonalExpense(state, true)).toBe(false)
  })

  it("supports partial lock editing: preserves locked split and allows splitting unlocked portion", async () => {
    const { createTransactionEditState, addEditSplit, removeEditSplit, canSaveTransactionEdit, prepareTransactionEditPayload } =
      await import("../src/components/transactionEdit")

    const state = createTransactionEditState(samplePartialLockTx)

    // Cannot remove the locked split at index 0
    expect(removeEditSplit(state, 0)).toBe(false)
    expect(state.splits).toHaveLength(2)

    // Edit unlocked split at index 1 from $50.00 to $30.00 and add a third split for $20.00
    state.splits[1].amount = "30.00"
    expect(canSaveTransactionEdit(state)).toBe(false) // Unbalanced ($20.00 remaining)

    expect(addEditSplit(state, "comp-3")).toBe(true)
    expect(state.splits).toHaveLength(3)
    expect(state.splits[2].amount).toBe("20.00")
    expect(state.splits[2].company_id).toBe("comp-3")
    expect(canSaveTransactionEdit(state)).toBe(true)

    const { isMultipart, payload } = prepareTransactionEditPayload(state)
    expect(isMultipart).toBe(false)
    const jsonPayload = payload as import("../src/types/transaction").TransactionUpdatePayload
    // Date and description are omitted when partially locked
    expect(jsonPayload.date).toBeUndefined()
    expect(jsonPayload.description).toBeUndefined()
    expect(jsonPayload.total_amount).toBe("150.00")
    expect(jsonPayload.allocations).toEqual([
      {
        id: "alloc-locked",
        amount: "100.00",
        is_personal: false,
        company_id: "comp-1",
        is_locked: true,
      },
      {
        id: "alloc-unlocked",
        amount: "30.00",
        is_personal: false,
        company_id: "comp-2",
        is_locked: false,
      },
      {
        amount: "20.00",
        is_personal: false,
        company_id: "comp-3",
        is_locked: false,
      },
    ])
  })

  it("permits receipt replacement and removal even when transaction is Fully Locked", async () => {
    const {
      createTransactionEditState,
      hasEffectiveReceipt,
      hasReceiptChanges,
      stageReceiptFile,
      markReceiptForRemoval,
      canSaveTransactionEdit,
      prepareTransactionEditPayload,
    } = await import("../src/components/transactionEdit")

    const state = createTransactionEditState(sampleFullyLockedTx)
    expect(hasEffectiveReceipt(state)).toBe(true)
    expect(hasReceiptChanges(state)).toBe(false)
    // Nothing changed on fully locked tx -> cannot save
    expect(canSaveTransactionEdit(state)).toBe(false)

    // Remove receipt on fully locked transaction
    markReceiptForRemoval(state)
    expect(hasEffectiveReceipt(state)).toBe(false)
    expect(hasReceiptChanges(state)).toBe(true)
    expect(canSaveTransactionEdit(state)).toBe(true)

    const removeResult = prepareTransactionEditPayload(state)
    expect(removeResult.isMultipart).toBe(false)
    expect(removeResult.payload).toEqual({ remove_receipt: true })

    // Stage a replacement receipt file on fully locked transaction
    const replacementFile = new File(["new receipt"], "new.pdf", { type: "application/pdf" })
    stageReceiptFile(state, replacementFile)
    expect(hasEffectiveReceipt(state)).toBe(true)
    expect(hasReceiptChanges(state)).toBe(true)
    expect(canSaveTransactionEdit(state)).toBe(true)

    const uploadResult = prepareTransactionEditPayload(state)
    expect(uploadResult.isMultipart).toBe(true)
    const fd = uploadResult.payload as FormData
    expect(fd.get("file")).toBe(replacementFile)
  })
})

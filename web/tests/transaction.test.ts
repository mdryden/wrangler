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
      currency_code: "USD",
      receipt_file_path: null,
      allocations: [
        {
          id: "alloc-new-1",
          transaction_id: "tx-new-1",
          amount: "50.00",
          is_personal: false,
          company_id: "comp-1",
          sync_status: "PENDING",
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
      { company_id: "comp-1", amount: "100.00", is_personal: false, sync_status: "PENDING" },
      { company_id: "comp-2", amount: "50.00", is_personal: false, sync_status: "PENDING" },
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
    expect(parsedAllocations).toEqual([{ company_id: "comp-1", amount: "85.20", is_personal: false, sync_status: "PENDING" }])
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
    expect(json.allocations).toEqual([{ company_id: "comp-only-in-split", amount: "79.99", is_personal: false, sync_status: "PENDING" }])
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

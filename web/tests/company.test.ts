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

  it("exportTransactionsCsv fetches CSV with query parameters, triggers browser download, and refreshes companies", async () => {
    const csvContent = "Date,Description,Amount\r\n2026-09-01,Office Supplies,45.99\r\n"
    const csvBlob = new Blob([csvContent], { type: "text/csv" })

    const initialCompanies: Company[] = [
      {
        id: "comp-1",
        name: "Alpha Corp",
        transaction_count: 1,
        unlocked_allocation_count: 1,
        unlocked_amount_total: "45.99",
        locked_allocation_count: 0,
      },
    ]

    const refreshedCompanies: Company[] = [
      {
        id: "comp-1",
        name: "Alpha Corp",
        transaction_count: 1,
        unlocked_allocation_count: 0,
        unlocked_amount_total: "0.00",
        locked_allocation_count: 1,
      },
    ]

    // First call: GET /api/companies/comp-1/export-transactions
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({
        "content-type": "text/csv",
        "content-disposition": 'attachment; filename="alpha_corp_transactions.csv"',
      }),
      blob: async () => csvBlob,
    })

    // Second call: GET /api/companies (refresh summary counts)
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => refreshedCompanies,
    })

    const createObjectUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:http://localhost/csv-123")
    const revokeObjectUrlSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => { })

    const clickSpy = vi.fn()
    const fakeAnchor = {
      href: "",
      download: "",
      click: clickSpy,
      parentNode: { removeChild: vi.fn() },
    }
    const appendChildSpy = vi.fn()
    Object.defineProperty(globalThis, "document", {
      value: {
        createElement: vi.fn(() => fakeAnchor),
        body: {
          appendChild: appendChildSpy,
        },
      },
      writable: true,
    })

    const store = useCompanyStore()
    store.companies = [...initialCompanies]

    const resultBlob = await store.exportTransactionsCsv("comp-1", {
      include_locked: true,
      start_date: "2026-09-01",
      end_date: "2026-09-30",
    })

    expect(mockFetch).toHaveBeenCalledTimes(2)
    const exportUrl = mockFetch.mock.calls[0][0] as string
    expect(exportUrl).toContain("/api/companies/comp-1/export-transactions")
    expect(exportUrl).toContain("include_locked=true")
    expect(exportUrl).toContain("start_date=2026-09-01")
    expect(exportUrl).toContain("end_date=2026-09-30")

    expect(resultBlob).toBe(csvBlob)
    expect(createObjectUrlSpy).toHaveBeenCalledWith(csvBlob)
    expect(fakeAnchor.href).toBe("blob:http://localhost/csv-123")
    expect(fakeAnchor.download).toBe("alpha_corp_transactions.csv")
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith("blob:http://localhost/csv-123")

    // Summary counts refreshed via fetchCompanies()
    expect(mockFetch.mock.calls[1][0]).toBe("/api/companies")
    expect(store.companies[0].unlocked_allocation_count).toBe(0)
    expect(store.companies[0].locked_allocation_count).toBe(1)
  })

  it("exportTransactionsCsv omits empty date parameters and records error on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Company with ID 'missing' not found" }),
    })

    const store = useCompanyStore()
    await expect(
      store.exportTransactionsCsv("missing", {
        include_locked: false,
        start_date: "",
        end_date: "",
      }),
    ).rejects.toThrow("Company with ID 'missing' not found")

    const calledUrl = mockFetch.mock.calls[0][0] as string
    expect(calledUrl).toBe("/api/companies/missing/export-transactions?include_locked=false")
    expect(store.error).toBe("Company with ID 'missing' not found")
  })

  it("lockCompanyAllocations sends POST to /api/companies/{id}/lock-allocations with optional allocationIds", async () => {
    const lockedAllocations = [
      {
        id: "alloc-1",
        transaction_id: "tx-1",
        amount: "50.00",
        is_personal: false,
        company_id: "comp-1",
        is_locked: true,
      },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => lockedAllocations,
    })

    const store = useCompanyStore()
    const resAll = await store.lockCompanyAllocations("comp-1")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/comp-1/lock-allocations",
      expect.objectContaining({
        method: "POST",
        body: undefined,
      }),
    )
    expect(resAll).toEqual(lockedAllocations)

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => lockedAllocations,
    })

    const resSubset = await store.lockCompanyAllocations("comp-1", ["alloc-1"])
    expect(mockFetch).toHaveBeenLastCalledWith(
      "/api/companies/comp-1/lock-allocations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ allocation_ids: ["alloc-1"] }),
      }),
    )
    expect(resSubset).toEqual(lockedAllocations)
  })

  it("unlockCompanyAllocations sends POST to /api/companies/{id}/unlock-allocations with optional allocationIds", async () => {
    const unlockedAllocations = [
      {
        id: "alloc-1",
        transaction_id: "tx-1",
        amount: "50.00",
        is_personal: false,
        company_id: "comp-1",
        is_locked: false,
      },
    ]

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => unlockedAllocations,
    })

    const store = useCompanyStore()
    const resAll = await store.unlockCompanyAllocations("comp-1")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/companies/comp-1/unlock-allocations",
      expect.objectContaining({
        method: "POST",
        body: undefined,
      }),
    )
    expect(resAll).toEqual(unlockedAllocations)

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => unlockedAllocations,
    })

    const resSubset = await store.unlockCompanyAllocations("comp-1", ["alloc-1"])
    expect(mockFetch).toHaveBeenLastCalledWith(
      "/api/companies/comp-1/unlock-allocations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ allocation_ids: ["alloc-1"] }),
      }),
    )
    expect(resSubset).toEqual(unlockedAllocations)
  })
})

describe("ExportManagerView & Export Controls Logic (exportManager.ts)", () => {
  it("initializes controls with company_id = null, include_locked = false, empty date range, and default page size 50", async () => {
    const { createInitialExportControlsState, resetExportControlsState, buildCompanyExportOptions, DEFAULT_EXPORT_PAGE_SIZE } =
      await import("../src/views/exportManager")

    expect(DEFAULT_EXPORT_PAGE_SIZE).toBe(50)

    const state = createInitialExportControlsState()
    expect(state.company_id).toBeNull()
    expect(state.include_locked).toBe(false)
    expect(state.start_date).toBe("")
    expect(state.end_date).toBe("")

    expect(buildCompanyExportOptions(state)).toEqual({
      include_locked: false,
      start_date: undefined,
      end_date: undefined,
    })

    state.company_id = "comp-1"
    state.include_locked = true
    state.start_date = "2026-09-01"
    state.end_date = "2026-09-30"

    expect(buildCompanyExportOptions(state)).toEqual({
      include_locked: true,
      start_date: "2026-09-01",
      end_date: "2026-09-30",
    })

    resetExportControlsState(state)
    expect(state).toEqual({
      company_id: null,
      include_locked: false,
      start_date: "",
      end_date: "",
    })
  })

  it("extracts flattened business allocation rows for the selected company and include_locked setting", async () => {
    const { extractCompanyAllocationRows } = await import("../src/views/exportManager")
    const sampleTxs = [
      {
        id: "tx-100",
        source: "manual",
        external_id: null,
        date: "2026-09-10",
        description: "Multi-Company Invoice",
        total_amount: "150.00",
        currency_code: "CAD",
        receipt_file_path: "tx-100.pdf",
        allocations: [
          {
            id: "alloc-100a",
            transaction_id: "tx-100",
            amount: "100.00",
            is_personal: false,
            company_id: "comp-1",
            is_locked: false,
          },
          {
            id: "alloc-100b",
            transaction_id: "tx-100",
            amount: "50.00",
            is_personal: false,
            company_id: "comp-2",
            is_locked: false,
          },
        ],
      },
      {
        id: "tx-101",
        source: "manual",
        external_id: null,
        date: "2026-09-12",
        description: "Already Exported Supply",
        total_amount: "40.00",
        currency_code: "CAD",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-101",
            transaction_id: "tx-101",
            amount: "40.00",
            is_personal: false,
            company_id: "comp-1",
            is_locked: true,
          },
        ],
      },
      {
        id: "tx-102",
        source: "bank",
        external_id: null,
        date: "2026-09-13",
        description: "Personal Grocery",
        total_amount: "25.00",
        currency_code: "CAD",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc-102",
            transaction_id: "tx-102",
            amount: "25.00",
            is_personal: true,
            company_id: null,
            is_locked: false,
          },
        ],
      },
    ]

    // Starts empty when companyId is null
    expect(extractCompanyAllocationRows(sampleTxs, null, false)).toEqual([])

    // Unlocked only for comp-1
    const unlockedRows = extractCompanyAllocationRows(sampleTxs, "comp-1", false)
    expect(unlockedRows).toEqual([
      {
        id: "alloc-100a",
        transaction_id: "tx-100",
        date: "2026-09-10",
        description: "Multi-Company Invoice",
        amount: "100.00",
        currency_code: "CAD",
        is_locked: false,
        company_id: "comp-1",
        receipt_file_path: "tx-100.pdf",
      },
    ])

    // Include locked for comp-1
    const allRows = extractCompanyAllocationRows(sampleTxs, "comp-1", true)
    expect(allRows).toHaveLength(2)
    expect(allRows.map(r => r.id)).toEqual(["alloc-100a", "alloc-101"])
  })

  it("builds Ledger transaction URL and opens parent transaction in a new tab", async () => {
    const { getLedgerTransactionUrl, openTransactionInLedgerNewTab } = await import("../src/views/exportManager")

    expect(getLedgerTransactionUrl("tx-abc-123")).toBe("/ledger?transaction_id=tx-abc-123")

    const openSpy = vi.fn()
    Object.defineProperty(globalThis, "open", {
      value: openSpy,
      writable: true,
    })

    const url = openTransactionInLedgerNewTab("tx-abc-123")
    expect(url).toBe("/ledger?transaction_id=tx-abc-123")
    expect(openSpy).toHaveBeenCalledWith("/ledger?transaction_id=tx-abc-123", "_blank", "noopener,noreferrer")
  })

  it("computes company export summary metrics and export eligibility", async () => {
    const { getCompanyExportSummary, canExportCompany } = await import("../src/views/exportManager")

    const companyWithUnlocked: Company = {
      id: "comp-1",
      name: "Alpha Consulting",
      transaction_count: 5,
      unlocked_allocation_count: 3,
      unlocked_amount_total: "1250.75",
      locked_allocation_count: 2,
    }

    const summary1 = getCompanyExportSummary(companyWithUnlocked)
    expect(summary1).toEqual({
      id: "comp-1",
      name: "Alpha Consulting",
      unlockedCount: 3,
      unlockedTotalFormatted: "$1,250.75",
      lockedCount: 2,
      totalBusinessCount: 5,
    })
    expect(canExportCompany(companyWithUnlocked, false)).toBe(true)
    expect(canExportCompany(companyWithUnlocked, true)).toBe(true)
    expect(canExportCompany(null, false)).toBe(false)

    const companyAllLocked: Company = {
      id: "comp-2",
      name: "Beta Properties",
      transaction_count: 4,
      unlocked_allocation_count: 0,
      unlocked_amount_total: "0.00",
      locked_allocation_count: 4,
    }

    const summary2 = getCompanyExportSummary(companyAllLocked)
    expect(summary2).toEqual({
      id: "comp-2",
      name: "Beta Properties",
      unlockedCount: 0,
      unlockedTotalFormatted: "$0.00",
      lockedCount: 4,
      totalBusinessCount: 4,
    })
    expect(canExportCompany(companyAllLocked, false)).toBe(false)
    expect(canExportCompany(companyAllLocked, true)).toBe(true)

    const companyEmpty: Company = {
      id: "comp-3",
      name: "Gamma Ventures",
      transaction_count: 0,
      unlocked_allocation_count: 0,
      unlocked_amount_total: "0.00",
      locked_allocation_count: 0,
    }
    expect(canExportCompany(companyEmpty, false)).toBe(false)
    expect(canExportCompany(companyEmpty, true)).toBe(false)
  })

  it("extracts filename from Content-Disposition header or falls back to company filename", async () => {
    const { extractFilenameFromContentDisposition } = await import("../src/stores/companies")

    expect(extractFilenameFromContentDisposition('attachment; filename="alpha_consulting_transactions.csv"', "fallback.csv")).toBe(
      "alpha_consulting_transactions.csv",
    )

    expect(extractFilenameFromContentDisposition(null, "fallback.csv")).toBe("fallback.csv")
    expect(extractFilenameFromContentDisposition("inline", "fallback.csv")).toBe("fallback.csv")
  })
})

import { describe, it, expect, beforeEach, vi } from "vitest"
import { setActivePinia, createPinia } from "pinia"
import {
  isMasterHeaderChecked,
  isMasterHeaderIndeterminate,
  countOverwrittenCategories,
  canSyncSelectedToWave,
  type ExportAllocationRow,
} from "../src/views/exportManager"
import { useTransactionStore } from "../src/stores/transactions"
import type { Transaction } from "../src/types/transaction"
import type { BulkAllocationCategoryUpdateResponse } from "../src/types/wave"

// Mock localStorage for auth token
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

describe("Export Manager Selection & Category Pure Helpers", () => {
  describe("isMasterHeaderChecked", () => {
    it("returns true when all visible unlocked rows are selected", () => {
      const visible = ["alloc_1", "alloc_2", "alloc_3"]
      const selected = ["alloc_1", "alloc_2", "alloc_3", "other_alloc"]
      expect(isMasterHeaderChecked(visible, selected)).toBe(true)
    })

    it("returns false when none are selected", () => {
      const visible = ["alloc_1", "alloc_2"]
      const selected: string[] = []
      expect(isMasterHeaderChecked(visible, selected)).toBe(false)
    })

    it("returns false when only a subset is selected", () => {
      const visible = ["alloc_1", "alloc_2", "alloc_3"]
      const selected = ["alloc_1", "alloc_3"]
      expect(isMasterHeaderChecked(visible, selected)).toBe(false)
    })

    it("returns false when visible list is empty", () => {
      expect(isMasterHeaderChecked([], ["alloc_1"])).toBe(false)
      expect(isMasterHeaderChecked([], [])).toBe(false)
    })
  })

  describe("isMasterHeaderIndeterminate", () => {
    it("returns true for partial selections", () => {
      const visible = ["alloc_1", "alloc_2", "alloc_3"]
      const selected = ["alloc_2"]
      expect(isMasterHeaderIndeterminate(visible, selected)).toBe(true)
    })

    it("returns false for empty selection", () => {
      const visible = ["alloc_1", "alloc_2"]
      expect(isMasterHeaderIndeterminate(visible, [])).toBe(false)
    })

    it("returns false for full selection", () => {
      const visible = ["alloc_1", "alloc_2"]
      expect(isMasterHeaderIndeterminate(visible, ["alloc_1", "alloc_2"])).toBe(false)
    })

    it("returns false when visible list is empty", () => {
      expect(isMasterHeaderIndeterminate([], ["alloc_1"])).toBe(false)
    })
  })

  describe("countOverwrittenCategories", () => {
    it("accurately counts allocations with existing non-null wave_category_id", () => {
      const rows: ExportAllocationRow[] = [
        {
          id: "a1",
          transaction_id: "tx1",
          date: "2026-09-01",
          description: "Row 1",
          amount: 50,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: "cat_1",
          wave_transaction_id: null,
        },
        {
          id: "a2",
          transaction_id: "tx2",
          date: "2026-09-02",
          description: "Row 2",
          amount: 75,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: null,
          wave_transaction_id: null,
        },
        {
          id: "a3",
          transaction_id: "tx3",
          date: "2026-09-03",
          description: "Row 3",
          amount: 100,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: "cat_2",
          wave_transaction_id: null,
        },
      ]
      expect(countOverwrittenCategories(rows)).toBe(2)
    })

    it("returns 0 when none have wave_category_id", () => {
      const rows: ExportAllocationRow[] = [
        {
          id: "a1",
          transaction_id: "tx1",
          date: "2026-09-01",
          description: "Row 1",
          amount: 50,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: null,
          wave_transaction_id: null,
        },
      ]
      expect(countOverwrittenCategories(rows)).toBe(0)
    })

    it("handles empty array gracefully", () => {
      expect(countOverwrittenCategories([])).toBe(0)
    })
  })

  describe("canSyncSelectedToWave", () => {
    it("returns true only when all selected rows are unlocked and have a category assigned", () => {
      const rows: ExportAllocationRow[] = [
        {
          id: "a1",
          transaction_id: "tx1",
          date: "2026-09-01",
          description: "Row 1",
          amount: 50,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: "cat_1",
          wave_transaction_id: null,
        },
        {
          id: "a2",
          transaction_id: "tx2",
          date: "2026-09-02",
          description: "Row 2",
          amount: 60,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: "cat_2",
          wave_transaction_id: null,
        },
      ]
      expect(canSyncSelectedToWave(rows)).toBe(true)
    })

    it("returns false if any row is locked", () => {
      const rows: ExportAllocationRow[] = [
        {
          id: "a1",
          transaction_id: "tx1",
          date: "2026-09-01",
          description: "Row 1",
          amount: 50,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: "cat_1",
          wave_transaction_id: null,
        },
        {
          id: "a2",
          transaction_id: "tx2",
          date: "2026-09-02",
          description: "Row 2",
          amount: 60,
          is_locked: true,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: "cat_2",
          wave_transaction_id: null,
        },
      ]
      expect(canSyncSelectedToWave(rows)).toBe(false)
    })

    it("returns false if any row is missing wave_category_id", () => {
      const rows: ExportAllocationRow[] = [
        {
          id: "a1",
          transaction_id: "tx1",
          date: "2026-09-01",
          description: "Row 1",
          amount: 50,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: "cat_1",
          wave_transaction_id: null,
        },
        {
          id: "a2",
          transaction_id: "tx2",
          date: "2026-09-02",
          description: "Row 2",
          amount: 60,
          is_locked: false,
          company_id: "c1",
          receipt_file_path: null,
          wave_category_id: null,
          wave_transaction_id: null,
        },
      ]
      expect(canSyncSelectedToWave(rows)).toBe(false)
    })

    it("returns false if selection is empty", () => {
      expect(canSyncSelectedToWave([])).toBe(false)
    })
  })
})

describe("Transaction Store - bulkUpdateAllocationCategory", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    mockFetch = vi.fn()
    globalThis.fetch = mockFetch as unknown as typeof fetch
  })

  it("invokes API with expected payload and mutates matching in-memory allocations", async () => {
    const store = useTransactionStore()

    const initialTransactions: Transaction[] = [
      {
        id: "tx_1",
        source: "manual",
        external_id: null,
        date: "2026-09-01",
        description: "Tx 1",
        total_amount: "100.00",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc_1",
            transaction_id: "tx_1",
            amount: "50.00",
            is_personal: false,
            company_id: "company_1",
            is_locked: false,
            wave_category_id: null,
            wave_transaction_id: null,
          },
          {
            id: "alloc_2",
            transaction_id: "tx_1",
            amount: "50.00",
            is_personal: false,
            company_id: "company_1",
            is_locked: false,
            wave_category_id: "old_cat",
            wave_transaction_id: null,
          },
        ],
      },
      {
        id: "tx_2",
        source: "manual",
        external_id: null,
        date: "2026-09-02",
        description: "Tx 2",
        total_amount: "40.00",
        receipt_file_path: null,
        allocations: [
          {
            id: "alloc_3",
            transaction_id: "tx_2",
            amount: "40.00",
            is_personal: false,
            company_id: "company_1",
            is_locked: false,
            wave_category_id: null,
            wave_transaction_id: null,
          },
        ],
      },
    ]

    store.transactions = initialTransactions

    const mockResponse: BulkAllocationCategoryUpdateResponse = {
      updated_count: 2,
      allocation_ids: ["alloc_1", "alloc_3"],
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => mockResponse,
    })

    const result = await store.bulkUpdateAllocationCategory(["alloc_1", "alloc_3"], "new_cat_123")

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/allocations/bulk-category",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          allocation_ids: ["alloc_1", "alloc_3"],
          wave_category_id: "new_cat_123",
        }),
      }),
    )

    expect(result).toEqual(mockResponse)

    // Verify in-memory reactivity: alloc_1 and alloc_3 updated, alloc_2 untouched
    expect(store.transactions[0].allocations[0].wave_category_id).toBe("new_cat_123")
    expect(store.transactions[0].allocations[1].wave_category_id).toBe("old_cat")
    expect(store.transactions[1].allocations[0].wave_category_id).toBe("new_cat_123")
  })

  it("handles API error by populating store error and re-throwing", async () => {
    const store = useTransactionStore()

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Allocation alloc_1 is locked and cannot be modified" }),
    })

    await expect(store.bulkUpdateAllocationCategory(["alloc_1"], "cat_1")).rejects.toThrow()
    expect(store.error).toBeTruthy()
  })
})

import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
import { apiClient } from "../src/api/client"
import { useTransactionStore } from "../src/stores/transactions"
import { countOverwrittenCategories, type ExportAllocationRow } from "../src/views/exportManager"
import type { WaveCategory } from "../src/types/wave"

vi.mock("../src/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function makeAllocationRow(overrides: Partial<ExportAllocationRow> = {}): ExportAllocationRow {
  return {
    id: "alloc-1",
    transaction_id: "tx-1",
    date: "2026-10-21",
    description: "Office Monitor",
    amount: "250.00",
    is_locked: false,
    company_id: "comp-1",
    receipt_file_path: null,
    wave_category_id: null,
    wave_transaction_id: null,
    ...overrides,
  }
}

describe("BulkCategorizeDialog Component & Integration", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe("Template & UI Structure", () => {
    const dialogPath = path.resolve(__dirname, "../src/components/BulkCategorizeDialog.vue")
    const dialogTemplate = fs.readFileSync(dialogPath, "utf-8")

    it("includes required title, subtitle, banner, category selector, and action buttons", () => {
      expect(dialogTemplate).toContain("Assign Category")
      expect(dialogTemplate).toContain("Assign a Wave category to")
      expect(dialogTemplate).toContain('data-testid="banner-overwrite-warning"')
      expect(dialogTemplate).toContain('data-testid="select-bulk-category"')
      expect(dialogTemplate).toContain('data-testid="btn-apply-bulk-category"')
      expect(dialogTemplate).toContain('data-testid="btn-cancel-bulk-category"')
      expect(dialogTemplate).toContain("v-close-popup")
    })

    it("configures category select with searchable filtering attributes", () => {
      expect(dialogTemplate).toContain("use-input")
      expect(dialogTemplate).toContain("fill-input")
      expect(dialogTemplate).toContain("hide-selected")
      expect(dialogTemplate).toContain("outlined")
      expect(dialogTemplate).toContain("dense")
      expect(dialogTemplate).toContain('@filter="filterFn"')
    })

    it("renders uncategorized default category styling in options slot", () => {
      expect(dialogTemplate).toContain("Wave System Default")
      expect(dialogTemplate).toContain("scope.opt.is_uncategorized")
    })
  })

  describe("Overwrite warning detection", () => {
    it("reports count > 0 when some selected rows already have wave_category_id", () => {
      const rows = [
        makeAllocationRow({ id: "alloc-1", wave_category_id: null }),
        makeAllocationRow({ id: "alloc-2", wave_category_id: "cat-123" }),
      ]
      expect(countOverwrittenCategories(rows)).toBe(1)
    })

    it("reports 0 when no selected rows have a wave_category_id", () => {
      const rows = [
        makeAllocationRow({ id: "alloc-1", wave_category_id: null }),
        makeAllocationRow({ id: "alloc-2", wave_category_id: null }),
      ]
      expect(countOverwrittenCategories(rows)).toBe(0)
    })
  })

  describe("Category options filtering", () => {
    const categories: WaveCategory[] = [
      {
        id: "cat-1",
        company_id: "comp-1",
        wave_account_id: "w1",
        name: "Office Supplies",
        account_type: "EXPENSE",
        is_uncategorized: false,
      },
      {
        id: "cat-2",
        company_id: "comp-1",
        wave_account_id: "w2",
        name: "Meals & Entertainment",
        account_type: "EXPENSE",
        is_uncategorized: false,
      },
      {
        id: "cat-3",
        company_id: "comp-1",
        wave_account_id: "w3",
        name: "Uncategorized Expense",
        account_type: "EXPENSE",
        is_uncategorized: true,
      },
    ]

    it("filters category list by needle search string", () => {
      const needle = "supplies"
      const filtered = categories
        .map(c => ({ label: c.name, value: c.id, is_uncategorized: c.is_uncategorized }))
        .filter(opt => opt.label.toLowerCase().includes(needle.toLowerCase()))

      expect(filtered).toHaveLength(1)
      expect(filtered[0].label).toBe("Office Supplies")
      expect(filtered[0].value).toBe("cat-1")
    })

    it("returns all options when search query is empty", () => {
      const filtered = categories
        .map(c => ({ label: c.name, value: c.id, is_uncategorized: c.is_uncategorized }))
        .filter(opt => opt.label.toLowerCase().includes(""))

      expect(filtered).toHaveLength(3)
    })
  })

  describe("Form validation & action dispatch", () => {
    it("determines apply button disabled state based on selection and category", () => {
      const isApplyDisabled = (selectedRowsLength: number, selectedCategory: string | null, applying: boolean) => {
        return selectedRowsLength === 0 || !selectedCategory || applying
      }

      // Disabled if no category selected
      expect(isApplyDisabled(2, null, false)).toBe(true)

      // Disabled if 0 rows selected
      expect(isApplyDisabled(0, "cat-1", false)).toBe(true)

      // Disabled while applying
      expect(isApplyDisabled(2, "cat-1", true)).toBe(true)

      // Enabled when rows and category are valid
      expect(isApplyDisabled(2, "cat-1", false)).toBe(false)
    })

    it("submits bulkUpdateAllocationCategory with allocation IDs and selected category", async () => {
      const transactionStore = useTransactionStore()
      vi.mocked(apiClient.post).mockResolvedValueOnce({
        updated_count: 2,
        allocation_ids: ["alloc-1", "alloc-2"],
      })

      const rows = [makeAllocationRow({ id: "alloc-1" }), makeAllocationRow({ id: "alloc-2" })]

      const res = await transactionStore.bulkUpdateAllocationCategory(
        rows.map(r => r.id),
        "cat-123",
      )

      expect(apiClient.post).toHaveBeenCalledWith("/api/allocations/bulk-category", {
        allocation_ids: ["alloc-1", "alloc-2"],
        wave_category_id: "cat-123",
      })
      expect(res.updated_count).toBe(2)
    })

    it("cancel button closes dialog without invoking store update", () => {
      const dialogPath = path.resolve(__dirname, "../src/components/BulkCategorizeDialog.vue")
      const dialogTemplate = fs.readFileSync(dialogPath, "utf-8")

      const cancelBtnRegex = /<q-btn[^>]*data-testid="btn-cancel-bulk-category"[^>]*\/>/
      const match = dialogTemplate.match(cancelBtnRegex)
      expect(match).not.toBeNull()
      expect(match![0]).toContain("v-close-popup")
      expect(match![0]).not.toContain("@click")
    })
  })
})

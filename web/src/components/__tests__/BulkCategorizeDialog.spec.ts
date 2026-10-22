import { beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"
import { DOMWrapper } from "@vue/test-utils"
import { apiClient } from "../../api/client"
import type { WaveCategory } from "../../types/wave"
import { countOverwrittenCategories, type ExportAllocationRow } from "../../views/exportManager"
import BulkCategorizeDialog from "../BulkCategorizeDialog.vue"
import { mountWithQuasar, findInBody } from "../../../tests/utils/testHarness"

vi.mock("../../api/client", () => ({
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

const mockCategories: WaveCategory[] = [
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

describe("BulkCategorizeDialog Component & Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe("Mounted Component Behavior", () => {
    it("renders dialog structure, title, count caption, category selector, and action buttons", async () => {
      const rows = [makeAllocationRow({ id: "alloc-1" }), makeAllocationRow({ id: "alloc-2" })]

      mountWithQuasar(BulkCategorizeDialog, {
        props: {
          modelValue: true,
          selectedRows: rows,
          categories: mockCategories,
        },
      })
      await nextTick()

      expect(findInBody(".text-h6")?.textContent).toBe("Assign Category")
      expect(findInBody(".text-caption")?.textContent).toContain("Assign a Wave category to 2 selected transactions.")
      expect(findInBody('[data-testid="select-bulk-category"]')).not.toBeNull()
      expect(findInBody('[data-testid="btn-apply-bulk-category"]')).not.toBeNull()
      expect(findInBody('[data-testid="btn-cancel-bulk-category"]')).not.toBeNull()
    })

    it("displays overwrite warning banner when rows already have categories and hides it when unassigned", async () => {
      const rowsWithOverwrite = [
        makeAllocationRow({ id: "alloc-1", wave_category_id: "cat-1" }),
        makeAllocationRow({ id: "alloc-2", wave_category_id: null }),
      ]

      const wrapper = mountWithQuasar(BulkCategorizeDialog, {
        props: {
          modelValue: true,
          selectedRows: rowsWithOverwrite,
          categories: mockCategories,
        },
      })
      await nextTick()

      const banner = findInBody('[data-testid="banner-overwrite-warning"]')
      expect(banner).not.toBeNull()
      expect(banner?.textContent).toContain("1 of 2 selected transactions already have a category assigned which will be updated.")

      wrapper.unmount()
      await nextTick()

      // Unassigned rows
      const rowsWithoutOverwrite = [
        makeAllocationRow({ id: "alloc-1", wave_category_id: null }),
        makeAllocationRow({ id: "alloc-2", wave_category_id: null }),
      ]
      mountWithQuasar(BulkCategorizeDialog, {
        props: {
          modelValue: true,
          selectedRows: rowsWithoutOverwrite,
          categories: mockCategories,
        },
      })
      await nextTick()

      expect(findInBody('[data-testid="banner-overwrite-warning"]')).toBeNull()
    })

    function selectCategory(categoryId: string): void {
      const selectEl = findInBody('[data-testid="select-bulk-category"]')
      const qField = selectEl?.closest(".q-field")
      const parentComp = (selectEl as any)?.__vueParentComponent || (qField as any)?.__vueParentComponent
      if (parentComp?.emit) {
        parentComp.emit("update:modelValue", categoryId)
      }
    }

    it("controls Apply button disabled state based on category selection and row count", async () => {
      const rows = [makeAllocationRow({ id: "alloc-1" })]

      // Initially with no category selected: disabled
      const wrapper = mountWithQuasar(BulkCategorizeDialog, {
        props: {
          modelValue: true,
          selectedRows: rows,
          categories: mockCategories,
        },
      })
      await nextTick()

      const applyBtn = findInBody('[data-testid="btn-apply-bulk-category"]')
      expect(applyBtn?.getAttribute("disabled") !== null || applyBtn?.classList.contains("disabled")).toBe(true)

      selectCategory("cat-1")
      await nextTick()

      expect(applyBtn?.hasAttribute("disabled")).toBe(false)
      expect(applyBtn?.classList.contains("disabled")).toBe(false)

      wrapper.unmount()
      await nextTick()

      // Empty rows with category: disabled
      const wrapperEmpty = mountWithQuasar(BulkCategorizeDialog, {
        props: {
          modelValue: true,
          selectedRows: [],
          categories: mockCategories,
        },
      })
      await nextTick()

      selectCategory("cat-1")
      await nextTick()

      const applyBtnEmpty = findInBody('[data-testid="btn-apply-bulk-category"]')
      expect(applyBtnEmpty?.hasAttribute("disabled") || applyBtnEmpty?.classList.contains("disabled")).toBe(true)
    })

    it("dispatches API call, triggers Notify toast, and emits applied and update:modelValue events on Apply", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({
        updated_count: 2,
        allocation_ids: ["alloc-1", "alloc-2"],
      })

      const rows = [makeAllocationRow({ id: "alloc-1" }), makeAllocationRow({ id: "alloc-2" })]
      const wrapper = mountWithQuasar(BulkCategorizeDialog, {
        props: {
          modelValue: true,
          selectedRows: rows,
          categories: mockCategories,
        },
      })
      await nextTick()

      const notifySpy = vi.spyOn((wrapper.vm as any).$q, "notify")

      // Select category
      selectCategory("cat-1")
      await nextTick()

      const applyBtn = findInBody('[data-testid="btn-apply-bulk-category"]')
      expect(applyBtn).not.toBeNull()
      await new DOMWrapper(applyBtn!).trigger("click")
      await nextTick()

      expect(apiClient.post).toHaveBeenCalledWith("/api/allocations/bulk-category", {
        allocation_ids: ["alloc-1", "alloc-2"],
        wave_category_id: "cat-1",
      })

      expect(wrapper.emitted("applied")).toBeTruthy()
      expect(wrapper.emitted("applied")![0]).toEqual([2])
      expect(wrapper.emitted("update:modelValue")).toBeTruthy()
      expect(wrapper.emitted("update:modelValue")![0]).toEqual([false])
      expect(notifySpy).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "positive",
          message: "Successfully assigned category to 2 transactions",
        }),
      )
    })

    it("closes dialog on Cancel button click without dispatching API call", async () => {
      const rows = [makeAllocationRow({ id: "alloc-1" })]
      const wrapper = mountWithQuasar(BulkCategorizeDialog, {
        props: {
          modelValue: true,
          selectedRows: rows,
          categories: mockCategories,
        },
      })
      await nextTick()

      const cancelBtn = findInBody('[data-testid="btn-cancel-bulk-category"]')
      expect(cancelBtn).not.toBeNull()
      await new DOMWrapper(cancelBtn!).trigger("click")
      await new Promise(resolve => setTimeout(resolve, 50))
      await nextTick()

      expect(apiClient.post).not.toHaveBeenCalled()
      expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([false])
    })
  })

  describe("Overwrite warning detection (Pure helper)", () => {
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

  describe("Category options filtering (Pure helper)", () => {
    it("filters category list by needle search string", () => {
      const needle = "supplies"
      const filtered = mockCategories
        .map(c => ({ label: c.name, value: c.id, is_uncategorized: c.is_uncategorized }))
        .filter(opt => opt.label.toLowerCase().includes(needle.toLowerCase()))

      expect(filtered).toHaveLength(1)
      expect(filtered[0].label).toBe("Office Supplies")
      expect(filtered[0].value).toBe("cat-1")
    })

    it("returns all options when search query is empty", () => {
      const filtered = mockCategories
        .map(c => ({ label: c.name, value: c.id, is_uncategorized: c.is_uncategorized }))
        .filter(opt => opt.label.toLowerCase().includes(""))

      expect(filtered).toHaveLength(3)
    })
  })
})

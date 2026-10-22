import { beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"
import { DOMWrapper } from "@vue/test-utils"
import { Notify } from "quasar"
import { apiClient } from "../../api/client"
import { useCompanyStore } from "../../stores/companies"
import type { StagedTransaction } from "../../types/staging"
import { buildBulkAllocatePayload, countOverwrittenTransactions } from "../bulkAllocate"
import BulkAllocateDialog from "../BulkAllocateDialog.vue"
import { mountWithQuasar, findInBody } from "../../../tests/utils/testHarness"

vi.mock("../../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function makeStagedTx(overrides: Partial<StagedTransaction> = {}): StagedTransaction {
  return {
    id: "stx-1",
    source: "amazon_csv",
    external_id: "ext-1",
    date: "2026-10-18",
    description: "Office Monitor",
    total_amount: "250.00",
    receipt_file_path: null,
    url: null,
    status: "STAGED",
    is_marked_imported: false,
    ledger_transaction_id: null,
    created_at: "2026-10-18T10:00:00Z",
    allocations: [],
    is_ready: false,
    supports_mark_imported: false,
    mark_imported_error: null,
    ...overrides,
  }
}

describe("BulkAllocateDialog Component & Logic", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue([])
  })

  describe("Mounted Component Behavior", () => {
    it("renders dialog structure, title, count caption, radio options, and action buttons", async () => {
      const tx1 = makeStagedTx({ id: "stx-1" })
      const tx2 = makeStagedTx({ id: "stx-2" })

      mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [tx1, tx2],
        },
      })
      await nextTick()

      expect(findInBody(".text-h6")?.textContent).toBe("Bulk Allocate Transactions")
      expect(findInBody(".text-caption")?.textContent).toContain("Assign an entity to 2 selected staged transactions.")
      expect(findInBody('[data-testid="radio-personal"]')).not.toBeNull()
      expect(findInBody('[data-testid="radio-company"]')).not.toBeNull()
      expect(findInBody('[data-testid="radio-clear"]')).not.toBeNull()
      expect(findInBody('[data-testid="btn-apply-allocation"]')).not.toBeNull()
      expect(findInBody('[data-testid="btn-cancel-allocation"]')).not.toBeNull()
    })

    it("displays overwrite warning banner when transactions have existing allocations and hides it when unallocated", async () => {
      const txWithAlloc = makeStagedTx({
        id: "stx-1",
        allocations: [{ id: "alloc-1", staged_transaction_id: "stx-1", amount: "250.00", is_personal: true, company_id: null }],
      })
      const txWithoutAlloc = makeStagedTx({ id: "stx-2", allocations: [] })

      // Mount with overwrite
      const wrapperWithOverwrites = mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [txWithAlloc, txWithoutAlloc],
        },
      })
      await nextTick()

      const warningBanner = findInBody('[data-testid="banner-overwrite-warning"]')
      expect(warningBanner).not.toBeNull()
      expect(warningBanner?.textContent).toContain("1 of 2 transactions already have allocations or splits which will be overwritten.")

      wrapperWithOverwrites.unmount()
      await nextTick()

      // Mount without overwrite
      mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [txWithoutAlloc],
        },
      })
      await nextTick()

      expect(findInBody('[data-testid="banner-overwrite-warning"]')).toBeNull()
    })

    it("toggles company selector display based on selected entity radio", async () => {
      const tx = makeStagedTx({ id: "stx-1" })
      mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [tx],
        },
      })
      await nextTick()

      // Initially personal is selected; company selector should not be visible
      expect(findInBody('[data-testid="select-company"]')).toBeNull()

      // Select Company radio
      const radioCompany = findInBody('[data-testid="radio-company"]')
      expect(radioCompany).not.toBeNull()
      await new DOMWrapper(radioCompany!).trigger("click")
      await nextTick()

      expect(findInBody('[data-testid="select-company"]')).not.toBeNull()

      // Select Personal radio
      const radioPersonal = findInBody('[data-testid="radio-personal"]')
      await new DOMWrapper(radioPersonal!).trigger("click")
      await nextTick()

      expect(findInBody('[data-testid="select-company"]')).toBeNull()

      // Select Company again, then Clear
      await new DOMWrapper(findInBody('[data-testid="radio-company"]')!).trigger("click")
      await nextTick()
      expect(findInBody('[data-testid="select-company"]')).not.toBeNull()

      const radioClear = findInBody('[data-testid="radio-clear"]')
      await new DOMWrapper(radioClear!).trigger("click")
      await nextTick()
      expect(findInBody('[data-testid="select-company"]')).toBeNull()
    })

    it("controls Apply button disabled state based on transactions and selection", async () => {
      // Empty transactions: disabled
      const wrapperEmpty = mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [],
        },
      })
      await nextTick()

      const btnEmpty = findInBody('[data-testid="btn-apply-allocation"]')
      expect(btnEmpty?.getAttribute("disabled") !== null || btnEmpty?.classList.contains("disabled")).toBe(true)

      wrapperEmpty.unmount()
      await nextTick()

      // Company selected with no companies available: disabled
      const tx = makeStagedTx({ id: "stx-1" })
      const wrapperNoCompany = mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [tx],
        },
      })
      await nextTick()

      // Switch to company radio
      await new DOMWrapper(findInBody('[data-testid="radio-company"]')!).trigger("click")
      await nextTick()

      const btnCompanyNoId = findInBody('[data-testid="btn-apply-allocation"]')
      expect(btnCompanyNoId?.getAttribute("disabled") !== null || btnCompanyNoId?.classList.contains("disabled")).toBe(true)

      wrapperNoCompany.unmount()
      await nextTick()

      // Valid transactions with Personal selected: enabled
      mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [tx],
        },
      })
      await nextTick()

      const btnPersonal = findInBody('[data-testid="btn-apply-allocation"]')
      expect(btnPersonal?.getAttribute("disabled")).toBeNull()
      expect(btnPersonal?.classList.contains("disabled")).toBe(false)
    })

    it("dispatches API call, triggers Notify toast, and emits applied and update:modelValue events on Apply", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({
        updated_count: 2,
        staged_transaction_ids: ["stx-1", "stx-2"],
      })

      const txList = [makeStagedTx({ id: "stx-1" }), makeStagedTx({ id: "stx-2" })]
      const wrapper = mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: txList,
        },
      })
      await nextTick()

      const notifySpy = vi.spyOn((wrapper.vm as any).$q, "notify")

      const applyBtn = findInBody('[data-testid="btn-apply-allocation"]')
      expect(applyBtn).not.toBeNull()
      await new DOMWrapper(applyBtn!).trigger("click")
      await nextTick()

      expect(apiClient.post).toHaveBeenCalledWith("/api/staging/bulk-allocate", {
        staged_transaction_ids: ["stx-1", "stx-2"],
        is_personal: true,
        clear: false,
        company_id: null,
      })

      expect(wrapper.emitted("applied")).toBeTruthy()
      expect(wrapper.emitted("applied")![0]).toEqual([2])
      expect(wrapper.emitted("update:modelValue")).toBeTruthy()
      expect(wrapper.emitted("update:modelValue")![0]).toEqual([false])
      expect(notifySpy).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "positive",
          message: "Successfully allocated 2 transactions",
        }),
      )
    })

    it("closes dialog on Cancel button click without dispatching API call", async () => {
      const tx = makeStagedTx({ id: "stx-1" })
      const wrapper = mountWithQuasar(BulkAllocateDialog, {
        props: {
          modelValue: true,
          selectedTransactions: [tx],
        },
      })
      await nextTick()

      const cancelBtn = findInBody('[data-testid="btn-cancel-allocation"]')
      expect(cancelBtn).not.toBeNull()
      await new DOMWrapper(cancelBtn!).trigger("click")
      await new Promise(resolve => setTimeout(resolve, 50))
      await nextTick()

      expect(apiClient.post).not.toHaveBeenCalled()
      // In Quasar, v-close-popup closes the dialog and emits update:modelValue with false
      expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([false])
    })
  })

  describe("Overwrite notice detection (Pure helper)", () => {
    it("reports count > 0 when at least one selected item has existing allocations", () => {
      const tx1 = makeStagedTx({ id: "stx-1", allocations: [] })
      const tx2 = makeStagedTx({
        id: "stx-2",
        allocations: [{ id: "alloc-1", staged_transaction_id: "stx-2", amount: "250.00", is_personal: true, company_id: null }],
      })
      const count = countOverwrittenTransactions([tx1, tx2])
      expect(count).toBe(1)
    })

    it("reports 0 when all selected items are unallocated", () => {
      const tx1 = makeStagedTx({ id: "stx-1", allocations: [] })
      const tx2 = makeStagedTx({ id: "stx-2", allocations: [] })
      const count = countOverwrittenTransactions([tx1, tx2])
      expect(count).toBe(0)
    })
  })

  describe("Payload generation (Pure helper)", () => {
    const txList = [makeStagedTx({ id: "tx-1", total_amount: "50.00" }), makeStagedTx({ id: "tx-2", total_amount: "150.00" })]

    it("constructs payload with is_personal: true, clear: false, company_id: null when selecting Personal", () => {
      const payload = buildBulkAllocatePayload(txList, "personal")
      expect(payload).toEqual({
        staged_transaction_ids: ["tx-1", "tx-2"],
        is_personal: true,
        clear: false,
        company_id: null,
      })
    })

    it("constructs payload with is_personal: false, clear: false, company_id: '<selected_id>' when selecting a Company", () => {
      const payload = buildBulkAllocatePayload(txList, "company", "comp-xyz")
      expect(payload).toEqual({
        staged_transaction_ids: ["tx-1", "tx-2"],
        is_personal: false,
        clear: false,
        company_id: "comp-xyz",
      })
    })

    it("constructs payload with clear: true, is_personal: false, company_id: null when selecting Unallocated", () => {
      const payload = buildBulkAllocatePayload(txList, "clear")
      expect(payload).toEqual({
        staged_transaction_ids: ["tx-1", "tx-2"],
        clear: true,
        is_personal: false,
        company_id: null,
      })
    })
  })
})

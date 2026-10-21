import fs from "fs"
import path from "path"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
import { apiClient } from "../../api/client"
import { useStagingStore } from "../../stores/staging"
import type { StagedTransaction } from "../../types/staging"
import { buildBulkAllocatePayload, countOverwrittenTransactions } from "../bulkAllocate"

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
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe("Template & UI Elements", () => {
    const dialogPath = path.resolve(__dirname, "../BulkAllocateDialog.vue")
    const dialogTemplate = fs.readFileSync(dialogPath, "utf-8")

    it("includes required title, notice banner, entity selectors, and action buttons", () => {
      expect(dialogTemplate).toContain("Bulk Allocate Transactions")
      expect(dialogTemplate).toContain('data-testid="banner-overwrite-warning"')
      expect(dialogTemplate).toContain('data-testid="radio-personal"')
      expect(dialogTemplate).toContain('data-testid="radio-company"')
      expect(dialogTemplate).toContain('data-testid="select-company"')
      expect(dialogTemplate).toContain('data-testid="radio-clear"')
      expect(dialogTemplate).toContain('data-testid="btn-apply-allocation"')
      expect(dialogTemplate).toContain('data-testid="btn-cancel-allocation"')
      expect(dialogTemplate).toContain("v-close-popup")
    })
  })

  describe("Overwrite notice detection", () => {
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

  describe("Payload generation", () => {
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

  describe("Store integration & dispatch", () => {
    it("dispatches bulkAllocateStaged with expected payload and receives updated count", async () => {
      const stagingStore = useStagingStore()
      vi.mocked(apiClient.post).mockResolvedValueOnce({
        updated_count: 2,
        staged_transaction_ids: ["tx-1", "tx-2"],
      })

      const txList = [makeStagedTx({ id: "tx-1" }), makeStagedTx({ id: "tx-2" })]
      const payload = buildBulkAllocatePayload(txList, "personal")

      const res = await stagingStore.bulkAllocateStaged(payload)

      expect(apiClient.post).toHaveBeenCalledWith("/api/staging/bulk-allocate", {
        staged_transaction_ids: ["tx-1", "tx-2"],
        is_personal: true,
        clear: false,
        company_id: null,
      })
      expect(res.updated_count).toBe(2)
    })

    it("cancel button closes dialog without dispatching store action", () => {
      const dialogPath = path.resolve(__dirname, "../BulkAllocateDialog.vue")
      const dialogTemplate = fs.readFileSync(dialogPath, "utf-8")

      // Verify cancel button uses v-close-popup and does not trigger onApply or any API call
      expect(dialogTemplate).toContain('data-testid="btn-cancel-allocation"')
      const cancelBtnRegex = /<q-btn[^>]*data-testid="btn-cancel-allocation"[^>]*\/>/
      const match = dialogTemplate.match(cancelBtnRegex)
      expect(match).not.toBeNull()
      expect(match![0]).toContain("v-close-popup")
      expect(match![0]).not.toContain("@click")
    })
  })
})

import { beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"
import { DOMWrapper } from "@vue/test-utils"
import { createPinia } from "pinia"
import { apiClient } from "../../api/client"
import { useCompanyStore } from "../../stores/companies"
import { useStagingStore } from "../../stores/staging"
import { useTransactionStore } from "../../stores/transactions"
import type { StagedTransaction } from "../../types/staging"
import StagedTransactionEditDialog from "../StagedTransactionEditDialog.vue"
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

describe("StagedTransactionEditDialog Component Specification", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiClient.get).mockResolvedValue([])
  })

  describe("Persistent Affordances & Receipt Controls (Spatial Stability)", () => {
    it("renders receipt action buttons persistently with disabled state when no receipt exists", async () => {
      const txWithoutReceipt = makeStagedTx({ receipt_file_path: null })

      mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: txWithoutReceipt,
        },
      })
      await nextTick()

      const viewBtn = findInBody('[data-testid="btn-staged-view-receipt"]')
      const scanBtn = findInBody('[data-testid="btn-staged-scan-receipt"]')

      // Must exist in DOM (no v-if conditional removal)
      expect(viewBtn).not.toBeNull()
      expect(scanBtn).not.toBeNull()

      // Must be disabled
      expect(viewBtn?.hasAttribute("disabled") || viewBtn?.classList.contains("disabled")).toBe(true)
      expect(scanBtn?.hasAttribute("disabled") || scanBtn?.classList.contains("disabled")).toBe(true)
    })

    it("enables receipt view and scan buttons when transaction has a receipt file path", async () => {
      const txWithReceipt = makeStagedTx({ receipt_file_path: "receipts/tx-1.pdf" })

      mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: txWithReceipt,
        },
      })
      await nextTick()

      const viewBtn = findInBody('[data-testid="btn-staged-view-receipt"]')
      const scanBtn = findInBody('[data-testid="btn-staged-scan-receipt"]')

      expect(viewBtn).not.toBeNull()
      expect(scanBtn).not.toBeNull()
      expect(viewBtn?.hasAttribute("disabled")).toBe(false)
      expect(scanBtn?.hasAttribute("disabled")).toBe(false)
    })
  })

  describe("Clearable Receipt Attachment", () => {
    it("marks receipt for removal and clears active suggestions when receipt is cleared", async () => {
      const txWithReceipt = makeStagedTx({ receipt_file_path: "receipts/tx-1.pdf" })

      const wrapper = mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: txWithReceipt,
        },
      })
      await nextTick()

      // Set active suggestions
      ;(wrapper.vm as any).aiSuggestions = {
        date: { extractedValue: "2026-10-18", displayValue: "2026-10-18", isMatch: true, isDismissed: false },
        total_amount: null,
        description: null,
      }
      await nextTick()

      // Trigger clear receipt handler exposed by component
      ;(wrapper.vm as any).onClearReceipt()
      await nextTick()

      expect((wrapper.vm as any).form.remove_receipt).toBe(true)
      expect((wrapper.vm as any).form.staged_receipt_file).toBeNull()
      expect((wrapper.vm as any).aiSuggestions.date).toBeNull()
      expect((wrapper.vm as any).hasReceipt).toBe(false)
    })
  })

  describe("Interactive AI Field Suggestions", () => {
    it("renders suggestion banners, accepts suggestion on click, and displays match badge", async () => {
      const tx = makeStagedTx({ date: "2026-10-10", total_amount: "250.00", description: "Old Description" })

      const wrapper = mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: tx,
        },
      })
      await nextTick()

      // Inject suggestions
      ;(wrapper.vm as any).aiSuggestions = {
        date: { extractedValue: "2026-10-15", displayValue: "2026-10-15", isMatch: false, isDismissed: false },
        total_amount: { extractedValue: "250.00", displayValue: "250.00", isMatch: true, isDismissed: false },
        description: {
          extractedValue: "AI Suggested Description",
          displayValue: "AI Suggested Description",
          isMatch: false,
          isDismissed: false,
        },
      }
      await nextTick()

      // Suggestion banner for date should be rendered
      expect(findInBody('[data-testid="suggestion-banner-date"]')).not.toBeNull()
      // Match badge for total amount should be rendered
      expect(findInBody('[data-testid="match-indicator-total_amount"]')).not.toBeNull()

      // Click accept date suggestion
      const acceptDateBtn = findInBody('[data-testid="btn-accept-suggestion-date"]')
      expect(acceptDateBtn).not.toBeNull()
      await new DOMWrapper(acceptDateBtn!).trigger("click")
      await nextTick()

      // Date should update to suggested value
      expect((wrapper.vm as any).form.date).toBe("2026-10-15")
      // Date match indicator should now appear
      expect(findInBody('[data-testid="match-indicator-date"]')).not.toBeNull()

      // Dismiss description suggestion banner
      const dismissDescBtn = findInBody('[data-testid="btn-dismiss-suggestion-description"]')
      expect(dismissDescBtn).not.toBeNull()
      await new DOMWrapper(dismissDescBtn!).trigger("click")
      await nextTick()

      // Description suggestion banner is dismissed from view
      expect(findInBody('[data-testid="suggestion-banner-description"]')).toBeNull()
    })
  })

  describe("Investigation URL Link", () => {
    it("renders external link button with open attributes when transaction has a URL", async () => {
      const txWithUrl = makeStagedTx({ url: "https://amazon.com/orders/123-456" })

      mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: txWithUrl,
        },
      })
      await nextTick()

      const openUrlBtn = findInBody('[data-testid="btn-open-url"]')
      expect(openUrlBtn).not.toBeNull()
      expect(openUrlBtn?.getAttribute("href")).toBe("https://amazon.com/orders/123-456")
      expect(openUrlBtn?.getAttribute("target")).toBe("_blank")
      expect(openUrlBtn?.getAttribute("rel")).toContain("noopener")
    })
  })

  describe("Split Balance Validation & Save Flow", () => {
    it("disables Save button when splits are unbalanced, and enables and saves when balanced", async () => {
      const tx = makeStagedTx({ total_amount: "100.00" })

      const wrapper = mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: tx,
        },
      })
      await nextTick()

      // Make splits unbalanced: split amount 60 vs total 100
      ;(wrapper.vm as any).form.splits = [{ amount: "60.00", is_personal: true, company_id: null }]
      await nextTick()

      const saveBtn = findInBody('[data-testid="btn-save-staged-edit"]')
      expect(saveBtn?.hasAttribute("disabled") || saveBtn?.classList.contains("disabled")).toBe(true)

      // Balance the split: 100.00
      ;(wrapper.vm as any).form.is_personal = true
      ;(wrapper.vm as any).form.splits = [{ amount: "100.00", is_personal: true, company_id: null }]
      await nextTick()

      expect(saveBtn?.hasAttribute("disabled")).toBe(false)
      expect(saveBtn?.classList.contains("disabled")).toBe(false)

      // Mock stagingStore update
      const stagingStore = useStagingStore((wrapper.vm as any).$pinia)
      const updatedTx = makeStagedTx({ id: "stx-1", total_amount: "100.00" })
      vi.spyOn(stagingStore, "updateStagedTransaction").mockResolvedValueOnce(updatedTx)

      // Trigger Save
      await (wrapper.vm as any).onSubmit()
      await nextTick()

      expect(stagingStore.updateStagedTransaction).toHaveBeenCalledWith(
        "stx-1",
        expect.objectContaining({
          total_amount: "100.00",
        }),
        null,
      )
      expect(wrapper.emitted("saved")).toBeTruthy()
      expect(wrapper.emitted("saved")![0]).toEqual([updatedTx])
    })
  })

  describe("Receipt-First Flow & Conditional Auto-Scan", () => {
    it("renders receipt attachment controls before the date input in DOM order", async () => {
      const tx = makeStagedTx()
      mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: tx,
        },
      })
      await nextTick()

      const receiptInput = findInBody('[data-testid="input-staged-receipt"]')
      const dateInput = findInBody('[data-testid="staged-edit-input-date"]')
      expect(receiptInput).not.toBeNull()
      expect(dateInput).not.toBeNull()

      // Node.compareDocumentPosition: 4 means DOCUMENT_POSITION_FOLLOWING (date follows receipt)
      const position = receiptInput!.compareDocumentPosition(dateInput!)
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })

    it("auto-scans receipt when incomplete fields exist, but does not auto-scan when all fields are complete", async () => {
      const txIncomplete = makeStagedTx({ description: "" })
      const wrapper = mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: txIncomplete,
        },
      })
      await nextTick()

      const transactionStore = useTransactionStore((wrapper.vm as any).$pinia)
      const parseSpy = vi.spyOn(transactionStore, "parseReceipt").mockResolvedValue({
        merchant: "Acme Supplies",
        date: "2026-10-18",
        total_amount: "250.00",
        description: "Extracted Payee",
      })
      const testFile = new File(["dummy"], "receipt.png", { type: "image/png" })

      // File selected with incomplete fields -> triggers auto-scan
      await (wrapper.vm as any).onReceiptSelected(testFile)
      expect(parseSpy).toHaveBeenCalledWith(testFile)

      parseSpy.mockClear()

      // Fully complete fields
      ;(wrapper.vm as any).form.date = "2026-10-18"
      ;(wrapper.vm as any).form.total_amount = "250.00"
      ;(wrapper.vm as any).form.description = "Complete Description"

      // File selected with complete fields -> does NOT trigger auto-scan
      await (wrapper.vm as any).onReceiptSelected(testFile)
      expect(parseSpy).not.toHaveBeenCalled()
    })

    it("defaults unallocated company transactions to a single split without clicking Add Split and disables delete", async () => {
      const unallocated = makeStagedTx({ allocations: [] })
      mountWithQuasar(StagedTransactionEditDialog, {
        props: {
          modelValue: true,
          stagedTransaction: unallocated,
        },
      })
      await nextTick()

      // 1 split row is already present in DOM
      const firstSplitRow = findInBody('[data-testid="staged-edit-split-row-0"]')
      expect(firstSplitRow).not.toBeNull()

      // Delete button on the single split is disabled
      const deleteBtn = findInBody('[data-testid="staged-edit-btn-remove-split-0"]')
      expect(deleteBtn).not.toBeNull()
      expect(deleteBtn?.hasAttribute("disabled") || deleteBtn?.classList.contains("disabled")).toBe(true)
    })
  })

  describe("defaultCompanyId Prop & Pre-selection", () => {
    it("pre-selects defaultCompanyId on the form split when prop is provided", async () => {
      const pinia = createPinia()
      const companyStore = useCompanyStore(pinia)
      companyStore.companies = [
        { id: "comp-1", name: "Company 1" },
        { id: "comp-2", name: "Company 2" },
      ]
      const tx = makeStagedTx({ allocations: [] })
      const wrapper = mountWithQuasar(StagedTransactionEditDialog, {
        pinia,
        props: {
          modelValue: true,
          stagedTransaction: tx,
          defaultCompanyId: "comp-2",
        },
      })
      await nextTick()

      expect((wrapper.vm as any).form.splits).toHaveLength(1)
      expect((wrapper.vm as any).form.splits[0].company_id).toBe("comp-2")
      expect((wrapper.vm as any).form.is_personal).toBe(false)
    })

    it("falls back to single company in store when defaultCompanyId is not provided and only 1 company exists", async () => {
      const pinia = createPinia()
      const companyStore = useCompanyStore(pinia)
      companyStore.companies = [{ id: "comp-solo", name: "Solo Company" }]
      const tx = makeStagedTx({ allocations: [] })
      const wrapper = mountWithQuasar(StagedTransactionEditDialog, {
        pinia,
        props: {
          modelValue: true,
          stagedTransaction: tx,
        },
      })
      await nextTick()

      expect((wrapper.vm as any).form.splits).toHaveLength(1)
      expect((wrapper.vm as any).form.splits[0].company_id).toBe("comp-solo")
    })
  })
})
